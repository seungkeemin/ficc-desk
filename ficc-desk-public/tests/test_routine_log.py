"""요일별 체크리스트의 저장.

체크는 날짜별로 저장되고 멱등해야 한다 — 같은 항목을 두 번 눌러 행이 둘로 늘면
연속 기록의 HAVING COUNT(*) 가 조용히 어긋난다.
"""

from __future__ import annotations

import sqlite3

import pytest

from ficc import db

DAY = "2026-08-11"


def test_toggle_is_idempotent(conn) -> None:
    db.set_routine_done(conn, DAY, "daily_snapshot", True)
    db.set_routine_done(conn, DAY, "daily_snapshot", True)

    rows = list(conn.execute(
        "SELECT * FROM routine_log WHERE task_date = ? AND routine_key = ?",
        (DAY, "daily_snapshot"),
    ))
    assert len(rows) == 1
    assert rows[0]["done"] == 1
    assert rows[0]["done_at"].endswith("+09:00")


def test_unchecking_clears_done_at(conn) -> None:
    db.set_routine_done(conn, DAY, "daily_why", True)
    db.set_routine_done(conn, DAY, "daily_why", False)

    row = conn.execute(
        "SELECT * FROM routine_log WHERE task_date = ? AND routine_key = ?",
        (DAY, "daily_why"),
    ).fetchone()
    assert row["done"] == 0
    assert row["done_at"] is None


def test_routines_for_returns_all_active_with_flags(conn) -> None:
    items = db.routines_for(conn, DAY)
    assert len(items) == 9                        # 일간 5 + 월/수/금 4 (004 에서 월간 7 종 off)
    assert all(item["done"] == 0 for item in items)

    db.set_routine_done(conn, DAY, "daily_snapshot", True)
    done = {item["key"]: item["done"] for item in db.routines_for(conn, DAY)}
    assert done["daily_snapshot"] == 1
    assert done["daily_why"] == 0


def test_routines_for_is_ordered_by_display_order(conn) -> None:
    items = db.routines_for(conn, DAY)
    assert [item["key"] for item in items][:3] == [
        "daily_overnight", "daily_snapshot", "daily_why",
    ]


def test_other_days_are_independent(conn) -> None:
    db.set_routine_done(conn, DAY, "daily_snapshot", True)
    other = {item["key"]: item["done"] for item in db.routines_for(conn, "2026-08-12")}
    assert other["daily_snapshot"] == 0


def test_unknown_routine_key_is_rejected(conn) -> None:
    """routine_def 에 없는 키는 외래키 제약에 걸린다."""
    with pytest.raises(sqlite3.IntegrityError):
        db.set_routine_done(conn, DAY, "daily_meditation", True)


def test_non_canonical_date_is_rejected(conn) -> None:
    with pytest.raises(ValueError):
        db.set_routine_done(conn, "2026-8-11", "daily_snapshot", True)
