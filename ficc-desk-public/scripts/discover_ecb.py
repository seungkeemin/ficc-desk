"""ECB Data Portal 확인 — 유로존 수익률곡선·환율·정책금리.

FRED 에는 유럽 국채금리가 **일별로 없다**. frequency=Daily 로 거른 검색이
0건이고 OECD 월별 시리즈만 존재하며 그것도 게시가 6주 늦다 (확인 2026-08-11).
ECB Data Portal 은 같은 것을 일별로 낸다. 인증키가 필요 없다.

  python scripts/discover_ecb.py           확정 시리즈 현재 상태
  python scripts/discover_ecb.py timing    게시 시각 구간 좁히기

확인 2026-08-11 (실호출):

  게시 지연 **1일**, 게시 시각 **19:00~21:00 KST**.
  updatedAfter=2026-08-11T10:00Z 는 08-10 관측을 돌려주고 12:00Z 는 0건이었다.
  즉 D 일 곡선은 D+1 일 저녁에 올라온다. 07:00·16:00 수집 창에서는 항상
  2영업일 전 값이 최신이다. 이 시차는 게시 지연이지 시간대 차이가 아니다 —
  프랑크푸르트에서 봐도 같은 간격이다.

  같은 날 분데스방크 연방채 10Y 는 3.19, ECB AAA 10Y 는 3.1993 으로 1bp 안에서
  일치했다. 두 기관의 서로 다른 적합 모형이 같은 값을 낸다 (scripts/discover_bbk.py).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from ficc.config.settings import today_kst  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://data-api.ecb.europa.eu/service/data"
UA = {"User-Agent": "ficc-desk-discovery"}
TIMEOUT = httpx.Timeout(40.0, connect=15.0)
KST = timezone(timedelta(hours=9))

# 확인 2026-08-11 · 괄호 안은 그날 받은 08-10 관측치.
SERIES: dict[str, tuple[str, str]] = {
    "AAA 국채 3M   (2.3182)": ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_3M"),
    "AAA 국채 2Y   (2.7208)": ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"),
    "AAA 국채 10Y  (3.1993)": ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"),
    "AAA 국채 30Y  (3.6502)": ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y"),
    # 전체 국채 - AAA 가 주변국 스프레드다. 08-10 기준 3.6077 - 3.1993 = 41bp.
    "전체 국채 10Y (3.6077)": ("YC", "B.U2.EUR.4F.G_N_C.SV_C_YM.SR_10Y"),
    "EUR/USD       (1.1555)": ("EXR", "D.USD.EUR.SP00.A"),
    "EUR/GBP       (0.85565)": ("EXR", "D.GBP.EUR.SP00.A"),
    # 정책금리는 매일 같은 값이 이월된다. 지연 0일이지만 신선한 게 아니다.
    "ECB MRO       (2.40)": ("FM", "D.U2.EUR.4F.KR.MRR_FR.LEV"),
    "ECB 예금금리  (2.25)": ("FM", "D.U2.EUR.4F.KR.DFR.LEV"),
}

TIMING_KEY = ("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y")


def observations(client: httpx.Client, flow: str, key: str,
                 **params: str) -> list[tuple[str, str]]:
    """(관측일, 값) 목록. 404 는 '해당 없음'이므로 빈 목록이다."""
    response = client.get(f"{BASE}/{flow}/{key}",
                          params={"format": "csvdata", **params})
    if response.status_code == 404:
        return []
    response.raise_for_status()
    lines = [ln for ln in response.text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split(",")
    i_date, i_value = header.index("TIME_PERIOD"), header.index("OBS_VALUE")
    rows = []
    for line in lines[1:]:
        cells = line.split(",")
        if len(cells) > max(i_date, i_value):
            rows.append((cells[i_date], cells[i_value]))
    return rows


def show_current(client: httpx.Client) -> None:
    today = today_kst()
    print(f"오늘(KST) {today}\n")
    for label, (flow, key) in SERIES.items():
        try:
            rows = observations(client, flow, key, lastNObservations="4")
        except Exception as exc:  # noqa: BLE001
            print(f"  {label:<24} 실패: {type(exc).__name__}: {exc}")
            continue
        if not rows:
            print(f"  {label:<24} 관측 없음")
            continue
        obs_date, value = rows[-1]
        try:
            gap = (today - datetime.strptime(obs_date, "%Y-%m-%d").date()).days
            gap_text = f"지연 {gap}일"
        except ValueError:
            gap_text = ""
        print(f"  {label:<24} 최신 {obs_date} = {value:<14} {gap_text}")


def show_timing(client: httpx.Client) -> None:
    """updatedAfter 로 게시 시각을 좁힌다. 건수가 0 으로 꺾이는 지점이 게시 시각."""
    flow, key = TIMING_KEY
    now = datetime.now(timezone.utc)
    print(f"지금 KST {now.astimezone(KST):%Y-%m-%d %H:%M}")
    print(f"대상 {flow}/{key}\n")
    for hours_ago in (36, 30, 24, 18, 14, 12, 10, 8, 6, 4, 2):
        moment = now - timedelta(hours=hours_ago)
        stamp = f"{moment:%Y-%m-%dT%H:%M:%S}Z"
        try:
            rows = observations(client, flow, key, updatedAfter=stamp)
        except Exception as exc:  # noqa: BLE001
            print(f"  {stamp}  오류: {type(exc).__name__}: {exc}")
            continue
        tail = ", ".join(f"{d}={v[:6]}" for d, v in rows[-2:]) or "(없음)"
        print(f"  {stamp} = KST {moment.astimezone(KST):%m-%d %H:%M}"
              f"  → {len(rows):>3}건  {tail}")
    print("\n  건수가 0 으로 꺾이는 구간이 게시 시각이다.")
    print("  2026-08-11 확인: 10:00Z 는 08-10 관측 있음, 12:00Z 는 0건")
    print("  → 게시 19:00~21:00 KST")


def main(argv: list[str]) -> int:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers=UA) as client:
        if argv and argv[0] == "timing":
            show_timing(client)
        else:
            show_current(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
