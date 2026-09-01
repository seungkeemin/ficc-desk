"""파생값 레지스트리.

CLAUDE.md 2: 파생값은 저장하지 않는다. 조회 시 계산하고, 구성 원본이 하나라도
없으면 None 을 돌려주며 0 으로 대체하지 않는다.

문자열 수식을 eval 하지 않는다 (SPEC 2.2). 계산은 아래 파이썬 함수다.
금리 파생값의 저장 단위는 pct 이고 표시 단위는 bp 이므로 (a - b) * 100 으로 환산한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Derived:
    key: str
    inputs: tuple[str, ...]
    fn: Callable[..., float]
    unit: str
    label_ko: str
    label_short: str
    decimals: int


def _spread_bp(minuend: float, subtrahend: float) -> float:
    """pct 로 저장된 두 금리의 차를 bp 로."""
    return (minuend - subtrahend) * 100.0


REGISTRY: dict[str, Derived] = {
    "curve_3s10s": Derived(
        key="curve_3s10s",
        inputs=("ktb_10y", "ktb_3y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="국고 3-10 스프레드",
        label_short="3-10",
        decimals=1,
    ),
    "bond_swap_3y": Derived(
        key="bond_swap_3y",
        inputs=("ktb_3y", "irs_3y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="본드-스왑 스프레드 3년",
        label_short="B/S 3Y",
        decimals=1,
    ),
    "ust_2s10s": Derived(
        key="ust_2s10s",
        inputs=("ust_10y", "ust_2y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="UST 2s10s",
        label_short="2s10s",
        decimals=1,
    ),
    "corp_aa3_spread_3y": Derived(
        key="corp_aa3_spread_3y",
        inputs=("corp_aa3_yield_3y", "ktb_3y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="회사채 AA- 3년 스프레드",
        label_short="SPD",
        decimals=1,
    ),
    # 초장기 커브. 3-10 이 정책 기대라면 10-30 은 보험사·연기금 수요의 자리다.
    "curve_10s30s": Derived(
        key="curve_10s30s",
        inputs=("ktb_30y", "ktb_10y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="국고 10-30 스프레드",
        label_short="10-30",
        decimals=1,
    ),
    # 국고 3년이 기준금리 대비 몇 bp 인가 = 시장이 가격에 넣은 정책 기대.
    "ktb_base_spread_3y": Derived(
        key="ktb_base_spread_3y",
        inputs=("ktb_3y", "bok_base_rate"),
        fn=_spread_bp,
        unit="bp",
        label_ko="국고 3년 - 기준금리",
        label_short="3Y-기준",
        decimals=1,
    ),
    # CD 91일 - KOFR. 담보부(무위험)와 무담보 은행 조달의 차이라 단기자금 시장의
    # 신용·텀 프리미엄이 여기서 먼저 벌어진다.
    "cd_kofr_spread": Derived(
        key="cd_kofr_spread",
        inputs=("cd_91d", "kofr"),
        fn=_spread_bp,
        unit="bp",
        label_ko="CD 91일 - KOFR",
        label_short="CD-KOFR",
        decimals=1,
    ),
    "ust_5s30s": Derived(
        key="ust_5s30s",
        inputs=("ust_30y", "ust_5y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="UST 5s30s",
        label_short="5s30s",
        decimals=1,
    ),
    # 한미 10년 금리차. 외국인 채권투자와 환율 압력을 같은 숫자로 본다.
    # 두 값의 관측일이 다를 수 있다 (FRED 는 T+1, ECOS 는 T+0) — 화면은 더 오래된
    # 쪽 날짜를 as of 로 붙인다 (dashboard._derived_cell).
    "kr_us_10y": Derived(
        key="kr_us_10y",
        inputs=("ktb_10y", "ust_10y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="한미 금리차 10년",
        label_short="한미10Y",
        decimals=1,
    ),
    "corp_bbb3_spread_3y": Derived(
        key="corp_bbb3_spread_3y",
        inputs=("corp_bbb3_yield_3y", "ktb_3y"),
        fn=_spread_bp,
        unit="bp",
        label_ko="회사채 BBB- 3년 스프레드",
        label_short="SPD BBB",
        decimals=1,
    ),
}


def is_derived(key: str) -> bool:
    return key in REGISTRY


def compute(key: str, values: Mapping[str, float | None]) -> float | None:
    """구성 필드가 전부 있을 때만 계산한다. 하나라도 없으면 None."""
    spec = REGISTRY.get(key)
    if spec is None:
        return None
    args: list[float] = []
    for name in spec.inputs:
        value = values.get(name)
        if value is None:
            return None
        args.append(float(value))
    return spec.fn(*args)


def compute_all(values: Mapping[str, float | None]) -> dict[str, float | None]:
    return {key: compute(key, values) for key in REGISTRY}


# 국채선물 호가단위. 전일 대비를 '틱'으로 보여주기 위한 값이다.
FUTURES_TICK = 0.01


def delta_in_display_unit(
    current: float | None, previous: float | None, delta_unit: str
) -> float | None:
    """전일 대비를 field_def.delta_unit 으로 환산한다.

    전일 값이 없으면 None — 화면은 '—' 로 표시한다 (SPEC 3.6). 0 이 아니다.
    """
    if current is None or previous is None:
        return None
    diff = current - previous
    if delta_unit == "bp":       # pct 로 저장된 금리
        return diff * 100.0
    if delta_unit == "tick":     # 선물 가격
        return diff / FUTURES_TICK
    return diff                  # won | point — 저장 단위 그대로


def missing_inputs(key: str, values: Mapping[str, float | None]) -> list[str]:
    """화면에 '무엇이 없어서 계산이 안 되는가'를 보여주기 위한 것."""
    spec = REGISTRY.get(key)
    if spec is None:
        return []
    return [name for name in spec.inputs if values.get(name) is None]
