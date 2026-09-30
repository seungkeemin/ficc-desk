"""Collector parsing against saved responses, without network access.

The fixtures in tests/fixtures/ follow the response formats documented in each
collector's docstring and in ficc/config/sources.py (confirmed by real calls on
2026-08-11). They only carry the fields the collectors read. ECOS and FRED values
come from the 2026-08-11 measurements recorded in sources.py where one exists.
KRX prices, volumes and open interest are synthetic round numbers: KRX data is not
redistributed in this repository. Only the row layout (PROD_NM, MKT_NM, ISU_NM
format) mirrors the real response.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ficc.sources import ecos, fred, krx
from ficc.sources.base import Failed, Fetched, Missing

FIXTURES = Path(__file__).parent / "fixtures"
TARGET = date(2026, 8, 11)


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fake_keys(monkeypatch):
    monkeypatch.setenv("ECOS_API_KEY", "test-key")
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setenv("KRX_AUTH_KEY", "test-key")
    ecos._table_cache.clear()
    krx._cache.clear()
    yield
    ecos._table_cache.clear()
    krx._cache.clear()


# ECOS -------------------------------------------------------------------------

def test_ecos_takes_latest_published_row_for_the_item(monkeypatch):
    calls = []

    def fake_get_json(url, **kwargs):
        calls.append(url)
        return load("ecos_817Y002_20260728_20260811.json")

    monkeypatch.setattr(ecos, "get_json", fake_get_json)

    result = ecos.fetch("ktb_3y", TARGET)
    assert result == Fetched("ktb_3y", 3.808, date(2026, 8, 11), "ecos")

    # 5Y differs from 3Y only in the last digit of the item code.
    assert ecos.fetch("ktb_5y", TARGET).value == 4.042
    # The whole table is fetched once and reused for every item in it.
    assert len(calls) == 1
    assert "/StatisticSearch/test-key/json/kr/1/1000/817Y002/D/20260728/20260811" in calls[0]


def test_ecos_blank_value_is_missing_not_zero(monkeypatch):
    monkeypatch.setattr(ecos, "get_json",
                        lambda url, **kw: load("ecos_817Y002_20260728_20260811.json"))
    result = ecos.fetch("kofr", TARGET)
    assert isinstance(result, Missing)


def test_ecos_info200_envelope_is_missing(monkeypatch):
    monkeypatch.setattr(ecos, "get_json", lambda url, **kw: load("ecos_info200.json"))
    assert isinstance(ecos.fetch("ktb_3y", TARGET), Missing)


def test_ecos_error_envelope_is_failed_with_code(monkeypatch):
    monkeypatch.setattr(ecos, "get_json", lambda url, **kw: load("ecos_auth_error.json"))
    result = ecos.fetch("ktb_3y", TARGET)
    assert isinstance(result, Failed)
    assert result.message.startswith("INFO-100")


def test_ecos_without_key_is_missing_and_makes_no_call(monkeypatch):
    monkeypatch.setenv("ECOS_API_KEY", "")

    def should_not_run(url, **kw):
        raise AssertionError("no HTTP call without a key")

    monkeypatch.setattr(ecos, "get_json", should_not_run)
    assert isinstance(ecos.fetch("ktb_3y", TARGET), Missing)


# FRED -------------------------------------------------------------------------

def test_fred_skips_dot_and_uses_real_observation_date(monkeypatch):
    seen = {}

    def fake_get_json(url, *, params=None, **kw):
        seen.update(params)
        return load("fred_DGS5_20260728_20260811.json")

    monkeypatch.setattr(fred, "get_json", fake_get_json)

    result = fred.fetch("ust_5y", TARGET)
    # obs_date is the observation date (T+1 publication), not the collection day.
    assert result == Fetched("ust_5y", 4.35, date(2026, 8, 7), "fred")
    assert seen["series_id"] == "DGS5"
    assert seen["observation_start"] == "2026-07-28"
    assert seen["observation_end"] == "2026-08-11"


def test_fred_error_message_is_failed(monkeypatch):
    monkeypatch.setattr(fred, "get_json",
                        lambda url, **kw: {"error_code": 400, "error_message": "Bad Request."})
    result = fred.fetch("ust_5y", TARGET)
    assert isinstance(result, Failed)
    assert "Bad Request" in result.message


def test_fred_network_exception_is_failed_not_raised(monkeypatch):
    def boom(url, **kw):
        raise RuntimeError("타임아웃")

    monkeypatch.setattr(fred, "get_json", boom)
    assert isinstance(fred.fetch("ust_5y", TARGET), Failed)


# KRX --------------------------------------------------------------------------

def _krx_by_day(monkeypatch):
    """20260811 has no rows yet (published T+1); 20260810 has the session."""
    days = []

    def fake_get_json(url, *, headers=None, params=None):
        assert headers == {"AUTH_KEY": "test-key"}
        days.append(params["basDd"])
        if params["basDd"] == "20260810":
            return load("krx_fut_bydd_trd_20260810.json")
        return {"OutBlock_1": []}

    monkeypatch.setattr(krx, "get_json", fake_get_json)
    return days


def test_krx_front_month_regular_session_close(monkeypatch):
    days = _krx_by_day(monkeypatch)
    result = krx.fetch("ktbf_3y", TARGET)
    assert result == Fetched("ktbf_3y", 100.10, date(2026, 8, 10), "krx",
                             note="3년국채    F 202609 (주간)")
    # Walks back from the empty target day to the last session.
    assert days == ["20260811", "20260810"]


def test_krx_open_interest_reuses_the_cached_day(monkeypatch):
    days = _krx_by_day(monkeypatch)
    assert krx.fetch("ktbf_3y", TARGET).value == 100.10
    assert krx.fetch("ktbf_3y_oi", TARGET).value == 7000
    assert krx.fetch("ktbf_10y_oi", TARGET).value == 4000
    assert days == ["20260811", "20260810"]


def test_krx_product_name_is_exact_match(monkeypatch):
    # The spread product has the largest volume and contains '3년' and '10년';
    # a partial match would pick it.
    _krx_by_day(monkeypatch)
    assert krx.fetch("ktbf_10y", TARGET).value == 110.00
    assert krx.fetch("ktbf_30y", TARGET).value == 120.00


def test_krx_roll_week_ignores_calendar_spread(monkeypatch):
    # Regression: on 2026-09-10/11/14 the spread row out-traded both outrights and
    # its price was stored as the futures close.
    monkeypatch.setattr(krx, "get_json",
                        lambda url, **kw: load("krx_fut_bydd_trd_20260910_roll.json"))
    price = krx.fetch("ktbf_3y", date(2026, 9, 10))
    assert price.value == 100.20 and price.note == "3년국채    F 202612 (주간)"
    # Open interest comes from the same outright row instead of a blank spread row.
    assert krx.fetch("ktbf_3y_oi", date(2026, 9, 10)).value == 5000


def test_krx_skips_weekends(monkeypatch):
    days = _krx_by_day(monkeypatch)
    krx.fetch("ktbf_3y", date(2026, 8, 16))   # Sunday
    assert "20260815" not in days and "20260816" not in days
    assert days[-1] == "20260810"
