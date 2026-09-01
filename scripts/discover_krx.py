"""KRX 국채선물 상품명·필드 확인 (일회성 조사용).

엔드포인트와 응답 필드는 openapi.krx.co.kr 의 '선물 일별매매정보(주식선물外)'
명세 + 샘플 호출로 확인했다. 남은 것은 실제 응답에서 국채선물의 PROD_NM 표기와
최근월물 판별이며, 그건 인증키로 실제 호출해야 알 수 있다.

  python scripts/discover_krx.py               최근 영업일 전 상품 목록
  python scripts/discover_krx.py 20260807      특정 일자
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ficc.config.settings import today_kst  # noqa: E402
from ficc.sources import krx  # noqa: E402
from ficc.sources.base import to_float  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENDPOINT = "drv/fut_bydd_trd"


def main(argv: list[str]) -> int:
    if not krx.auth_key():
        print("KRX_AUTH_KEY 없음. .env 를 채워라.")
        return 2

    try:
        if argv:
            rows = krx.call(ENDPOINT, argv[0])
            session = argv[0]
        else:
            found = krx.rows_for_latest_session(ENDPOINT, today_kst())
            if found is None:
                print("최근 10일 안에 데이터가 있는 영업일이 없다.")
                return 1
            day, rows = found
            session = str(day)
    except Exception as exc:  # noqa: BLE001
        print(f"KRX 오류: {type(exc).__name__}: {exc}")
        return 1

    print(f"기준일 {session} · {len(rows)}행")
    if not rows:
        print("  (행 없음 — 휴장일이거나 미게시)")
        return 0

    print(f"응답 필드: {sorted(rows[0])}\n")

    products = sorted({str(r.get("PROD_NM", "")) for r in rows})
    print(f"--- PROD_NM {len(products)}종 ---")
    for name in products:
        count = sum(1 for r in rows if str(r.get("PROD_NM", "")) == name)
        print(f"  {name}  ({count}행)")

    print("\n--- 국채선물 후보 행 ---")
    for row in rows:
        prod = str(row.get("PROD_NM", ""))
        if "국채" not in prod and "국고" not in prod:
            continue
        volume = to_float(row.get("ACC_TRDVOL"))
        print(f"  PROD_NM={prod!r}  MKT={row.get('MKT_NM','')!r}  "
              f"ISU_NM={row.get('ISU_NM','')!r}  ISU_CD={row.get('ISU_CD','')}\n"
              f"     종가={row.get('TDD_CLSPRC','') or '-':<8} "
              f"대비={row.get('CMPPREVDD_PRC','') or '-':<7} "
              f"정산가={row.get('SETL_PRC','') or '-':<8} "
              f"거래량={f'{volume:,.0f}' if volume is not None else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
