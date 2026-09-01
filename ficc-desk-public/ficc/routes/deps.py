"""라우트 공통 의존성.

커넥션 의존성이 라우트 모듈마다 한 벌씩 있으면 테스트에서
`app.dependency_overrides` 로 갈아끼울 대상이 여러 개가 된다.
하나만 둔다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends

from .. import db


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
