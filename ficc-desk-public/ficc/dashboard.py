"""DB → DashboardVM.

demo.py 가 코드 픽스처로 만들던 것과 **똑같은 모양**을 실제 DB 에서 만든다.
그러라고 viewmodel.py 로 계약을 먼저 못박았다 — 템플릿과 CSS 는 바뀌지 않는다.

값이 없으면 None 이다. 어디서도 0 이나 추정치로 채우지 않는다 (CLAUDE.md 1).
파생값은 조회 시 계산하고 저장하지 않는다 (CLAUDE.md 2).
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import db, derived, streak
from .config.settings import as_ymd, today_kst
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

WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

# 카테고리 제목만은 코드에 있다. field_def 에 제목 컬럼이 없고, 새 카테고리가 생기면
# 화면 배치도 같이 손봐야 하기 때문이다. 모르는 값은 그대로 보여준다.
CATEGORY_TITLES = {
    "policy_kr":    "정책·단기금리",
    "krw_rates":    "원화금리",
    "krw_futures":  "국채선물",
    "swap":         "스왑",
    "global_rates": "해외금리",
    "fx":           "FX",
    "credit":       "크레딧",
    "risk":         "리스크",
}

# 포지션 레벨 단위 환산. (관측값의 저장 단위, idea.level_unit) → 배수.
# 표에 없는 조합은 환산하지 않고 None 을 돌려준다 — 조용히 통과시키거나 100 을 곱하면
# 손익 숫자가 거짓말을 한다.
LEVEL_CONVERSION: dict[tuple[str, str], float] = {
    ("pct", "bp"):   100.0,
    ("pct", "pct"):    1.0,
    ("bp",  "bp"):     1.0,
    ("bp",  "pct"):    0.01,
    ("krw", "krw"):    1.0,
    ("jpy", "krw"):    1.0,      # USD/JPY 레벨을 그대로 쓰는 포지션
    ("index", "krw"):  1.0,
    ("futures", "krw"): 1.0,
    ("won_jeon", "krw"): 1.0,
}


# ---------------------------------------------------------------------------
# 스냅샷
# ---------------------------------------------------------------------------

def _stored_cell(
    definition: sqlite3.Row,
    obs_date: str,
    stored: dict[str, sqlite3.Row],
    previous_values: dict[str, float | None],
) -> Cell:
    key = definition["field_key"]
    row = stored.get(key)

    if row is None:
        # 미수집. 행이 없는 것이지 값이 0 인 것이 아니다.
        return Cell(
            field_key=key,
            label_short=definition["label_short"],
            unit=definition["unit"],
            decimals=definition["decimals"],
            delta_unit=definition["delta_unit"],
            auto_provider=definition["auto_provider"],
        )

    return Cell(
        field_key=key,
        label_short=definition["label_short"],
        unit=definition["unit"],
        decimals=definition["decimals"],
        delta_unit=definition["delta_unit"],
        value=row["value"],
        delta=derived.delta_in_display_unit(
            row["value"], previous_values.get(key), definition["delta_unit"]
        ),
        source=row["source"],
        auto_provider=definition["auto_provider"],
        as_of=row["obs_date"],
        stale=row["obs_date"] != obs_date,
    )


def _derived_cell(
    definition: sqlite3.Row,
    obs_date: str,
    values: dict[str, float | None],
    previous_values: dict[str, float | None],
    as_of: dict[str, str],
) -> Cell:
    key = definition["field_key"]
    spec = derived.REGISTRY.get(key)

    if spec is None:
        # field_def 는 파생이라는데 레지스트리에 없다. 추측해서 계산하지 않는다.
        return Cell(
            field_key=key,
            label_short=definition["label_short"],
            unit=definition["unit"],
            decimals=definition["decimals"],
            delta_unit=definition["delta_unit"],
            is_derived=True,
            missing_inputs=tuple((definition["derived_from"] or "").split(",")),
        )

    current = derived.compute(key, values)
    prior = derived.compute(key, previous_values)

    # 파생 delta 에 derived.delta_in_display_unit() 를 쓰면 안 된다. 그 함수의 'bp' 분기는
    # pct 로 저장된 원본을 bp 로 바꾸는 것(×100)이고, 파생값은 이미 bp 다.
    delta = None if (current is None or prior is None) else current - prior

    # 입력들의 관측일이 서로 다를 수 있다. 가장 오래된 쪽을 밝힌다 —
    # 오늘 국고 3년과 지난주 IRS 3년의 차이를 '오늘의 스프레드'라고 부르면 거짓말이다.
    input_dates = [as_of[name] for name in spec.inputs if name in as_of]

    return Cell(
        field_key=key,
        label_short=definition["label_short"],
        unit=definition["unit"],
        decimals=definition["decimals"],
        delta_unit=definition["delta_unit"],
        value=current,
        delta=delta,
        as_of=min(input_dates) if input_dates else None,
        stale=bool(input_dates) and min(input_dates) != obs_date,
        is_derived=True,
        missing_inputs=tuple(derived.missing_inputs(key, values)),
    )


def build_cells(
    conn: sqlite3.Connection, obs_date: str
) -> tuple[tuple[CellGroup, ...], dict[str, Cell]]:
    """스냅샷 셀 전체. 그룹(화면용)과 키별 조회(저장 응답용)를 함께 돌려준다."""
    definitions = db.field_defs(conn)
    stored = db.latest_on_or_before(conn, obs_date)

    # 전일 값은 필드마다 한 번만 읽는다. 저장 셀의 delta 와 파생 셀의 전일 계산이
    # 같은 값을 쓰므로 따로 읽으면 질의가 두 배가 되고 언젠가 둘이 어긋난다.
    values: dict[str, float | None] = {}
    previous_values: dict[str, float | None] = {}
    as_of: dict[str, str] = {}

    for definition in definitions:
        if definition["is_derived"]:
            continue
        key = definition["field_key"]
        row = stored.get(key)
        values[key] = row["value"] if row else None
        previous_values[key] = None
        if row is not None:
            as_of[key] = row["obs_date"]
            previous = db.previous_observation(conn, key, row["obs_date"])
            if previous is not None:
                previous_values[key] = previous["value"]

    cells: dict[str, Cell] = {}
    grouped: dict[str, list[Cell]] = {}

    for definition in definitions:
        if definition["is_derived"]:
            cell = _derived_cell(definition, obs_date, values, previous_values, as_of)
        else:
            cell = _stored_cell(definition, obs_date, stored, previous_values)
        cells[cell.field_key] = cell
        grouped.setdefault(definition["category"], []).append(cell)

    groups = tuple(
        CellGroup(category, CATEGORY_TITLES.get(category, category), tuple(items))
        for category, items in grouped.items()
    )
    return groups, cells


def affected_keys(field_key: str) -> set[str]:
    """이 필드를 고치면 같이 달라지는 셀. 파생 레지스트리가 알려 준다.

    irs_3y 를 넣으면 bond_swap_3y 가 같이 살아난다 — 화면이 그걸 즉시 보여줘야
    사용자가 '왜 아직 미수집이지' 하고 새로고침하지 않는다.
    """
    return {field_key} | {
        key for key, spec in derived.REGISTRY.items() if field_key in spec.inputs
    }


def cell_updates(
    conn: sqlite3.Connection, obs_date: str, field_key: str
) -> tuple[dict[str, Cell], dict[str, int]]:
    """저장 직후 되돌려 줄 (달라진 셀들, 상단 바 카운트).

    카운트를 본문과 같은 셀 목록에서 세는 것이 핵심이다. 따로 세면 언젠가 어긋난다.
    """
    _, cells = build_cells(conn, obs_date)
    stored = [cell for cell in cells.values() if not cell.is_derived]

    keys = affected_keys(field_key)
    updates = {key: cell for key, cell in cells.items() if key in keys}
    counts = {
        "manual_count": sum(1 for cell in stored if cell.source == "manual"),
        "miss_count": sum(1 for cell in stored if cell.status == "miss"),
    }
    return updates, counts


# ---------------------------------------------------------------------------
# 포지션
# ---------------------------------------------------------------------------

def _current_level(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    obs_date: str,
    cells: dict[str, Cell],
) -> tuple[float | None, str]:
    """(현재 레벨, 마킹 방식). 값이 없으면 None — 추정해 채우지 않는다 (SPEC 4-3)."""
    pricing_key = row["pricing_key"]

    if not pricing_key:
        mark = db.latest_mark(conn, row["id"], obs_date)
        return (mark["level"] if mark else None), "manual"

    cell = cells.get(pricing_key)
    if cell is None or cell.value is None:
        return None, "auto"

    factor = LEVEL_CONVERSION.get((cell.unit, row["level_unit"]))
    if factor is None:
        return None, "auto"     # 정의되지 않은 조합을 조용히 통과시키지 않는다
    return cell.value * factor, "auto"


def _pnl_bp(
    current: float | None, row: sqlite3.Row
) -> float | None:
    """진입 대비 손익을 bp 로. 내게 유리한 방향이 + 다."""
    if current is None:
        return None

    # 목표가 진입보다 위면 레벨 상승이 이익, 아래면 하락이 이익이다.
    direction = 1.0 if row["target_level"] >= row["entry_level"] else -1.0
    raw = (current - row["entry_level"]) * direction

    unit = row["level_unit"]
    if unit == "bp":
        return raw
    if unit == "pct":
        return raw * 100.0
    # 원화 레벨의 차이는 bp 가 아니다. 단위 없는 숫자를 만들지 않는다 (CLAUDE.md 코드 스타일).
    return None


def build_positions(
    conn: sqlite3.Connection, obs_date: str, cells: dict[str, Cell]
) -> tuple[PositionVM, ...]:
    rows = db.open_positions(conn, obs_date)
    if not rows:
        return ()

    today = date.fromisoformat(obs_date)
    order: list[int] = []
    heads: dict[int, sqlite3.Row] = {}
    conditions: dict[int, list[InvalidationVM]] = {}

    for row in rows:
        idea_id = row["id"]
        if idea_id not in heads:
            order.append(idea_id)
            heads[idea_id] = row
            conditions[idea_id] = []
        if row["inv_id"] is not None:
            conditions[idea_id].append(
                InvalidationVM(row["inv_id"], row["inv_text"], row["inv_state"])
            )

    positions: list[PositionVM] = []
    for idea_id in order:
        row = heads[idea_id]
        current, mark_mode = _current_level(conn, row, obs_date, cells)

        # idea.holding_days 는 '보유기간 목표'(001_init.sql:82)이고
        # PositionVM.holding_days 는 '진입 후 경과일 D+n'(viewmodel.py:107)이다.
        # 이름이 같고 뜻이 다르다 — 화면에는 경과일을 넣는다. 달력일 기준이다.
        elapsed = (today - date.fromisoformat(row["opened_on"])).days

        positions.append(PositionVM(
            code=row["code"],
            position=row["position"],
            strategy=row["strategy"],
            level_unit=row["level_unit"],
            entry_level=row["entry_level"],
            target_level=row["target_level"],
            stop_level=row["stop_level"],
            dv01_krw=row["dv01_krw"],
            holding_days=max(elapsed, 0),
            current_level=current,
            pnl_bp=_pnl_bp(current, row),
            flow_agent=row["flow_agent"],
            mark_mode=mark_mode,
            invalidations=tuple(conditions[idea_id]),
            id=idea_id,
        ))
    return tuple(positions)


# ---------------------------------------------------------------------------
# 나머지 패널
# ---------------------------------------------------------------------------

def build_journal(conn: sqlite3.Connection, obs_date: str) -> JournalVM:
    row = db.journal_on(conn, obs_date)
    if row is None:
        return JournalVM()
    return JournalVM(
        review_ny=row["review_ny"],
        review_ldn=row["review_ldn"],
        why_moved=row["why_moved"],
        brief_en=row["brief_en"],
    )


def build_routines(conn: sqlite3.Connection, obs_date: str) -> tuple[RoutineItem, ...]:
    return tuple(
        RoutineItem(row["key"], row["label"], row["cadence"], done=bool(row["done"]))
        for row in db.routines_for(conn, obs_date)
    )


def week_bounds(day: date) -> tuple[str, str]:
    """그 날짜가 속한 주(월~일). '이번 주 이벤트'의 범위다."""
    monday = day - timedelta(days=day.weekday())
    return as_ymd(monday), as_ymd(monday + timedelta(days=6))


def build_events(conn: sqlite3.Connection, obs_date: str) -> tuple[EventVM, ...]:
    start, end = week_bounds(date.fromisoformat(obs_date))
    return tuple(
        EventVM(
            event_date=row["event_date"],
            region=row["region"],
            name=row["name"],
            consensus=row["consensus"],
            my_expectation=row["my_expectation"],
            actual=row["actual"],
            my_call=row["my_call"],
            id=row["id"],
        )
        for row in db.events_between(conn, start, end)
    )


def build_header(
    conn: sqlite3.Connection,
    obs_date: str,
    *,
    groups: tuple[CellGroup, ...],
    routines: tuple[RoutineItem, ...],
    positions: tuple[PositionVM, ...],
    color_convention: str,
) -> HeaderVM:
    """MANUAL·MISS·미점검 수를 본문 데이터에서 센다. 상단 바가 본문과 어긋나면 안 된다."""
    day = date.fromisoformat(obs_date)
    weekday = WEEKDAYS[day.weekday()]

    cells = [cell for group in groups for cell in group.cells if not cell.is_derived]
    today_items = [
        item for item in routines
        if item.cadence in ("daily", weekday.lower())
    ]

    holidays = streak.parse_holidays(db.setting(conn, "market_holidays_kr", ""))
    complete = db.complete_streak_days(conn, obs_date)

    last = db.last_run(conn)
    finished = (last or {}).get("run", {}).get("finished_at") if last else None

    return HeaderVM(
        obs_date=obs_date,
        weekday=weekday,
        streak_days=streak.streak_days(complete, day, holidays),
        undone_today=sum(1 for item in today_items if not item.done),
        total_today=len(today_items),
        data_as_of=finished[11:16] if finished else None,
        manual_count=sum(1 for cell in cells if cell.source == "manual"),
        miss_count=sum(1 for cell in cells if cell.status == "miss"),
        unchecked_count=sum(position.unchecked_count for position in positions),
        color_convention=color_convention,
    )


def build(
    conn: sqlite3.Connection,
    *,
    obs_date: str | None = None,
    color_convention: str = "kr",
) -> DashboardVM:
    """오늘(KST)의 화면 하나. 빈 DB 에서도 예외 없이 그려져야 한다."""
    day = obs_date or as_ymd(today_kst())

    groups, cells = build_cells(conn, day)
    positions = build_positions(conn, day, cells)
    routines = build_routines(conn, day)

    return DashboardVM(
        header=build_header(
            conn, day,
            groups=groups, routines=routines, positions=positions,
            color_convention=color_convention,
        ),
        groups=groups,
        journal=build_journal(conn, day),
        routines=routines,
        events=build_events(conn, day),
        positions=positions,
    )


def routine_counts(conn: sqlite3.Connection, obs_date: str) -> dict[str, int]:
    """루틴 체크 후 상단 바에 되돌려 줄 숫자. 연속 기록도 여기서 다시 센다."""
    day = date.fromisoformat(obs_date)
    weekday = WEEKDAYS[day.weekday()].lower()

    routines = build_routines(conn, obs_date)
    today_items = [item for item in routines if item.cadence in ("daily", weekday)]

    holidays = streak.parse_holidays(db.setting(conn, "market_holidays_kr", ""))
    return {
        "streak_days": streak.streak_days(
            db.complete_streak_days(conn, obs_date), day, holidays
        ),
        "undone_today": sum(1 for item in today_items if not item.done),
        "total_today": len(today_items),
    }


def position_summary(
    conn: sqlite3.Connection, obs_date: str
) -> tuple[tuple[PositionVM, ...], int]:
    """무효화 점검 후 되돌려 줄 포지션 상태 + 오늘 미점검 조건 수."""
    _, cells = build_cells(conn, obs_date)
    positions = build_positions(conn, obs_date, cells)
    return positions, sum(position.unchecked_count for position in positions)
