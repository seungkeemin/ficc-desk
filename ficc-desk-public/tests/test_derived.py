"""파생값 — 저장하지 않고 조회 시 계산한다. 결측은 None 이지 0 이 아니다."""

from __future__ import annotations

import pytest

from ficc import derived


def test_spread_is_converted_to_bp() -> None:
    values = {"ktb_10y": 3.120, "ktb_3y": 2.845}
    assert derived.compute("curve_3s10s", values) == pytest.approx(27.5)


def test_registry_is_the_full_derived_set() -> None:
    assert set(derived.REGISTRY) == {
        "curve_3s10s", "bond_swap_3y", "ust_2s10s", "corp_aa3_spread_3y",
        "curve_10s30s", "ktb_base_spread_3y", "cd_kofr_spread",
        "ust_5s30s", "kr_us_10y", "corp_bbb3_spread_3y",
    }


def test_spread_direction_is_first_input_minus_second() -> None:
    """빼는 순서가 뒤집히면 부호가 통째로 거짓말이 된다."""
    assert derived.compute(
        "kr_us_10y", {"ktb_10y": 3.120, "ust_10y": 4.180}) == pytest.approx(-106.0)
    assert derived.compute(
        "ktb_base_spread_3y",
        {"ktb_3y": 2.845, "bok_base_rate": 2.500}) == pytest.approx(34.5)
    assert derived.compute(
        "cd_kofr_spread", {"cd_91d": 3.070, "kofr": 2.478}) == pytest.approx(59.2)


@pytest.mark.parametrize("key,values", [
    ("curve_3s10s", {"ktb_10y": 3.120}),                    # ktb_3y 없음
    ("curve_3s10s", {"ktb_3y": 2.845}),                     # ktb_10y 없음
    ("curve_3s10s", {}),                                    # 둘 다 없음
    ("bond_swap_3y", {"ktb_3y": 2.845, "irs_3y": None}),    # 명시적 None
])
def test_missing_input_returns_none_not_zero(key: str, values: dict) -> None:
    result = derived.compute(key, values)
    assert result is None
    assert result != 0  # 0 으로 채우지 않는다 (CLAUDE.md 1·2)


def test_bond_swap_can_be_negative() -> None:
    """본드-스왑은 음수가 정상이다. 부호를 뒤집거나 절대값을 취하지 않는다."""
    values = {"ktb_3y": 2.845, "irs_3y": 2.910}
    assert derived.compute("bond_swap_3y", values) == pytest.approx(-6.5)


def test_missing_inputs_names_the_gap() -> None:
    assert derived.missing_inputs("ust_2s10s", {"ust_10y": 4.18}) == ["ust_2y"]
    assert derived.missing_inputs("ust_2s10s", {"ust_10y": 4.18, "ust_2y": 3.76}) == []


def test_compute_all_keeps_partial_results() -> None:
    """일부만 계산돼도 나머지가 죽지 않는다."""
    values = {"ktb_10y": 3.120, "ktb_3y": 2.845}
    result = derived.compute_all(values)
    assert result["curve_3s10s"] == pytest.approx(27.5)
    assert result["ust_2s10s"] is None


class TestDelta:
    def test_rates_delta_in_bp(self) -> None:
        assert derived.delta_in_display_unit(2.845, 2.833, "bp") == pytest.approx(1.2)

    def test_fx_delta_in_won(self) -> None:
        assert derived.delta_in_display_unit(1382.40, 1380.30, "won") == pytest.approx(2.10)

    def test_futures_delta_in_ticks(self) -> None:
        assert derived.delta_in_display_unit(106.12, 106.16, "tick") == pytest.approx(-4.0)

    def test_no_previous_value_is_none(self) -> None:
        """전일 값이 없으면 '—' 다. 0 으로 표시하면 '보합'이라는 거짓말이 된다 (SPEC 3.6)."""
        assert derived.delta_in_display_unit(2.845, None, "bp") is None
        assert derived.delta_in_display_unit(None, 2.833, "bp") is None
