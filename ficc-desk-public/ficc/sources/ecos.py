"""한국은행 경제통계시스템(ECOS) OpenAPI.

요청 URL 형식 (경로에 값을 끼워 넣는 방식. 쿼리스트링이 아니다):

  https://ecos.bok.or.kr/api/{서비스명}/{인증키}/{json|xml}/{kr|en}
        /{요청시작건수}/{요청종료건수}/{통계표코드}/{주기}/{시작일}/{종료일}
        /{항목코드1}/{항목코드2}/{항목코드3}/{항목코드4}

  StatisticTableList  통계표목록        — 통계표코드 찾기
  StatisticItemList   통계세부항목목록  — 항목코드·단위·주기·수록기간 찾기
  StatisticSearch     통계조회          — 실제 시계열

통계표코드·항목코드는 이 파일에 적지 않는다. scripts/discover_ecos.py 로 실제
호출해 확인한 뒤 ficc/config/sources.py 에 확인 날짜와 함께 고정한다 (CLAUDE.md 3).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import sources as srcs
from ..config.settings import as_compact, env
from .base import Failed, Fetched, FetchResult, Missing, get_json, to_float

BASE = "https://ecos.bok.or.kr/api"
PROVIDER = "ecos"

# 게시 지연·연휴를 흡수할 조회 창. 이 안에서 가장 최근 게시분을 취한다 (SPEC 4-2).
LOOKBACK_DAYS = 14

# StatisticSearch 한 번에 받을 수 있는 행 수 상한. 이 수만큼 돌아오면 잘렸을
# 가능성이 있으므로 통계표 통째 조회를 믿지 않고 항목별 조회로 되돌아간다.
PAGE_LIMIT = 1000

# (통계표, 주기, 시작, 종료) → 그 창의 전체 행. 통계표 하나를 한 번만 받는다.
# 시장금리(일별)에서만 필드 12 개를 쓰는데 항목마다 호출하면 아침 수집이 그만큼
# 느려진다. 항목코드를 빼고 부르면 그 표의 전 항목이 한 번에 온다 (2026-08-11 실측:
# 817Y002 · 14일 창 = 27항목 290행). 캐시는 프로세스 안에서만 산다.
_table_cache: dict[tuple[str, str, str, str], list[dict] | None] = {}


class EcosError(RuntimeError):
    """ECOS 가 RESULT 봉투로 돌려준 오류."""


def api_key() -> str:
    return env("ECOS_API_KEY")


def call(service: str, *segments: str, start: int = 1, end: int = 100,
         lang: str = "kr") -> list[dict]:
    """서비스를 호출해 row 리스트를 돌려준다.

    데이터가 없을 때(INFO-200)는 빈 리스트, 그 외 오류는 EcosError.
    """
    key = api_key()
    if not key:
        raise EcosError("ECOS_API_KEY 없음")

    path = "/".join(
        [BASE, service, key, "json", lang, str(start), str(end), *segments]
    )
    payload = get_json(path)

    if isinstance(payload, dict) and "RESULT" in payload:
        result = payload["RESULT"]
        code = str(result.get("CODE", ""))
        message = str(result.get("MESSAGE", "")).strip()
        if code == "INFO-200":  # 해당하는 데이터 없음 — 오류가 아니다
            return []
        raise EcosError(f"{code} {message}".strip())

    body = payload.get(service) if isinstance(payload, dict) else None
    if not isinstance(body, dict):
        raise EcosError(f"예상 밖 응답 구조: {list(payload)[:5]}")
    rows = body.get("row") or []
    return [row for row in rows if isinstance(row, dict)]


def table_rows(stat_code: str, cycle: str, start: str, end: str) -> list[dict] | None:
    """통계표 전체(항목 무관)를 한 번 받아 캐시한다. 상한에 걸렸으면 None.

    None 은 '데이터 없음'이 아니라 '이 방법을 믿지 마라'는 뜻이다. 잘린 응답에서
    항목을 골라내면 값이 없는 것처럼 보이는 필드가 생긴다.
    """
    key = (stat_code, cycle, start, end)
    if key not in _table_cache:
        rows = call("StatisticSearch", stat_code, cycle, start, end,
                    start=1, end=PAGE_LIMIT)
        _table_cache[key] = None if len(rows) >= PAGE_LIMIT else rows
    return _table_cache[key]


def search(spec: "srcs.EcosSeries", target: date,
           lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    """[target-lookback, target] 구간의 시계열 행."""
    start = as_compact(target - timedelta(days=lookback_days))
    end = as_compact(target)
    codes = [code for code in spec.item_codes if code]

    # 항목이 하나면 통계표 통째 조회(캐시)에서 골라 쓴다. 다차원 항목은 서버가
    # 조합을 걸러 주는 쪽이 정확하므로 그대로 항목별로 부른다.
    if len(codes) == 1:
        cached = table_rows(spec.stat_code, spec.cycle, start, end)
        if cached is not None:
            return [row for row in cached if row.get("ITEM_CODE1") == codes[0]]

    segments = [spec.stat_code, spec.cycle, start, end, *codes]
    return call("StatisticSearch", *segments, start=1, end=200)


def fetch(field_key: str, target: date) -> FetchResult:
    """필드 하나를 수집한다. 예외를 밖으로 내지 않는다."""
    spec = srcs.ECOS_SERIES.get(field_key)
    if spec is None:
        return Missing(field_key, "ECOS 코드 미확인 — 수동 입력")
    if not api_key():
        return Missing(field_key, "ECOS_API_KEY 없음")

    try:
        rows = search(spec, target)
    except EcosError as exc:
        return Failed(field_key, str(exc))
    except Exception as exc:  # noqa: BLE001
        return Failed(field_key, f"{type(exc).__name__}: {exc}")

    dated: list[tuple[date, float]] = []
    for row in rows:
        obs = parse_time(str(row.get("TIME", "")), spec.cycle)
        value = to_float(row.get("DATA_VALUE"))
        if obs is not None and value is not None:
            dated.append((obs, value))

    if not dated:
        return Missing(field_key, f"{spec.stat_code} 최근 {LOOKBACK_DAYS}일 게시분 없음")

    obs_date, value = max(dated, key=lambda pair: pair[0])
    return Fetched(field_key, value, obs_date, PROVIDER)


def parse_time(raw: str, cycle: str) -> date | None:
    """ECOS 의 TIME 문자열을 날짜로. 주기마다 자릿수가 다르다."""
    text = raw.strip()
    try:
        if cycle == "D" and len(text) == 8:
            return datetime.strptime(text, "%Y%m%d").date()
        if cycle == "M" and len(text) == 6:  # 월 자료는 그 달 1일로 둔다
            return datetime.strptime(text + "01", "%Y%m%d").date()
        if cycle == "A" and len(text) == 4:
            return date(int(text), 12, 31)
        if len(text) == 8:
            return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None
    return None
