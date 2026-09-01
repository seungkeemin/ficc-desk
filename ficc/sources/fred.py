"""FRED (세인트루이스 연준) API.

  https://api.stlouisfed.org/fred/series/observations
      ?series_id=DGS10&api_key=...&file_type=json
      &observation_start=YYYY-MM-DD&observation_end=YYYY-MM-DD&sort_order=desc

결측은 value 가 "." 로 온다 (미 국채 휴장일). 이는 오류가 아니라 Missing 이다.
시리즈 ID·단위는 scripts/discover_fred.py 로 확인해 config/sources.py 에 고정한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import sources as srcs
from ..config.settings import as_ymd, env
from .base import Failed, Fetched, FetchResult, Missing, get_json, to_float

BASE = "https://api.stlouisfed.org/fred"
PROVIDER = "fred"
LOOKBACK_DAYS = 14


class FredError(RuntimeError):
    pass


def api_key() -> str:
    return env("FRED_API_KEY")


def call(path: str, **params: str) -> dict:
    key = api_key()
    if not key:
        raise FredError("FRED_API_KEY 없음")
    query = {"api_key": key, "file_type": "json", **params}
    payload = get_json(f"{BASE}/{path}", params=query)
    if not isinstance(payload, dict):
        raise FredError("예상 밖 응답 구조")
    if "error_message" in payload:
        raise FredError(str(payload["error_message"]))
    return payload


def series_meta(series_id: str) -> dict:
    rows = call("series", series_id=series_id).get("seriess") or []
    return rows[0] if rows else {}


def observations(series_id: str, target: date,
                 lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    payload = call(
        "series/observations",
        series_id=series_id,
        observation_start=as_ymd(target - timedelta(days=lookback_days)),
        observation_end=as_ymd(target),
        sort_order="asc",
    )
    rows = payload.get("observations") or []
    return [row for row in rows if isinstance(row, dict)]


def fetch(field_key: str, target: date) -> FetchResult:
    spec = srcs.FRED_SERIES.get(field_key)
    if spec is None:
        return Missing(field_key, "FRED 시리즈 미확인 — 수동 입력")
    if not api_key():
        return Missing(field_key, "FRED_API_KEY 없음")

    try:
        rows = observations(spec.series_id, target)
    except FredError as exc:
        return Failed(field_key, str(exc))
    except Exception as exc:  # noqa: BLE001
        return Failed(field_key, f"{type(exc).__name__}: {exc}")

    dated: list[tuple[date, float]] = []
    for row in rows:
        value = to_float(row.get("value"))  # "." → None
        if value is None:
            continue
        try:
            obs = datetime.strptime(str(row.get("date", "")), "%Y-%m-%d").date()
        except ValueError:
            continue
        dated.append((obs, value))

    if not dated:
        return Missing(field_key, f"{spec.series_id} 최근 {LOOKBACK_DAYS}일 게시분 없음")

    obs_date, value = max(dated, key=lambda pair: pair[0])
    return Fetched(field_key, value, obs_date, PROVIDER)
