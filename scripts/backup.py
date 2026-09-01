"""DB 백업. VACUUM INTO 로 backups/ficc-YYYYMMDD.db 를 만들고 30일치만 남긴다.

    .venv\\Scripts\\python scripts\\backup.py

VACUUM INTO 를 쓰는 이유: 파일 복사가 아니라 SQLite 가 스스로 만드는 정합성 있는
스냅샷이다. WAL 모드에서 data/ficc.db 만 복사하면 아직 본체에 반영되지 않은 -wal
내용이 빠져 조용히 과거 상태의 DB 가 나온다. VACUUM INTO 는 WAL 을 포함한 현재
상태를 담고, 결과가 조각모음된 단일 파일이라 그대로 열어 볼 수 있다.

하루 한 번, 23:30 수집 회차에 함께 돈다 (scripts/register_tasks.ps1).
백업이 실패해도 수집은 이미 끝난 뒤이므로 그날 데이터가 사라지지 않는다.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ficc.config.settings import REPO_ROOT, db_path, today_kst  # noqa: E402

KEEP_DAYS = 30
NAME_PREFIX = "ficc-"
NAME_SUFFIX = ".db"


def backup_dir() -> Path:
    path = REPO_ROOT / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp(day: date) -> str:
    return f"{NAME_PREFIX}{day:%Y%m%d}{NAME_SUFFIX}"


def _parse_stamp(name: str) -> date | None:
    """백업 파일명에서 날짜를 뽑는다. 형식이 정확히 맞지 않으면 None.

    삭제 대상을 이름으로만 고르기 때문에 여기서 엄격해야 한다. 사용자가 손으로
    떠 둔 ficc-before-migration.db 같은 파일을 롤링이 지우면 안 된다.
    """
    if not (name.startswith(NAME_PREFIX) and name.endswith(NAME_SUFFIX)):
        return None
    digits = name[len(NAME_PREFIX):-len(NAME_SUFFIX)]
    if len(digits) != 8 or not digits.isdigit():
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
    except ValueError:
        return None


def vacuum_into(source: Path, target: Path) -> None:
    """VACUUM INTO 는 대상 파일이 이미 있으면 실패한다. 임시 파일을 거쳐 교체한다.

    하루에 여러 번 돌려도 그날 파일이 최신으로 갱신되고, 도중에 죽어도 기존
    백업이 반쯤 덮인 상태로 남지 않는다.
    """
    tmp = target.with_suffix(".db.partial")
    tmp.unlink(missing_ok=True)

    conn = sqlite3.connect(source)
    try:
        conn.execute("VACUUM INTO ?", (str(tmp),))
    finally:
        conn.close()

    os.replace(tmp, target)


def prune(directory: Path, today: date, keep_days: int = KEEP_DAYS) -> list[Path]:
    """오늘 기준 keep_days 보다 오래된 백업을 지운다. 지운 목록을 돌려준다."""
    cutoff = today - timedelta(days=keep_days)
    removed: list[Path] = []
    for path in sorted(directory.glob(f"{NAME_PREFIX}*{NAME_SUFFIX}")):
        stamped = _parse_stamp(path.name)
        if stamped is None or stamped >= cutoff:
            continue
        path.unlink()
        removed.append(path)
    return removed


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    source = db_path()
    if not source.exists():
        print(f"DB 가 없다: {source}")
        return 1

    today = today_kst()
    directory = backup_dir()
    target = directory / _stamp(today)

    vacuum_into(source, target)
    size_mb = target.stat().st_size / 1024 / 1024
    print(f"백업 {target}  {target.stat().st_size:,} bytes ({size_mb:.2f} MB)")

    for path in prune(directory, today):
        print(f"만료 삭제 {path.name}")

    kept = sorted(p.name for p in directory.glob(f"{NAME_PREFIX}*{NAME_SUFFIX}"))
    print(f"보관 중 {len(kept)}개 (최대 {KEEP_DAYS}일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
