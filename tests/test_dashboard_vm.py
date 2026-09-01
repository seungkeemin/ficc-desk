"""DB → DashboardVM 빌더.

빈 DB 에서 예외 없이 그려지는 것이 첫 번째 요구다 — 처음 켠 날 화면이 깨지면
이 도구는 그날로 끝난다. 두 번째는 '미수집'이 0 으로 새지 않는 것이다 (CLAUDE.md 1).
"""

from __future__ import annotations

from datetime import date

import pytest

from ficc import dashboard, db


def approx(value: float):
    """부동소수 비교. 27.499999999999996 == 27.5 로 읽히게 한다."""
    return pytest.approx(value, abs=1e-9)

DAY = "2026-08-11"          # 화요일
PREV = "2026-08-10"


def test_empty_db_builds_without_error(conn) -> None:
    vm = dashboard.build(conn, obs_date=DAY)

    assert vm.header.obs_date == DAY
    assert vm.header.weekday == "TUE"
    assert vm.header.streak_days == 0
    assert vm.header.data_as_of is None
    assert vm.positions == ()
    assert vm.events == ()
    assert vm.journal.why_moved is None


def test_empty_db_marks_every_stored_field_missing(conn) -> None:
    vm = dashboard.build(conn, obs_date=DAY)
    cells = [cell for group in vm.groups for cell in group.cells]

    assert len(cells) == 51                       # 저장 41 + 파생 10
    assert all(cell.value is None for cell in cells)
    assert all(cell.status == "miss" for cell in cells)
    assert vm.header.miss_count == 41              # 파생은 세지 않는다
    assert vm.header.manual_count == 0


def test_groups_follow_field_def_order(conn) -> None:
    vm = dashboard.build(conn, obs_date=DAY)
    assert [group.category for group in vm.groups] == [
        "policy_kr", "krw_rates", "krw_futures", "swap",
        "global_rates", "fx", "credit", "risk",
    ]
    assert vm.groups[0].title == "정책·단기금리"
    assert [cell.field_key for cell in vm.groups[0].cells][:3] == [
        "bok_base_rate", "kofr", "cd_91d",
    ]
    # 국고 커브는 만기 순으로 선다. 3년이 1년보다 먼저 오면 눈이 커브를 못 읽는다.
    assert [cell.field_key for cell in vm.groups[1].cells] == [
        "ktb_1y", "ktb_3y", "ktb_5y", "ktb_10y", "ktb_20y", "ktb_30y",
        "curve_3s10s", "curve_10s30s", "ktb_base_spread_3y",
    ]


def test_single_observation_has_no_delta(conn) -> None:
    """전일 값이 없으면 delta 는 0 이 아니라 None 이다 (SPEC 3.6)."""
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")
    _, cells = dashboard.build_cells(conn, DAY)

    assert cells["ktb_3y"].value == 2.845
    assert cells["ktb_3y"].delta is None
    assert cells["ktb_3y"].source == "auto"
    assert cells["ktb_3y"].as_of == DAY
    assert cells["ktb_3y"].stale is False


def test_delta_is_converted_to_bp(conn) -> None:
    db.upsert_observation(conn, PREV, "ktb_3y", 2.833, "auto", "ecos")
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")

    _, cells = dashboard.build_cells(conn, DAY)
    assert cells["ktb_3y"].delta == approx(1.2)


def test_stale_value_is_flagged_with_its_own_date(conn) -> None:
    """ECOS 가 T+1 이면 오늘 자 행이 없다. 앞 날짜로 채우는 게 아니라 언제 값인지 밝힌다."""
    db.upsert_observation(conn, PREV, "ktb_3y", 2.845, "auto", "ecos")
    _, cells = dashboard.build_cells(conn, DAY)

    assert cells["ktb_3y"].value == 2.845
    assert cells["ktb_3y"].as_of == PREV
    assert cells["ktb_3y"].stale is True


def test_derived_needs_all_inputs(conn) -> None:
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")
    _, cells = dashboard.build_cells(conn, DAY)

    assert cells["curve_3s10s"].value is None
    assert cells["curve_3s10s"].status == "miss"
    assert cells["curve_3s10s"].missing_inputs == ("ktb_10y",)


def test_derived_value_is_computed_in_bp(conn) -> None:
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")
    db.upsert_observation(conn, DAY, "ktb_10y", 3.120, "auto", "ecos")

    _, cells = dashboard.build_cells(conn, DAY)
    assert cells["curve_3s10s"].value == approx(27.5)
    assert cells["curve_3s10s"].is_derived is True


def test_derived_delta_is_a_plain_difference(conn) -> None:
    """파생값은 이미 bp 다. delta_in_display_unit 의 ×100 을 태우면 100 배 틀린다."""
    db.upsert_observation(conn, PREV, "ktb_3y", 2.833, "auto", "ecos")
    db.upsert_observation(conn, PREV, "ktb_10y", 3.100, "auto", "ecos")
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")
    db.upsert_observation(conn, DAY, "ktb_10y", 3.120, "auto", "ecos")

    _, cells = dashboard.build_cells(conn, DAY)
    # 오늘 27.5bp, 어제 26.7bp → +0.8bp. 80.0 이 아니다.
    assert cells["curve_3s10s"].delta == approx(0.8)


def test_derived_as_of_is_the_oldest_input(conn) -> None:
    """오늘 국고 3년과 지난주 국고 10년의 차이를 '오늘의 스프레드'라 부르지 않는다."""
    db.upsert_observation(conn, "2026-08-05", "ktb_10y", 3.120, "auto", "ecos")
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")

    _, cells = dashboard.build_cells(conn, DAY)
    assert cells["curve_3s10s"].value is not None
    assert cells["curve_3s10s"].as_of == "2026-08-05"
    assert cells["curve_3s10s"].stale is True


def test_manual_source_is_counted(conn) -> None:
    db.upsert_observation(conn, DAY, "irs_3y", 2.910, "manual", "user")
    vm = dashboard.build(conn, obs_date=DAY)

    assert vm.header.manual_count == 1
    assert vm.header.miss_count == 40


def test_affected_keys_include_dependent_derived(conn) -> None:
    assert dashboard.affected_keys("irs_3y") == {"irs_3y", "bond_swap_3y"}
    assert dashboard.affected_keys("ktb_3y") == {
        "ktb_3y", "curve_3s10s", "bond_swap_3y",
        "corp_aa3_spread_3y", "corp_bbb3_spread_3y", "ktb_base_spread_3y",
    }
    assert dashboard.affected_keys("dxy") == {"dxy"}


def test_today_counts_only_daily_and_this_weekday(conn) -> None:
    """화요일에는 일간 5 종만 오늘 항목이다. 월/수/금 항목과 월간 항목은 빠진다."""
    vm = dashboard.build(conn, obs_date=DAY)
    assert vm.header.total_today == 5
    assert vm.header.undone_today == 5

    db.set_routine_done(conn, DAY, "daily_snapshot", True)
    assert dashboard.build(conn, obs_date=DAY).header.undone_today == 4


def test_wednesday_adds_the_idea_routine(conn) -> None:
    vm = dashboard.build(conn, obs_date="2026-08-12")
    assert vm.header.weekday == "WED"
    assert vm.header.total_today == 6            # 일간 5 + wed_idea


def test_streak_reaches_the_header(conn) -> None:
    for key in ("daily_overnight", "daily_snapshot", "daily_why",
                "daily_brief_en", "daily_invalidation"):
        db.set_routine_done(conn, PREV, key, True)

    vm = dashboard.build(conn, obs_date=DAY)
    assert vm.header.streak_days == 1            # 오늘 미완료여도 어제가 살아 있다


def test_journal_round_trips(conn) -> None:
    db.upsert_journal_field(conn, DAY, "why_moved", "CPI 프리뷰")
    vm = dashboard.build(conn, obs_date=DAY)
    assert vm.journal.why_moved == "CPI 프리뷰"
    assert vm.journal.brief_en is None


def test_events_cover_the_containing_week(conn) -> None:
    db.create_event(conn, event_date="2026-08-09", region="KR", name="지난 주 일요일")
    db.create_event(conn, event_date="2026-08-10", region="US", name="3년 국채 입찰")
    db.create_event(conn, event_date="2026-08-16", region="KR", name="이번 주 일요일")
    db.create_event(conn, event_date="2026-08-17", region="KR", name="다음 주 월요일")

    vm = dashboard.build(conn, obs_date=DAY)
    assert [event.name for event in vm.events] == ["3년 국채 입찰", "이번 주 일요일"]


def test_week_bounds() -> None:
    assert dashboard.week_bounds(date(2026, 8, 11)) == ("2026-08-10", "2026-08-16")
    assert dashboard.week_bounds(date(2026, 8, 10)) == ("2026-08-10", "2026-08-16")
    assert dashboard.week_bounds(date(2026, 8, 16)) == ("2026-08-10", "2026-08-16")


def test_data_as_of_comes_from_the_last_ingest(conn) -> None:
    run_id = db.start_run(conn, DAY)
    db.finish_run(conn, run_id, "ok")

    vm = dashboard.build(conn, obs_date=DAY)
    assert vm.header.data_as_of is not None
    assert len(vm.header.data_as_of) == 5 and ":" in vm.header.data_as_of
