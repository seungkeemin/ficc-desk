"""실제 호출로 확인된 외부 소스 코드만 여기에 고정한다.

CLAUDE.md 3: API 스펙을 추측하지 않는다. 통계표코드·항목코드·엔드포인트는
탐색 스크립트로 실제 호출해 확인한 뒤, 확인 날짜와 확인 방법을 주석으로 남긴다.
확인 전에는 비워 두고 해당 필드를 수동 입력으로 돌린다.

  탐색:  .venv\\Scripts\\python scripts\\discover_ecos.py
         .venv\\Scripts\\python scripts\\discover_fred.py
         .venv\\Scripts\\python scripts\\discover_krx.py

유럽 소스는 확인만 하고 **채택하지 않았다** (아래 표에 없다). 붙일지는 단계
게이트를 통과한 뒤 결정한다. 확인 결과는 각 스크립트 docstring 에 있다.

         .venv\\Scripts\\python scripts\\discover_ecb.py   유로존 곡선·환율·정책금리
         .venv\\Scripts\\python scripts\\discover_boe.py   gilt 곡선·SONIA
         .venv\\Scripts\\python scripts\\discover_bbk.py   독일 연방채 곡선

요약: FRED 에는 유럽 국채금리가 일별로 없다. ECB·BoE 는 D 일 값을 D+1 에 내서
07:00 수집 창에서는 2영업일 전이 최신이다. 분데스방크만 D 일에 내므로 다음날
아침에 전날 세션 값이 잡힌다 (전부 2026-08-11 실호출 확인).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EcosSeries:
    stat_code: str          # 통계표코드
    cycle: str              # D | M | Q | A
    item_codes: tuple[str, ...]
    unit: str               # 응답 DATA_VALUE 의 단위 (ECOS UNIT_NAME 기준)
    stat_name: str = ""
    item_name: str = ""
    verified_on: str = ""   # YYYY-MM-DD


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    unit: str
    verified_on: str = ""


@dataclass(frozen=True)
class KrxSeries:
    endpoint: str           # data-dbg.krx.co.kr/svc/apis/ 이후 경로
    product_name: str       # 응답 PROD_NM 과 **정확히** 일치해야 한다 (부분일치 아님)
    value_field: str        # 값으로 쓸 응답 필드명
    unit: str
    verified_on: str = ""


# ---------------------------------------------------------------------------
# ECOS — 한국은행
# ---------------------------------------------------------------------------
# 확인 2026-08-11: StatisticTableList(834건) → StatisticItemList → StatisticSearch 실호출.
#
#   817Y002  1.3.2.1. 시장금리(일별)          CYCLE=D  SRCH_YN=Y
#   731Y003  3.1.1.3. 원화의 대미달러, 대위안/대엔 환율  CYCLE=D  SRCH_YN=Y
#
# 게시 지연: **T+0**. 2026-08-11(화) 당일 조회에서 TIME=20260811 행이 이미 나왔다.
# SPEC 4-2 는 T+1 가능성을 우려했으나 시장금리(일별)·환율(일별)은 당일 게시된다.
# 다만 게시 시각까지 확인한 것은 아니므로 아침 07:00 수집은 전일 값이 최신일 수 있다.
# 그래서 수집기는 여전히 '가장 최근 게시분'을 취하고 obs_date 에 실제 관측일을 넣는다.
#
# USD/KRW 는 두 후보가 모두 T+0 로 존재한다:
#   731Y003/0000003  원/달러(종가 15:30)   ← 채택. 장 마감 실거래 종가다.
#   731Y001/0000001  원/미국달러(매매기준율) 1415.3 (08-11). 전일 거래 가중평균 개념이라
#                    "오늘 시장이 어디서 끝났나"를 묻는 이 대시보드의 질문과 맞지 않는다.
#
# 회사채도 두 후보가 있다:
#   010300000  회사채(3년, AA-)        ← 채택 (1995-01-03~, 당일 게시)
#   010310000  회사채(3년, AA-, 민평)  전일까지만 게시되고 있었다 (08-10)
#
# 2026-08-11 확장: 817Y002 세부항목 27종을 다시 훑어 데스크에서 매일 보는 것만 골랐다
# (`discover_ecos.py items 817Y002`). 각 항목의 08-11 실측값은 아래 행 주석에 있다.
# 넣지 않은 것과 이유:
#   010195000 국고채(2년)          발행 잔량이 얇고 3년이 대표 단기 지표다
#   010102000 콜금리(중개회사거래)  KOFR 가 무위험지표금리 자리를 대체했다
#   010150000~ KORIBOR 3/6/12개월  실거래 기반이 아니라 호가 제출 금리다
#   010501000 MMF · 010504000 CMA  리테일 수신금리라 데스크 지표가 아니다
#   010260000 산금채(1년)          은행채 스프레드는 크레딧 탭을 따로 만들 때
# 콜금리(1일, 전체거래)와 KOFR 는 END_TIME 이 08-10 이었다 — 이 둘만 T+1 이다.
ECOS_SERIES: dict[str, EcosSeries] = {
    # 확인 2026-08-11 · 단위 연% · 수록 1999-05-06~ · 08-10 값 2.75 (T+1)
    # 722Y001 은 시장금리(817Y002)와 다른 통계표다. 정책금리 앵커가 없으면
    # '국고 3년이 기준금리 대비 몇 bp' 라는 질문에 답할 수 없다.
    "bok_base_rate": EcosSeries(
        stat_code="722Y001", cycle="D", item_codes=("0101000",), unit="pct",
        stat_name="한국은행 기준금리 및 여수신금리", item_name="한국은행 기준금리",
        verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 2021-11-25~ · 08-10 값 2.771 (T+1)
    "kofr": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010901000",), unit="pct",
        stat_name="시장금리(일별)", item_name="KOFR(공시RFR)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 1995-01-03~ · 08-11 값 3.17
    "cp_91d": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010503000",), unit="pct",
        stat_name="시장금리(일별)", item_name="CP(91일)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 1995-01-03~ · 08-11 값 3.263
    "msb_1y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010400001",), unit="pct",
        stat_name="시장금리(일별)", item_name="통안증권(1년)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 2000-02-01~ · 08-11 값 3.395
    "ktb_1y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010190000",), unit="pct",
        stat_name="시장금리(일별)", item_name="국고채(1년)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 2000-01-04~ · 08-11 값 4.042
    # 항목코드가 010200001 이다 — 3년(010200000)과 마지막 한 자리만 다르니 조심한다.
    "ktb_5y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010200001",), unit="pct",
        stat_name="시장금리(일별)", item_name="국고채(5년)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 2006-01-25~ · 08-11 값 4.639
    "ktb_20y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010220000",), unit="pct",
        stat_name="시장금리(일별)", item_name="국고채(20년)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 2012-09-11~ · 08-11 값 4.666
    # 50년(010240000)도 있으나 발행이 비정기라 매일 보는 지표가 아니다.
    "ktb_30y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010230000",), unit="pct",
        stat_name="시장금리(일별)", item_name="국고채(30년)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 2000-09-30~ · 08-11 값 10.305
    # AA- 와 마찬가지로 수익률을 저장한다. 국고 대비 스프레드는 derived.py 가 계산한다.
    "corp_bbb3_yield_3y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010320000",), unit="pct",
        stat_name="시장금리(일별)", item_name="회사채(3년, BBB-)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 원 · 수록 2005-03-02~ · 08-11 값 889.24
    # 100엔당 원이다. 1엔당으로 착각하면 자릿수가 두 자리 틀린다.
    "jpykrw_100": EcosSeries(
        stat_code="731Y003", cycle="D", item_codes=("0000006",), unit="krw",
        stat_name="원화의 대미달러, 대위안/대엔 환율", item_name="원/100엔(하나은행고시)",
        verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 원 · 수록 2014-12-01~ · 08-11 값 209.94
    # 역외 USD/CNH 는 무료 공개 소스가 없다. FRED DEXCHUS 는 역내 고시환율이고
    # T+4 로 밀려서 아침 화면에 늘 4일 전 값이 뜬다 — 넣지 않았다 (2026-08-11 실측).
    "cnykrw": EcosSeries(
        stat_code="731Y003", cycle="D", item_codes=("0000010",), unit="krw",
        stat_name="원화의 대미달러, 대위안/대엔 환율", item_name="원/위안(종가)",
        verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 1998-11-13~ · 08-11 값 3.808
    "ktb_3y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010200000",), unit="pct",
        stat_name="시장금리(일별)", item_name="국고채(3년)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 2000-12-18~ · 08-11 값 4.301
    "ktb_10y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010210000",), unit="pct",
        stat_name="시장금리(일별)", item_name="국고채(10년)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 1995-01-03~ · 08-11 값 2.93
    "cd_91d": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010502000",), unit="pct",
        stat_name="시장금리(일별)", item_name="CD(91일)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 연% · 수록 1995-01-03~ · 08-11 값 4.504
    # 스프레드가 아니라 수익률이다. 국고 대비 스프레드는 derived.py 에서 계산한다.
    "corp_aa3_yield_3y": EcosSeries(
        stat_code="817Y002", cycle="D", item_codes=("010300000",), unit="pct",
        stat_name="시장금리(일별)", item_name="회사채(3년, AA-)", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · 단위 원 · 수록 1990-03-02~ · 08-11 값 1416.0
    "usdkrw": EcosSeries(
        stat_code="731Y003", cycle="D", item_codes=("0000003",), unit="krw",
        stat_name="원화의 대미달러 환율", item_name="원/달러(종가 15:30)",
        verified_on="2026-08-11",
    ),
}


# ---------------------------------------------------------------------------
# FRED — 세인트루이스 연준
# ---------------------------------------------------------------------------
# 확인 2026-08-11: fred/series + fred/series/observations 실호출.
# 게시 지연: **영업일 T+1**. 08-10(월) 15:16 CDT 갱신 시점의 최신 관측일이 08-07(금)이었다.
# 한국 아침에 수집하면 미국 전일치가 아직 안 올라와 있을 수 있다 —
# 그래서 obs_date 에 '오늘'이 아니라 관측일을 넣는 설계가 필요하다 (SPEC 4-2).
#
# 2026-08-11 확장: 아래 시리즈를 전부 fred/series + observations 로 실호출해
# 단위·주기·최신 관측일을 확인했다 (`discover_fred.py <ID>`). 지연은 두 갈래다.
#   H.15 국채 금리(DGS*)·환율(DEX*)  15:16 CDT 갱신 · 최신 관측일 08-07 → 지연 4일
#   그 외 (SOFR·EFFR·OAS·VIX·BEI)   당일 07~09시 CDT 갱신 · 최신 08-10 → 지연 1일
# 같은 화면에 지연이 다른 값이 섞이므로 셀마다 as of 날짜를 띄우는 설계가 필수다.
#
# 넣지 않은 것:
#   DCOILBRENTEU / DCOILWTICO  08-11 기준 최신 관측일이 08-03 이었다 (지연 8일).
#                              매일 아침 8일 전 유가를 띄우느니 비워 두는 게 낫다.
#   DTWEXBGS                   DXY 가 아니다. 라벨을 DXY 로 붙이면 거짓말이 된다.
#   DFII10 (10년 실질금리)      BEI 와 명목금리가 있으면 되고, 셀 하나가 아깝다.
#   DEXCHUS                    역내 위안 고시환율 · 지연 4일. 원/위안(ECOS)으로 갈음.
FRED_SERIES: dict[str, FredSeries] = {
    # Market Yield on U.S. Treasury Securities at 2-Year Constant Maturity · Percent
    "ust_2y": FredSeries(series_id="DGS2", unit="pct", verified_on="2026-08-11"),
    # Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity · Percent
    "ust_10y": FredSeries(series_id="DGS10", unit="pct", verified_on="2026-08-11"),
    # Japanese Yen to U.S. Dollar Spot Exchange Rate · JPY per 1 USD
    "usdjpy": FredSeries(series_id="DEXJPUS", unit="jpy", verified_on="2026-08-11"),

    # 3-Month Constant Maturity · Percent · 08-07 값 3.87 (T-bill 벤치마크)
    "ust_3m": FredSeries(series_id="DGS3MO", unit="pct", verified_on="2026-08-11"),
    # 5-Year Constant Maturity · Percent · 08-07 값 4.35
    "ust_5y": FredSeries(series_id="DGS5", unit="pct", verified_on="2026-08-11"),
    # 30-Year Constant Maturity · Percent · 08-07 값 5.19
    "ust_30y": FredSeries(series_id="DGS30", unit="pct", verified_on="2026-08-11"),
    # Secured Overnight Financing Rate · Percent · 08-10 값 3.63
    # 미 단기자금 시장의 기준금리. IRS·베이시스의 출발점이다.
    "sofr": FredSeries(series_id="SOFR", unit="pct", verified_on="2026-08-11"),
    # Federal Funds Target Range - Upper Limit · Percent · 08-11 값 3.75 (T+0)
    # 목표'범위'의 상단이다. EFFR(실효금리, 08-10 3.63)과 다른 숫자다.
    "ff_target_upper": FredSeries(
        series_id="DFEDTARU", unit="pct", verified_on="2026-08-11"),
    # 10-Year Breakeven Inflation Rate · Percent · 08-10 값 2.29
    "us_bei_10y": FredSeries(series_id="T10YIE", unit="pct", verified_on="2026-08-11"),
    # ICE BofA US Corporate Index Option-Adjusted Spread · Percent · 08-10 값 0.78
    # 단위가 bp 가 아니라 % 다. 0.78 은 78bp 라는 뜻 — 원본 단위 그대로 저장한다.
    "us_ig_oas": FredSeries(
        series_id="BAMLC0A0CM", unit="pct", verified_on="2026-08-11"),
    # ICE BofA US High Yield Index Option-Adjusted Spread · Percent · 08-10 값 2.70
    "us_hy_oas": FredSeries(
        series_id="BAMLH0A0HYM2", unit="pct", verified_on="2026-08-11"),
    # U.S. Dollars to Euro Spot Exchange Rate · USD per 1 EUR · 08-07 값 1.1559
    # DEXJPUS 와 방향이 반대다 (엔은 1달러당 엔, 유로는 1유로당 달러).
    "eurusd": FredSeries(series_id="DEXUSEU", unit="usd", verified_on="2026-08-11"),
    # CBOE Volatility Index: VIX · Index · 08-10 값 15.46
    "vix": FredSeries(series_id="VIXCLS", unit="index", verified_on="2026-08-11"),
}


# ---------------------------------------------------------------------------
# KRX — 한국거래소 Data Marketplace
# ---------------------------------------------------------------------------
# 엔드포인트는 확인됨 (2026-08-11):
#   GET https://data-dbg.krx.co.kr/svc/apis/drv/fut_bydd_trd?basDd=YYYYMMDD
#   Header: AUTH_KEY
#   Response: {"OutBlock_1":[{BAS_DD, PROD_NM, MKT_NM, ISU_CD, ISU_NM, TDD_CLSPRC,
#              CMPPREVDD_PRC, TDD_OPNPRC, TDD_HGPRC, TDD_LWPRC, SPOT_PRC, SETL_PRC,
#              ACC_TRDVOL, ACC_TRDVAL, ACC_OPNINT_QTY}, ...]}
#   근거: openapi.krx.co.kr '선물 일별매매정보(주식선물外)' 명세 + 공식 샘플 키로
#         /svc/sample/apis/drv/fut_bydd_trd 호출 200 확인.
#
# 인증키는 2026-08-11 활성화됐다 (그 전에는 전 서비스 401 이었다).
#
# PROD_NM 실측 (basDd=20260810, 385행, 34개 상품):
#   '3년국채 선물'   '5년국채 선물'   '10년국채 선물'   '30년국채 선물'
#   '3년-10년국채선물스프레드 선물'   ← 별개 상품이다
# 숫자와 '년' 사이에 공백이 없고 '국채'와 '선물' 사이에만 공백이 있다.
# '10년국채 선물' 과 '30년국채 선물' 은 한 글자 차이이므로 **정확일치**로 고른다.
#
# 한 PROD_NM 안의 행 구성 (3년국채 선물 = 6행):
#   F 202609 (주간) 정규  정산가 있음  거래량 대부분       ← 최근월물, 이걸 쓴다
#   F 202609 (야간) 야간  정산가 없음  거래량 적음
#   F 202612 (주간) 정규  정산가 있음  거래량 거의 없음    ← 차근월물
#   SP 2609-2612 등 캘린더 스프레드 3행
# → MKT_NM='정규' 로 거르고 스프레드 행을 뺀 뒤 ACC_TRDVOL 최대 행을 고르면
#   최근월물만 남는다. 롤오버 주간에는 스프레드 거래량이 가장 커지므로
#   스프레드를 빼는 단계가 필요하다 (ficc/sources/krx.py).
# KRX 데이터 재배포를 피하려고 실측 가격·거래량·미결제약정은 여기 적지 않는다.
#
# 값은 TDD_CLSPRC(종가). 최근월물에서는 SETL_PRC(정산가)와 같은 값이었다.
#
# 게시 지연: **최소 T+1**. 2026-08-11(화) 18:58 KST 에 basDd=20260811 은 0행이고
# 20260810 은 385행이었다. 그날 장이 끝난 지 3시간이 지나서도 당일치가 없다는 뜻이라,
# SPEC 5 의 07:00·16:00 수집 창에서는 국채선물이 **항상 전일 종가**로 들어온다.
# 장중 선물 레벨이 필요하면 그 필드만 수동으로 덮어쓴다.
KRX_SERIES: dict[str, KrxSeries] = {
    # 확인 2026-08-11 · basDd=20260810 · F 202609 종가 확인
    "ktbf_3y": KrxSeries(
        endpoint="drv/fut_bydd_trd", product_name="3년국채 선물",
        value_field="TDD_CLSPRC", unit="futures", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · basDd=20260810 · F 202609 종가 확인
    "ktbf_10y": KrxSeries(
        endpoint="drv/fut_bydd_trd", product_name="10년국채 선물",
        value_field="TDD_CLSPRC", unit="futures", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · basDd=20260810 · F 202609 종가 확인
    # 얇지만 초장기 커브의 유일한 헤지 수단이라 데스크가 매일 본다.
    "ktbf_30y": KrxSeries(
        endpoint="drv/fut_bydd_trd", product_name="30년국채 선물",
        value_field="TDD_CLSPRC", unit="futures", verified_on="2026-08-11",
    ),
    # 미결제약정. 같은 응답 행의 다른 필드일 뿐이라 추가 호출이 없다 (일자별 캐시).
    # 가격은 '얼마'를, 미결제약정은 '누가 얼마나 들고 있나'를 말한다. 방향이 같은
    # 가격·미결제 증가는 신규 진입, 가격만 움직이고 미결제가 줄면 청산이다.
    # 확인 2026-08-11 · basDd=20260810 · 3년 F 202609 미결제약정 확인
    "ktbf_3y_oi": KrxSeries(
        endpoint="drv/fut_bydd_trd", product_name="3년국채 선물",
        value_field="ACC_OPNINT_QTY", unit="contracts", verified_on="2026-08-11",
    ),
    # 확인 2026-08-11 · basDd=20260810 · 10년 F 202609 미결제약정 확인
    "ktbf_10y_oi": KrxSeries(
        endpoint="drv/fut_bydd_trd", product_name="10년국채 선물",
        value_field="ACC_OPNINT_QTY", unit="contracts", verified_on="2026-08-11",
    ),
}

# 확인만 하고 채택하지 않은 KRX 후보 (2026-08-11 실호출):
#   '5년국채 선물'          거래량·미결제가 거의 없다.
#   '3개월무위험금리 선물'   거래량·미결제가 적다. KOFR 선물은 아직 시장이 얕다.
#   '미국달러 선물'         거래량이 두껍다. 다만 현물 USD/KRW(ECOS)와
#                          NDF(수동)가 이미 있어 FX 칸이 세 겹이 된다. 보류.
#   bon/kts_bydd_trd       국채전문유통시장(IDB) 일별매매정보. **HTTP 401** —
#   bon/bnd_bydd_trd       인증키는 살아 있으나 채권 서비스 '활용신청'이 승인되지
#   bon/smb_bydd_trd       않았다. 승인되면 지표종목 체결수익률·거래대금이 열린다.
