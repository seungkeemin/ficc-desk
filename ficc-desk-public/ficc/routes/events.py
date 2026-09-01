"""이벤트 등록과 인라인 수정.

월요일 루틴은 '이벤트 캘린더 + 내 예상' 이다. 등록 수단이 화면에 없으면 그 체크박스는
거짓말이 된다. 컨센서스는 남이 만든 숫자라 인라인 대상이 아니고, 고치는 것은
내 예상·실제·판정뿐이다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .. import db
from ..config.settings import canonical_date
from .deps import Conn

router = APIRouter(prefix="/api", tags=["event"])

REGIONS = frozenset({"KR", "US", "EU", "JP", "CN"})


class EventIn(BaseModel):
    event_date: str
    region: str
    name: str = Field(min_length=1)
    event_time: str | None = None
    consensus: str | None = None

    @field_validator("event_date")
    @classmethod
    def _valid_date(cls, raw: str) -> str:
        return canonical_date(raw)


class EventPatch(BaseModel):
    column: str
    value: str | None = None


@router.post("/event", status_code=201)
def post_event(payload: EventIn, conn: Conn) -> dict[str, Any]:
    if payload.region not in REGIONS:
        raise HTTPException(422, f"region 은 {'|'.join(sorted(REGIONS))}: {payload.region}")

    event_id = db.create_event(
        conn,
        event_date=payload.event_date,
        region=payload.region,
        name=payload.name.strip(),
        event_time=payload.event_time,
        consensus=payload.consensus,
    )
    return {"id": event_id}


@router.patch("/event/{event_id}")
def patch_event(event_id: int, payload: EventPatch, conn: Conn) -> dict[str, Any]:
    # 빈 칸은 '안 썼다'로 되돌린다 — 빈 문자열을 기록으로 남기지 않는다.
    value = (payload.value or "").strip() or None
    try:
        found = db.patch_event(conn, event_id, payload.column, value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not found:
        raise HTTPException(404, f"모르는 이벤트: {event_id}")
    return {"id": event_id, "column": payload.column, "value": value}
