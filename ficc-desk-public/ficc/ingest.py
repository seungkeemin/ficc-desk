"""수집 엔트리.

    .venv\\Scripts\\python -m ficc.ingest
    .venv\\Scripts\\python -m ficc.ingest --date 2026-08-07

한 소스가 죽어도 전체가 죽지 않는다. 성공한 필드만 저장하고, 실패는 ingest_result 에
남겨 화면이 "왜 이 필드가 비었는가"를 설명할 수 있게 한다 (CLAUDE.md 6).

수집 대상은 '오늘'이 아니라 '가장 최근 게시일'이고, obs_date 에는 그 값의 실제
관측일이 들어간다 (SPEC 4-2). 오늘 자로 끌어다 쓰면 시계열이 하루씩 밀린다.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import unicodedata
from datetime import date, datetime

from . import db, derived
from .config.settings import as_ymd, today_kst
from .sources import ecos, fred, krx
from .sources.base import Failed, Fetched, Missing

PROVIDERS = {
    "ecos": ecos.fetch,
    "fred": fred.fetch,
    "krx": krx.fetch,
}


# ---------------------------------------------------------------------------
# 표 렌더링 (한글 폭 보정. 외부 라이브러리 없이)
# ---------------------------------------------------------------------------

def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int, align: str = "<") -> str:
    gap = max(0, width - _width(text))
    if align == ">":
        return " " * gap + text
    return text + " " * gap


def render_table(headers: list[str], rows: list[list[str]],
                 aligns: str = "") -> str:
    aligns = aligns or "<" * len(headers)
    widths = [
        max(_width(headers[i]), *(_width(row[i]) for row in rows)) if rows
        else _width(headers[i])
        for i in range(len(headers))
    ]
    line = "  ".join(_pad(headers[i], widths[i]) for i in range(len(headers)))
    rule = "  ".join("-" * widths[i] for i in range(len(headers)))
    body = [
        "  ".join(_pad(row[i], widths[i], aligns[i]) for i in range(len(headers)))
        for row in rows
    ]
    return "\n".join([line, rule, *body])


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

def collect(conn: sqlite3.Connection, target: date, run_id: int) -> dict[str, str]:
    """자동 수집 대상 필드를 순회한다. 자동 필드의 상태 문자열만 돌려준다.

    수동 전용 필드는 시도조차 하지 않지만 'skipped' 로 기록해 둔다 —
    화면이 "비어 있음 + 수동 전용"을 구분해 보여줘야 하기 때문이다.
    """
    statuses: dict[str, str] = {}

    for field in db.field_defs(conn):
        if field["is_derived"] or field["auto_provider"]:
            continue
        db.record_result(conn, run_id, field["field_key"], "skipped", "수동 전용")

    for field in db.auto_fields(conn):
        key = field["field_key"]
        provider = field["auto_provider"]
        fetcher = PROVIDERS.get(provider)

        if fetcher is None:
            db.record_result(conn, run_id, key, "error", f"미등록 provider: {provider}")
            statuses[key] = "error"
            continue

        try:
            result = fetcher(key, target)
        except Exception as exc:  # noqa: BLE001 - 소스가 못 잡은 예외까지 여기서 막는다
            result = Failed(key, f"{type(exc).__name__}: {exc}")

        match result:
            case Fetched():
                day = as_ymd(result.obs_date)
                existing = conn.execute(
                    "SELECT value, source FROM market_observation"
                    " WHERE obs_date = ? AND field_key = ?", (day, key)
                ).fetchone()

                if existing and existing["source"] == "manual":
                    # 사용자가 손으로 고친 값을 자동 수집이 되돌리지 않는다.
                    # 하루 두 번 도는 스케줄러(SPEC 5)가 오전의 정정을 지우면
                    # '수동 덮어쓰기'가 무의미해진다.
                    db.record_result(conn, run_id, key, "skipped",
                                     f"수동 입력값 보존 ({existing['value']})")
                    statuses[key] = "skipped"
                elif existing and existing["value"] == result.value:
                    # 같은 값을 다시 쓰면 덮어쓰기 로그만 불어난다. 로그는
                    # '무엇이 언제 바뀌었나'를 읽는 곳이지 실행 횟수를 세는 곳이 아니다.
                    db.record_result(conn, run_id, key, "ok", f"{day} 변화 없음")
                    statuses[key] = "ok"
                else:
                    db.upsert_observation(
                        conn, result.obs_date, key, result.value,
                        source="auto", provider=result.provider, note=result.note,
                    )
                    db.record_result(conn, run_id, key, "ok", day)
                    statuses[key] = "ok"
            case Missing():
                db.record_result(conn, run_id, key, "miss", result.reason)
                statuses[key] = "miss"
            case Failed():
                db.record_result(conn, run_id, key, "error", result.message)
                statuses[key] = "error"

    return statuses


def report(conn: sqlite3.Connection, target: date, run_id: int,
           statuses: dict[str, str]) -> None:
    """어떤 필드가 채워졌고 어떤 필드가 비었는지 표로 출력한다."""
    target_ymd = as_ymd(target)
    stored = db.latest_on_or_before(conn, target_ymd)
    messages = {
        row["field_key"]: (row["message"] or "")
        for row in conn.execute(
            "SELECT field_key, message FROM ingest_result WHERE run_id = ?", (run_id,)
        )
    }

    rows: list[list[str]] = []
    manual_todo: list[str] = []
    values: dict[str, float | None] = {}

    for field in db.field_defs(conn):
        key = field["field_key"]
        if field["is_derived"]:
            continue

        obs = stored.get(key)
        values[key] = obs["value"] if obs else None

        if field["auto_provider"]:
            status = statuses.get(key, "skipped")
            note = "" if status == "ok" else messages.get(key, "")
        else:
            status = "manual"
            note = "수동 전용"

        if obs is None:
            # 값이 아예 없다 — 자동이든 수동이든 오늘 손으로 넣어야 한다.
            manual_todo.append(key)
            rows.append([
                field["category"], key, field["label_short"], status,
                "-", "-", "-", note,
            ])
            continue

        if not field["auto_provider"] and obs["obs_date"] != target_ymd:
            # 수동 필드는 매일 새로 넣는 값이다. 어제 값이 남아 있는 건 미입력이다.
            manual_todo.append(key)

        rows.append([
            field["category"], key, field["label_short"], status,
            f"{obs['value']:,.{field['decimals']}f}",
            obs["obs_date"],
            "M" if obs["source"] == "manual" else (obs["provider"] or "auto"),
            note,
        ])

    print(f"\n수집 대상일 {target_ymd} (KST)   run #{run_id}\n")
    print(render_table(
        ["CATEGORY", "FIELD", "LABEL", "STATUS", "VALUE", "AS OF", "SRC", "NOTE"],
        rows,
        aligns="<<<<><<<",
    ))

    ok = sum(1 for s in statuses.values() if s == "ok")
    miss = sum(1 for s in statuses.values() if s == "miss")
    err = sum(1 for s in statuses.values() if s == "error")
    kept = sum(1 for s in statuses.values() if s == "skipped")
    manual_fields = [f for f in db.field_defs(conn)
                     if not f["is_derived"] and not f["auto_provider"]]
    line = (f"\n자동 성공 {ok} · 미게시 {miss} · 실패 {err} · "
            f"수동 전용 {len(manual_fields)}")
    if kept:
        line += f" · 수동값 보존 {kept}"
    print(line)

    # 파생값은 저장하지 않는다. 참고로만 계산해 보여준다 (CLAUDE.md 2).
    drows: list[list[str]] = []
    for key, spec in derived.REGISTRY.items():
        result = derived.compute(key, values)
        lacking = derived.missing_inputs(key, values)
        drows.append([
            key, spec.label_short,
            f"{result:,.{spec.decimals}f}" if result is not None else "-",
            spec.unit,
            "+".join(spec.inputs),
            "" if result is not None else f"미수집: {', '.join(lacking)}",
        ])
    print("\n파생값 (저장하지 않음 · 조회 시 계산)\n")
    print(render_table(["KEY", "LABEL", "VALUE", "UNIT", "FROM", "NOTE"],
                       drows, aligns="<<><<<"))

    todo = [k for k in dict.fromkeys(manual_todo)]
    if todo:
        print(f"\n오늘 손으로 채울 필드 {len(todo)}개: {' '.join(todo)}")
        print("  PUT /api/observation  또는  Phase 3 의 인라인 입력")


def run(target: date) -> int:
    conn = db.connect()
    try:
        applied = db.migrate(conn)
        if applied:
            print(f"마이그레이션 적용: {applied}")

        run_id = db.start_run(conn, as_ymd(target))
        statuses = collect(conn, target, run_id)

        # 'skipped'(수동값 보존)는 실패가 아니다. 성공/실패만 세어 등급을 정한다.
        ok = sum(1 for s in statuses.values() if s == "ok")
        bad = sum(1 for s in statuses.values() if s in {"miss", "error"})
        if bad and not ok:
            status = "failed"
        elif bad:
            status = "partial"
        else:
            status = "ok"
        db.finish_run(conn, run_id, status)

        report(conn, target, run_id, statuses)
        print(f"\nrun #{run_id} 종료: {status}")
        return 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="python -m ficc.ingest")
    parser.add_argument("--date", help="수집 기준일 YYYY-MM-DD (기본: 오늘 KST)")
    args = parser.parse_args(argv)

    target = (
        datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else today_kst()
    )
    return run(target)


if __name__ == "__main__":
    raise SystemExit(main())
