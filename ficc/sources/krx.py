"""KRX Data Marketplace OPEN API — 국채선물.

  GET https://data-dbg.krx.co.kr/svc/apis/drv/fut_bydd_trd?basDd=YYYYMMDD
  Header: AUTH_KEY: <인증키>
  Response: {"OutBlock_1": [ {BAS_DD, PROD_NM, MKT_NM, ISU_CD, ISU_NM,
                              TDD_CLSPRC, CMPPREVDD_PRC, ..., ACC_TRDVOL, ...}, ... ]}

확인 근거는 ficc/config/sources.py 주석에 남긴다.

이 API 는 '일별' 매매정보라 장중 값이 아니다. 당일 종가는 장 마감 뒤에 올라오고,
휴장일에는 행이 0건이다. 그래서 target 부터 하루씩 거슬러 올라가며 행이 있는
가장 최근 영업일을 찾는다 (SPEC 4-2).

PROD_NM 은 **정확히 일치**시킨다. 부분일치를 쓰면 '10년국채 선물' 이 '30년국채 선물' 과
한 글자 차이라 위험하고, 별개 상품인 '3년-10년국채선물스프레드 선물' 도 있다.

한 PROD_NM 안에는 결제월이 다른 종목과 캘린더 스프레드(ISU_NM 에 'SP')가 섞여 나온다.
최근월물이 유동성을 독점하므로 거래량(ACC_TRDVOL) 최대 행을 고르면 그것만 남는다.
같은 종목이 정규장·야간장 두 줄로 오는데, 정산가(SETL_PRC)가 붙는 정규장이 공식 종가다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import sources as srcs
from ..config.settings import as_compact, env
from .base import Failed, Fetched, FetchResult, Missing, get_json, to_float

BASE = "https://data-dbg.krx.co.kr/svc/apis"
PROVIDER = "krx"
LOOKBACK_DAYS = 10

_cache: dict[tuple[str, str], list[dict]] = {}


class KrxError(RuntimeError):
    pass


def auth_key() -> str:
    return env("KRX_AUTH_KEY")


def call(endpoint: str, bas_dd: str) -> list[dict]:
    key = auth_key()
    if not key:
        raise KrxError("KRX_AUTH_KEY 없음")

    cached = _cache.get((endpoint, bas_dd))
    if cached is not None:
        return cached

    payload = get_json(
        f"{BASE}/{endpoint}",
        headers={"AUTH_KEY": key},
        params={"basDd": bas_dd},
    )
    if not isinstance(payload, dict):
        raise KrxError("예상 밖 응답 구조")
    rows = payload.get("OutBlock_1")
    if rows is None:
        raise KrxError(f"OutBlock_1 없음: {list(payload)[:5]}")
    rows = [row for row in rows if isinstance(row, dict)]
    _cache[(endpoint, bas_dd)] = rows
    return rows


def is_calendar_spread(row: dict) -> bool:
    """ISU_NM 에 ' SP ' 토큰이 있으면 캘린더 스프레드 종목이다 (단일 결제월은 ' F ')."""
    return "SP" in str(row.get("ISU_NM", "")).split()


def rows_for_latest_session(endpoint: str, target: date,
                            lookback_days: int = LOOKBACK_DAYS
                            ) -> tuple[date, list[dict]] | None:
    """행이 존재하는 가장 최근 영업일과 그 행들."""
    for back in range(lookback_days + 1):
        day = target - timedelta(days=back)
        if day.weekday() >= 5:  # 토·일은 호출하지 않는다
            continue
        rows = call(endpoint, as_compact(day))
        if rows:
            return day, rows
    return None


def fetch(field_key: str, target: date) -> FetchResult:
    spec = srcs.KRX_SERIES.get(field_key)
    if spec is None:
        return Missing(field_key, "KRX 엔드포인트 미확인 — 수동 입력")
    if not auth_key():
        return Missing(field_key, "KRX_AUTH_KEY 없음")

    try:
        found = rows_for_latest_session(spec.endpoint, target)
    except KrxError as exc:
        return Failed(field_key, str(exc))
    except Exception as exc:  # noqa: BLE001
        return Failed(field_key, f"{type(exc).__name__}: {exc}")

    if found is None:
        return Missing(field_key, f"최근 {LOOKBACK_DAYS}일 영업일 데이터 없음")

    session, rows = found
    # 캘린더 스프레드 행은 거래량 비교 전에 뺀다. 롤오버 주간에는 스프레드 거래량이
    # 최근월물보다 커서, 빼지 않으면 스프레드 가격이 선물 종가로 저장된다
    # (2026-09-10·11·14 실측: ISU_NM '3년국채    SP 2609-2612 (주간)').
    matched = [
        row for row in rows
        if str(row.get("PROD_NM", "")).strip() == spec.product_name
        and str(row.get("MKT_NM", "")).strip() in {"", "정규"}
        and not is_calendar_spread(row)
    ]
    if not matched:
        return Missing(field_key, f"{session} 행 중 '{spec.product_name}' 없음")

    front = max(matched, key=lambda row: to_float(row.get("ACC_TRDVOL")) or 0.0)
    value = to_float(front.get(spec.value_field))
    if value is None:
        return Missing(field_key, f"{spec.value_field} 값 없음 ({front.get('ISU_NM','')})")

    bas_dd = str(front.get("BAS_DD", "")).strip()
    try:
        obs_date = datetime.strptime(bas_dd, "%Y%m%d").date()
    except ValueError:
        obs_date = session

    return Fetched(field_key, value, obs_date, PROVIDER,
                   note=str(front.get("ISU_NM", "")).strip() or None)
