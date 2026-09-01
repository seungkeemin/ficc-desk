"""요일별 체크리스트의 저장.

체크 하나가 상단 바의 '오늘 미완료'와 '연속'을 동시에 바꾼다. 응답에 둘 다 실어서
화면이 새로고침 없이 맞춰지게 한다 — 두 숫자를 클라이언트가 따로 계산하면
서버와 어긋난 화면이 만들어진다.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from .. import dashboard as builder
from .. import db
from ..config.settings import canonical_date
from .deps import Conn

router = APIRouter(prefix="/api", tags=["routine"])


class RoutineIn(BaseModel):
    task_date: str
    routine_key: str
    done: bool

    @field_validator("task_date")
    @classmethod
    def _valid_date(cls, raw: str) -> str:
        return canonical_date(raw)


@router.put("/routine")
def put_routine(payload: RoutineIn, conn: Conn) -> dict[str, Any]:
    try:
        db.set_routine_done(conn, payload.task_date, payload.routine_key, payload.done)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, f"모르는 루틴: {payload.routine_key}") from exc

    return {
        "routine_key": payload.routine_key,
        "done": payload.done,
        "header": builder.routine_counts(conn, payload.task_date),
    }
