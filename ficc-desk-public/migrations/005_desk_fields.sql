-- 005_desk_fields.sql
--
-- 스냅샷을 데스크가 실제로 매일 보는 판으로 넓힌다.
-- 저장 17 → 41, 파생 4 → 10.
--
-- 새로 넣는 24 개는 **전부 자동 수집**이다. 수동 입력 필드는 하나도 늘지 않는다 —
-- SPEC 4-1 이 못박은 대로 손으로 채우는 시간이 60초를 넘기면 이 도구는 버려진다.
-- 그래서 "공개 API 로 매일 자동으로 들어오는가"를 채택 기준으로 삼았고,
-- 각 코드의 실호출 확인 근거(확인일·그날의 값)는 ficc/config/sources.py 주석에 있다.
--
-- 카테고리를 5 → 8 로 쪼갠다. 원화금리 한 칸에 정책금리·국고 커브·선물이 섞이면
-- 20 셀짜리 덩어리가 되어 아침에 눈이 어디를 봐야 할지 모르게 된다.
--   policy_kr     정책·단기금리   기준금리 · KOFR · CD · CP · 통안
--   krw_rates     원화금리        국고 1/3/5/10/20/30 + 커브
--   krw_futures   국채선물        KTBF 3/10/30 + 미결제약정
--   swap          스왑            (그대로)
--   global_rates  해외금리        UST 커브 + SOFR + 정책금리 + BEI
--   fx            FX
--   credit        크레딧          국내 회사채 + 미 IG/HY OAS
--   risk          리스크          VIX · 한국 CDS
--
-- display_order 는 전 필드를 100 단위 구간으로 다시 매긴다. 002 의 10~210 과
-- 섞이지 않게 하기 위해서다. 순서는 데이터이므로 코드는 손대지 않는다 (SPEC 2.1).

-- --------------------------------------------------------------------------
-- 1. 새 저장 필드 (24) — auto_provider 는 확인된 소스만 채운다 (CLAUDE.md 3)
-- --------------------------------------------------------------------------
INSERT OR IGNORE INTO field_def
  (field_key, label_ko, label_short, category, unit, decimals, delta_unit,
   display_order, auto_provider, is_derived, derived_from, active)
VALUES
  -- 정책·단기금리 -------------------------------------------------------------
  -- 기준금리는 하루하루 움직이는 값이 아니다. 그래도 매일 띄우는 이유는
  -- 국고 3년과의 거리(ktb_base_spread_3y)가 오늘의 정책 기대이기 때문이다.
  ('bok_base_rate', '한국은행 기준금리', 'BOK BASE', 'policy_kr', 'pct', 2, 'bp',  10, 'ecos', 0, NULL, 1),
  ('kofr',          'KOFR (공시RFR)',   'KOFR',     'policy_kr', 'pct', 3, 'bp',  20, 'ecos', 0, NULL, 1),
  ('cp_91d',        'CP 91일',          'CP91D',    'policy_kr', 'pct', 3, 'bp',  50, 'ecos', 0, NULL, 1),
  ('msb_1y',        '통안증권 1년',      'MSB1Y',    'policy_kr', 'pct', 3, 'bp',  60, 'ecos', 0, NULL, 1),

  -- 국고 커브 ----------------------------------------------------------------
  ('ktb_1y',  '국고채 1년',  '국고1Y',  'krw_rates', 'pct', 3, 'bp', 100, 'ecos', 0, NULL, 1),
  ('ktb_5y',  '국고채 5년',  '국고5Y',  'krw_rates', 'pct', 3, 'bp', 120, 'ecos', 0, NULL, 1),
  ('ktb_20y', '국고채 20년', '국고20Y', 'krw_rates', 'pct', 3, 'bp', 140, 'ecos', 0, NULL, 1),
  ('ktb_30y', '국고채 30년', '국고30Y', 'krw_rates', 'pct', 3, 'bp', 150, 'ecos', 0, NULL, 1),

  -- 국채선물 -----------------------------------------------------------------
  ('ktbf_30y',    '30년 국채선물',      'KTBF30Y', 'krw_futures', 'futures',   2, 'tick', 220, 'krx', 0, NULL, 1),
  -- 미결제약정은 계약 수다. 전일 대비도 계약 수 그대로 본다 (delta_unit='qty').
  ('ktbf_3y_oi',  '3년 선물 미결제약정',  'OI 3Y',   'krw_futures', 'contracts', 0, 'qty',  230, 'krx', 0, NULL, 1),
  ('ktbf_10y_oi', '10년 선물 미결제약정', 'OI 10Y',  'krw_futures', 'contracts', 0, 'qty',  240, 'krx', 0, NULL, 1),

  -- 해외금리 -----------------------------------------------------------------
  ('ust_3m',          'UST 3개월',        'UST3M',  'global_rates', 'pct', 3, 'bp', 400, 'fred', 0, NULL, 1),
  ('ust_5y',          'UST 5년',          'UST5Y',  'global_rates', 'pct', 3, 'bp', 420, 'fred', 0, NULL, 1),
  ('ust_30y',         'UST 30년',         'UST30Y', 'global_rates', 'pct', 3, 'bp', 440, 'fred', 0, NULL, 1),
  ('sofr',            'SOFR',             'SOFR',   'global_rates', 'pct', 2, 'bp', 470, 'fred', 0, NULL, 1),
  -- 연준 목표'범위'의 상단이다. 실효금리(EFFR)와 다른 숫자라 라벨에 UP 을 남긴다.
  ('ff_target_upper', 'FF 목표금리 상단',  'FF UP',  'global_rates', 'pct', 2, 'bp', 480, 'fred', 0, NULL, 1),
  ('us_bei_10y',      '미 10년 BEI',      'BEI10',  'global_rates', 'pct', 2, 'bp', 490, 'fred', 0, NULL, 1),

  -- FX -----------------------------------------------------------------------
  -- DEXUSEU 는 1유로당 달러다. 소수 4 자리로 보고 전일 대비도 4 자리로 본다.
  ('eurusd',     'EUR/USD',     'EUR/USD', 'fx', 'usd', 4, 'fx4',  640, 'fred', 0, NULL, 1),
  -- 100 엔당 원. 1 엔당으로 착각하면 자릿수가 두 자리 틀린다.
  ('jpykrw_100', '원/100엔',    '원/100엔', 'fx', 'krw', 2, 'won', 650, 'ecos', 0, NULL, 1),
  ('cnykrw',     '원/위안',     '원/위안',   'fx', 'krw', 2, 'won', 660, 'ecos', 0, NULL, 1),

  -- 크레딧 -------------------------------------------------------------------
  ('corp_bbb3_yield_3y', '회사채 BBB- 3년 수익률', 'BBB-3Y', 'credit', 'pct', 3, 'bp', 720, 'ecos', 0, NULL, 1),
  -- ICE BofA OAS 는 단위가 % 다. 0.78 이 78bp 라는 뜻 — 원본 단위를 바꾸지 않는다.
  ('us_ig_oas',          '미 IG 회사채 OAS',       'IG OAS', 'credit', 'pct', 2, 'bp', 740, 'fred', 0, NULL, 1),
  ('us_hy_oas',          '미 HY 회사채 OAS',       'HY OAS', 'credit', 'pct', 2, 'bp', 750, 'fred', 0, NULL, 1),

  -- 리스크 -------------------------------------------------------------------
  ('vix', 'VIX', 'VIX', 'risk', 'index', 2, 'point', 800, 'fred', 0, NULL, 1);


-- --------------------------------------------------------------------------
-- 2. 새 파생 필드 (6) — 계산은 derived.py, 여기 derived_from 은 문서용이다
-- --------------------------------------------------------------------------
INSERT OR IGNORE INTO field_def
  (field_key, label_ko, label_short, category, unit, decimals, delta_unit,
   display_order, auto_provider, is_derived, derived_from, active)
VALUES
  ('cd_kofr_spread',      'CD 91일 - KOFR',        'CD-KOFR', 'policy_kr',    'bp', 1, 'bp',  70, NULL, 1, 'cd_91d,kofr', 1),
  ('curve_10s30s',        '국고 10-30 스프레드',     '10-30',   'krw_rates',    'bp', 1, 'bp', 170, NULL, 1, 'ktb_30y,ktb_10y', 1),
  ('ktb_base_spread_3y',  '국고 3년 - 기준금리',     '3Y-기준',  'krw_rates',    'bp', 1, 'bp', 180, NULL, 1, 'ktb_3y,bok_base_rate', 1),
  ('ust_5s30s',           'UST 5s30s',            '5s30s',   'global_rates', 'bp', 1, 'bp', 460, NULL, 1, 'ust_30y,ust_5y', 1),
  ('kr_us_10y',           '한미 금리차 10년',        '한미10Y',  'global_rates', 'bp', 1, 'bp', 500, NULL, 1, 'ktb_10y,ust_10y', 1),
  ('corp_bbb3_spread_3y', '회사채 BBB- 3년 스프레드', 'SPD BBB', 'credit',       'bp', 1, 'bp', 730, NULL, 1, 'corp_bbb3_yield_3y,ktb_3y', 1);


-- --------------------------------------------------------------------------
-- 3. 기존 필드 재배치 — 값은 건드리지 않는다. 화면 순서와 소속만 바뀐다.
-- --------------------------------------------------------------------------
-- CD 91일은 IRS 변동레그의 기준이자 단기자금 지표다. KOFR·CP 옆이 제자리다.
UPDATE field_def SET category = 'policy_kr', display_order =  40 WHERE field_key = 'cd_91d';

UPDATE field_def SET category = 'krw_rates', display_order = 110 WHERE field_key = 'ktb_3y';
UPDATE field_def SET category = 'krw_rates', display_order = 130 WHERE field_key = 'ktb_10y';
UPDATE field_def SET category = 'krw_rates', display_order = 160 WHERE field_key = 'curve_3s10s';

UPDATE field_def SET category = 'krw_futures', display_order = 200 WHERE field_key = 'ktbf_3y';
UPDATE field_def SET category = 'krw_futures', display_order = 210 WHERE field_key = 'ktbf_10y';

UPDATE field_def SET display_order = 300 WHERE field_key = 'irs_1y';
UPDATE field_def SET display_order = 310 WHERE field_key = 'irs_3y';
UPDATE field_def SET display_order = 320 WHERE field_key = 'irs_5y';
UPDATE field_def SET display_order = 330 WHERE field_key = 'bond_swap_3y';

UPDATE field_def SET display_order = 410 WHERE field_key = 'ust_2y';
UPDATE field_def SET display_order = 430 WHERE field_key = 'ust_10y';
UPDATE field_def SET display_order = 450 WHERE field_key = 'ust_2s10s';

UPDATE field_def SET display_order = 600 WHERE field_key = 'usdkrw';
UPDATE field_def SET display_order = 610 WHERE field_key = 'ndf_1m';
UPDATE field_def SET display_order = 620 WHERE field_key = 'swap_point_1m';
UPDATE field_def SET display_order = 630 WHERE field_key = 'usdjpy';
UPDATE field_def SET display_order = 670 WHERE field_key = 'dxy';

UPDATE field_def SET display_order = 700 WHERE field_key = 'corp_aa3_yield_3y';
UPDATE field_def SET display_order = 710 WHERE field_key = 'corp_aa3_spread_3y';

-- 한국 CDS 는 크레딧 스프레드가 아니라 국가 리스크 프리미엄이다. VIX 옆에 둔다.
UPDATE field_def SET category = 'risk', display_order = 810 WHERE field_key = 'kr_cds_5y';
