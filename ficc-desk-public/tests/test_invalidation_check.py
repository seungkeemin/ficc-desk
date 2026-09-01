"""무효화 조건의 일별 점검 — 시그니처 패널의 데이터 소스.

SPEC 3.5: 조건마다 유효/흔들림/깨짐 토글, 클릭 즉시 그날 날짜로 저장된다.
하루 한 행이므로 마음이 바뀌면 덮어쓰지만, 처음 점검한 시각은 보존한다.
"""

from __future__ import annotations

import pytest

from ficc import db

DAY = "2026-08-11"


def _condition(conn) -> int:
    db.create_idea(
        conn,
        fields={
            "position": "국고 3-10 스티프너", "flow_agent": None, "strategy": "momentum",
            "dv01_krw": 30_000_000.0, "holding_days": 10, "pricing_key": "curve_3s10s",
            "level_unit": "bp", "entry_level": 45.0, "target_level": 60.0,
            "stop_level": 38.0, "opened_on": DAY,
        },
        theses=[],
        invalidations=["금통위가 매파로 선회"],
    )
    return conn.execute("SELECT id FROM invalidation ORDER BY id LIMIT 1").fetchone()["id"]


def test_same_day_updates_state_in_place(conn) -> None:
    cid = _condition(conn)
    db.upsert_invalidation_check(conn, cid, DAY, "valid")
    first = conn.execute(
        "SELECT * FROM invalidation_check WHERE invalidation_id = ?", (cid,)
    ).fetchone()

    db.upsert_invalidation_check(conn, cid, DAY, "broken")
    rows = list(conn.execute(
        "SELECT * FROM invalidation_check WHERE invalidation_id = ?", (cid,)))

    assert len(rows) == 1
    assert rows[0]["state"] == "broken"
    assert rows[0]["created_at"] == first["created_at"]   # 처음 점검한 시각은 그대로


def test_different_days_are_separate_rows(conn) -> None:
    cid = _condition(conn)
    db.upsert_invalidation_check(conn, cid, "2026-08-10", "valid")
    db.upsert_invalidation_check(conn, cid, "2026-08-11", "shaky")

    rows = list(conn.execute(
        "SELECT * FROM invalidation_check WHERE invalidation_id = ? ORDER BY check_date",
        (cid,),
    ))
    assert [row["state"] for row in rows] == ["valid", "shaky"]


def test_note_is_preserved_when_omitted(conn) -> None:
    cid = _condition(conn)
    db.upsert_invalidation_check(conn, cid, DAY, "shaky", note="의사록에 인상 소수의견")
    db.upsert_invalidation_check(conn, cid, DAY, "broken")

    row = conn.execute(
        "SELECT * FROM invalidation_check WHERE invalidation_id = ?", (cid,)
    ).fetchone()
    assert row["state"] == "broken"
    assert row["note"] == "의사록에 인상 소수의견"


@pytest.mark.parametrize("bad", ["ok", "BROKEN", "", "깨짐"])
def test_bad_state_is_rejected(conn, bad: str) -> None:
    cid = _condition(conn)
    with pytest.raises(ValueError):
        db.upsert_invalidation_check(conn, cid, DAY, bad)


def test_non_canonical_date_is_rejected(conn) -> None:
    cid = _condition(conn)
    with pytest.raises(ValueError):
        db.upsert_invalidation_check(conn, cid, "2026-8-11", "valid")
