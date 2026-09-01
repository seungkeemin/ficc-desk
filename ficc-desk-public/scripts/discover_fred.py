"""FRED 시리즈 메타 확인 (단위·주기·최종갱신·게시 지연).

시리즈 ID 는 알려져 있지만 단위와 갱신 지연은 실제로 확인해야 한다 (SPEC §6).

  python scripts/discover_fred.py                채택한 시리즈 전부
  python scripts/discover_fred.py DGS10 DEXJPUS  지정한 시리즈만
  python scripts/discover_fred.py --rejected     확인하고 안 쓴 시리즈
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ficc.config.settings import today_kst  # noqa: E402
from ficc.sources import fred  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CANDIDATES = {
    "ust_3m": "DGS3MO",
    "ust_2y": "DGS2",
    "ust_5y": "DGS5",
    "ust_10y": "DGS10",
    "ust_30y": "DGS30",
    "sofr": "SOFR",
    "ff_target_upper": "DFEDTARU",
    "us_bei_10y": "T10YIE",
    "us_ig_oas": "BAMLC0A0CM",
    "us_hy_oas": "BAMLH0A0HYM2",
    "usdjpy": "DEXJPUS",
    "eurusd": "DEXUSEU",
    "vix": "VIXCLS",
}

# 확인만 하고 채택하지 않은 것들. 다시 조사하지 않으려고 남긴다 —
# 이유는 ficc/config/sources.py 의 FRED_SERIES 주석에 있다.
REJECTED = ("DCOILBRENTEU", "DCOILWTICO", "DTWEXBGS", "DFII10", "DEXCHUS", "EFFR")


def main(argv: list[str]) -> int:
    if not fred.api_key():
        print("FRED_API_KEY 없음. .env 를 채워라.")
        return 2

    if argv and argv[0] == "--rejected":
        series_ids = list(REJECTED)
    else:
        series_ids = argv or list(CANDIDATES.values())
    today = today_kst()
    for series_id in series_ids:
        try:
            meta = fred.series_meta(series_id)
        except Exception as exc:  # noqa: BLE001
            print(f"{series_id:<10} 오류: {exc}")
            continue

        print(f"\n{series_id}")
        print(f"  title        {meta.get('title','')}")
        print(f"  units        {meta.get('units','')} ({meta.get('units_short','')})")
        print(f"  frequency    {meta.get('frequency','')}")
        print(f"  last_updated {meta.get('last_updated','')}")
        print(f"  range        {meta.get('observation_start','')}"
              f" ~ {meta.get('observation_end','')}")

        rows = fred.observations(series_id, today)
        usable = [r for r in rows if str(r.get("value")) != "."]
        print(f"  최근 14일 {len(rows)}건 중 값 있는 행 {len(usable)}건")
        for row in rows[-5:]:
            print(f"    {row.get('date','')}  {row.get('value','')}")
        if usable:
            gap = (today - __import__("datetime").datetime.strptime(
                usable[-1]["date"], "%Y-%m-%d").date()).days
            print(f"  최신 관측일 {usable[-1]['date']} → 오늘({today}) 기준 지연 {gap}일")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
