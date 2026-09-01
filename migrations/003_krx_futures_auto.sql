-- 003_krx_futures_auto.sql
--
-- 국채선물 3년/10년을 수동에서 KRX 자동 수집으로 전환한다.
--
-- 002 시드 시점에는 KRX 인증키가 전 서비스에서 401 이라 응답을 볼 수 없었고,
-- CLAUDE.md 3 에 따라 확인되지 않은 것은 수동으로 두었다.
-- 2026-08-11 인증키가 활성화되어 basDd=20260810 응답으로 PROD_NM 실제 표기
-- ('3년국채 선물' / '10년국채 선물')과 최근월물 판별 규칙을 확인했다.
-- 근거는 ficc/config/sources.py 의 KRX_SERIES 주석에 있다.

UPDATE field_def SET auto_provider = 'krx'
 WHERE field_key IN ('ktbf_3y', 'ktbf_10y')
   AND auto_provider IS NULL;
