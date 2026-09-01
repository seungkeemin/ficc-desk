-- 004_monthly_routines_off.sql
--
-- 격주·월간·분기 루틴을 화면에서 내린다 (2026-08-11 사용자 결정).
--
-- 상품 분해, 트랙 레코드 집계, 기관 해부, 규제 추적, 딥다이브, 네트워킹, 성향 점검은
-- 사용자가 이 도구 밖에서 직접 계획해 수행한다. 매일 여는 화면에 한 달짜리 항목이
-- 섞여 있으면 '오늘 할 일' 의 정의가 흐려지고, 체크되지 않은 채 몇 주씩 남아 있는
-- 목록은 화면을 읽지 않게 만든다.
--
-- 행을 지우지 않고 active = 0 으로 끈다. routine_def 를 지우면 routine_log 의 외래키가
-- 걸리고, 나중에 다시 켜고 싶을 때 시드를 되살려야 한다. 끄는 방식은 field_def 와 같다
-- (002_seed.sql: "필드를 끄고 싶으면 코드를 고치지 말고 active = 0 으로 바꾼다").
--
-- 연속 기록에는 영향이 없다 — 이 7 종은 전부 counts_streak = 0 이었다.

UPDATE routine_def SET active = 0
 WHERE cadence IN ('biweekly', 'monthly', 'quarterly');
