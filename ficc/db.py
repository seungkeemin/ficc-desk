"""커넥션 · 마이그레이션 러너 · 관측값 쓰기 경로.

ORM 을 쓰지 않는다. SQL 은 손으로 쓰고 sqlite3.Row 로 받는다 (CLAUDE.md 코드 스타일).

market_observation 에 쓰는 경로는 upsert_observation() 하나뿐이다.
자동 수집이든 수동 입력이든 전부 이 함수를 통과하고, 통과할 때마다
market_observation_log 에 append-only 로 이력이 남는다 (CLAUDE.md 4).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from .config.settings import (
    MIGRATIONS_DIR, as_ymd, canonical_date, db_path, now_kst,
)

MIGRATION_PATTERN = re.compile(r"^(\d+)_.+\.sql$")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """WAL + synchronous=FULL. 시계열 유실이 이 프로젝트의 유일한 치명적 실패다 (SPEC 4-6a)."""
    target = path or db_path()
    conn = sqlite3.connect(target, isolation_level=None)  # 트랜잭션은 명시적으로 연다
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# ---------------------------------------------------------------------------
# 마이그레이션
# ---------------------------------------------------------------------------

def migrate(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> list[int]:
    """미적용 마이그레이션을 번호순으로 적용하고 적용된 버전 목록을 돌려준다.

    schema_version 은 러너 자신이 부트스트랩하므로 001 에 넣지 않는다.
    각 파일은 BEGIN/COMMIT 으로 감싸 적용되므로 중간에 실패하면 통째로 롤백된다.
    """
    directory = migrations_dir or MIGRATIONS_DIR
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    done = {row["version"] for row in conn.execute("SELECT version FROM schema_version")}

    applied: list[int] = []
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in done:
            continue
        body = path.read_text(encoding="utf-8")
        script = (
            "BEGIN;\n"
            f"{body}\n"
            "INSERT INTO schema_version(version, applied_at) VALUES "
            f"({version}, '{now_kst()}');\n"
            "COMMIT;"
        )
        conn.executescript(script)
        applied.append(version)
    return applied


# ---------------------------------------------------------------------------
# 필드 사전
# ---------------------------------------------------------------------------

def field_defs(conn: sqlite3.Connection, *, active_only: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM field_def"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY display_order"
    return list(conn.execute(sql))


def field_def(conn: sqlite3.Connection, field_key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM field_def WHERE field_key = ?", (field_key,)
    ).fetchone()


def auto_fields(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """자동 수집 대상. 파생값은 저장 대상이 아니므로 제외한다."""
    return list(conn.execute(
        "SELECT * FROM field_def"
        " WHERE active = 1 AND is_derived = 0 AND auto_provider IS NOT NULL"
        " ORDER BY display_order"
    ))


# ---------------------------------------------------------------------------
# 관측값
# ---------------------------------------------------------------------------

def upsert_observation(
    conn: sqlite3.Connection,
    obs_date: str | date,
    field_key: str,
    value: float,
    source: str,
    provider: str | None,
    note: str | None = None,
) -> str:
    """관측값을 쓰고 이력을 남긴다. 'insert' 또는 'update' 를 돌려준다.

    market_observation 에 쓰는 유일한 경로다. 값이 없으면 이 함수를 부르지 않는다 —
    NULL 행을 만들거나 0 으로 채우지 않는다 (CLAUDE.md 1).
    """
    if source not in {"auto", "manual"}:
        raise ValueError(f"source 는 auto|manual: {source!r}")

    day = canonical_date(obs_date) if isinstance(obs_date, str) else as_ymd(obs_date)
    stamp = now_kst()

    with transaction(conn):
        prev = conn.execute(
            "SELECT value, source FROM market_observation"
            " WHERE obs_date = ? AND field_key = ?", (day, field_key)
        ).fetchone()
        action = "update" if prev else "insert"

        conn.execute(
            "INSERT INTO market_observation"
            " (obs_date, field_key, value, source, provider, captured_at, note)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(obs_date, field_key) DO UPDATE SET"
            "   value=excluded.value, source=excluded.source,"
            "   provider=excluded.provider, captured_at=excluded.captured_at,"
            "   note=excluded.note",
            (day, field_key, value, source, provider, stamp, note),
        )
        conn.execute(
            "INSERT INTO market_observation_log"
            " (obs_date, field_key, action, prev_value, prev_source,"
            "  new_value, new_source, provider, written_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (day, field_key, action,
             prev["value"] if prev else None,
             prev["source"] if prev else None,
             value, source, provider, stamp),
        )
    return action


def observations_on(conn: sqlite3.Connection, obs_date: str) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM market_observation WHERE obs_date = ?", (obs_date,)
    )
    return {row["field_key"]: row for row in rows}


def latest_on_or_before(conn: sqlite3.Connection, obs_date: str) -> dict[str, sqlite3.Row]:
    """각 필드의 obs_date 이하 최신 행.

    ECOS 가 T+1 로 게시하면 오늘 자 행이 없을 수 있다. 화면은 '가장 최근 게시분'을
    보여주고 그 날짜를 함께 표시한다 (SPEC 4-2). 없는 값을 앞 날짜로 채우는 게
    아니라, 언제 관측된 값인지 밝히는 것이다.
    """
    rows = conn.execute(
        "SELECT o.* FROM market_observation o"
        " JOIN (SELECT field_key, MAX(obs_date) AS d FROM market_observation"
        "       WHERE obs_date <= ? GROUP BY field_key) m"
        "   ON o.field_key = m.field_key AND o.obs_date = m.d",
        (obs_date,),
    )
    return {row["field_key"]: row for row in rows}


def previous_observation(
    conn: sqlite3.Connection, field_key: str, before: str
) -> sqlite3.Row | None:
    """전일 대비 계산용. before 미만의 가장 최근 1행."""
    return conn.execute(
        "SELECT * FROM market_observation"
        " WHERE field_key = ? AND obs_date < ?"
        " ORDER BY obs_date DESC LIMIT 1",
        (field_key, before),
    ).fetchone()


def observation_log(
    conn: sqlite3.Connection, field_key: str, obs_date: str
) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT * FROM market_observation_log"
        " WHERE field_key = ? AND obs_date = ? ORDER BY id",
        (field_key, obs_date),
    ))


# ---------------------------------------------------------------------------
# 수집 실행 기록
# ---------------------------------------------------------------------------

def start_run(conn: sqlite3.Connection, target_date: str) -> int:
    cursor = conn.execute(
        "INSERT INTO ingest_run (started_at, target_date, status)"
        " VALUES (?,?,'running')",
        (now_kst(), target_date),
    )
    return int(cursor.lastrowid)


def record_result(
    conn: sqlite3.Connection, run_id: int, field_key: str,
    status: str, message: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO ingest_result (run_id, field_key, status, message)"
        " VALUES (?,?,?,?)"
        " ON CONFLICT(run_id, field_key) DO UPDATE SET"
        "   status=excluded.status, message=excluded.message",
        (run_id, field_key, status, message),
    )


def finish_run(conn: sqlite3.Connection, run_id: int, status: str) -> None:
    conn.execute(
        "UPDATE ingest_run SET finished_at = ?, status = ? WHERE id = ?",
        (now_kst(), status, run_id),
    )


def last_run(conn: sqlite3.Connection) -> dict[str, Any] | None:
    run = conn.execute(
        "SELECT * FROM ingest_run ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if run is None:
        return None
    results = conn.execute(
        "SELECT * FROM ingest_result WHERE run_id = ? ORDER BY field_key",
        (run["id"],),
    )
    return {
        "run": dict(run),
        "results": [dict(row) for row in results],
    }


def setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM app_setting WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES (?,?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# ---------------------------------------------------------------------------
# 저널
# ---------------------------------------------------------------------------

# 컬럼명을 SQL 에 문자열로 끼워 넣는 유일한 곳이다. 화이트리스트 밖은 통과할 수 없다.
JOURNAL_FIELDS = frozenset({
    "review_ny", "review_ldn", "pre_open_expect", "why_moved", "brief_en",
})


def journal_on(conn: sqlite3.Connection, obs_date: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM journal WHERE obs_date = ?", (canonical_date(obs_date),)
    ).fetchone()


def upsert_journal_field(
    conn: sqlite3.Connection, obs_date: str, column: str, text: str | None
) -> None:
    """저널을 한 칸씩 저장한다.

    통째로 저장하면 두 칸의 디바운스가 겹칠 때 늦게 도착한 요청이 다른 칸을
    옛 값으로 덮어쓴다. 칸마다 따로 쓰면 그 경합이 원천적으로 없다.

    빈 문자열은 None 으로 정규화해서 넣는다 — '안 썼다'와 '비워 뒀다'를 섞지 않는다
    (viewmodel.JournalVM).
    """
    if column not in JOURNAL_FIELDS:
        raise ValueError(f"모르는 저널 칸: {column!r}")

    day = canonical_date(obs_date)
    conn.execute(
        f"INSERT INTO journal (obs_date, {column}, updated_at) VALUES (?,?,?)"
        f" ON CONFLICT(obs_date) DO UPDATE SET"
        f"   {column} = excluded.{column}, updated_at = excluded.updated_at",
        (day, text, now_kst()),
    )


# ---------------------------------------------------------------------------
# 루틴
# ---------------------------------------------------------------------------

def routine_defs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT * FROM routine_def WHERE active = 1 ORDER BY display_order"
    ))


def routines_for(conn: sqlite3.Connection, task_date: str) -> list[sqlite3.Row]:
    """그 날짜의 루틴 정의 + 완료 여부. 기록이 없으면 done = 0 이다."""
    return list(conn.execute(
        "SELECT rd.key, rd.label, rd.cadence, rd.counts_streak, rd.display_order,"
        "       COALESCE(rl.done, 0) AS done"
        "  FROM routine_def rd"
        "  LEFT JOIN routine_log rl"
        "    ON rl.routine_key = rd.key AND rl.task_date = ?"
        " WHERE rd.active = 1"
        " ORDER BY rd.display_order",
        (canonical_date(task_date),),
    ))


def set_routine_done(
    conn: sqlite3.Connection, task_date: str, routine_key: str, done: bool
) -> bool:
    """멱등. 같은 값으로 두 번 눌러도 행은 하나다."""
    day = canonical_date(task_date)
    conn.execute(
        "INSERT INTO routine_log (task_date, routine_key, done, done_at)"
        " VALUES (?,?,?,?)"
        " ON CONFLICT(task_date, routine_key) DO UPDATE SET"
        "   done = excluded.done, done_at = excluded.done_at",
        (day, routine_key, 1 if done else 0, now_kst() if done else None),
    )
    return done


def complete_streak_days(conn: sqlite3.Connection, upto: str) -> set[str]:
    """counts_streak = 1 인 활성 루틴이 '전부' 완료된 날짜 집합 (002_seed.sql:63).

    분모가 지금 시점의 정의라, 나중에 일간 루틴을 하나 늘리면 과거의 완료일이
    소급해서 미완료가 된다. 그날의 정의를 따로 저장하면 막을 수 있지만 스키마가
    늘어난다. 일간 5종을 바꿀 일이 사실상 없어 이 한계를 안고 간다.
    """
    rows = conn.execute(
        "SELECT rl.task_date AS d"
        "  FROM routine_log rl"
        "  JOIN routine_def rd ON rd.key = rl.routine_key"
        " WHERE rd.counts_streak = 1 AND rd.active = 1"
        "   AND rl.done = 1 AND rl.task_date <= ?"
        " GROUP BY rl.task_date"
        " HAVING COUNT(*) = (SELECT COUNT(*) FROM routine_def"
        "                     WHERE counts_streak = 1 AND active = 1)",
        (canonical_date(upto),),
    )
    return {row["d"] for row in rows}


# ---------------------------------------------------------------------------
# 아이디어 · 무효화 조건
# ---------------------------------------------------------------------------

def open_positions(conn: sqlite3.Connection, on_date: str) -> list[sqlite3.Row]:
    """활성 아이디어 × 무효화 조건 × 그날 점검 상태를 한 번에 읽는다.

    아이디어당 조건 수만큼 행이 나오므로 호출부가 idea id 로 묶는다.
    조건마다 따로 질의하면 N+1 이 되고, 조건이 없는 아이디어(있을 수 없지만)도
    LEFT JOIN 이라 사라지지 않는다.
    """
    return list(conn.execute(
        "SELECT i.id, i.code, i.position, i.flow_agent, i.strategy, i.dv01_krw,"
        "       i.holding_days, i.pricing_key, i.level_unit,"
        "       i.entry_level, i.target_level, i.stop_level, i.opened_on,"
        "       v.id AS inv_id, v.text AS inv_text, c.state AS inv_state"
        "  FROM idea i"
        "  LEFT JOIN invalidation v ON v.idea_id = i.id"
        "  LEFT JOIN invalidation_check c"
        "    ON c.invalidation_id = v.id AND c.check_date = ?"
        " WHERE i.status = 'open'"
        " ORDER BY i.opened_on, i.id, v.id",
        (canonical_date(on_date),),
    ))


CHECK_STATES = frozenset({"valid", "shaky", "broken"})


def upsert_invalidation_check(
    conn: sqlite3.Connection,
    invalidation_id: int,
    check_date: str,
    state: str,
    note: str | None = None,
) -> None:
    """그날의 점검 상태. 같은 날 다시 누르면 상태만 바뀐다.

    created_at 은 충돌 시 갱신하지 않는다 — 이름이 created_at 이고, 하루 단위 행이라
    '그날 처음 점검한 시각'이 더 정직하다.
    """
    if state not in CHECK_STATES:
        raise ValueError(f"state 는 valid|shaky|broken: {state!r}")

    conn.execute(
        "INSERT INTO invalidation_check"
        " (invalidation_id, check_date, state, note, created_at)"
        " VALUES (?,?,?,?,?)"
        " ON CONFLICT(invalidation_id, check_date) DO UPDATE SET"
        "   state = excluded.state,"
        "   note  = COALESCE(excluded.note, invalidation_check.note)",
        (invalidation_id, canonical_date(check_date), state, note, now_kst()),
    )


def latest_mark(
    conn: sqlite3.Connection, idea_id: int, on_date: str
) -> sqlite3.Row | None:
    """수동 마킹의 on_date 이하 최신 1건. 없으면 None — 추정해 채우지 않는다 (SPEC 4-3)."""
    return conn.execute(
        "SELECT * FROM idea_mark WHERE idea_id = ? AND mark_date <= ?"
        " ORDER BY mark_date DESC LIMIT 1",
        (idea_id, canonical_date(on_date)),
    ).fetchone()


def upsert_idea_mark(
    conn: sqlite3.Connection, idea_id: int, mark_date: str, level: float
) -> None:
    conn.execute(
        "INSERT INTO idea_mark (idea_id, mark_date, level, created_at)"
        " VALUES (?,?,?,?)"
        " ON CONFLICT(idea_id, mark_date) DO UPDATE SET"
        "   level = excluded.level, created_at = excluded.created_at",
        (idea_id, canonical_date(mark_date), level, now_kst()),
    )


def next_idea_code(conn: sqlite3.Connection) -> str:
    """IDEA-001, IDEA-002 … 형식이 다른 코드는 GLOB 이 걸러낸다."""
    row = conn.execute(
        "SELECT COALESCE(MAX(CAST(substr(code, 6) AS INTEGER)), 0) + 1 AS n"
        "  FROM idea WHERE code GLOB 'IDEA-[0-9][0-9][0-9]'"
    ).fetchone()
    return f"IDEA-{int(row['n']):03d}"


IDEA_STRATEGIES = frozenset({"momentum", "mean_reversion"})


def create_idea(
    conn: sqlite3.Connection,
    *,
    fields: dict[str, Any],
    theses: Sequence[str],
    invalidations: Sequence[str],
) -> tuple[int, str]:
    """아이디어 1건 + 논리 + 무효화 조건을 한 트랜잭션에 쓴다.

    무효화 조건이 하나도 없으면 **아무것도 쓰지 않고** 실패한다 (CLAUDE.md 7).
    검사가 트랜잭션 바깥이라 idea 행이 만들어졌다 롤백되는 일조차 없다.
    """
    conditions = [text.strip() for text in invalidations if text and text.strip()]
    if not conditions:
        raise ValueError("무효화 조건 없는 아이디어는 저장할 수 없다. 최소 1건을 적어라.")

    lines = [text.strip() for text in theses if text and text.strip()]
    if len(lines) > 3:
        raise ValueError("논리는 3개까지다.")

    if fields["strategy"] not in IDEA_STRATEGIES:
        raise ValueError(f"strategy 는 momentum|mean_reversion: {fields['strategy']!r}")

    opened_on = canonical_date(fields["opened_on"])
    stamp = now_kst()

    with transaction(conn):
        code = next_idea_code(conn)     # 같은 트랜잭션 안에서 채번, UNIQUE 가 최종 보증
        cursor = conn.execute(
            "INSERT INTO idea"
            " (code, position, flow_agent, strategy, dv01_krw, holding_days,"
            "  pricing_key, level_unit, entry_level, target_level, stop_level,"
            "  opened_on, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?)",
            (code, fields["position"], fields.get("flow_agent"), fields["strategy"],
             fields["dv01_krw"], fields["holding_days"], fields.get("pricing_key"),
             fields["level_unit"], fields["entry_level"], fields["target_level"],
             fields["stop_level"], opened_on, stamp, stamp),
        )
        idea_id = int(cursor.lastrowid)

        for seq, text in enumerate(lines, start=1):
            conn.execute(
                "INSERT INTO idea_thesis (idea_id, seq, text) VALUES (?,?,?)",
                (idea_id, seq, text),
            )
        for text in conditions:
            conn.execute(
                "INSERT INTO invalidation (idea_id, text, created_at) VALUES (?,?,?)",
                (idea_id, text, stamp),
            )
    return idea_id, code


# ---------------------------------------------------------------------------
# 이벤트
# ---------------------------------------------------------------------------

EVENT_PATCH_FIELDS = frozenset({
    "consensus", "my_expectation", "actual", "my_call", "note", "event_time",
})
EVENT_CALLS = frozenset({"hit", "miss", "partial"})


def events_between(
    conn: sqlite3.Connection, start: str, end: str
) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT * FROM event WHERE event_date BETWEEN ? AND ?"
        " ORDER BY event_date, COALESCE(event_time, '99:99'), id",
        (canonical_date(start), canonical_date(end)),
    ))


def create_event(
    conn: sqlite3.Connection,
    *,
    event_date: str,
    region: str,
    name: str,
    event_time: str | None = None,
    consensus: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO event (event_date, event_time, region, name, consensus, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (canonical_date(event_date), event_time, region, name, consensus, now_kst()),
    )
    return int(cursor.lastrowid)


def patch_event(
    conn: sqlite3.Connection, event_id: int, column: str, value: str | None
) -> bool:
    """이벤트 한 칸 수정. 행이 없으면 False."""
    if column not in EVENT_PATCH_FIELDS:
        raise ValueError(f"수정할 수 없는 칸: {column!r}")
    if column == "my_call" and value is not None and value not in EVENT_CALLS:
        raise ValueError(f"my_call 은 hit|miss|partial: {value!r}")

    cursor = conn.execute(
        f"UPDATE event SET {column} = ? WHERE id = ?", (value, event_id)
    )
    return cursor.rowcount > 0
