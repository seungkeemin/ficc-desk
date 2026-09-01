"""화면이 소비하는 모양. Phase 2 와 Phase 3 사이의 계약이다.

여기에는 데이터클래스만 있고 로직이 없다. Phase 2 는 ficc/demo.py 가,
Phase 3 은 DB 빌더가 같은 DashboardVM 을 만들어 같은 템플릿에 넘긴다.
템플릿이 이 모양에만 의존하면 데이터 연결은 빌더 교체 한 번으로 끝난다.

값이 없는 것과 0 은 다르다 (CLAUDE.md 1). 그래서 수치 필드는 전부 `float | None`
이고, 템플릿은 None 을 '미수집' / '—' 로 그린다. 어디서도 0 으로 채우지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CellStatus = Literal["ok", "miss"]
CheckState = Literal["valid", "shaky", "broken"]
MarkMode = Literal["auto", "manual"]


@dataclass(frozen=True)
class Cell:
    """스냅샷 셀 하나. field_def 한 행 + 그 날짜의 관측값."""

    field_key: str
    label_short: str
    unit: str
    decimals: int
    delta_unit: str
    value: float | None = None
    delta: float | None = None          # 이미 delta_unit 으로 환산된 값
    source: str | None = None           # 'auto' | 'manual' | None(미수집)
    auto_provider: str | None = None    # None 이면 자동 수집 불가 필드 → 화면 ⓘ
    as_of: str | None = None            # 값의 실제 관측일
    stale: bool = False                 # as_of 가 화면 날짜보다 이전이면 True
    is_derived: bool = False
    missing_inputs: tuple[str, ...] = ()  # 파생값이 계산 안 된 이유

    @property
    def status(self) -> CellStatus:
        return "ok" if self.value is not None else "miss"


@dataclass(frozen=True)
class CellGroup:
    """스냅샷의 카테고리 묶음. field_def.category 하나에 대응한다."""

    category: str
    title: str
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class JournalVM:
    """journal 테이블 한 행. 빈 칸은 None — 빈 문자열과 구분한다."""

    review_ny: str | None = None
    review_ldn: str | None = None
    why_moved: str | None = None
    brief_en: str | None = None


@dataclass(frozen=True)
class RoutineItem:
    key: str
    label: str
    cadence: str
    done: bool = False


@dataclass(frozen=True)
class EventVM:
    event_date: str
    region: str
    name: str
    consensus: str | None = None
    my_expectation: str | None = None
    actual: str | None = None
    my_call: str | None = None          # 'hit' | 'miss' | 'partial' | None
    # 인라인 수정의 대상. demo 픽스처는 None 이라 입력창 없이 레이아웃만 확인한다.
    # 새 필드는 반드시 맨 끝에 기본값으로 붙인다 — 앞에 넣으면 demo 의 위치 인자가 어긋난다.
    id: int | None = None


@dataclass(frozen=True)
class InvalidationVM:
    """무효화 조건 1건. state 가 None 이면 오늘 아직 점검하지 않았다는 뜻이다."""

    id: int
    text: str
    state: CheckState | None = None

    @property
    def checked_today(self) -> bool:
        return self.state is not None


@dataclass(frozen=True)
class PositionVM:
    """활성 포지션 1건. 블로터 행이자 무효화 워치 블록의 머리다."""

    code: str
    position: str
    strategy: str                       # 'momentum' | 'mean_reversion'
    level_unit: str
    entry_level: float
    target_level: float
    stop_level: float
    dv01_krw: float
    holding_days: int                   # 진입 후 경과일 (D+n)
    current_level: float | None = None  # 마킹 불가면 None → 손익도 None
    pnl_bp: float | None = None
    flow_agent: str | None = None
    mark_mode: MarkMode = "auto"
    invalidations: tuple[InvalidationVM, ...] = ()
    id: int | None = None               # 수동 마킹 저장 대상. 규칙은 EventVM.id 와 같다

    @property
    def worst_state(self) -> CheckState | None:
        """가장 나쁜 점검 상태. 블로터 행과 워치 블록의 경고색을 이걸로 켠다."""
        for level in ("broken", "shaky", "valid"):
            if any(item.state == level for item in self.invalidations):
                return level  # type: ignore[return-value]
        return None

    @property
    def unchecked_count(self) -> int:
        return sum(1 for item in self.invalidations if not item.checked_today)


@dataclass(frozen=True)
class HeaderVM:
    obs_date: str                       # 'YYYY-MM-DD'
    weekday: str                        # 'TUE'
    streak_days: int                    # 숫자만 표시한다. 게임화하지 않는다.
    undone_today: int
    total_today: int
    data_as_of: str | None = None       # 마지막 수집 시각 'HH:MM'
    manual_count: int = 0
    miss_count: int = 0
    unchecked_count: int = 0            # 오늘 미점검 무효화 조건 수
    color_convention: str = "kr"        # 'kr' | 'bbg'


@dataclass(frozen=True)
class DashboardVM:
    header: HeaderVM
    groups: tuple[CellGroup, ...] = ()
    journal: JournalVM = field(default_factory=JournalVM)
    routines: tuple[RoutineItem, ...] = ()
    events: tuple[EventVM, ...] = ()
    positions: tuple[PositionVM, ...] = ()
