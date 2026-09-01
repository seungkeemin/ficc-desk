"""연속 기록 일수.

SPEC 4-7: 한국 영업일 기준으로만 세고, 휴장일은 app_setting.market_holidays_kr 의
수동 목록으로 관리한다. counts_streak = 1 인 일간 항목이 전부 완료된 날만 센다.
**게임화하지 않는다** — 화면은 이 숫자만 보여주고 배지도 축하도 경고도 없다.

완료된 날 집합은 SQL 이 뽑고(db.complete_streak_days), 달력 역주행은 여기 순수 함수가 한다.
휴장일이 쉼표 구분 문자열 한 칸이라 SQL 로 파싱하면 손으로 쓴 SQL 이 아니라 손으로 쓴
파서가 되고, '행이 아예 없는 날'에서 끊는 규칙은 날짜 시리즈 생성을 요구한다.
하루 5행 규모라 성능 논거도 없다.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .config.settings import as_ymd, canonical_date

# 영업일 약 4년. 휴장일 목록이 이상해도 화면이 멈추지 않게 하는 안전장치다.
MAX_SCAN = 1000


def parse_holidays(raw: str) -> frozenset[str]:
    """'2026-01-01, 2026-03-01' → {'2026-01-01', '2026-03-01'}.

    빈 문자열은 빈 집합이다 — split(',') 의 [''] 가 날짜 하나로 새지 않게 한다.
    """
    return frozenset(
        canonical_date(part) for part in re.split(r"[,\s]+", raw.strip()) if part
    )


def is_business_day(day: date, holidays: frozenset[str]) -> bool:
    return day.weekday() < 5 and as_ymd(day) not in holidays


def streak_days(
    complete: set[str], today: date, holidays: frozenset[str] = frozenset()
) -> int:
    """오늘까지 연속으로 완료된 영업일 수. 오늘은 완료됐을 때만 센다.

    오늘이 아직 미완료여도 0 으로 떨어뜨리지 않는다. 07:00 에는 무엇도 완료가 아니고,
    오늘을 끊김으로 치면 하루의 대부분을 D+0 으로 표시하다 저녁에 튀어오른다.
    매일 아침 0 으로 리셋되는 표시는 형태만 다른 연속 끊김 경고다 (CLAUDE.md UI 규칙).

    예외는 오늘 하루뿐이다 — 이미 끝난 영업일이 미완료면 그 자리에서 끊긴다.
    주말과 휴장일은 건너뛴다(끊지 않는다).
    """
    if not complete:
        return 0                       # 첫 실행. routine_log 가 비어 있으면 0 이다

    earliest = min(complete)
    count = 0
    day = today
    scanned = 0

    while scanned < MAX_SCAN:
        key = as_ymd(day)
        if key < earliest and day != today:
            break                      # 더 과거에 완료일이 존재할 수 없다
        if is_business_day(day, holidays):
            if key in complete:
                count += 1
            elif day == today:
                pass                   # 오늘만 '진행 중' 으로 봐준다
            else:
                break
            scanned += 1
        day -= timedelta(days=1)

    return count
