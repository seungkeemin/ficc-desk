"""BoE IADB 확인 — gilt 곡선·SONIA·정책금리.

  python scripts/discover_boe.py           확정 코드 현재 상태
  python scripts/discover_boe.py titles    코드의 공식 제목 재확인

확인 2026-08-11 (실호출):

  IADB 는 CSV 를 준다. 단 **UsingCodes=N 은 CSV 가 아니라 HTML 을 돌려준다** —
  제목을 받으려면 CSV 가 아니라 화면(HTML)에서 뽑아야 한다. 그래서 titles 모드가
  따로 있다. 코드가 값을 돌려준다는 것과 그 값이 무엇인지는 다른 문제다 (CLAUDE.md 3).

  게시 지연: **최소 T+2**. 08-11(화) 런던 14:16 과 14:33 두 번 모두 최신이
  08-07(금)이었다. 월요일치가 화요일 오후까지 안 올라온다. 따라서 22:00 KST
  (= 런던 14:00) 수집 창은 gilt 를 잡지 못한다. 07:00 KST (= 전날 런던 23:00)
  창이 잡는지는 **확인 필요** — 그 시각대 관측이 아직 없다.

  IUDBEDR 만 08-10 이 있었는데 정책금리라 값이 매일 이월되기 때문이지
  신선해서가 아니다.

  존재하지 않는 코드로 확인된 것: IUAAMNPY, IUMAJNB (빈 응답).
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from ficc.config.settings import today_kst  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSV_URL = "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
HTML_URL = "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"
UA = {"User-Agent": "ficc-desk-discovery"}
TIMEOUT = httpx.Timeout(40.0, connect=15.0)

# 확인 2026-08-11 · 제목은 IADB 화면에서 그대로 옮겼다 · 괄호는 그날 받은 값.
CODES: dict[str, str] = {
    "IUDSNZC": "British Government Securities 5y Nominal Zero Coupon  (4.4396, 08-07)",
    "IUDMNZC": "British Government Securities 10y Nominal Zero Coupon (4.9945, 08-07)",
    "IUDLNPY": "British Government Securities 20y Nominal Par Yield   (5.4311, 08-07)",
    "IUDSOIA": "Daily Sterling overnight index average (SONIA) rate   (3.7318, 08-07)",
    "IUDBEDR": "Official Bank Rate                                    (3.75,   08-10)",
}

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def date_range() -> tuple[str, str]:
    today = today_kst()
    start = today.replace(day=1)
    return (f"{start:%d/%b/%Y}", f"{today:%d/%b/%Y}")


def show_current(client: httpx.Client) -> None:
    start, end = date_range()
    print(f"오늘(KST) {today_kst()} · 조회 {start} ~ {end}\n")
    for code, label in CODES.items():
        params = {
            "csv.x": "yes", "Datefrom": start, "Dateto": end,
            "SeriesCodes": code, "CSVF": "TN", "UsingCodes": "Y",
            "VPD": "Y", "VFD": "N",
        }
        try:
            response = client.get(CSV_URL, params=params)
        except Exception as exc:  # noqa: BLE001
            print(f"  {code:<10} 실패: {type(exc).__name__}: {exc}")
            continue
        lines = [ln for ln in response.text.strip().splitlines() if ln.strip()]
        if len(lines) < 2 or "DATE" not in lines[0].upper():
            head = lines[0][:60] if lines else "(빈 응답)"
            print(f"  {code:<10} 데이터 아님 — {head}")
            continue
        last = lines[-1].split(",")
        print(f"  {code:<10} 최신 {last[0]:<14} = {last[-1]:<10} ({len(lines)-1}행)")
        print(f"  {'':<10} {label}")


def text_of(fragment: str) -> str:
    return WS.sub(" ", html.unescape(TAG.sub(" ", fragment))).strip()


def show_titles(client: httpx.Client) -> None:
    """공식 제목은 CSV 가 아니라 HTML 화면에만 있다."""
    print("코드가 실제로 무엇인지 IADB 화면에서 확인한다.\n")
    for code in CODES:
        params = {
            "Travel": "NIxSUx", "FromSeries": "1", "ToSeries": "50",
            "DAT": "RNG", "FD": "1", "FM": "Aug", "FY": "2026",
            "TD": "11", "TM": "Aug", "TY": "2026",
            "CSVF": "TT", "html.x": "66", "html.y": "26",
            "SeriesCodes": code, "UsingCodes": "Y",
            "Filter": "N", "title": code, "VPD": "Y",
        }
        try:
            response = client.get(HTML_URL, params=params)
        except Exception as exc:  # noqa: BLE001
            print(f"  {code:<10} 실패: {type(exc).__name__}: {exc}")
            continue
        found = ""
        for match in re.finditer(r"<t[hd][^>]*>(.*?)</t[hd]>", response.text,
                                 re.S | re.I):
            cell = text_of(match.group(1))
            if code in cell and len(cell) > len(code) + 8:
                found = cell
                break
        print(f"  {code:<10} {found or '(제목 못 찾음)'}"[:140])


def main(argv: list[str]) -> int:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers=UA) as client:
        if argv and argv[0] == "titles":
            show_titles(client)
        else:
            show_current(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
