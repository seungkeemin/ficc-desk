"""무효화 조건 점검의 저장 — 시그니처 패널이 쓰는 유일한 쓰기 경로.

SPEC 3.5: 클릭 즉시 그날 날짜로 저장된다. '깨짐' 이 되면 그 포지션 블록과 블로터 행이
함께 경고색으로 바뀌므로, 응답에 그 포지션의 최신 상태를 실어 돌려준다.
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

router = APIRouter(prefix="/api", tags=["watch"])


class CheckIn(BaseModel):
    check_date: str
    state: str
    note: str | None = None

    @field_validator("check_date")
    @classmethod
    def _valid_date(cls, raw: str) -> str:
        return canonical_date(raw)


@router.put("/invalidation/{invalidation_id}/check")
def put_check(invalidation_id: int, payload: CheckIn, conn: Conn) -> dict[str, Any]:
    exists = conn.execute(
        "SELECT idea_id FROM invalidation WHERE id = ?", (invalidation_id,)
    ).fetchone()
    if exists is None:
        raise HTTPException(404, f"모르는 무효화 조건: {invalidation_id}")

    try:
        db.upsert_invalidation_check(
            conn, invalidation_id, payload.check_date, payload.state, payload.note
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc

    positions, unchecked = builder.position_summary(conn, payload.check_date)
    return {
        "invalidation_id": invalidation_id,
        "state": payload.state,
        "unchecked_count": unchecked,
        "positions": [
            {"id": position.id, "worst_state": position.worst_state}
            for position in positions
        ],
    }
