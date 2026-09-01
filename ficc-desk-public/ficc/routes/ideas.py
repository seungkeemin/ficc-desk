"""아이디어 생성과 수동 마킹.

무효화 조건 최소 1건은 **여기가 권위다** (CLAUDE.md 7). 화면의 required 는 편의일 뿐이고,
curl 로 직접 POST 해도 통과해서는 안 된다. db.create_idea() 가 트랜잭션을 열기 전에
검사하므로 실패해도 idea 행이 만들어졌다 지워지는 일조차 없다.

청산 엔드포인트는 만들지 않는다 — 이번 범위는 생성까지다.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .. import dashboard as builder
from .. import db, formatting
from ..config.settings import canonical_date
from .deps import Conn

router = APIRouter(prefix="/api", tags=["idea"])


class IdeaIn(BaseModel):
    position: str = Field(min_length=1)
    strategy: str
    dv01_krw: float
    holding_days: int = Field(ge=0)
    level_unit: str
    entry_level: float
    target_level: float
    stop_level: float
    opened_on: str
    flow_agent: str | None = None
    pricing_key: str | None = None
    theses: list[str] = Field(default_factory=list)
    invalidations: list[str] = Field(default_factory=list)

    @field_validator("opened_on")
    @classmethod
    def _valid_date(cls, raw: str) -> str:
        return canonical_date(raw)


class MarkIn(BaseModel):
    mark_date: str
    level: float

    @field_validator("mark_date")
    @classmethod
    def _valid_date(cls, raw: str) -> str:
        return canonical_date(raw)


@router.post("/idea", status_code=201)
def post_idea(payload: IdeaIn, conn: Conn) -> dict[str, Any]:
    if payload.pricing_key:
        definition = db.field_def(conn, payload.pricing_key)
        if definition is None:
            raise HTTPException(422, f"모르는 손익 기준: {payload.pricing_key}")

    fields = payload.model_dump(exclude={"theses", "invalidations"})
    try:
        idea_id, code = db.create_idea(
            conn,
            fields=fields,
            theses=payload.theses,
            invalidations=payload.invalidations,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, f"저장할 수 없다: {exc}") from exc

    return {"id": idea_id, "code": code}


@router.put("/idea/{idea_id}/mark")
def put_mark(idea_id: int, payload: MarkIn, conn: Conn) -> dict[str, Any]:
    """pricing_key 가 없는 포지션의 그날 레벨. 없는 값을 추정해 채우지 않는다 (SPEC 4-3)."""
    row = conn.execute(
        "SELECT pricing_key FROM idea WHERE id = ?", (idea_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"모르는 아이디어: {idea_id}")
    if row["pricing_key"]:
        raise HTTPException(
            422,
            f"이 포지션은 {row['pricing_key']} 로 자동 산출된다. 수동 마킹 대상이 아니다.",
        )

    db.upsert_idea_mark(conn, idea_id, payload.mark_date, payload.level)

    positions, _ = builder.position_summary(conn, payload.mark_date)
    updated = next((p for p in positions if p.id == idea_id), None)
    if updated is None:
        return {"id": idea_id}
    return {
        "id": idea_id,
        "current_level": formatting.fmt_level(updated.current_level),
        "pnl_bp": formatting.fmt_signed(updated.pnl_bp),
        "dir": formatting.dir_class(updated.pnl_bp),
    }
