-- 002_seed.sql — 필드 사전 · 루틴 정의 · 기본 설정.
-- 전부 INSERT OR IGNORE 라 여러 번 적용해도 사용자가 바꾼 값을 덮어쓰지 않는다.
--
-- 표시 순서·단위·소수자리를 코드가 아니라 데이터로 두는 것이 SPEC 2.1 의 원칙이다.
-- 필드를 끄고 싶으면 코드를 고치지 말고 active = 0 으로 바꾼다.
--
-- auto_provider 는 '실제 호출로 확인된 소스'만 채운다 (CLAUDE.md 3).
-- 확인되지 않은 필드는 NULL(수동 전용)이고, 근거는 각 행 주석에 있다.

-- 저장 17 필드 + 파생 4 필드 = 21
INSERT OR IGNORE INTO field_def
  (field_key, label_ko, label_short, category, unit, decimals, delta_unit,
   display_order, auto_provider, is_derived, derived_from, active)
VALUES
  -- 원화금리 -----------------------------------------------------------------
  ('ktb_3y',   '국고채 3년',  '국고3Y',  'krw_rates', 'pct',     3, 'bp',    10, 'ecos', 0, NULL, 1),
  ('ktb_10y',  '국고채 10년', '국고10Y', 'krw_rates', 'pct',     3, 'bp',    20, 'ecos', 0, NULL, 1),
  ('curve_3s10s', '국고 3-10 스프레드', '3-10', 'krw_rates', 'bp', 1, 'bp',  30, NULL,   1, 'ktb_10y,ktb_3y', 1),
  -- 국채선물: 엔드포인트(drv/fut_bydd_trd)는 확인됐지만 사용자 인증키가 401 이라
  -- 실제 응답의 PROD_NM 표기를 확인하지 못했다. 확인 전에는 수동 입력이다 (CLAUDE.md 3).
  -- 인증키가 활성화되면 마이그레이션으로 auto_provider 를 'krx' 로 바꾼다.
  ('ktbf_3y',  '3년 국채선물',  'KTBF3Y',  'krw_rates', 'futures', 2, 'tick',  40, NULL, 0, NULL, 1),
  ('ktbf_10y', '10년 국채선물', 'KTBF10Y', 'krw_rates', 'futures', 2, 'tick',  50, NULL, 0, NULL, 1),
  -- CD 91일: IRS 변동금리 레그의 기준이라 넣었다. 불필요하면 active = 0.
  ('cd_91d',   'CD 91일',     'CD91D',   'krw_rates', 'pct',     3, 'bp',    60, 'ecos', 0, NULL, 1),

  -- 스왑 ---------------------------------------------------------------------
  -- IRS 는 서울외국환중개 고시가 원천이고 공식 API 가 없다. 스크래핑은 불안정해
  -- Phase 1 에서 하지 않는다 (SPEC 4-1). 수동 입력이 기본 경로다.
  ('irs_1y',   'KRW IRS 1년', 'IRS1Y',   'swap', 'pct', 3, 'bp',  70, NULL, 0, NULL, 1),
  ('irs_3y',   'KRW IRS 3년', 'IRS3Y',   'swap', 'pct', 3, 'bp',  80, NULL, 0, NULL, 1),
  ('irs_5y',   'KRW IRS 5년', 'IRS5Y',   'swap', 'pct', 3, 'bp',  90, NULL, 0, NULL, 1),
  ('bond_swap_3y', '본드-스왑 스프레드 3년', 'B/S 3Y', 'swap', 'bp', 1, 'bp', 100, NULL, 1, 'ktb_3y,irs_3y', 1),

  -- 해외금리 -----------------------------------------------------------------
  ('ust_2y',   'UST 2년',  'UST2Y',  'global_rates', 'pct', 3, 'bp', 110, 'fred', 0, NULL, 1),
  ('ust_10y',  'UST 10년', 'UST10Y', 'global_rates', 'pct', 3, 'bp', 120, 'fred', 0, NULL, 1),
  ('ust_2s10s','UST 2s10s','2s10s',  'global_rates', 'bp',  1, 'bp', 130, NULL,   1, 'ust_10y,ust_2y', 1),

  -- FX -----------------------------------------------------------------------
  ('usdkrw',   'USD/KRW',   'USD/KRW', 'fx', 'krw',      2, 'won',   140, 'ecos', 0, NULL, 1),
  -- 1M NDF: 무료 공개 소스가 사실상 없다 (SPEC 4-1). 수동 전용.
  ('ndf_1m',   '1개월 NDF', 'NDF1M',   'fx', 'krw',      2, 'won',   150, NULL,   0, NULL, 1),
  -- FRED DEXJPUS 는 '1달러당 엔'이다. index 로 분류하면 라벨이 거짓말이 된다.
  ('usdjpy',   'USD/JPY',   'USD/JPY', 'fx', 'jpy',      2, 'point', 160, 'fred', 0, NULL, 1),
  -- DXY 는 ICE 독점 지수라 무료 공개 API 가 없다. FRED 의 광의 달러지수는 구성과
  -- 가중치가 다른 별개 숫자이므로 DXY 라는 라벨로 채우지 않는다. 수동 전용 + 화면 ⓘ.
  -- (2026-08-11 사용자 결정)
  ('dxy',      'DXY',       'DXY',     'fx', 'index',    2, 'point', 170, NULL,   0, NULL, 1),
  -- 스왑포인트는 1개월물로 고정한다. 기간 없는 '스왑포인트'는 비교 불가능한 숫자다.
  ('swap_point_1m', '스왑포인트 1개월', 'SWPT1M', 'fx', 'won_jeon', 2, 'won', 180, NULL, 0, NULL, 1),

  -- 크레딧 -------------------------------------------------------------------
  -- 회사채는 스프레드가 아니라 수익률을 저장한다. 공개 소스가 주는 값이 수익률이고,
  -- 스프레드는 국고 대비 파생이므로 원본을 보존하는 쪽이 옳다 (SPEC 2.2).
  ('corp_aa3_yield_3y', '회사채 AA- 3년 수익률', 'AA-3Y', 'credit', 'pct', 3, 'bp', 190, 'ecos', 0, NULL, 1),
  ('corp_aa3_spread_3y','회사채 AA- 3년 스프레드','SPD',   'credit', 'bp',  1, 'bp', 200, NULL,  1, 'corp_aa3_yield_3y,ktb_3y', 1),
  -- 한국 CDS 5년물로 고정. 무료 공개 소스 사실상 없음 → 수동 전용.
  ('kr_cds_5y', '한국 CDS 5년', 'KR CDS5Y', 'credit', 'bp', 1, 'bp', 210, NULL, 0, NULL, 1);


-- 루틴 정의 (SPEC 2.5) ------------------------------------------------------
-- counts_streak = 1 인 일간 항목이 전부 완료된 날만 연속 기록으로 센다.
INSERT OR IGNORE INTO routine_def (key, label, cadence, counts_streak, display_order, active)
VALUES
  ('daily_overnight',     '야간장 리뷰 (뉴욕/런던)',   'daily',     1, 10, 1),
  ('daily_snapshot',      '마켓 스냅샷',               'daily',     1, 20, 1),
  ('daily_why',           '왜 움직였나 한 문장',       'daily',     1, 30, 1),
  ('daily_brief_en',      '영문 시황 브리핑',          'daily',     1, 40, 1),
  ('daily_invalidation',  '무효화 조건 점검',          'daily',     1, 50, 1),
  ('mon_events',          '이벤트 캘린더 + 내 예상',   'mon',       0, 60, 1),
  ('wed_idea',            'shadowing 아이디어 1건',    'wed',       0, 70, 1),
  ('fri_review',          '주간 리뷰',                 'fri',       0, 80, 1),
  ('fri_drill',           '리스크 60초 즉답 드릴',     'fri',       0, 90, 1),
  ('biweekly_product',    '상품 분해 → 재조합',        'biweekly',  0, 100, 1),
  ('monthly_track',       '트랙 레코드 집계',          'monthly',   0, 110, 1),
  ('monthly_institution', '기관 해부 1건',             'monthly',   0, 120, 1),
  ('monthly_regulation',  '규제 추적 1건',             'monthly',   0, 130, 1),
  ('monthly_deepdive',    '이론→구현 딥다이브',        'monthly',   0, 140, 1),
  ('monthly_network',     '네트워킹 1건',              'monthly',   0, 150, 1),
  ('quarterly_self',      '성향 점검',                 'quarterly', 0, 160, 1);


-- 기본 설정 -----------------------------------------------------------------
-- color_convention: 'kr' = 상승 빨강/하락 파랑, 'bbg' = 상승 초록/하락 빨강.
-- 금리 상승은 좋지도 나쁘지도 않다. 색은 방향만 나타낸다.
INSERT OR IGNORE INTO app_setting (key, value) VALUES
  ('color_convention',   'kr'),
  -- 볼트 경로는 기계마다 다르다. 비워 두고 .env 의 OBSIDIAN_VAULT_PATH 로 채운다.
  ('obsidian_vault_path', ''),
  -- 국내 휴장일 자동 소스는 확인되지 않았다. 수동 목록으로 관리한다 (SPEC 4-7).
  ('market_holidays_kr', '');
