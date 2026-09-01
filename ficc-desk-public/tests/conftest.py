from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from ficc import db


@pytest.fixture(autouse=True)
def isolate_db(tmp_path: Path, monkeypatch) -> None:
    """테스트가 사용자의 data/ficc.db 를 열지 않게 한다.

    FastAPI 의 lifespan 이 기동 때 db.connect() 로 마이그레이션을 돌린다. 멱등이라
    망가뜨리진 않지만, 테스트가 실제 기록 파일을 여는 일 자체를 만들지 않는다.
    """
    monkeypatch.setenv("FICC_DB_PATH", str(tmp_path / "app.db"))


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """테스트 DB 파일. API 테스트는 요청마다 여기에 따로 연결한다 —
    sqlite3 커넥션은 만든 스레드에서만 쓸 수 있고 TestClient 는 스레드풀을 쓴다."""
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_file: Path) -> Iterator[sqlite3.Connection]:
    """마이그레이션이 적용된 빈 DB. 사용자의 data/ficc.db 는 건드리지 않는다."""
    connection = db.connect(db_file)
    db.migrate(connection)
    try:
        yield connection
    finally:
        connection.close()
