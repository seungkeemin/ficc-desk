"""서술형 4칸의 저장.

야간장 NY/LDN · 왜 움직였나 · 영문 브리핑. 화면이 디바운스로 보내고 여기는 한 칸씩 쓴다.
통째로 받으면 두 칸의 디바운스가 겹칠 때 늦게 도착한 요청이 다른 칸을 되돌린다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from .. import db
from ..config.settings import canonical_date
from .deps import Conn

router = APIRouter(prefix="/api", tags=["journal"])


class JournalIn(BaseModel):
    obs_date: str
    column: str
    text: str | None = None

    @field_validator("obs_date")
    @classmethod
    def _valid_date(cls, raw: str) -> str:
        return canonical_date(raw)


@router.put("/journal")
def put_journal(payload: JournalIn, conn: Conn) -> dict[str, Any]:
    if payload.column not in db.JOURNAL_FIELDS:
        raise HTTPException(422, f"모르는 저널 칸: {payload.column}")

    # 공백만 남은 칸은 '안 썼다'로 저장한다. 빈 문자열과 NULL 을 섞지 않는다.
    text = (payload.text or "").strip() or None
    db.upsert_journal_field(conn, payload.obs_date, payload.column, text)
    return {"obs_date": payload.obs_date, "column": payload.column, "stored": text is not None}
