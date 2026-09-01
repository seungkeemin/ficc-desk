"""ECOS 통계표코드·항목코드 탐색 도구 (일회성 조사용, 저장소에 남긴다).

CLAUDE.md 3 — 코드를 추측해서 커밋하지 않는다. 이 스크립트로 실제 응답을 본 뒤
확정된 값만 ficc/config/sources.py 에 확인 날짜 주석과 함께 넣는다.

  python scripts/discover_ecos.py                    키워드 스윕 (기본)
  python scripts/discover_ecos.py tables 국고채       통계표 검색
  python scripts/discover_ecos.py items 817Y002       세부항목·단위·수록기간
  python scripts/discover_ecos.py search 817Y002 D 010200000
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ficc.config.settings import as_compact, today_kst  # noqa: E402
from ficc.sources import ecos  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# SPEC 4-1 이 ECOS 로 지목한 필드들의 검색어
SWEEP = {
    "ktb_3y / ktb_10y": ["국고채", "시장금리"],
    "cd_91d": ["CD", "양도성"],
    "corp_aa3_yield_3y": ["회사채", "무보증"],
    "usdkrw": ["환율"],
    # 2026-08-11 확장에서 찾은 것. 기준금리만 다른 통계표(722Y001)에 있고
    # 나머지 금리는 전부 817Y002 안에 있다 — `items 817Y002` 로 27 항목을 본다.
    "bok_base_rate": ["기준금리"],
}


def all_tables() -> list[dict]:
    """통계표목록 전체. 한 번에 1000건씩 긁는다."""
    rows: list[dict] = []
    start = 1
    while True:
        chunk = ecos.call("StatisticTableList", start=start, end=start + 999)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        start += 1000
    return rows


def show_tables(keywords: list[str]) -> None:
    rows = all_tables()
    print(f"통계표 전체 {len(rows)}건")
    if rows:
        print(f"응답 필드: {sorted(rows[0])}\n")
    for keyword in keywords:
        hits = [r for r in rows if keyword in str(r.get("STAT_NAME", ""))]
        print(f"--- '{keyword}' {len(hits)}건 ---")
        for row in hits:
            # CYCLE 은 상위(폴더) 통계표에서 None 으로 온다 — 그대로 두고 표시만 보정한다
            print(f"  {str(row.get('STAT_CODE') or ''):<12} "
                  f"{str(row.get('CYCLE') or '-'):<4} "
                  f"조회가능={row.get('SRCH_YN') or '-'}  {row.get('STAT_NAME') or ''}")
        print()


def show_items(stat_code: str, keyword: str = "") -> None:
    rows = ecos.call("StatisticItemList", stat_code, start=1, end=1000)
    print(f"{stat_code} 세부항목 {len(rows)}건")
    if not rows:
        return
    print(f"응답 필드: {sorted(rows[0])}\n")
    for row in rows:
        name = str(row.get("ITEM_NAME") or "")
        if keyword and keyword not in name:
            continue
        print(f"  {str(row.get('ITEM_CODE') or ''):<14} "
              f"{str(row.get('CYCLE') or '-'):<3} "
              f"{str(row.get('UNIT_NAME') or '-'):<10} "
              f"{row.get('START_TIME') or ''}~{row.get('END_TIME') or ''}  {name}")


def show_search(stat_code: str, cycle: str, *item_codes: str) -> None:
    """최근 30일 창으로 시험 호출 — 값과 최신 TIME(= 게시 지연)을 눈으로 확인한다."""
    today = today_kst()
    start = as_compact(today - timedelta(days=30))
    segments = [stat_code, cycle, start, as_compact(today), *item_codes]
    rows = ecos.call("StatisticSearch", *segments, start=1, end=200)
    print(f"{stat_code}/{cycle}/{'/'.join(item_codes)} → {len(rows)}건")
    if not rows:
        print("  (해당 구간 데이터 없음)")
        return
    print(f"응답 필드: {sorted(rows[0])}\n")
    for row in rows[-12:]:
        print(f"  {row.get('TIME',''):<10} {str(row.get('DATA_VALUE','')):>12}  "
              f"{row.get('UNIT_NAME','')}  {row.get('ITEM_NAME1','')}")
    print(f"\n  최신 게시일: {rows[-1].get('TIME','')}   (오늘 KST {today})")


def main(argv: list[str]) -> int:
    if not ecos.api_key():
        print("ECOS_API_KEY 없음. .env.example 을 .env 로 복사해 키를 넣어라.")
        return 2

    try:
        if not argv:
            for label, keywords in SWEEP.items():
                print(f"\n{'='*70}\n{label}\n{'='*70}")
                show_tables(keywords)
        elif argv[0] == "tables":
            show_tables(argv[1:] or ["국고채"])
        elif argv[0] == "items":
            show_items(argv[1], argv[2] if len(argv) > 2 else "")
        elif argv[0] == "search":
            show_search(argv[1], argv[2], *argv[3:])
        else:
            print(__doc__)
            return 2
    except ecos.EcosError as exc:
        print(f"ECOS 오류: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
