"""마이그레이션 러너.

빈 DB 에서 처음부터 실행해 깨지는 곳이 없어야 한다 (SPEC Phase 5 완료 조건의 선행).
"""

from __future__ import annotations

from pathlib import Path

from ficc import db
from ficc.config.settings import MIGRATIONS_DIR


def test_applies_all_and_is_idempotent(tmp_path: Path) -> None:
    expected = sorted(
        int(path.name.split("_", 1)[0])
        for path in MIGRATIONS_DIR.glob("*.sql")
    )

    conn = db.connect(tmp_path / "a.db")
    first = db.migrate(conn)
    assert first == expected

    second = db.migrate(conn)
    assert second == []  # 두 번째 실행은 아무것도 하지 않는다

    versions = [row["version"] for row in conn.execute(
        "SELECT version FROM schema_version ORDER BY version")]
    assert versions == expected
    conn.close()


def test_seed_counts(conn) -> None:
    fields = db.field_defs(conn)
    assert len(fields) == 51                                   # 저장 41 + 파생 10
    assert sum(1 for f in fields if f["is_derived"]) == 10
    # ecos 16 + fred 13 + krx 5 (krx 는 003 에서 전환, 005 에서 3 종 추가)
    assert sum(1 for f in fields if f["auto_provider"]) == 34
    # 005 가 늘린 24 개는 전부 자동이다. 손으로 채우는 필드는 늘지 않았다 (SPEC 4-1).
    assert sum(1 for f in fields
               if not f["is_derived"] and not f["auto_provider"]) == 7

    routines = list(conn.execute("SELECT * FROM routine_def"))
    assert len(routines) == 16                                 # 행은 지우지 않는다
    assert sum(1 for r in routines if r["counts_streak"]) == 5  # 일간 5종만 연속 기록
    # 004 가 격주·월간·분기 7 종을 껐다. 사용자가 도구 밖에서 직접 계획한다.
    assert sum(1 for r in routines if r["active"]) == 9
    assert all(
        r["active"] == 0
        for r in routines
        if r["cadence"] in ("biweekly", "monthly", "quarterly")
    )

    assert db.setting(conn, "color_convention") == "kr"


def test_pragmas(conn) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_derived_fields_are_not_auto_collected(conn) -> None:
    """파생값은 수집 대상이 아니다. 저장되면 안 되므로 auto_fields 에 없어야 한다."""
    keys = {row["field_key"] for row in db.auto_fields(conn)}
    derived_keys = {row["field_key"] for row in db.field_defs(conn) if row["is_derived"]}
    assert keys & derived_keys == set()
