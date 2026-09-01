"""표시 서식.

숫자 규칙이 두 곳에 흩어지면 '값 없음'과 '0' 이 언젠가 섞인다 (CLAUDE.md 1).
그래서 서식은 전부 여기 한 곳에 있고, 두 소비자가 같은 함수를 쓴다.

  - 최초 렌더: routes/dashboard.py 가 Jinja 필터로 등록한다
  - 인라인 저장 응답: routes/observations.py 가 직접 호출한다

클라이언트는 숫자를 만지지 않는다. 서버가 만든 문자열을 그대로 넣을 뿐이다.
"""

from __future__ import annotations

from .viewmodel import Cell

MISSING = "미수집"
NO_DELTA = "—"

# 전일 대비의 소수 자리와 꼬리표. delta_unit 은 field_def 가 정한다 (SPEC 3.6).
DELTA_FORMAT: dict[str, tuple[int, str]] = {
    "bp":    (1, ""),
    "won":   (2, ""),
    "point": (2, ""),
    "tick":  (0, "t"),
    "qty":   (0, ""),   # 미결제약정 — 계약 수는 소수가 없다
    "fx4":   (4, ""),   # EUR/USD 처럼 소수 4 자리로 보는 환율. 2 자리면 하루치가 0.00 이 된다
}


def fmt_value(cell: Cell) -> str:
    if cell.value is None:
        return MISSING
    return f"{cell.value:,.{cell.decimals}f}"


def fmt_input(cell: Cell) -> str:
    """인라인 입력창의 value 속성. 미수집이면 빈 문자열이다.

    '미수집' 이라는 글자를 입력창에 넣으면 사용자가 지우고 타이핑해야 한다.
    placeholder 로 보여주고 실제 값은 비운다.

    값이 있으면 fmt_value 와 **같은 문자열**이다 — 입력창으로 바뀌었다고 해서
    천 단위 구분이 사라지면 화면이 달라 보인다. 저장할 때 클라이언트가 쉼표를 뗀다.
    """
    if cell.value is None:
        return ""
    return fmt_value(cell)


def fmt_delta(cell: Cell) -> str:
    """▲1.2 / ▼4t / — . 전일 값이 없으면 0 이 아니라 '—' 다."""
    if cell.delta is None:
        return NO_DELTA
    decimals, suffix = DELTA_FORMAT.get(cell.delta_unit, (2, ""))
    magnitude = f"{abs(cell.delta):,.{decimals}f}{suffix}"
    if cell.delta > 0:
        return f"▲{magnitude}"
    if cell.delta < 0:
        return f"▼{magnitude}"
    return f" {magnitude}"


def dir_class(delta: float | None) -> str:
    """방향 클래스. 색은 방향만 나타내고 가치판단을 암시하지 않는다."""
    if delta is None:
        return "na"
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def fmt_level(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return MISSING
    return f"{value:,.{decimals}f}"


def fmt_signed(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return NO_DELTA
    return f"{value:+,.{decimals}f}"


def fmt_dv01(krw: float) -> str:
    """명목 DV01 을 백만원 단위로. 계산하지 않고 사용자가 넣은 값을 그대로 쓴다 (SPEC 4-4)."""
    return f"{krw / 1_000_000:,.1f}M"


def strategy_short(strategy: str) -> str:
    return {"momentum": "MOM", "mean_reversion": "MR"}.get(strategy, strategy.upper())


def cell_payload(cell: Cell) -> dict[str, object]:
    """app.js 의 applyValues() 가 그대로 DOM 에 넣는 모양.

    value 가 None 이면 null 을 보낸다 — 클라이언트가 '미수집' 으로 그린다.
    0 으로 채우지 않는다 (CLAUDE.md 1).
    """
    return {
        "value": None if cell.value is None else fmt_input(cell),
        "delta": fmt_delta(cell),
        "dir": dir_class(cell.delta),
        "mark": "ᴹ" if cell.source == "manual" else "",
        "derived": cell.is_derived,
    }


FILTERS = (
    ("fmt_value", fmt_value),
    ("fmt_input", fmt_input),
    ("fmt_delta", fmt_delta),
    ("dir_class", dir_class),
    ("fmt_level", fmt_level),
    ("fmt_signed", fmt_signed),
    ("fmt_dv01", fmt_dv01),
    ("strategy_short", strategy_short),
)
