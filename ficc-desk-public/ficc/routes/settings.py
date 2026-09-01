"""app_setting 쓰기. 지금은 색 관례 하나뿐이다.

전체 설정을 열지 않는다 — obsidian_vault_path 나 market_holidays_kr 을 화면에서
고치게 하면 잘못된 값 하나로 저장 경로나 연속 기록이 조용히 틀어진다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from .deps import Conn

router = APIRouter(prefix="/api", tags=["setting"])

CONVENTIONS = frozenset({"kr", "bbg"})


class ConventionIn(BaseModel):
    value: str


@router.put("/setting/color_convention")
def put_convention(payload: ConventionIn, conn: Conn) -> dict[str, Any]:
    if payload.value not in CONVENTIONS:
        raise HTTPException(422, f"color_convention 은 kr|bbg: {payload.value}")
    db.set_setting(conn, "color_convention", payload.value)
    return {"color_convention": payload.value}
