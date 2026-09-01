"""연속 기록 일수.

SPEC 4-7 이 정한 것은 두 줄뿐이다 — 영업일만 세고, counts_streak 일간 항목이 전부
완료된 날만 센다. 나머지 경계(오늘이 아직 미완료일 때, 휴장일, 주말)는 여기서 못박는다.
게임화하지 않는다는 규칙 때문에 '오늘 미완료 → 0' 이 특히 중요하다: 매일 아침 0 으로
리셋되는 숫자는 형태만 다른 연속 끊김 경고다.
"""

from __future__ import annotations

from datetime import date

import pytest

from ficc import db, streak

# 2026-08-11 은 화요일. 08-10 월, 08-08~09 주말, 08-07 금.
TUE = date(2026, 8, 11)
MON = date(2026, 8, 10)
FRI = date(2026, 8, 7)
SAT = date(2026, 8, 15)

DAILY_KEYS = (
    "daily_overnight", "daily_snapshot", "daily_why",
    "daily_brief_en", "daily_invalidation",
)


def _complete(conn, day: str, keys=DAILY_KEYS) -> None:
    for key in keys:
        db.set_routine_done(conn, day, key, True)


# --------------------------------------------------------------- 순수 함수


def test_no_records_is_zero() -> None:
    assert streak.streak_days(set(), TUE) == 0


def test_today_complete_counts_one() -> None:
    assert streak.streak_days({"2026-08-11"}, TUE) == 1


def test_today_incomplete_keeps_yesterday_streak() -> None:
    """오늘 아침에는 아무것도 완료가 아니다. D+n 이 0 으로 떨어지면 안 된다."""
    assert streak.streak_days({"2026-08-10"}, TUE) == 1


def test_today_and_yesterday_incomplete_is_zero() -> None:
    """오늘 예외는 오늘 하루뿐이다. 어제가 비면 거기서 끊긴다."""
    assert streak.streak_days({"2026-08-07"}, TUE) == 0


def test_weekend_is_skipped_not_broken() -> None:
    """월요일과 직전 금요일이 완료면 연속 2 다. 토·일은 세지도, 끊지도 않는다."""
    assert streak.streak_days({"2026-08-10", "2026-08-07"}, MON) == 2


def test_holiday_is_skipped() -> None:
    """휴장일은 기록이 없어도 끊기지 않는다."""
    holidays = streak.parse_holidays("2026-08-10")
    assert streak.streak_days({"2026-08-11", "2026-08-07"}, TUE, holidays) == 2


def test_business_day_without_record_breaks() -> None:
    holidays = streak.parse_holidays("")
    assert streak.streak_days({"2026-08-11", "2026-08-07"}, TUE, holidays) == 1


def test_saturday_does_not_excuse_incomplete_friday() -> None:
    """오늘이 주말이면 예외가 적용될 자리가 없다. 금요일이 비면 0 이다."""
    assert streak.streak_days({"2026-08-07"}, SAT) == 0


def test_parse_holidays_empty_is_empty_set() -> None:
    """split(',') 의 [''] 가 날짜 하나로 새면 모든 날이 휴장일이 된다."""
    assert streak.parse_holidays("") == frozenset()
    assert streak.parse_holidays("   ") == frozenset()


def test_parse_holidays_accepts_commas_and_whitespace() -> None:
    assert streak.parse_holidays("2026-01-01, 2026-03-01\n2026-05-05") == frozenset(
        {"2026-01-01", "2026-03-01", "2026-05-05"}
    )


def test_parse_holidays_rejects_non_canonical() -> None:
    with pytest.raises(ValueError):
        streak.parse_holidays("2026-1-1")


def test_scan_is_bounded() -> None:
    """완료일이 아주 오래전 하나뿐이어도 역주행이 즉시 끝난다."""
    assert streak.streak_days({"2020-01-02"}, TUE) == 0


def test_is_business_day() -> None:
    assert streak.is_business_day(MON, frozenset())
    assert not streak.is_business_day(SAT, frozenset())
    assert not streak.is_business_day(MON, frozenset({"2026-08-10"}))


# ------------------------------------------------------------------- DB 연동


def test_complete_streak_days_needs_all_daily(conn) -> None:
    _complete(conn, "2026-08-11", DAILY_KEYS[:4])          # 5 개 중 4 개
    assert db.complete_streak_days(conn, "2026-08-11") == set()

    db.set_routine_done(conn, "2026-08-11", "daily_invalidation", True)
    assert db.complete_streak_days(conn, "2026-08-11") == {"2026-08-11"}


def test_non_streak_routines_do_not_matter(conn) -> None:
    """counts_streak = 0 인 요일 항목은 연속 기록과 무관하다."""
    _complete(conn, "2026-08-11")
    assert db.complete_streak_days(conn, "2026-08-11") == {"2026-08-11"}
    # wed_idea 를 안 해도 그날은 여전히 완료일이다
    assert db.routines_for(conn, "2026-08-11")


def test_complete_streak_days_respects_upper_bound(conn) -> None:
    _complete(conn, "2026-08-10")
    _complete(conn, "2026-08-11")
    assert db.complete_streak_days(conn, "2026-08-10") == {"2026-08-10"}


def test_unchecking_removes_the_day(conn) -> None:
    _complete(conn, "2026-08-11")
    db.set_routine_done(conn, "2026-08-11", "daily_why", False)
    assert db.complete_streak_days(conn, "2026-08-11") == set()
