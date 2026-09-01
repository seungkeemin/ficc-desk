# ficc-desk

FICC 트레이딩 데스크 루틴을 매일 실행하기 위한 1인용 로컬 웹 대시보드다.
금리·FX·크레딧 지표를 자동 수집해 한 화면에 모으고, 루틴 체크·관측 기록·
페이퍼 트레이딩 아이디어를 같은 자리에서 남긴다.

목적은 수익이 아니라 **규율과 기록**이다. 실제 자금은 없고 모든 포지션은
페이퍼 트레이딩이다. 사용자 1명, 로컬 실행, 인증 없음, 인터넷 배포 없음을
전제로 설계했다.

- 설계 문서: [SPEC.md](SPEC.md)
- 운영 규칙 / 코드 스타일: [CLAUDE.md](CLAUDE.md)
- 수동 입력 필드와 출처: [docs/manual_fields.md](docs/manual_fields.md)

## 스택

Python 3.14 · FastAPI + Uvicorn · Jinja2 서버 렌더링 · SQLite(WAL) ·
번호순 `.sql` 마이그레이션 · httpx · pytest. 프론트엔드 빌드 단계가 없다.

## 데이터 소스

| 소스 | 용도 | 키 |
|---|---|---|
| 한국은행 ECOS | 원화 금리, 회사채, USD/KRW 등 | `ECOS_API_KEY` |
| 세인트루이스 연준 FRED | UST, SOFR, OAS, VIX 등 | `FRED_API_KEY` |
| 한국거래소 Data Marketplace | 국채선물 종가·미결제약정 | `KRX_AUTH_KEY` |

공개 소스가 없는 필드(IRS, NDF, DXY, 한국 CDS 등)는 수동 입력이다.
키가 비어 있으면 해당 필드만 "키 없음"으로 표시되고 수집은 죽지 않는다.

## 시작하기

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

`.env.example` 을 `.env` 로 복사하고 API 키를 채운다.

```bash
copy .env.example .env
```

서버를 띄운다. DB 마이그레이션은 기동 시 자동으로 적용된다.

```bash
.venv\Scripts\python -m uvicorn ficc.app:app --port 8787 --reload
```

수집을 한 번 돌린다.

```bash
.venv\Scripts\python -m ficc.ingest
```

`127.0.0.1:8787` 을 연다. (`localhost` 가 아니라 `127.0.0.1` 을 쓰는 이유는
CLAUDE.md 코드 스타일 항목에 적혀 있다.)

## Windows 편의 스크립트

| 스크립트 | 하는 일 |
|---|---|
| `scripts\install_shortcut.ps1` | 바탕화면 실행 아이콘 생성 |
| `scripts\register_tasks.ps1` | 하루 3회 수집 + 마지막 회차 백업 작업 등록 |
| `scripts\unregister_tasks.ps1` | 위 작업 해제 |
| `scripts\backup.py` | `VACUUM INTO` 백업 (30일 롤링) |

## 테스트

```bash
.venv\Scripts\python -m pytest
```

## 저장소에 없는 것

`data/` 의 SQLite DB, `backups/`, `.env` 는 커밋하지 않는다. 시계열 원본은
git 이 아니라 백업 파일과 CSV 내보내기로 보존한다.
