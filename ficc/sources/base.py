"""수집 결과 타입과 HTTP 헬퍼.

CLAUDE.md 6: 수집 실패는 정상 상황이다. 한 소스가 죽어도 전체가 죽지 않는다.
그래서 소스 함수는 예외를 밖으로 던지지 않고 아래 세 가지 중 하나를 반환한다.

  Fetched — 값을 받았다. obs_date 는 '오늘'이 아니라 그 값의 실제 관측일이다.
  Missing — 소스는 정상 응답했지만 그 날짜에 값이 없다 (휴장일, 미게시).
  Failed  — 호출 자체가 실패했다 (키 없음, 타임아웃, 4xx/5xx, 파싱 불가).

Missing 과 Failed 를 섞지 않는 것이 중요하다. 화면에서 "왜 이 필드가 비었는가"를
설명하려면 '아직 안 나온 값'과 '내 수집기가 고장난 것'이 구분돼야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(15.0, connect=10.0)
RETRIES = 1


@dataclass(frozen=True)
class Fetched:
    field_key: str
    value: float
    obs_date: date
    provider: str
    note: str | None = None


@dataclass(frozen=True)
class Missing:
    field_key: str
    reason: str


@dataclass(frozen=True)
class Failed:
    field_key: str
    message: str


FetchResult = Fetched | Missing | Failed


def get_json(url: str, *, headers: dict[str, str] | None = None,
             params: dict[str, Any] | None = None) -> Any:
    """GET → JSON. 1회 재시도. 실패는 예외로 던지고 호출자가 Failed 로 변환한다."""
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # noqa: BLE001 - 경계에서 전부 잡는 것이 의도다
            last = exc
            if attempt == RETRIES:
                break
    raise RuntimeError(_describe(last))


def _describe(exc: Exception | None) -> str:
    if exc is None:
        return "알 수 없는 오류"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "타임아웃"
    if isinstance(exc, httpx.TransportError):
        return f"연결 실패: {type(exc).__name__}"
    return f"{type(exc).__name__}: {exc}"


def to_float(raw: Any) -> float | None:
    """소스가 주는 문자열 값을 float 로. 결측 표기는 None 으로 돌려준다.

    FRED 는 결측을 '.' 로, ECOS 는 빈 문자열이나 '-' 로 준다.
    0 으로 채우지 않는다 (CLAUDE.md 1).
    """
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if text in {"", ".", "-", "NA", "N/A", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
