"""분데스방크 확인 — 독일 연방채 수익률곡선 (BBSIS).

  python scripts/discover_bbk.py           확정 시리즈 현재 상태
  python scripts/discover_bbk.py dims      DSD 차원·코드 재확인

**키 없이 호출하지 마라.** 확인 중에 /data/BBSIS 를 키 없이 불렀다가 701MB 를
받았다. lastNObservations 를 붙여도 줄지 않는다 (시리즈 수가 많은 것이지 관측
수가 많은 게 아니다). 반드시 차원을 채운 키로 부른다.

확인 2026-08-11 (실호출):

  게시 지연 **0일**. 프랑크푸르트 15:50 시점에 당일(08-11) 값 3.26 이 이미
  있었고 OBS_STATUS 플래그가 비어 있었다 — 코드리스트에 P(잠정)·E(추정)·
  R(수정)이 정의돼 있는데 어느 것도 안 붙었다. 주말은 status=K 로 값이 없다.

  이게 중요한 이유: FRED·ECB·BoE 는 전부 D 일 값을 D+1 에 낸다. 그래서 07:00 KST
  아침 리뷰 시점에 최신이 2영업일 전이었다. 분데스방크는 D 일 값을 D 일에 내므로
  **다음날 07:00 에 전날 세션 값이 이미 있다.** 22:00 수집 창을 추가하지 않아도
  기존 07:00 만으로 잡힌다.

  교차검증: 08-10 기준 연방채 10Y 3.19 vs ECB AAA 10Y 3.1993 (1bp 이내 일치).

  확인 필요: 당일치가 나중에 수정되는지. 하루 뒤 같은 날짜를 다시 읽어 값이
  그대로인지 봐야 안다. 최초 게시 시각도 모른다 (15:50 CEST 에 있었다는 것만).
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from ficc.config.settings import today_kst  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REST = "https://api.statistiken.bundesbank.de/rest"
UA = {"User-Agent": "ficc-desk-discovery"}
TIMEOUT = httpx.Timeout(60.0, connect=20.0)

# BBSIS 차원 15개. DSD BBK_SEIS 에서 확인 (dims 모드로 재확인 가능).
DIMS = ["FREQ", "BEARER", "ITEM", "VALUATION", "CURRENCY", "ISSUER",
        "LISTED", "SEC_CLASS", "MATURITY", "INT_TYPE", "INT_RATE",
        "REDEMPTION", "CERT", "COVERAGE", "RATING"]

# 확인된 코드값:
#   ITEM      ZST   Term structure of spot interest rates (Svensson)
#             ZAR   Yields, derived from the term structure
#             UMR   Yield on debt securities outstanding (weighted)
#   ISSUER    S1311 Central government        S122  Deposit-taking corporations
#   SEC_CLASS A604  Listed Government Bonds   A100  Pfandbriefe
#   MATURITY  R10XX Residual maturity of 10 years
#
# R0102 등 짧은 만기는 ZST 조합에 존재하지 않는다 (404 확인). 만기별 스팟은
# ZST 전체를 받아 MATURITY 를 훑어야 한다.


def key_of(**fixed: str) -> str:
    """빈 칸은 와일드카드. 채운 칸만 조건이 된다."""
    return ".".join(fixed.get(name, "") for name in DIMS)


QUERIES: dict[str, str] = {
    "10년 스팟 (Svensson)": key_of(FREQ="D", ITEM="ZST", MATURITY="R10XX"),
    "10년 곡선유도 수익률": key_of(FREQ="D", ITEM="ZAR", MATURITY="R10XX"),
}


def tag(element: ET.Element) -> str:
    return element.tag.split("}")[-1]


def series_of(body: str) -> list[tuple[str, dict, list[tuple[str, str, str]]]]:
    """SDMX generic → (제목, 차원, [(관측일, 값, 상태)])."""
    root = ET.fromstring(body)
    out = []
    for element in [e for e in root.iter() if tag(e) == "Series"]:
        dims: dict[str, str] = {}
        attrs: dict[str, str] = {}
        rows: list[tuple[str, str, str]] = []
        for child in element:
            name = tag(child)
            if name == "SeriesKey":
                for value in child:
                    dims[value.get("id", "")] = value.get("value", "")
            elif name == "Attributes":
                for value in child:
                    attrs[value.get("id", "")] = value.get("value", "")
            elif name == "Obs":
                period = obs_value = status = ""
                for part in child:
                    kind = tag(part)
                    if kind == "ObsDimension":
                        period = part.get("value", "")
                    elif kind == "ObsValue":
                        obs_value = part.get("value", "")
                    elif kind == "Attributes":
                        for value in part:
                            if value.get("id", "").endswith("OBS_STATUS"):
                                status = value.get("value", "")
                if period:
                    rows.append((period, obs_value, status))
        rows.sort()
        title = attrs.get("BBK_TITLE_ENG") or attrs.get("BBK_TITLE", "")
        out.append((title, dims, rows))
    return out


def show_current(client: httpx.Client) -> None:
    today = today_kst()
    print(f"오늘(KST) {today}\n")
    for label, key in QUERIES.items():
        print(f"[{label}]  key {key}")
        try:
            response = client.get(f"{REST}/data/BBSIS/{key}",
                                  params={"lastNObservations": "6"})
        except Exception as exc:  # noqa: BLE001
            print(f"  실패: {type(exc).__name__}: {exc}\n")
            continue
        if response.status_code != 200:
            print(f"  HTTP {response.status_code} — {response.text[:120]}\n")
            continue

        for title, dims, rows in series_of(response.text):
            print(f"  {'.'.join(dims.values())}")
            print(f"    {title[:104]}")
            dated = [r for r in rows if r[1]]
            if not dated:
                print("    값 있는 관측 없음")
                continue
            obs_date, value, status = dated[-1]
            try:
                gap = (today - date.fromisoformat(obs_date)).days
                gap_text = f"지연 {gap}일"
            except ValueError:
                gap_text = ""
            flag = f"status={status}" if status else "status 없음(확정)"
            print(f"    최신 {obs_date} = {value}  {gap_text}  {flag}")
            tail = ", ".join(f"{d}={v or '-'}{'/' + s if s else ''}"
                             for d, v, s in rows[-5:])
            print(f"    꼬리 {tail}")
        print()


def show_dims(client: httpx.Client) -> None:
    """DSD 를 다시 받아 차원 순서와 주요 코드를 확인한다."""
    response = client.get(f"{REST}/metadata/datastructure/BBK/BBK_SEIS",
                          params={"references": "children"})
    print(f"DSD BBK_SEIS · HTTP {response.status_code} · "
          f"{len(response.text)} bytes\n")
    root = ET.fromstring(response.text)

    print("=== 차원 (순서대로) ===")
    found = []
    for element in root.iter():
        if tag(element) != "Dimension" or not element.get("id"):
            continue
        codelist = ""
        for ref in element.iter():
            if tag(ref) == "Ref" and ref.get("class") == "Codelist":
                codelist = ref.get("id", "")
        found.append((element.get("position", "?"), element.get("id", ""),
                      codelist))
    for pos, dim_id, codelist in found:
        print(f"  {pos:>2}  {dim_id:<24} {codelist}")

    print("\n=== 이 스크립트가 쓰는 코드 ===")
    want = {"ZST", "ZAR", "UMR", "S1311", "S122", "A604", "A100", "R10XX",
            "P", "E", "R", "K"}
    for codelist in [e for e in root.iter() if tag(e) == "Codelist"]:
        list_id = codelist.get("id", "")
        for code in [c for c in codelist if tag(c) == "Code"]:
            code_id = code.get("id", "")
            if code_id not in want:
                continue
            english = ""
            for child in code:
                if tag(child) == "Name" and child.get(
                        "{http://www.w3.org/XML/1998/namespace}lang") == "en":
                    english = (child.text or "").strip()
            if english:
                print(f"  [{list_id:<28}] {code_id:<6} {english}"[:126])


def main(argv: list[str]) -> int:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers=UA) as client:
        if argv and argv[0] == "dims":
            show_dims(client)
        else:
            show_current(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
