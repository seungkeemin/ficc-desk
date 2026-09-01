"""포지션 마킹과 손익.

SPEC 4-3: 마킹이 불가능하면 None 이다. **없는 값을 추정해 채우지 않는다.**
SPEC 4-4: DV01 은 계산하지 않고, 손익은 bp 로만 환산한다.
"""

from __future__ import annotations

import pytest

from ficc import dashboard, db

DAY = "2026-08-11"

BASE = {
    "position": "국고 3-10 스티프너",
    "flow_agent": "보험사 장기물 매수",
    "strategy": "momentum",
    "dv01_krw": 30_000_000.0,
    "holding_days": 10,
    "pricing_key": "curve_3s10s",
    "level_unit": "bp",
    "entry_level": 45.0,
    "target_level": 60.0,
    "stop_level": 38.0,
    "opened_on": "2026-08-08",
}


def _idea(conn, **overrides) -> int:
    fields = dict(BASE)
    fields.update(overrides)
    idea_id, _ = db.create_idea(
        conn, fields=fields, theses=["논리"], invalidations=["조건"]
    )
    return idea_id


def _curve(conn, three: float = 2.845, ten: float = 3.120) -> None:
    db.upsert_observation(conn, DAY, "ktb_3y", three, "auto", "ecos")
    db.upsert_observation(conn, DAY, "ktb_10y", ten, "auto", "ecos")


def _position(conn):
    vm = dashboard.build(conn, obs_date=DAY)
    return vm.positions[0]


def test_auto_mark_from_derived_pricing_key(conn) -> None:
    _idea(conn)
    _curve(conn)

    position = _position(conn)
    assert position.mark_mode == "auto"
    assert position.current_level == pytest.approx(27.5, abs=1e-9)
    assert position.pnl_bp == pytest.approx(-17.5, abs=1e-9)   # 45 → 27.5, 목표가 위였다
    assert position.holding_days == 3                          # 08-08 진입 → D+3


def test_auto_mark_from_stored_pct_field_converts_to_bp(conn) -> None:
    _idea(conn, pricing_key="ktb_3y", entry_level=280.0, target_level=300.0)
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")

    position = _position(conn)
    assert position.current_level == pytest.approx(284.5, abs=1e-9)
    assert position.pnl_bp == pytest.approx(4.5, abs=1e-9)


def test_short_position_flips_the_sign(conn) -> None:
    """목표가 진입보다 아래면 레벨 하락이 이익이다."""
    _idea(conn, entry_level=45.0, target_level=30.0, stop_level=52.0)
    _curve(conn)

    position = _position(conn)
    assert position.current_level == pytest.approx(27.5, abs=1e-9)
    assert position.pnl_bp == pytest.approx(17.5, abs=1e-9)


def test_missing_input_leaves_level_and_pnl_none(conn) -> None:
    """구성 원본이 없으면 파생값이 None 이고, 손익도 None 이다. 0 이 아니다."""
    _idea(conn)
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")

    position = _position(conn)
    assert position.current_level is None
    assert position.pnl_bp is None


def test_krw_level_unit_has_no_bp_pnl(conn) -> None:
    """원화 차이를 bp 칸에 넣는 것은 단위 거짓말이다. 레벨은 보이고 손익만 비운다."""
    _idea(conn, pricing_key="usdkrw", level_unit="krw",
          entry_level=1380.0, target_level=1400.0, stop_level=1370.0)
    db.upsert_observation(conn, DAY, "usdkrw", 1382.40, "auto", "ecos")

    position = _position(conn)
    assert position.current_level == pytest.approx(1382.40, abs=1e-9)
    assert position.pnl_bp is None


def test_undefined_unit_combination_is_not_guessed(conn) -> None:
    """(futures, bp) 는 환산표에 없다. 조용히 통과시키지 않고 미수집으로 둔다."""
    _idea(conn, pricing_key="ktbf_3y", level_unit="bp")
    db.upsert_observation(conn, DAY, "ktbf_3y", 106.12, "auto", "krx")

    position = _position(conn)
    assert position.current_level is None
    assert position.pnl_bp is None


def test_manual_marking_when_pricing_key_is_null(conn) -> None:
    idea_id = _idea(conn, pricing_key=None)
    position = _position(conn)
    assert position.mark_mode == "manual"
    assert position.current_level is None       # 아직 마킹하지 않았다

    db.upsert_idea_mark(conn, idea_id, DAY, 27.5)
    position = _position(conn)
    assert position.mark_mode == "manual"
    assert position.current_level == pytest.approx(27.5, abs=1e-9)
    assert position.pnl_bp == pytest.approx(-17.5, abs=1e-9)


def test_manual_mark_falls_back_to_the_latest_earlier_date(conn) -> None:
    idea_id = _idea(conn, pricing_key=None)
    db.upsert_idea_mark(conn, idea_id, "2026-08-10", 26.0)

    position = _position(conn)
    assert position.current_level == pytest.approx(26.0, abs=1e-9)


def test_worst_state_and_unchecked_count(conn) -> None:
    idea_id, _ = db.create_idea(
        conn, fields=dict(BASE), theses=[],
        invalidations=["조건1", "조건2", "조건3"],
    )
    ids = [row["id"] for row in conn.execute(
        "SELECT id FROM invalidation WHERE idea_id = ? ORDER BY id", (idea_id,))]
    db.upsert_invalidation_check(conn, ids[0], DAY, "valid")
    db.upsert_invalidation_check(conn, ids[1], DAY, "broken")

    vm = dashboard.build(conn, obs_date=DAY)
    position = vm.positions[0]
    assert len(position.invalidations) == 3
    assert position.worst_state == "broken"
    assert position.unchecked_count == 1
    assert vm.header.unchecked_count == 1


def test_positions_carry_their_id_for_inline_marking(conn) -> None:
    idea_id = _idea(conn, pricing_key=None)
    assert _position(conn).id == idea_id


def test_closed_ideas_leave_the_blotter(conn) -> None:
    idea_id = _idea(conn)
    conn.execute("UPDATE idea SET status = 'closed' WHERE id = ?", (idea_id,))
    assert dashboard.build(conn, obs_date=DAY).positions == ()


def test_opened_today_is_d_plus_zero(conn) -> None:
    _idea(conn, opened_on=DAY)
    assert _position(conn).holding_days == 0
