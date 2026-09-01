-- 001_init.sql — 최초 스키마. SPEC.md §2 의 DDL.
-- 이 파일은 적용된 뒤 절대 수정하지 않는다. 변경은 새 번호 파일로 추가한다 (CLAUDE.md 코드 스타일).

-- ---------------------------------------------------------------------------
-- 마켓 데이터 (SPEC 2.2)
-- ---------------------------------------------------------------------------

-- 필드 사전: 화면 순서, 단위, 자동 수집 가능 여부를 여기서 관리한다.
-- 표시 규칙을 코드가 아니라 데이터로 두어야 필드 추가에 스키마 변경이 필요 없다.
CREATE TABLE field_def (
  field_key      TEXT PRIMARY KEY,      -- 'ktb_3y'
  label_ko       TEXT NOT NULL,         -- '국고 3년'
  label_short    TEXT NOT NULL,         -- '국고3Y'  (티커 밴드용)
  category       TEXT NOT NULL,         -- krw_rates | swap | global_rates | fx | credit
  unit           TEXT NOT NULL,         -- pct | bp | krw | index | futures | won_jeon
  decimals       INTEGER NOT NULL,
  delta_unit     TEXT NOT NULL,         -- bp | won | tick | point
  display_order  INTEGER NOT NULL,
  auto_provider  TEXT,                  -- 'ecos' | 'fred' | 'krx' | NULL(수동 전용)
  is_derived     INTEGER NOT NULL DEFAULT 0,
  derived_from   TEXT,                  -- 'ktb_10y,ktb_3y' (문서화용. 계산은 derived.py)
  active         INTEGER NOT NULL DEFAULT 1
);

-- 관측값 본체. (날짜, 필드) 당 최신 1행.
-- 미수집은 NULL 이 아니라 '행 부재'다. 0 으로 채우지 않는다 (CLAUDE.md 1).
CREATE TABLE market_observation (
  obs_date    TEXT NOT NULL,            -- 'YYYY-MM-DD' (KST 관측일)
  field_key   TEXT NOT NULL REFERENCES field_def(field_key),
  value       REAL NOT NULL,
  source      TEXT NOT NULL CHECK (source IN ('auto','manual')),
  provider    TEXT,                     -- 'ecos' | 'fred' | 'krx' | 'user'
  captured_at TEXT NOT NULL,            -- ISO8601 +09:00
  note        TEXT,
  PRIMARY KEY (obs_date, field_key)
) WITHOUT ROWID;

-- 덮어쓰기 이력. 절대 UPDATE/DELETE 하지 않는다 (CLAUDE.md 4).
-- 실수로 덮어쓴 값이 여기서 복구된다.
CREATE TABLE market_observation_log (
  id          INTEGER PRIMARY KEY,
  obs_date    TEXT NOT NULL,
  field_key   TEXT NOT NULL,
  action      TEXT NOT NULL CHECK (action IN ('insert','update')),
  prev_value  REAL,
  prev_source TEXT,
  new_value   REAL NOT NULL,
  new_source  TEXT NOT NULL,
  provider    TEXT,
  written_at  TEXT NOT NULL
);
CREATE INDEX idx_mol_date ON market_observation_log(obs_date, field_key);

-- 수집 실행 기록: "왜 이 필드가 비었는가"를 화면에서 설명하기 위한 것.
CREATE TABLE ingest_run (
  id          INTEGER PRIMARY KEY,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  target_date TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('running','ok','partial','failed'))
);
CREATE TABLE ingest_result (
  run_id      INTEGER NOT NULL REFERENCES ingest_run(id),
  field_key   TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('ok','miss','error','skipped')),
  message     TEXT,
  PRIMARY KEY (run_id, field_key)
);

-- ---------------------------------------------------------------------------
-- 페이퍼 포지션 (SPEC 2.3)
-- ---------------------------------------------------------------------------

CREATE TABLE idea (
  id             INTEGER PRIMARY KEY,
  code           TEXT NOT NULL UNIQUE,          -- 'IDEA-012' (옵시디언 파일명과 동일)
  position       TEXT NOT NULL,
  flow_agent     TEXT,                          -- 수급 주체
  strategy       TEXT NOT NULL CHECK (strategy IN ('momentum','mean_reversion')),
  dv01_krw       REAL NOT NULL,
  holding_days   INTEGER NOT NULL,
  pricing_key    TEXT,                          -- field_key 또는 파생키. NULL 이면 수동 마킹
  level_unit     TEXT NOT NULL,                 -- 'bp' | 'pct' | 'krw'
  entry_level    REAL NOT NULL,
  target_level   REAL NOT NULL,
  stop_level     REAL NOT NULL,
  opened_on      TEXT NOT NULL,
  closed_on      TEXT,
  status         TEXT NOT NULL CHECK (status IN ('open','closed')),
  result_bp      REAL,
  postmortem_tag TEXT CHECK (postmortem_tag IN ('logic','timing','sizing','none')),
  postmortem     TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

-- 논리는 3개까지 (요구사항의 "3개 이내"를 스키마로 강제)
CREATE TABLE idea_thesis (
  idea_id INTEGER NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
  seq     INTEGER NOT NULL CHECK (seq BETWEEN 1 AND 3),
  text    TEXT NOT NULL,
  PRIMARY KEY (idea_id, seq)
);

-- 무효화 조건: 최소 1건 없으면 아이디어 저장 불가 (앱 레벨에서 강제, CLAUDE.md 7)
CREATE TABLE invalidation (
  id         INTEGER PRIMARY KEY,
  idea_id    INTEGER NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- 매일의 점검 이력. 시그니처 패널의 데이터 소스이자 사후분석의 근거.
CREATE TABLE invalidation_check (
  invalidation_id INTEGER NOT NULL REFERENCES invalidation(id) ON DELETE CASCADE,
  check_date      TEXT NOT NULL,
  state           TEXT NOT NULL CHECK (state IN ('valid','shaky','broken')),
  note            TEXT,
  created_at      TEXT NOT NULL,
  PRIMARY KEY (invalidation_id, check_date)
);

-- 수동 마킹 (pricing_key 로 자동 산출이 안 되는 포지션)
CREATE TABLE idea_mark (
  idea_id    INTEGER NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
  mark_date  TEXT NOT NULL,
  level      REAL NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (idea_id, mark_date)
);

-- ---------------------------------------------------------------------------
-- 저널 · 이벤트 · 루틴 · 노트 (SPEC 2.4)
-- ---------------------------------------------------------------------------

CREATE TABLE journal (
  obs_date        TEXT PRIMARY KEY,
  review_ny       TEXT,   -- 아침: 뉴욕장
  review_ldn      TEXT,   -- 저녁: 런던장
  pre_open_expect TEXT,   -- 개장 전 예상
  why_moved       TEXT,   -- 한 문장
  brief_en        TEXT,   -- 영문 시황 브리핑
  updated_at      TEXT NOT NULL
);

CREATE TABLE event (
  id             INTEGER PRIMARY KEY,
  event_date     TEXT NOT NULL,
  event_time     TEXT,
  region         TEXT NOT NULL,          -- KR | US | EU | JP | CN
  name           TEXT NOT NULL,
  consensus      TEXT,
  my_expectation TEXT,                   -- 월요일에 기록
  actual         TEXT,                   -- 발표 후 기록
  my_call        TEXT CHECK (my_call IN ('hit','miss','partial')),
  note           TEXT,
  created_at     TEXT NOT NULL
);
CREATE INDEX idx_event_date ON event(event_date);

CREATE TABLE routine_def (
  key           TEXT PRIMARY KEY,        -- 'daily_snapshot'
  label         TEXT NOT NULL,
  cadence       TEXT NOT NULL CHECK (cadence IN
                  ('daily','mon','wed','fri','biweekly','monthly','quarterly')),
  counts_streak INTEGER NOT NULL DEFAULT 0,
  display_order INTEGER NOT NULL,
  active        INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE routine_log (
  task_date   TEXT NOT NULL,
  routine_key TEXT NOT NULL REFERENCES routine_def(key),
  done        INTEGER NOT NULL DEFAULT 0,
  done_at     TEXT,
  PRIMARY KEY (task_date, routine_key)
) WITHOUT ROWID;

-- 서술형 콘텐츠. Phase 6 에서 institution/product/regulation/deepdive 는
-- 볼트가 원본이 되고 이 표는 읽기 전용 인덱스로 역할이 바뀐다.
CREATE TABLE note (
  id         INTEGER PRIMARY KEY,
  type       TEXT NOT NULL CHECK (type IN
               ('institution','product','regulation','deepdive',
                'networking','weekly_review','drill','quarterly_review')),
  title      TEXT NOT NULL,
  body_md    TEXT NOT NULL DEFAULT '',
  tags       TEXT,                       -- 쉼표 구분
  origin     TEXT NOT NULL DEFAULT 'db' CHECK (origin IN ('db','vault')),
  file_path  TEXT,                       -- 볼트 원본 경로 (origin='vault')
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE note_link (            -- 무효화 조건 <-> 관련 노트
  note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
  idea_id         INTEGER REFERENCES idea(id) ON DELETE CASCADE,
  invalidation_id INTEGER REFERENCES invalidation(id) ON DELETE CASCADE
);

CREATE TABLE app_setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
