"""Phase 2 더미 데이터.

DB 에는 손대지 않는다. 가짜 관측값을 market_observation 에 넣으면 진짜 기록에
가짜 시계열이 섞이고, 시계열 유실이 이 프로젝트의 유일한 치명적 실패다 (CLAUDE.md 1).
그래서 더미는 코드 픽스처로만 존재한다.

ficc/dashboard.py 의 DB 빌더가 같은 DashboardVM 을 만들어 화면의 기본이 됐고, 이 모듈은
`?data=demo` / `?data=empty` 로 남았다 — 레이아웃 회귀를 눈으로 확인하는 픽스처다.
OBS_DATE 가 고정이라 상단 바 날짜가 오늘과 달라 보이는 것은 정상이다.
이 화면에서는 저장을 연결하지 않는다(dashboard.html 의 data-mode) — 확인용 화면에서
실제 관측값이 써지면 안 된다.

값은 SPEC 3.3 ASCII 목업의 숫자를 그대로 쓰고, 2026-08-11 확장분(정책·단기금리,
국고 커브, 선물 미결제약정, UST 커브, 해외 크레딧, 리스크)은 그 목업과 앞뒤가
맞게 지어낸 숫자다. **실제 시장 값이 아니다** — 여기서 확인하는 것은 레이아웃뿐이고,
진짜 값은 `python -m ficc.ingest` 가 공개 API 에서 받아 온다.

일부러 비워둔 것:
  ktbf_10y  자동(KRX)인데 T+1 이라 아직 없음 → 미수집 셀
  irs_3y    수동인데 아직 안 넣음 → 파생값 bond_swap_3y 가 계산 불가가 된다
  kr_cds_5y 수동 전용 → 미수집 셀
"""

from __future__ import annotations

from .viewmodel import (
    Cell,
    CellGroup,
    DashboardVM,
    EventVM,
    HeaderVM,
    InvalidationVM,
    JournalVM,
    PositionVM,
    RoutineItem,
)

OBS_DATE = "2026-08-11"


def _rate(key: str, label: str, value: float | None, delta: float | None,
          decimals: int = 3, **kw: object) -> Cell:
    """pct 로 저장되고 bp 로 비교되는 금리 셀."""
    return Cell(
        field_key=key, label_short=label, unit="pct", decimals=decimals,
        delta_unit="bp", value=value, delta=delta, **kw,  # type: ignore[arg-type]
    )


def _spread(key: str, label: str, value: float | None, delta: float | None, **kw: object) -> Cell:
    """bp 로 표시되는 파생 스프레드."""
    return Cell(
        field_key=key, label_short=label, unit="bp", decimals=1,
        delta_unit="bp", value=value, delta=delta, is_derived=True, **kw,  # type: ignore[arg-type]
    )


def _groups() -> tuple[CellGroup, ...]:
    return (
        CellGroup("policy_kr", "정책·단기금리", (
            # 기준금리는 며칠씩 같은 값이다. delta 가 0.0 인 것과 None 인 것은 다르다.
            _rate("bok_base_rate", "BOK BASE", 2.500, 0.0, decimals=2,
                  source="auto", auto_provider="ecos", as_of="2026-08-10", stale=True),
            _rate("kofr", "KOFR", 2.478, -0.3, source="auto", auto_provider="ecos",
                  as_of="2026-08-10", stale=True),
            _rate("cd_91d", "CD91D", 3.070, None, source="auto", auto_provider="ecos",
                  as_of="2026-08-08", stale=True),
            _rate("cp_91d", "CP91D", 3.190, 1.0, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _rate("msb_1y", "MSB1Y", 2.760, 0.5, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _spread("cd_kofr_spread", "CD-KOFR", 59.2, 0.3),
        )),
        CellGroup("krw_rates", "원화금리", (
            _rate("ktb_1y",  "국고1Y",  2.700, 0.4, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _rate("ktb_3y",  "국고3Y",  2.845, 1.2, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _rate("ktb_5y",  "국고5Y",  2.980, 1.6, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _rate("ktb_10y", "국고10Y", 3.120, 2.0, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _rate("ktb_20y", "국고20Y", 3.180, 2.4, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _rate("ktb_30y", "국고30Y", 3.150, 2.6, source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _spread("curve_3s10s", "3-10", 27.5, 0.8),
            _spread("curve_10s30s", "10-30", 3.0, 0.6),
            _spread("ktb_base_spread_3y", "3Y-기준", 34.5, 1.2),
        )),
        CellGroup("krw_futures", "국채선물", (
            Cell("ktbf_3y", "KTBF3Y", "futures", 2, "tick", value=106.12, delta=-4.0,
                 source="auto", auto_provider="krx", as_of="2026-08-10", stale=True),
            # KRX 는 최소 T+1 이다 (SPEC '확인 필요' 목록). 07:00 수집에는 당일치가 없다.
            Cell("ktbf_10y", "KTBF10Y", "futures", 2, "tick", auto_provider="krx"),
            Cell("ktbf_30y", "KTBF30Y", "futures", 2, "tick", value=120.45, delta=-9.0,
                 source="auto", auto_provider="krx", as_of="2026-08-10", stale=True),
            Cell("ktbf_3y_oi", "OI 3Y", "contracts", 0, "qty", value=512_300, delta=8_140,
                 source="auto", auto_provider="krx", as_of="2026-08-10", stale=True),
            Cell("ktbf_10y_oi", "OI 10Y", "contracts", 0, "qty", value=298_700, delta=-2_050,
                 source="auto", auto_provider="krx", as_of="2026-08-10", stale=True),
        )),
        CellGroup("swap", "스왑", (
            _rate("irs_1y", "IRS1Y", 2.780, -0.5, source="manual", as_of=OBS_DATE),
            _rate("irs_3y", "IRS3Y", None, None),
            _rate("irs_5y", "IRS5Y", 3.040, 1.5, source="manual", as_of=OBS_DATE),
            _spread("bond_swap_3y", "B/S 3Y", None, None, missing_inputs=("irs_3y",)),
        )),
        CellGroup("global_rates", "해외금리", (
            _rate("ust_3m",  "UST3M",  4.220, 0.0, source="auto", auto_provider="fred", as_of="2026-08-08", stale=True),
            _rate("ust_2y",  "UST2Y",  3.760, 3.0, source="auto", auto_provider="fred", as_of="2026-08-08", stale=True),
            _rate("ust_5y",  "UST5Y",  3.900, 2.5, source="auto", auto_provider="fred", as_of="2026-08-08", stale=True),
            _rate("ust_10y", "UST10Y", 4.180, 2.0, source="auto", auto_provider="fred", as_of="2026-08-08", stale=True),
            _rate("ust_30y", "UST30Y", 4.520, 1.5, source="auto", auto_provider="fred", as_of="2026-08-08", stale=True),
            _spread("ust_2s10s", "2s10s", 42.0, -1.0),
            _spread("ust_5s30s", "5s30s", 62.0, -1.0),
            _rate("sofr", "SOFR", 4.310, -1.0, decimals=2, source="auto", auto_provider="fred",
                  as_of="2026-08-10", stale=True),
            _rate("ff_target_upper", "FF UP", 4.500, 0.0, decimals=2, source="auto",
                  auto_provider="fred", as_of=OBS_DATE),
            _rate("us_bei_10y", "BEI10", 2.310, 1.0, decimals=2, source="auto",
                  auto_provider="fred", as_of="2026-08-10", stale=True),
            # 한미 금리차는 관측일이 다른 두 값의 차다 — as of 는 더 오래된 쪽이다.
            _spread("kr_us_10y", "한미10Y", -106.0, 0.0, as_of="2026-08-08", stale=True),
        )),
        CellGroup("fx", "FX", (
            Cell("usdkrw", "USD/KRW", "krw", 2, "won", value=1382.40, delta=2.10,
                 source="auto", auto_provider="ecos", as_of=OBS_DATE),
            Cell("ndf_1m", "NDF1M", "krw", 2, "won", value=1381.90, delta=1.80,
                 source="manual", as_of=OBS_DATE),
            Cell("swap_point_1m", "SWPT1M", "won_jeon", 2, "won", value=-1.85, delta=-0.05,
                 source="manual", as_of=OBS_DATE),
            Cell("usdjpy", "USD/JPY", "jpy", 2, "point", value=147.20, delta=0.35,
                 source="auto", auto_provider="fred", as_of="2026-08-08", stale=True),
            Cell("eurusd", "EUR/USD", "usd", 4, "fx4", value=1.0920, delta=-0.0035,
                 source="auto", auto_provider="fred", as_of="2026-08-08", stale=True),
            Cell("jpykrw_100", "원/100엔", "krw", 2, "won", value=939.10, delta=-1.20,
                 source="auto", auto_provider="ecos", as_of=OBS_DATE),
            Cell("cnykrw", "원/위안", "krw", 2, "won", value=192.30, delta=0.24,
                 source="auto", auto_provider="ecos", as_of=OBS_DATE),
            # DXY 는 ICE 독점 지수라 무료 공개 API 가 없다 → 수동 전용 + ⓘ (SPEC 4-1).
            Cell("dxy", "DXY", "index", 2, "point", value=99.12, delta=-0.08,
                 source="manual", as_of=OBS_DATE),
        )),
        CellGroup("credit", "크레딧", (
            _rate("corp_aa3_yield_3y", "AA-3Y", 3.290, 1.0,
                  source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _spread("corp_aa3_spread_3y", "SPD", 44.5, -0.2),
            _rate("corp_bbb3_yield_3y", "BBB-3Y", 9.850, 0.5,
                  source="auto", auto_provider="ecos", as_of=OBS_DATE),
            _spread("corp_bbb3_spread_3y", "SPD BBB", 700.5, -0.7),
            # ICE BofA OAS 는 단위가 % 다. 0.92 는 92bp 라는 뜻이다.
            _rate("us_ig_oas", "IG OAS", 0.920, -1.0, decimals=2, source="auto",
                  auto_provider="fred", as_of="2026-08-10", stale=True),
            _rate("us_hy_oas", "HY OAS", 3.150, -3.0, decimals=2, source="auto",
                  auto_provider="fred", as_of="2026-08-10", stale=True),
        )),
        CellGroup("risk", "리스크", (
            Cell("vix", "VIX", "index", 2, "point", value=16.40, delta=-0.62,
                 source="auto", auto_provider="fred", as_of="2026-08-10", stale=True),
            Cell("kr_cds_5y", "KR CDS5Y", "bp", 1, "bp"),
        )),
    )


def _positions() -> tuple[PositionVM, ...]:
    return (
        PositionVM(
            code="IDEA-012",
            position="국고 3-10 스티프너 (3년 매수/10년 매도)",
            strategy="momentum",
            level_unit="bp",
            entry_level=45.0, target_level=60.0, stop_level=38.0,
            current_level=27.5, pnl_bp=-17.5,
            dv01_krw=30_000_000, flow_agent="보험사 장기물 매수",
            holding_days=3, mark_mode="auto",
            invalidations=(
                InvalidationVM(1, "금통위가 매파로 선회 (의사록에 인상 소수의견)", "shaky"),
                InvalidationVM(2, "10년 입찰이 3회 연속 강하게 소화", "valid"),
            ),
        ),
        PositionVM(
            code="IDEA-013",
            position="UST-KTB 10년 스프레드 축소",
            strategy="mean_reversion",
            level_unit="bp",
            entry_level=118.0, target_level=130.0, stop_level=112.0,
            current_level=120.5, pnl_bp=2.5,
            dv01_krw=20_000_000, flow_agent="외사 조달 데스크",
            holding_days=9, mark_mode="manual",
            invalidations=(
                InvalidationVM(3, "미 근원 CPI 가 3개월 연속 컨센서스 상회", "broken"),
                InvalidationVM(4, "연준 인사 발언 톤이 완화로 돌아섬", None),
            ),
        ),
    )


def _routines() -> tuple[RoutineItem, ...]:
    return (
        RoutineItem("daily_overnight",    "야간장 리뷰 (뉴욕/런던)", "daily", done=True),
        RoutineItem("daily_snapshot",     "마켓 스냅샷",             "daily", done=True),
        RoutineItem("daily_why",          "왜 움직였나 한 문장",     "daily"),
        RoutineItem("daily_brief_en",     "영문 시황 브리핑",        "daily"),
        RoutineItem("daily_invalidation", "무효화 조건 점검",        "daily", done=True),
        RoutineItem("wed_idea",   "shadowing 아이디어 1건", "wed"),
        RoutineItem("fri_review", "주간 리뷰",              "fri"),
        RoutineItem("fri_drill",  "리스크 60초 즉답 드릴",  "fri"),
    )


def _events() -> tuple[EventVM, ...]:
    return (
        EventVM("2026-08-10", "US", "3년 국채 입찰", consensus=None,
                my_expectation="테일 소폭", actual="테일 0.4bp", my_call="hit"),
        EventVM("2026-08-12", "KR", "금통위", consensus="동결",
                my_expectation="동결, 인하 소수의견 1"),
        EventVM("2026-08-13", "US", "CPI (7월)", consensus="+0.3% MoM",
                my_expectation="+0.2% MoM"),
        EventVM("2026-08-14", "KR", "국고 10년 입찰", consensus="1.2조"),
    )


def _header(vm_groups: tuple[CellGroup, ...],
            positions: tuple[PositionVM, ...],
            color_convention: str) -> HeaderVM:
    """MANUAL·MISS·미점검 수를 데이터에서 센다. 상단 바가 본문과 어긋나면 안 된다."""
    cells = [cell for group in vm_groups for cell in group.cells if not cell.is_derived]
    return HeaderVM(
        obs_date=OBS_DATE,
        weekday="TUE",
        streak_days=47,
        undone_today=2,
        total_today=5,
        data_as_of="07:02",
        manual_count=sum(1 for cell in cells if cell.source == "manual"),
        miss_count=sum(1 for cell in cells if cell.status == "miss"),
        unchecked_count=sum(position.unchecked_count for position in positions),
        color_convention=color_convention,
    )


def build_demo(color_convention: str = "kr") -> DashboardVM:
    groups = _groups()
    positions = _positions()
    return DashboardVM(
        header=_header(groups, positions, color_convention),
        groups=groups,
        journal=JournalVM(
            review_ny=(
                "장 초반 CPI 프리뷰로 금리 상승 출발. 3년 입찰이 테일 0.4bp 로 무난히 "
                "소화되며 되돌림, 10년 4.18% 마감. 커브는 2bp 스팁."
            ),
            review_ldn="길트 30년 발행 부담에 초장기 약세. 분트는 보합권.",
            why_moved=None,     # 오늘 미완료
            brief_en=None,      # 오늘 미완료
        ),
        routines=_routines(),
        events=_events(),
        positions=positions,
    )


def build_empty(color_convention: str = "kr") -> DashboardVM:
    """빈 상태 확인용. 사과하지 않고 다음 행동을 지시하는 문구를 검증한다."""
    return DashboardVM(
        header=HeaderVM(
            obs_date=OBS_DATE,
            weekday="TUE",
            streak_days=0,
            undone_today=5,
            total_today=5,
            data_as_of=None,
            manual_count=0,
            miss_count=41,      # 저장 필드 수. 파생은 세지 않는다 (viewmodel.HeaderVM)
            unchecked_count=0,
            color_convention=color_convention,
        ),
        groups=(),
        journal=JournalVM(),
        routines=tuple(
            RoutineItem(item.key, item.label, item.cadence) for item in _routines()
        ),
        events=(),
        positions=(),
    )
