"""아이디어 생성 — 무효화 조건 강제가 여기 있다.

CLAUDE.md 7: 무효화 조건 없는 아이디어는 저장할 수 없다. 최소 1건을 앱 레벨에서 강제한다.
검사가 트랜잭션 바깥이므로 idea 행이 만들어졌다 롤백되는 일조차 없어야 한다.
"""

from __future__ import annotations

import pytest

from ficc import db

FIELDS = {
    "position": "국고 3-10 스티프너 (3년 매수/10년 매도)",
    "flow_agent": "보험사 장기물 매수",
    "strategy": "momentum",
    "dv01_krw": 30_000_000.0,
    "holding_days": 10,
    "pricing_key": "curve_3s10s",
    "level_unit": "bp",
    "entry_level": 45.0,
    "target_level": 60.0,
    "stop_level": 38.0,
    "opened_on": "2026-08-11",
}


def _create(conn, **overrides):
    payload = dict(FIELDS)
    payload.update(overrides.pop("fields", {}))
    return db.create_idea(
        conn,
        fields=payload,
        theses=overrides.get("theses", ["금통위 인하 사이클 진입"]),
        invalidations=overrides.get("invalidations", ["금통위가 매파로 선회"]),
    )


def test_create_writes_idea_thesis_and_invalidation(conn) -> None:
    idea_id, code = _create(conn, theses=["논리1", "논리2"], invalidations=["조건1", "조건2"])

    assert code == "IDEA-001"
    row = conn.execute("SELECT * FROM idea WHERE id = ?", (idea_id,)).fetchone()
    assert row["status"] == "open"
    assert row["position"] == FIELDS["position"]
    assert row["pricing_key"] == "curve_3s10s"
    assert row["created_at"].endswith("+09:00")

    theses = list(conn.execute(
        "SELECT * FROM idea_thesis WHERE idea_id = ? ORDER BY seq", (idea_id,)))
    assert [t["seq"] for t in theses] == [1, 2]
    assert [t["text"] for t in theses] == ["논리1", "논리2"]

    conditions = list(conn.execute(
        "SELECT * FROM invalidation WHERE idea_id = ? ORDER BY id", (idea_id,)))
    assert [c["text"] for c in conditions] == ["조건1", "조건2"]


def test_no_invalidation_writes_nothing(conn) -> None:
    """행이 만들어졌다 롤백되는 것도 아니다 — 아예 실행되지 않는다."""
    with pytest.raises(ValueError, match="무효화 조건"):
        _create(conn, invalidations=[])

    assert conn.execute("SELECT COUNT(*) AS n FROM idea").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM invalidation").fetchone()["n"] == 0


def test_blank_invalidations_do_not_count(conn) -> None:
    with pytest.raises(ValueError, match="무효화 조건"):
        _create(conn, invalidations=["", "   ", "\n"])
    assert conn.execute("SELECT COUNT(*) AS n FROM idea").fetchone()["n"] == 0


def test_blank_theses_are_dropped_not_stored(conn) -> None:
    idea_id, _ = _create(conn, theses=["논리1", "", "  "])
    theses = list(conn.execute(
        "SELECT * FROM idea_thesis WHERE idea_id = ?", (idea_id,)))
    assert len(theses) == 1
    assert theses[0]["seq"] == 1        # 빈 칸을 건너뛰어도 seq 는 1 부터 촘촘하다


def test_more_than_three_theses_is_rejected(conn) -> None:
    """idea_thesis 의 CHECK (seq BETWEEN 1 AND 3) 에 걸리기 전에 막는다."""
    with pytest.raises(ValueError, match="논리"):
        _create(conn, theses=["1", "2", "3", "4"])
    assert conn.execute("SELECT COUNT(*) AS n FROM idea").fetchone()["n"] == 0


def test_bad_strategy_is_rejected(conn) -> None:
    with pytest.raises(ValueError, match="strategy"):
        _create(conn, fields={"strategy": "carry"})


def test_bad_opened_on_is_rejected(conn) -> None:
    with pytest.raises(ValueError):
        _create(conn, fields={"opened_on": "2026-8-11"})


def test_codes_increment(conn) -> None:
    assert _create(conn)[1] == "IDEA-001"
    assert _create(conn)[1] == "IDEA-002"
    assert _create(conn)[1] == "IDEA-003"


def test_code_numbering_ignores_foreign_formats(conn) -> None:
    _create(conn)
    conn.execute(
        "UPDATE idea SET code = 'LEGACY-7' WHERE code = 'IDEA-001'"
    )
    assert _create(conn)[1] == "IDEA-001"


def test_pricing_key_may_be_null(conn) -> None:
    """매핑이 불가능하면 NULL 로 두고 매일 수동 마킹한다 (SPEC 4-3)."""
    idea_id, _ = _create(conn, fields={"pricing_key": None})
    row = conn.execute("SELECT pricing_key FROM idea WHERE id = ?", (idea_id,)).fetchone()
    assert row["pricing_key"] is None


def test_idea_mark_upsert(conn) -> None:
    idea_id, _ = _create(conn, fields={"pricing_key": None})
    db.upsert_idea_mark(conn, idea_id, "2026-08-11", 27.5)
    db.upsert_idea_mark(conn, idea_id, "2026-08-11", 28.0)

    rows = list(conn.execute("SELECT * FROM idea_mark WHERE idea_id = ?", (idea_id,)))
    assert len(rows) == 1
    assert rows[0]["level"] == 28.0

    db.upsert_idea_mark(conn, idea_id, "2026-08-10", 26.0)
    assert db.latest_mark(conn, idea_id, "2026-08-11")["level"] == 28.0
    assert db.latest_mark(conn, idea_id, "2026-08-10")["level"] == 26.0
    assert db.latest_mark(conn, idea_id, "2026-08-09") is None


def test_open_positions_joins_conditions_and_checks(conn) -> None:
    idea_id, _ = _create(conn, invalidations=["조건1", "조건2"])
    condition = conn.execute(
        "SELECT id FROM invalidation WHERE idea_id = ? ORDER BY id", (idea_id,)
    ).fetchone()
    db.upsert_invalidation_check(conn, condition["id"], "2026-08-11", "shaky")

    rows = db.open_positions(conn, "2026-08-11")
    assert len(rows) == 2                              # 조건 수만큼 행이 나온다
    assert {row["inv_text"] for row in rows} == {"조건1", "조건2"}
    states = {row["inv_text"]: row["inv_state"] for row in rows}
    assert states["조건1"] == "shaky"
    assert states["조건2"] is None                      # 오늘 미점검


def test_open_positions_excludes_closed(conn) -> None:
    idea_id, _ = _create(conn)
    conn.execute("UPDATE idea SET status = 'closed' WHERE id = ?", (idea_id,))
    assert db.open_positions(conn, "2026-08-11") == []
