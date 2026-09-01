# SPEC.md — FICC 데스크 루틴 대시보드

> Phase 0 산출물. 작성일 2026-08-11.
> 운영 규칙은 [CLAUDE.md](CLAUDE.md)에 있다.

## 0. 배경과 목적

FICC 트레이딩 데스크의 일간·주간·격주·월간·분기 루틴을 장기간 끊김 없이 실행하기
위한 도구다. 루틴 정의는 코드가 아니라 `migrations/002_seed.sql` 의 `routine_def`
에 데이터로 들어 있고, 쓰는 사람이 자기 루틴으로 바꿔 넣을 수 있다.

- 실제 자금 없음. 모든 포지션은 **페이퍼 트레이딩**.
- 목적은 수익이 아니라 **규율과 기록**.
- 최종 산출물은 대시보드가 아니라, 충분한 기록이 쌓인 뒤 **"내 실패가 논리·타이밍·사이징 중 어디에 몰려 있는가"** 를 데이터로 답하는 능력이다.
- 사용자 1명, 로컬 실행, 인증 없음, 인터넷 배포 없음.
- **시계열 유실이 이 프로젝트의 유일한 치명적 실패다.**

### 확인된 환경 (실측, 2026-08-11)

| 항목 | 결과 |
|---|---|
| Node.js / npm | 미설치 |
| Python | 3.14.5 / pip 26.1.1 |
| SQLite (stdlib) | 3.50.4 |
| git | 2.55.0 |
| 옵시디언 볼트 | 환경변수 `OBSIDIAN_VAULT_PATH` (`.obsidian` 존재, 커뮤니티 플러그인 없음 → **Dataview 미설치**) |
| 프로젝트 위치 | 볼트 밖의 별도 git 저장소 |
| ECOS · FRED API 키 | 각자 발급받아 `.env` 에 넣는다 (`.env.example` 참고) |

---

## 1. 기술 스택과 근거

| 계층 | 선택 | 근거 |
|------|------|------|
| 언어/런타임 | Python 3.14 (표준 `venv`) | 이미 설치되어 있고, 월간 딥다이브(부트스트래핑·NSS 피팅·CDS 변환)와 대시보드가 같은 언어면 코드가 저장소 하나에 모인다. |
| 웹 프레임워크 | FastAPI + Uvicorn | 타입 힌트 기반 검증이 수동 입력 필드의 오타·단위 오류를 진입 지점에서 막아준다. |
| 템플릿 | Jinja2 (서버 렌더링) | 화면이 하나뿐이고 상태가 거의 없어 SPA가 필요 없다 — 빌드 단계 없이 새로고침만으로 확인된다. |
| 상호작용 | 순수 JS (~200줄) + `fetch` | 인라인 입력·디바운스 저장·플래시에 프레임워크가 필요 없고, 의존성이 늘면 1년 뒤 실행이 안 된다. |
| DB | SQLite (stdlib `sqlite3`, WAL) | 단일 파일이라 백업이 파일 복사이고, 시계열 유실을 막기 가장 쉽다. |
| 마이그레이션 | 번호순 `.sql` + `schema_version` | Alembic은 1인 로컬 DB에 과하고, 스키마 이력이 읽히는 텍스트로 남는 편이 낫다. |
| HTTP 클라이언트 | `httpx` | 타임아웃·재시도를 명시적으로 다루기 쉬워 수집 실패를 조용히 삼키지 않는다. |
| 수치 계산 | `numpy` (딥다이브 전용, 대시보드 비의존) | 대시보드가 numpy 없이도 떠서, 계산 라이브러리 문제로 기록이 끊기지 않는다. |
| 스케줄링 | Windows 작업 스케줄러 + `.bat` | OS 기본 기능이라 상주 프로세스가 없고, PC를 켜면 알아서 돈다. |
| 테스트 | `pytest` (파생값·백필·내보내기 멱등성만) | UI 테스트는 투자 대비 효과가 없고, 데이터 정확성만 지키면 된다. |
| 폰트 | 로컬 `Cascadia Mono` / `Consolas` + `tabular-nums` | 오프라인에서 뜨고, 자릿수가 흔들리지 않아야 숫자 스캔이 가능하다. |

**의도적으로 쓰지 않는 것**: Docker, PostgreSQL, 인증, ORM, Tailwind, 프론트엔드 빌드 툴, 상태관리 라이브러리, WebSocket. 1인 로컬 앱에서 전부 유지비만 늘린다.

### 폴더 구조

```
ficc-desk/
├── CLAUDE.md
├── SPEC.md
├── README.md              (Phase 5)
├── .env                   (API 키. git 제외)
├── .env.example
├── requirements.txt
├── data/ficc.db
├── backups/
├── migrations/001_init.sql ...
├── ficc/
│   ├── app.py             FastAPI 엔트리
│   ├── db.py              커넥션·마이그레이션 러너
│   ├── derived.py         파생값 레지스트리 (문자열 eval 금지)
│   ├── ingest.py          수집 엔트리
│   ├── sources/{ecos,fred,krx}.py
│   ├── config/sources.py  통계표코드 등 확인된 상수 + 확인 날짜 주석
│   ├── routes/
│   ├── templates/
│   └── static/
├── templates_md/          서술형 템플릿 4종 (Phase 4)
├── scripts/*.bat          스케줄러·백업·앱모드 실행
└── tests/
```

---

## 2. 데이터 모델

### 2.1 설계 원칙

- **마켓 데이터는 넓은 표가 아니라 긴 표(long format).** 필드마다 값·출처·수집시각을 따로 들고, 필드 추가가 스키마 변경 없이 된다.
- **미수집은 `NULL`이 아니라 행 부재.** 0으로 채우지 않는다.
- **파생값은 저장하지 않는다.** 조회 시 계산하고, 원본이 하나라도 없으면 `None`.
- **덮어쓰기는 append-only 로그로 남긴다.** 실수로 지운 값이 복구 가능해야 한다.
- **표시 순서·단위·소수자리는 코드가 아니라 데이터**(`field_def`)로 둔다.

### 2.2 마켓 데이터

```sql
-- 필드 사전: 화면 순서, 단위, 자동 수집 가능 여부를 여기서 관리
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
CREATE TABLE market_observation (
  obs_date    TEXT NOT NULL,            -- 'YYYY-MM-DD' (KST 관측일)
  field_key   TEXT NOT NULL REFERENCES field_def(field_key),
  value       REAL NOT NULL,            -- 미수집은 행을 만들지 않는다
  source      TEXT NOT NULL CHECK (source IN ('auto','manual')),
  provider    TEXT,                     -- 'ecos' | 'fred' | 'krx' | 'user'
  captured_at TEXT NOT NULL,            -- ISO8601 +09:00
  note        TEXT,
  PRIMARY KEY (obs_date, field_key)
) WITHOUT ROWID;

-- 덮어쓰기 이력. 절대 UPDATE/DELETE 하지 않는다.
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

-- 수집 실행 기록: "왜 이 필드가 비었는가"를 화면에서 설명하기 위한 것
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
```

#### 저장 필드 17 / 파생 4

| 카테고리 | 저장 field_key | 파생 (조회 시 계산) |
|---|---|---|
| 원화금리 | `ktb_3y`, `ktb_10y`, `ktbf_3y`, `ktbf_10y`, `cd_91d` | `curve_3s10s = ktb_10y − ktb_3y` |
| 스왑 | `irs_1y`, `irs_3y`, `irs_5y` | `bond_swap_3y = ktb_3y − irs_3y` |
| 해외금리 | `ust_2y`, `ust_10y` | `ust_2s10s = ust_10y − ust_2y` |
| FX | `usdkrw`, `ndf_1m`, `usdjpy`, `dxy`, `swap_point_1m` | — |
| 크레딧 | `corp_aa3_yield_3y`, `kr_cds_5y` | `corp_aa3_spread_3y = corp_aa3_yield_3y − ktb_3y` |

- 회사채는 **스프레드가 아니라 수익률을 저장한다.** 공개 소스가 주는 값이 수익률이고, 스프레드는 국고 대비 파생이므로 원본을 보존하는 쪽이 옳다.
- `cd_91d`는 요구 목록에 없지만 IRS 변동금리 레그의 기준이라 추가했다. 불필요하면 `field_def.active = 0`으로 끈다.
- `swap_point_1m`은 **1개월물로 고정**한다. 기간을 명시하지 않은 "스왑포인트"는 비교 불가능한 숫자가 된다.
- `kr_cds_5y`는 **5년물로 고정**한다.

#### 2026-08-11 확장 — 저장 41 / 파생 10 (migration `005_desk_fields.sql`)

Phase 1에서 ECOS·FRED·KRX를 실제로 호출해 보니 위 17필드는 **공개 API가 주는 것의 일부**였다. 커브가 3년·10년 두 점뿐이라 스티프너 하나도 눈으로 못 읽고, 정책금리·단기자금·미결제약정이 없어 "왜 움직였나"에 답할 재료가 부족했다. 그래서 매일 보는 것만 골라 24개를 더 붙였다. **새로 붙인 24개는 전부 자동 수집이다 — 수동 입력 필드는 7개 그대로다** (4-1의 "손으로 채우는 데 60초를 넘기면 버려진다"를 지키기 위해).

| 카테고리 | 추가된 저장 field_key | 추가된 파생 |
|---|---|---|
| 정책·단기금리 `policy_kr` | `bok_base_rate`, `kofr`, `cp_91d`, `msb_1y` (+`cd_91d` 이동) | `cd_kofr_spread` |
| 원화금리 `krw_rates` | `ktb_1y`, `ktb_5y`, `ktb_20y`, `ktb_30y` | `curve_10s30s`, `ktb_base_spread_3y` |
| 국채선물 `krw_futures` | `ktbf_30y`, `ktbf_3y_oi`, `ktbf_10y_oi` | — |
| 해외금리 `global_rates` | `ust_3m`, `ust_5y`, `ust_30y`, `sofr`, `ff_target_upper`, `us_bei_10y` | `ust_5s30s`, `kr_us_10y` |
| FX | `eurusd`, `jpykrw_100`, `cnykrw` | — |
| 크레딧 | `corp_bbb3_yield_3y`, `us_ig_oas`, `us_hy_oas` | `corp_bbb3_spread_3y` |
| 리스크 `risk` | `vix` (+`kr_cds_5y` 이동) | — |

- 채택 기준은 하나다: **공개 API로 매일 자동으로 들어오는가.** 항목코드·시리즈ID·상품명은 전부 실호출로 확인했고 확인일과 그날의 값이 `config/sources.py` 주석에 있다 (CLAUDE.md 3).
- 확인하고도 **넣지 않은 것**과 이유(유가 = 지연 8일, `DTWEXBGS` = DXY가 아님, 5년 국채선물·KOFR 선물 = 거래량 20~30, KRX 채권 엔드포인트 = 401 미승인)도 같은 주석에 남겼다. 나중에 "왜 이건 없지"를 다시 조사하지 않기 위해서다.
- 카테고리를 5 → 8로 쪼갠 이유는 3.4의 압박 문제다. 원화금리 한 칸에 정책금리·커브·선물이 섞이면 20셀 덩어리가 된다.
- **대가**: 51셀이 한 번에 안 들어간다. 그리드 2·3행을 30px씩 내려 스냅샷 본문을 548 → **608px**로 넓혔지만(블로터·워치는 그만큼 아래에서 시작한다) 내용은 1126px이라 패널 안에서 약 1.9화면 스크롤한다. 페이지는 여전히 스크롤하지 않고, 카테고리 머리는 `position: sticky`로 붙어 있다. 더 줄이려면 `field_def.active = 0` 이 유일한 손잡이다 (2.1).
- ECOS는 항목코드를 빼면 통계표 전 항목이 한 번에 온다. 그래서 `ecos.py`가 (통계표, 주기, 창) 단위로 캐시해 12개 필드를 호출 1번으로 받는다. 응답이 1000행 상한에 닿으면 잘렸을 수 있으므로 항목별 조회로 되돌아간다.

#### 파생값 규칙

`derived.py`에 `{키: (구성 필드 튜플, 계산 함수, 표시 단위)}` 레지스트리로 둔다.
**문자열 수식을 `eval`하지 않는다.** 구성 필드가 하나라도 없으면 `None`을 반환하고, 화면은 그 셀을 "미수집"으로 표시한다.

금리 파생값의 표시 단위는 **bp**이고, 저장 단위가 `pct`이므로 `(a − b) × 100`으로 환산한다.

### 2.3 페이퍼 포지션

```sql
CREATE TABLE idea (
  id             INTEGER PRIMARY KEY,
  code           TEXT NOT NULL UNIQUE,          -- 'IDEA-012' (옵시디언 파일명과 동일)
  position       TEXT NOT NULL,                 -- '국고 3-10 스티프너 (3년 매수/10년 매도)'
  flow_agent     TEXT,                          -- 수급 주체
  strategy       TEXT NOT NULL CHECK (strategy IN ('momentum','mean_reversion')),
  dv01_krw       REAL NOT NULL,
  holding_days   INTEGER NOT NULL,              -- 보유기간 목표
  pricing_key    TEXT,                          -- 손익 산출 기준 (field_key 또는 파생키). NULL이면 수동 마킹
  level_unit     TEXT NOT NULL,                 -- 'bp' | 'pct' | 'krw'
  entry_level    REAL NOT NULL,
  target_level   REAL NOT NULL,
  stop_level     REAL NOT NULL,
  opened_on      TEXT NOT NULL,
  closed_on      TEXT,
  status         TEXT NOT NULL CHECK (status IN ('open','closed')),
  result_bp      REAL,                          -- 청산 시 확정
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

-- 무효화 조건: 최소 1건 없으면 아이디어 저장 불가 (앱 레벨에서 강제)
CREATE TABLE invalidation (
  id         INTEGER PRIMARY KEY,
  idea_id    INTEGER NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- 매일의 점검 이력. 시그니처 패널의 데이터 소스이자, 사후분석의 근거.
CREATE TABLE invalidation_check (
  invalidation_id INTEGER NOT NULL REFERENCES invalidation(id) ON DELETE CASCADE,
  check_date      TEXT NOT NULL,
  state           TEXT NOT NULL CHECK (state IN ('valid','shaky','broken')),
  note            TEXT,
  created_at      TEXT NOT NULL,
  PRIMARY KEY (invalidation_id, check_date)
);

-- 수동 마킹 (pricing_key로 자동 산출이 안 되는 포지션)
CREATE TABLE idea_mark (
  idea_id    INTEGER NOT NULL REFERENCES idea(id) ON DELETE CASCADE,
  mark_date  TEXT NOT NULL,
  level      REAL NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (idea_id, mark_date)
);
```

요구된 레코드 구조와의 대응: 포지션 `position` / 논리 `idea_thesis` / 수급 주체 `flow_agent` / 전략 유형 `strategy` / DV01 사이징 `dv01_krw` / 보유기간 목표 `holding_days` / 목표·손절 `target_level`·`stop_level` / 무효화 조건 `invalidation` / 진입일 `opened_on` / 청산일 `closed_on` / 결과 `result_bp` / 사후분석 `postmortem_tag`·`postmortem`.

### 2.4 저널 · 이벤트 · 루틴 · 노트

```sql
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
  counts_streak INTEGER NOT NULL DEFAULT 0,  -- 연속 기록 일수 계산에 포함할지
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

-- 서술형 콘텐츠. Phase 6에서 institution/product/regulation/deepdive는
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
CREATE TABLE note_link (            -- 무효화 조건 ↔ 관련 노트
  note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
  idea_id         INTEGER REFERENCES idea(id) ON DELETE CASCADE,
  invalidation_id INTEGER REFERENCES invalidation(id) ON DELETE CASCADE
);

CREATE TABLE app_setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- color_convention  = 'kr' (기본) | 'bbg'
-- obsidian_vault_path
-- market_holidays_kr = 'YYYY-MM-DD,...' (수동 관리)

CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
```

### 2.5 루틴 시드 (`routine_def`)

| key | cadence | streak | 라벨 |
|---|---|---|---|
| `daily_overnight` | daily | ✓ | 야간장 리뷰 (뉴욕/런던) |
| `daily_snapshot` | daily | ✓ | 마켓 스냅샷 |
| `daily_why` | daily | ✓ | 왜 움직였나 한 문장 |
| `daily_brief_en` | daily | ✓ | 영문 시황 브리핑 |
| `daily_invalidation` | daily | ✓ | 무효화 조건 점검 |
| `mon_events` | mon | | 이벤트 캘린더 + 내 예상 |
| `wed_idea` | wed | | shadowing 아이디어 1건 |
| `fri_review` | fri | | 주간 리뷰 |
| `fri_drill` | fri | | 리스크 60초 즉답 드릴 |
| ~~`biweekly_product`~~ | biweekly | | 상품 분해 → 재조합 |
| ~~`monthly_track`~~ | monthly | | 트랙 레코드 집계 |
| ~~`monthly_institution`~~ | monthly | | 기관 해부 1건 |
| ~~`monthly_regulation`~~ | monthly | | 규제 추적 1건 |
| ~~`monthly_deepdive`~~ | monthly | | 이론→구현 딥다이브 |
| ~~`monthly_network`~~ | monthly | | 네트워킹 1건 |
| ~~`quarterly_self`~~ | quarterly | | 성향 점검 |

#### 격주·월간·분기 7종은 껐다 (2026-08-11 사용자 결정, 마이그레이션 004)

사용자가 이 도구 밖에서 직접 계획해 수행한다. 행은 지우지 않고 `active = 0` 이므로
`routine_def` 는 여전히 16행이고, 되살리려면 `active = 1` 로 바꾸는 마이그레이션 하나면 된다.
다만 화면의 '이번 달' 섹션은 `_routine.html` 에서 함께 제거했으므로 그것도 되돌려야 한다.

화면에 남은 것은 **일간 5 + 월/수/금 4 = 9종**이다. 연속 기록은 영향이 없다 —
껀 7종은 전부 `counts_streak = 0` 이었다.

### 2.6 집계는 테이블이 아니라 쿼리

누적 손익(bp / DV01 환산 원화), 최대 손실, 승률, 손익비, 사후분석 태그별 빈도는 `idea`에서 직접 계산한다. 별도 라우트 `/monthly`에서만 보여주고 **메인 화면에 넣지 않는다**.

---

## 3. 단일 화면 레이아웃

### 3.1 높이 예산

1920×1080 물리 화면에서 브라우저 크롬을 빼면 실사용 세로는 약 940~990px이다. 아래 예산은 **940px** 기준이며 Chrome `--app` 모드(`scripts/open.bat`) 또는 F11을 전제한다.

채택안(3.2 안 A)의 실제 그리드는 아래와 같다. Phase 2 구현·실측치다 (2026-08-11).

| 행 | 높이 | 내용 |
|---|---|---|
| 상단 바 | 36 | 날짜 · 연속 · 미완료 · DATA · MANUAL · MISS · 미점검 · 색 관례 |
| 중단 상 | 300 | 야간장 리뷰 │ 마켓 스냅샷 │ 오늘의 루틴 |
| 중단 하 | 270 | 왜 움직였나 + 영문 브리핑 │ (스냅샷 계속) │ 이번 주 이벤트 |
| 하단 | 334 (`1fr`) | 활성 포지션 블로터 (2열 span) │ 무효화 조건 워치 |
| 합계 | 940 | |

- 별도 상태 바를 두지 않는다. `DATA/MANUAL/MISS` 는 상단 바가 흡수한다.
- 스냅샷은 중단 두 행을 세로로 걸쳐 본문 548px 을 갖고, 21셀이 내부 스크롤 없이 들어간다. (2026-08-11: 필드가 41개로 늘면서 본문 608px · 내부 스크롤로 바뀌었다 — 2.2 확장 절 참조)
- 마지막 행만 `1fr` 이라 세로가 940보다 크면 블로터·워치가 늘어난다.
- 1440×900 은 유일한 브레이크포인트(`max-width: 1560px`)에서
  열 296/1fr/360 · 행 36/288/252/1fr · 스냅샷 3열로 접힌다. 여기서도 페이지 스크롤이 없다.

CSS Grid의 `grid-template-rows`로 고정하고, 각 패널 내부만 `overflow-y: auto`. **페이지 스크롤은 금지.**

### 3.2 안 A — 「블로터형」 (원안 구조 계승) ★ 채택 (2026-08-11 결정 변경, 3.4 참조)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2026-08-11 TUE  ·  D+47  ·  오늘 미완료 2/5  ·  DATA 07:02 KST  ·  MANUAL 5  ·  MISS 3      [국내색상] │
├──────────────────────┬──────────────────────────────────────────────────┬──────────────────────────────┤
│ 야간장 리뷰 NY       │ 마켓 스냅샷                                      │ 오늘의 루틴 (TUE)            │
│ ──────────────────── │ ── 원화금리 ──────────────────────────────────── │ ──────────────────────────── │
│ [                  ] │ 국고3Y   2.845 ▲1.2    국고10Y  3.120 ▲2.0       │ ☑ 야간장 리뷰                │
│ [                  ] │ 3-10      27.5 ▲0.8    KTBF3Y  106.12 ▼4t        │ ☑ 마켓 스냅샷                │
│ 야간장 리뷰 LDN      │ KTBF10Y 118.44 ▼11t    CD91D    3.070 —          │ ☐ 왜 움직였나                │
│ [                  ] │ ── 스왑 ──────────────────────────────────────── │ ☐ 영문 브리핑                │
├──────────────────────┤ IRS1Y  ᴹ 2.780 ▼0.5    IRS3Y  ᴹ 2.910 ▲1.0       │ ── 이번 주 ────────────────  │
│ 왜 움직였나          │ IRS5Y  ᴹ 3.040 ▲1.5    B/S 3Y    -6.5 ▲0.2       │ 수 shadowing 아이디어        │
│ [한 문장           ] │ ── 해외금리 ──────────────────────────────────── │ 금 리뷰 + 60초 드릴          │
├──────────────────────┤ UST2Y    3.760 ▲3.0    UST10Y   4.180 ▲2.0       ├──────────────────────────────┤
│ 영문 브리핑          │ 2s10s     42.0 ▼1.0                              │ 이번 주 이벤트               │
│ [                  ] │ ── FX ────────────────────────────────────────── │ 08/12 KR 금통위  예상:동결   │
│ [                  ] │ USD/KRW 1382.40 ▲2.10  NDF1M ᴹ 1381.90 ▲1.80     │ 08/13 US CPI     예상:+0.3%  │
│ [                  ] │ USD/JPY  147.20 ▲0.35  DXY ⓘ    99.12 ▼0.08      │ 08/14 KTB10Y 입찰            │
│ [                  ] │ SWPT1M ᴹ  -1.85 ▼0.05                            │                              │
│                      │ ── 크레딧 ────────────────────────────────────── │                              │
│                      │ AA-3Y    3.290 ▲1.0   → SPD 44.5 ▼0.2            │                              │
│                      │ KR CDS5Y  [ 미수집 — 입력 ]                      │                              │
├──────────────────────┴──────────────────────────────────────────────────┼──────────────────────────────┤
│ 활성 포지션 블로터                                                      │ 무효화 조건 워치             │
│ ID   포지션              진입   현재   손익bp   DV01    보유  상태      │ #012 금통위 매파 선회        │
│ 012  국고 3-10 스티프너   45.0   27.5   -17.5   30.0M    3d   ●         │      ○유효 ◉흔들림 ○깨짐     │
│ 013  UST-KTB 스프레드    118.0  120.5    +2.5   20.0M    9d   ●         │ #013 미 CPI 3개월 연속 상회  │
│                                                                         │      ○유효 ○흔들림 ◉깨짐     │
└─────────────────────────────────────────────────────────────────────────┴──────────────────────────────┘
```

### 3.3 안 B — 「리스크 콘솔형」 (기각)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2026-08-11 TUE · D+47 · 미완료 2/5 · DATA 07:02 KST · MANUAL 5 · MISS 3                     [국내색상] │
├────────┬────────┬────────┬────────┬────────┬────────╥────────┬────────┬────────┬────────╥──────────────┤
│ 원화금리                                            ║ 스왑                              ║ 크레딧       │
│국고3Y  │국고10Y │ 3-10   │KTBF3Y  │KTBF10Y │CD91D   ║IRS1Y ᴹ │IRS3Y ᴹ │IRS5Y ᴹ │B/S 3Y  ║AA-3Y  →SPD  │
│  2.845 │  3.120 │   27.5 │ 106.12 │ 118.44 │  3.070 ║  2.780 │  2.910 │  3.040 │   -6.5 ║ 3.290   44.5 │
│  ▲1.2  │  ▲2.0  │  ▲0.8  │  ▼4t   │  ▼11t  │   —    ║  ▼0.5  │  ▲1.0  │  ▲1.5  │  ▲0.2  ║ ▲1.0   ▼0.2  │
├────────┼────────┼────────╥────────┼────────┼────────┼────────┼────────┼────────╥────────┴──────────────┤
│ 해외금리                 ║ FX                                                  ║                       │
│UST2Y   │UST10Y  │ 2s10s  ║USD/KRW │NDF1M ᴹ │USD/JPY │DXY  ⓘ  │SWPT1M ᴹ│KR CDS5Y║                       │
│  3.760 │  4.180 │   42.0 ║1382.40 │1381.90 │ 147.20 │  99.12 │  -1.85 │ ┌────┐ ║                       │
│  ▲3.0  │  ▲2.0  │  ▼1.0  ║  ▲2.10 │  ▲1.80 │  ▲0.35 │  ▼0.08 │  ▼0.05 │ │입력│ ║                       │
├──────────────────────────┴────────────────╥────────┴────────┴────────┴─┴────┴─╨───────────────────────┤
│ 야간장 NY                                 ║ ███ 무효화 조건 워치 ███          ║ 오늘의 루틴 (TUE)      │
│ [                                       ] ║                                   ║ ☑ 야간장   ☑ 스냅샷    │
│ 야간장 LDN                                ║ #012 국고 3-10 스티프너           ║ ☐ 왜 움직였나          │
│ [                                       ] ║      D+3   -17.5bp   목표 60/38   ║ ☐ 영문 브리핑          │
│ ───────────────────────────────────────── ║  └ 금통위 매파 선회               ║ ── 이번 주 ─────────── │
│ 왜 움직였나                               ║       ○유효  ◉흔들림  ○깨짐       ║ 수 shadowing 1건       │
│ [한 문장                                ] ║  └ 10년 입찰 강한 소화            ║ 금 리뷰 + 60초 드릴    │
│ ───────────────────────────────────────── ║       ◉유효  ○흔들림  ○깨짐       ╟────────────────────────┤
│ 영문 브리핑                               ║ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ║ 이번 주 이벤트         │
│ [                                       ] ║ ▓ #013 UST-KTB 스프레드         ▓ ║ 08/12 금통위 예상:동결 │
│ [                                       ] ║ ▓     D+9   +2.5bp              ▓ ║ 08/13 US CPI 예상:+0.3%│
│ [                                       ] ║ ▓  └ 미 CPI 3개월 연속 상회     ▓ ║ 08/14 KTB10Y 입찰      │
│ [                                       ] ║ ▓      ○유효 ○흔들림 ◉깨짐      ▓ ║                        │
│                                           ║ ▓  → 청산 검토  [[미 CPI 경로]] ▓ ║                        │
│                                           ║ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ║                        │
│                                           ║ 오늘 미점검 조건 1건              ║                        │
├───────────────────────────────────────────╨───────────────────────────────────╨────────────────────────┤
│ 활성 포지션 블로터                                                                                     │
│ ID   포지션              전략  진입   현재   손익bp  목표/손절   DV01    수급주체       보유  상태      │
│ 012  국고 3-10 스티프너  MOM    45.0   27.5   -17.5   60 / 38   30.0M   보험사 장기물   3d   흔들림    │
│ 013  UST-KTB 스프레드    MOM   118.0  120.5    +2.5  130 / 112  20.0M   외사 조달       9d   깨짐 ▲   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 비교와 선택

| 기준 | 안 A 블로터형 | 안 B 리스크 콘솔형 |
|---|---|---|
| 무효화 워치의 무게중심 | 우하단 구석 — 시선이 마지막에 닿는다 | **화면 정중앙** — 앉자마자 보인다 |
| 스냅샷 스캔성 | 카테고리별 세로 그룹, 라벨-값이 가까움 | 티커 밴드 2행. 카테고리 구분이 약해져 그룹 헤더·이중선으로 보완 필요 |
| 21개 셀 배치 | 중앙 열 하나에 세로로 쌓임 (세로 압박) | 가로 전폭에 펼침 (셀당 ~170×58px, 여유 있음) |
| 서술형 입력 공간 | 좌열이 좁아 영문 브리핑 4~5줄이 한계 | 좌열이 넓어 8줄 이상 확보 |
| 블로터 컬럼 수 | 8개 (전략·목표/손절·수급주체 생략) | **12개 전부** — 아이디어 레코드가 다 보인다 |
| 1440px 축소 | 중앙 열이 먼저 깨진다 | 티커 밴드가 3행으로 접히고 나머지 유지 — 열화가 완만 |
| 구현 난이도 | 낮음 (3열 그리드) | 중간 (밴드 정렬 + 중앙 강조 패널) |

~~**채택: 안 B.**~~ 요구사항이 "이 화면에서 가장 눈에 띄어야 할 단 하나의 패널"로 지정한 것이 무효화 조건 워치인데, 안 A는 그것을 구조적으로 구석에 놓는다. 안 B의 카테고리 가독성 손실은 그룹 헤더 행과 이중 세로선(`║`)으로 회복되지만, 안 A의 무게중심 문제는 레이아웃을 바꾸지 않으면 회복되지 않는다.

#### 결정 변경 — 안 A 채택 (2026-08-11, Phase 2 착수 시 사용자 결정)

위 결론은 **뒤집혔다.** 사용자가 안 A(3열 + 우하단 워치)를 선택했다. 안 B의 유일한 우위였던
"워치가 화면 정중앙"은 **구조가 아니라 시각 위계로 대체한다.** 화면에서 무효화 워치 패널만:

1. 패널 좌측에 3px 앰버 세로 바를 갖는다.
2. 헤더 배경이 앰버 틴트이고 제목이 앰버 + 14px (다른 패널 헤더는 11px `--fg-label`).
3. 강조색을 **면적으로** 쓰는 유일한 곳이다 — 나머지 화면은 앰버를 선과 기호로만 쓴다.
4. 상단 바의 `미점검 n` 이 상단에서 유일하게 앰버로 칠해져 이 패널을 가리킨다.

안 B가 해결하려던 나머지 문제도 안 A 안에서 처리됐다.

| 안 B가 지적한 안 A의 약점 | Phase 2 처리 |
|---|---|
| 좌열이 좁아 영문 브리핑이 4~5줄 한계 | 좌열 340px + 브리핑 칸이 남는 높이를 전부 차지(`1fr`) + 내부 스크롤 |
| 21셀이 중앙 열 하나에 세로로 쌓여 압박 | 스냅샷이 중단 두 행을 세로로 걸쳐 1176×548 확보. 카테고리 5그룹 × 4열 그리드 |
| 블로터 컬럼 8개로 축소 | 하단이 2열을 span 하므로 **11개 전부** 들어간다 |
| 1440px에서 중앙 열이 먼저 깨진다 | 브레이크포인트 1개에서 스냅샷 4열→3열로 접고 행 높이를 줄여 무스크롤 유지 (실측) |

### 3.5 시그니처 패널: 무효화 조건 워치

- 활성 포지션마다 사용자가 적어둔 무효화 조건을 **상시** 표시한다.
- 감시 대상은 손익이 아니라 **"내 논리가 아직 유효한가"** 다.
- 조건마다 상태 토글: **유효 / 흔들림 / 깨짐**. 클릭 즉시 `invalidation_check`에 그날 날짜로 저장된다.
- `깨짐`으로 바뀌면 해당 포지션 블록 전체가 경고색으로 전환되고, 블로터의 해당 행도 같이 전환된다.
- 그날 아직 점검하지 않은 조건 수를 패널 하단에 표시한다.

### 3.6 표시 규칙

- 전일 대비: 금리 → **bp**, FX → **원(전)**, 선물 → **틱**, 지수 → **포인트**. 전일 값이 없으면 `—`.
- `source='manual'` 값은 라벨 옆에 `ᴹ`, 자동 수집 불가로 정의된 필드는 `ⓘ`.
- 미수집 셀은 값 자리에 **인라인 입력창**. Tab만으로 21개 필드를 순서대로 채울 수 있어야 한다.
- 저장은 디바운스 자동 저장. 저장 버튼을 만들지 않는다.
- 값 갱신 시 해당 셀 150ms 플래시 1회. `prefers-reduced-motion` 존중.
- 색 규칙은 `app_setting.color_convention` (`kr` 기본: 상승 빨강/하락 파랑, `bbg`: 상승 초록/하락 빨강). **금리 상승은 좋지도 나쁘지도 않다.**

---

## 4. 기술적으로 어려운 지점과 대안

### 4-1. 21개 표시 셀 중 자동 수집이 확실한 것은 2~4개뿐이다

| 필드 | 상태 | 대응 |
|---|---|---|
| `ust_2y`, `ust_10y` | FRED `DGS2` / `DGS10` — 안정적 | 자동 |
| `usdjpy` | FRED `DEXJPUS` 후보 — **갱신 주기·지연 확인 필요** | 자동 시도 + 수동 보정 |
| `ktb_3y`, `ktb_10y`, `cd_91d`, `corp_aa3_yield_3y`, `usdkrw` | ECOS에 존재하나 **통계표코드·항목코드·주기 확인 필요** | 코드를 추측하지 말고 통계표목록 / 통계세부항목목록 API로 탐색한 뒤 `config/sources.py`에 확인 날짜와 함께 고정 |
| `dxy` | **DXY는 ICE 독점 지수. 무료 공개 API 없음.** FRED의 `DTWEXBGS` 등은 구성·가중치가 다른 별개 지수다 | 라벨을 실제 지수명으로 정직하게 바꾸거나, DXY는 수동 전용으로 두고 `ⓘ` 표시 |
| `ktbf_3y`, `ktbf_10y` | KRX 오픈API의 국채선물 제공 여부·엔드포인트 **확인 필요** | 확인 전까지 수동 |
| `irs_1y/3y/5y`, `swap_point_1m` | 서울외국환중개 고시. 공식 API 없음, 스크래핑은 불안정 | **수동 입력 기본.** 스크래핑은 Phase 5 이후 선택 |
| `ndf_1m` | 무료 공개 소스 사실상 없음 | 수동 전용 |
| `kr_cds_5y` | 무료 공개 소스 사실상 없음 | 수동 전용 |
| `corp_aa3_yield_3y` | ECOS에 있으나 만기 구분이 제한적일 수 있음 **확인 필요**. 금융투자협회 채권정보센터 API 존재 여부도 **확인 필요** | 자동 + 수동 보정 |

→ **대안**: 수동 입력을 예외가 아니라 **기본 경로**로 설계한다. 채우는 데 60초를 넘기면 이 도구는 버려진다.

### 4-2. ECOS 일별 데이터는 당일 아침에 없을 가능성이 높다

한국은행 통계는 통상 T+1 이후 확정 게시된다 (**확인 필요 — Phase 1에서 실제 호출로 검증**). 07:00 수집이 오늘 값을 못 채울 수 있다.

→ **대안**: 수집 대상을 "오늘"이 아니라 "가장 최근 게시일"로 두고, 상단 바에 `DATA AS OF` 날짜를 명시한다. 장중 값이 필요하면 그 필드만 수동으로 덮어쓴다. 16:00 2차 수집으로 당일치를 백필한다.

### 4-3. 활성 포지션의 현재가를 자동으로 못 매기는 경우가 생긴다

3-10 스티프너는 `curve_3s10s`로 산출되지만, "국고 5년 대 IRS 5년" 같은 포지션은 스냅샷 필드 조합으로 안 잡힌다.

→ **대안**: `idea.pricing_key`에 field_key 또는 파생키를 등록하고, 매핑이 불가능하면 `NULL`로 두어 `idea_mark`에 매일 수동 마킹한다. 자동 산출 손익과 수동 마킹을 화면에서 구분 표시한다. **없는 값을 추정해 채우지 않는다.**

### 4-4. DV01은 계산하지 않는다

진짜 DV01에는 커브 부트스트래핑과 채권 현금흐름이 필요하다. 그건 9~10월 딥다이브의 주제이지 대시보드의 기능이 아니다.

→ **대안**: 사용자가 입력한 명목 DV01(원)을 그대로 신뢰하고, 손익은 `result_bp × dv01_krw`로만 환산한다. 딥다이브에서 부트스트래핑을 구현한 뒤 같은 저장소의 모듈로 붙이는 것이 Phase 5 이후 과제다.

### 4-5. "스크롤 없는 1920×1080"은 실제로 940~990px이다

폰트 하한(라벨 11px, 값 15px)과 21개 셀, 서술형 입력 4종, 블로터, 워치 패널을 동시에 넣으면 여유가 거의 없다.

→ **대안**: (a) Chrome `--app` 모드 실행 `.bat`으로 크롬 UI를 없앤다, (b) 3.1의 높이 예산을 CSS Grid 고정 행으로 못박고 패널 내부만 `overflow-y`를 허용한다, (c) 영문 브리핑처럼 길어지는 입력은 패널 내부 스크롤로 처리한다.

### 4-6. 기록 유실은 SQLite가 아니라 사람과 동기화 때문에 생긴다

DB 엔진의 안정성은 문제가 아니다. 실제 위험은 ① 잘못 덮어쓴 값, ② 폴더 삭제/이동, ③ 클라우드 동기화 도구가 WAL 파일을 건드리는 것.

→ **대안**:
(a) WAL 모드 + `synchronous=FULL`
(b) 모든 덮어쓰기를 `market_observation_log`에 append-only로 남겨 되돌리기 가능하게
(c) 매일 `VACUUM INTO backups/ficc-YYYYMMDD.db` — 30일 롤링
(d) 주 1회 전체 테이블 CSV 내보내기 후 git 커밋 — **DB가 깨져도 텍스트가 남는다**
(e) 저장소를 클라우드 동기화 폴더 밖에 둔다 (결정 완료)

### 4-7. 연속 기록 일수의 정의가 애매하다

주말·공휴일·시험기간을 어떻게 셀 것인가. 국내 휴장일 자동 소스는 **확인 필요**.

→ **대안**: 한국 영업일 기준으로만 세고, 휴장일은 `app_setting.market_holidays_kr`의 수동 목록으로 관리한다. `counts_streak=1`인 일간 항목이 전부 완료된 날만 카운트한다. **게임화하지 않는다.**

### 4-8. PC가 꺼져 있으면 그날 데이터가 빈다

→ **대안**: 부팅 시 실행되는 백필 태스크를 두고, 마지막 성공 수집일 이후 영업일을 소급 수집한다. 소급된 값은 `captured_at`으로 구분된다.

### 4-9. 서술형 콘텐츠를 대시보드에서 편집하면 옵시디언과 충돌한다

→ **대안**: 원본 방향을 데이터 성격으로 나눈다. **양방향 동기화는 만들지 않는다.**

| 데이터 | 원본 | 방향 |
|---|---|---|
| 스냅샷 · 아이디어 · 체크리스트 · 이벤트 | SQLite | DB → 볼트 (내보내기) |
| 기관해부 · 상품분해 · 규제추적 · 딥다이브 | 볼트 | 볼트 → DB (읽기 전용 인덱스) |

볼트 경로는 `OBSIDIAN_VAULT_PATH`로 받고, `.obsidian/`은 절대 건드리지 않으며, 볼트 파일을 삭제하는 코드는 어떤 경우에도 쓰지 않는다. 옵시디언 쪽에서 **Dataview 플러그인 설치가 필요하다** (현재 미설치).

### 4-10. 도구를 만드는 일이 루틴을 대체할 위험

가장 현실적인 실패는 대시보드가 안 만들어지는 게 아니라, 만드는 데 두 달을 쓰고 기록이 0일인 것이다.

→ **대안**: Phase 3까지가 실사용 최소 단위다. **Phase 4·5·6은 실제로 3주(15영업일) 이상 매일 쓴 뒤에 착수한다.**

---

## 5. 구현 로드맵

| Phase | 범위 | 완료 조건 |
|---|---|---|
| **0** | 스펙 확정 | CLAUDE.md · SPEC.md (완료) |
| **1** | 스키마·마이그레이션, ECOS/FRED 수집, 수동 입력 API | `python -m ficc.ingest` 실행 시 채워진 필드 / 빈 필드가 콘솔 표로 출력된다. ECOS 코드는 탐색으로 확인한 뒤 주석과 함께 config에 기록. 스크래핑 금지. |
| **2** | 레이아웃 셸 + 디자인 시스템 (안 B), 더미 데이터 | 1920×1080 스크린샷에서 페이지 스크롤 없음 확인 |
| **3** | 데이터 연결, 인라인 입력(디바운스), 요일별 체크리스트, 아이디어 모달 | 마우스 없이 키보드만으로 하루치 입력 완주 |
| **게이트** | **3주 이상 매일 사용** | `routine_log` 기준 15영업일 이상 기록 |
| **4** | 서술형 템플릿 4종, 별도 라우트, `.md` 미러 | 메인 대시보드를 건드리지 않는다 |
| **5** | 작업 스케줄러 자동화, 백업, 월간 집계 뷰(`/monthly`), README | 빈 DB에서 처음부터 실행해 깨지는 곳 없음 |
| **6** | 옵시디언 단방향 내보내기, 볼트 노트 읽기 인덱스 | 내보내기를 두 번 실행해도 사용자 메모가 보존됨 |

### Phase 6 사전 확정 사항

볼트 안 폴더 구조 (`FICC-Desk/`): `00-Daily/` `10-Ideas/` `20-Weekly/` `30-Monthly/` `40-기관해부/` `50-상품분해/` `60-규제추적/` `70-딥다이브/` `90-Templates/`.
40~70은 사용자가 직접 작성하는 영역이라 **코드가 파일을 만들지 않는다.** 90-Templates에 빈 템플릿만 넣는다.

재생성 안전성: 파일명은 날짜/ID로 결정론적. 파일 하단에 마커를 두고 **마커 아래는 절대 덮어쓰지 않는다.**

```
<!-- BELOW THIS LINE IS YOURS -->
```

프론트매터에 정량 데이터를 넣어 Dataview로 조회 가능하게 한다 (`ktb3y`, `usdkrw`, `result_bp`, `postmortem` 등). 이 중 **사후분석 태그별 집계**가 가장 쓸모 있는 산출물이다.

---

## 6. "확인 필요" 목록

Phase 1 시작 전에 실제 호출로 검증하고, 확인된 값만 확인 날짜 주석과 함께 `config/sources.py`에 고정한다. **추측한 코드를 커밋하지 않는다.**

- [x] **ECOS 통계표코드 / 항목코드** (확인 2026-08-11, Phase 1) — 전부 `817Y002` 시장금리(일별),
      단위 연%: 국고채 3년 `010200000` · 10년 `010210000` · CD 91일 `010502000` ·
      회사채(3년, AA-) `010300000`. USD/KRW 는 `731Y003` / `0000003` 원/달러(종가 15:30), 단위 원.
      → `ficc/config/sources.py`
- [x] **ECOS 일별 데이터의 게시 지연** — **T+0**. 08-11(화) 당일 조회에서 `TIME=20260811` 행이 나왔다.
      단, 게시 *시각*은 확인하지 않았다. 07:00 수집은 전일치가 최신일 수 있으므로
      수집기는 계속 '가장 최근 게시분'을 취하고 `obs_date` 에 실제 관측일을 넣는다.
- [x] **ECOS 요청 URL 형식 및 응답 스키마** — 경로 삽입형
      `/api/{서비스}/{키}/json/kr/{시작}/{끝}/{통계표}/{주기}/{시작일}/{종료일}/{항목1..4}`.
      데이터 없음은 `{"RESULT":{"CODE":"INFO-200"}}` 봉투로 오며 오류가 아니다.
      일일 호출 한도는 여전히 **확인 필요** (탐색 중 한도에 걸리지 않았다).
- [x] **FRED 갱신 지연** — `DGS2`/`DGS10`/`DEXJPUS` 모두 **영업일 T+1**.
      08-10(월) 15:16 CDT 갱신 시점의 최신 관측일이 08-07(금)이었다.
- [x] **DXY** — 수동 입력 전용 + 화면 `ⓘ` (2026-08-11 결정). 대체 지수로 라벨을 바꾸지 않는다.
- [x] **KRX 국채선물 엔드포인트** — 제공된다.
      `GET https://data-dbg.krx.co.kr/svc/apis/drv/fut_bydd_trd?basDd=YYYYMMDD`,
      헤더 `AUTH_KEY`, 응답 `OutBlock_1[]` (`PROD_NM`, `ISU_NM`, `TDD_CLSPRC`, `ACC_TRDVOL` 등).
      인증키 활성화 후 실응답 확인(2026-08-11, basDd=20260810, 385행/34상품):
      `PROD_NM` 은 `'3년국채 선물'` / `'10년국채 선물'` (별개 상품 `'3년-10년국채선물스프레드 선물'`,
      한 글자 차이인 `'30년국채 선물'` 이 있어 **정확일치**로 고른다).
      한 상품 안에 결제월·캘린더스프레드·정규/야간이 섞여 오므로
      `MKT_NM='정규'` + `ACC_TRDVOL` 최대 행이 최근월물이다. 값은 `TDD_CLSPRC`.
      → `ktbf_3y`/`ktbf_10y` 자동 수집 (마이그레이션 `003`)
- [x] **KRX 게시 지연** — **최소 T+1**. 08-11(화) 18:58 KST 에 당일치가 0행이었다.
      07:00·16:00 수집에서는 국채선물이 항상 전일 종가다. 장중 레벨은 수동 덮어쓰기.
- [ ] 금융투자협회 채권정보센터의 공개 API 존재 여부
- [ ] 한국 휴장일 자동 소스 존재 여부
- [ ] 연합인포맥스 학교 도서관 접근 가능 여부 (가능하면 수동 입력 소스로 활용)
