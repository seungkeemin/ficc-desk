# 데이터 사전

`scripts/data_dictionary.py`가 마이그레이션과 `ficc/config/sources.py`에서 생성한다. 직접 고치지 않는다.

저장 필드 41개, 조회 시 계산하는 파생 필드 10개.

## 저장 필드

| field_key | 이름 | 분류 | 단위 | 수집 | 소스 코드 | 확인일 |
|---|---|---|---|---|---|---|
| `bok_base_rate` | 한국은행 기준금리 | policy_kr | pct | ecos | `722Y001` / `0101000` | 2026-08-11 |
| `kofr` | KOFR (공시RFR) | policy_kr | pct | ecos | `817Y002` / `010901000` | 2026-08-11 |
| `cd_91d` | CD 91일 | policy_kr | pct | ecos | `817Y002` / `010502000` | 2026-08-11 |
| `cp_91d` | CP 91일 | policy_kr | pct | ecos | `817Y002` / `010503000` | 2026-08-11 |
| `msb_1y` | 통안증권 1년 | policy_kr | pct | ecos | `817Y002` / `010400001` | 2026-08-11 |
| `ktb_1y` | 국고채 1년 | krw_rates | pct | ecos | `817Y002` / `010190000` | 2026-08-11 |
| `ktb_3y` | 국고채 3년 | krw_rates | pct | ecos | `817Y002` / `010200000` | 2026-08-11 |
| `ktb_5y` | 국고채 5년 | krw_rates | pct | ecos | `817Y002` / `010200001` | 2026-08-11 |
| `ktb_10y` | 국고채 10년 | krw_rates | pct | ecos | `817Y002` / `010210000` | 2026-08-11 |
| `ktb_20y` | 국고채 20년 | krw_rates | pct | ecos | `817Y002` / `010220000` | 2026-08-11 |
| `ktb_30y` | 국고채 30년 | krw_rates | pct | ecos | `817Y002` / `010230000` | 2026-08-11 |
| `ktbf_3y` | 3년 국채선물 | krw_futures | futures | krx | `drv/fut_bydd_trd` 3년국채 선물 · `TDD_CLSPRC` | 2026-08-11 |
| `ktbf_10y` | 10년 국채선물 | krw_futures | futures | krx | `drv/fut_bydd_trd` 10년국채 선물 · `TDD_CLSPRC` | 2026-08-11 |
| `ktbf_30y` | 30년 국채선물 | krw_futures | futures | krx | `drv/fut_bydd_trd` 30년국채 선물 · `TDD_CLSPRC` | 2026-08-11 |
| `ktbf_3y_oi` | 3년 선물 미결제약정 | krw_futures | contracts | krx | `drv/fut_bydd_trd` 3년국채 선물 · `ACC_OPNINT_QTY` | 2026-08-11 |
| `ktbf_10y_oi` | 10년 선물 미결제약정 | krw_futures | contracts | krx | `drv/fut_bydd_trd` 10년국채 선물 · `ACC_OPNINT_QTY` | 2026-08-11 |
| `irs_1y` | KRW IRS 1년 | swap | pct | 수동 |  |  |
| `irs_3y` | KRW IRS 3년 | swap | pct | 수동 |  |  |
| `irs_5y` | KRW IRS 5년 | swap | pct | 수동 |  |  |
| `ust_3m` | UST 3개월 | global_rates | pct | fred | `DGS3MO` | 2026-08-11 |
| `ust_2y` | UST 2년 | global_rates | pct | fred | `DGS2` | 2026-08-11 |
| `ust_5y` | UST 5년 | global_rates | pct | fred | `DGS5` | 2026-08-11 |
| `ust_10y` | UST 10년 | global_rates | pct | fred | `DGS10` | 2026-08-11 |
| `ust_30y` | UST 30년 | global_rates | pct | fred | `DGS30` | 2026-08-11 |
| `sofr` | SOFR | global_rates | pct | fred | `SOFR` | 2026-08-11 |
| `ff_target_upper` | FF 목표금리 상단 | global_rates | pct | fred | `DFEDTARU` | 2026-08-11 |
| `us_bei_10y` | 미 10년 BEI | global_rates | pct | fred | `T10YIE` | 2026-08-11 |
| `usdkrw` | USD/KRW | fx | krw | ecos | `731Y003` / `0000003` | 2026-08-11 |
| `ndf_1m` | 1개월 NDF | fx | krw | 수동 |  |  |
| `swap_point_1m` | 스왑포인트 1개월 | fx | won_jeon | 수동 |  |  |
| `usdjpy` | USD/JPY | fx | jpy | fred | `DEXJPUS` | 2026-08-11 |
| `eurusd` | EUR/USD | fx | usd | fred | `DEXUSEU` | 2026-08-11 |
| `jpykrw_100` | 원/100엔 | fx | krw | ecos | `731Y003` / `0000006` | 2026-08-11 |
| `cnykrw` | 원/위안 | fx | krw | ecos | `731Y003` / `0000010` | 2026-08-11 |
| `dxy` | DXY | fx | index | 수동 |  |  |
| `corp_aa3_yield_3y` | 회사채 AA- 3년 수익률 | credit | pct | ecos | `817Y002` / `010300000` | 2026-08-11 |
| `corp_bbb3_yield_3y` | 회사채 BBB- 3년 수익률 | credit | pct | ecos | `817Y002` / `010320000` | 2026-08-11 |
| `us_ig_oas` | 미 IG 회사채 OAS | credit | pct | fred | `BAMLC0A0CM` | 2026-08-11 |
| `us_hy_oas` | 미 HY 회사채 OAS | credit | pct | fred | `BAMLH0A0HYM2` | 2026-08-11 |
| `vix` | VIX | risk | index | fred | `VIXCLS` | 2026-08-11 |
| `kr_cds_5y` | 한국 CDS 5년 | risk | bp | 수동 |  |  |

## 파생 필드

구성 원본이 하나라도 없으면 `None`이다. DB에 저장하지 않는다.

| field_key | 이름 | 단위 | 구성 |
|---|---|---|---|
| `cd_kofr_spread` | CD 91일 - KOFR | bp | `cd_91d`, `kofr` |
| `curve_3s10s` | 국고 3-10 스프레드 | bp | `ktb_10y`, `ktb_3y` |
| `curve_10s30s` | 국고 10-30 스프레드 | bp | `ktb_30y`, `ktb_10y` |
| `ktb_base_spread_3y` | 국고 3년 - 기준금리 | bp | `ktb_3y`, `bok_base_rate` |
| `bond_swap_3y` | 본드-스왑 스프레드 3년 | bp | `ktb_3y`, `irs_3y` |
| `ust_2s10s` | UST 2s10s | bp | `ust_10y`, `ust_2y` |
| `ust_5s30s` | UST 5s30s | bp | `ust_30y`, `ust_5y` |
| `kr_us_10y` | 한미 금리차 10년 | bp | `ktb_10y`, `ust_10y` |
| `corp_aa3_spread_3y` | 회사채 AA- 3년 스프레드 | bp | `corp_aa3_yield_3y`, `ktb_3y` |
| `corp_bbb3_spread_3y` | 회사채 BBB- 3년 스프레드 | bp | `corp_bbb3_yield_3y`, `ktb_3y` |
