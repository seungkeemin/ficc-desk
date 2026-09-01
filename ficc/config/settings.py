"""경로·API 키·시각 헬퍼.

.env 파싱에 python-dotenv 를 쓰지 않는다. 필요한 문법이 `KEY=VALUE` 뿐이고,
의존성이 하나 늘 때마다 1년 뒤 실행이 안 될 확률이 올라간다 (CLAUDE.md: 표준 라이브러리 우선).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"

# 한국 표준시. zoneinfo 는 Windows 에서 tzdata 패키지를 요구하는데,
# KST 는 서머타임이 없어 고정 오프셋이 정확하다. 의존성을 늘리지 않는다.
KST = timezone(timedelta(hours=9), "KST")


def load_env(path: Path | None = None) -> dict[str, str]:
    """.env 를 읽어 os.environ 에 넣는다. 이미 설정된 환경변수는 덮어쓰지 않는다.

    파일이 없어도 예외를 내지 않는다 — 키 없이도 스키마·수동입력은 동작해야 한다.
    """
    path = path or (REPO_ROOT / ".env")
    parsed: dict[str, str] = {}
    if not path.exists():
        return parsed

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        parsed[key] = value
        os.environ.setdefault(key, value)
    return parsed


def env(key: str, default: str = "") -> str:
    load_env()
    return os.environ.get(key, default) or default


def db_path() -> Path:
    """DB 파일 경로. 부모 디렉터리가 없으면 만든다."""
    configured = env("FICC_DB_PATH")
    path = Path(configured) if configured else REPO_ROOT / "data" / "ficc.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def now_kst() -> str:
    """ISO8601 + +09:00. 모든 captured_at / created_at 이 이 형식을 쓴다."""
    return datetime.now(KST).isoformat(timespec="seconds")


def today_kst() -> date:
    return datetime.now(KST).date()


def as_ymd(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def as_compact(value: date) -> str:
    """ECOS(D 주기)·KRX 가 요구하는 YYYYMMDD."""
    return value.strftime("%Y%m%d")


def canonical_date(raw: str) -> str:
    """'YYYY-MM-DD' 인지 엄격히 검사하고 그대로 돌려준다.

    obs_date 는 전부 문자열로 비교·정렬된다(BETWEEN, MAX, obs_date < ?).
    '2026-8-11' 같은 값이 한 줄이라도 섞이면 정렬이 조용히 어긋나 시계열이 깨진다.
    strptime 은 0 패딩을 강제하지 않으므로 fromisoformat 으로 막는다.
    """
    text = raw.strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"날짜는 YYYY-MM-DD 여야 한다: {raw!r}") from exc
    if as_ymd(parsed) != text:
        raise ValueError(f"날짜는 YYYY-MM-DD 여야 한다: {raw!r}")
    return text
