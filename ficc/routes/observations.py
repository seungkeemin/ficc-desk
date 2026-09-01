"""수동 입력 API.

자동 수집이 안 되는 필드(KRW IRS, 스왑포인트, 한국 CDS, 1M NDF, DXY)를 저장하고,
자동 수집된 값도 여기서 덮어쓴다. 덮어쓴 값은 source='manual' 로 기록되고
이전 값은 market_observation_log 에 남는다 (CLAUDE.md 4).

삭제 엔드포인트는 만들지 않는다. append-only 로그를 유지하는 이상 되돌리기는
'원래 값을 다시 넣는 것'이지 '행을 지우는 것'이 아니다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .. import dashboard as builder
from .. import db, derived, formatting
from ..config.settings import canonical_date
from .deps import Conn

router = APIRouter(prefix="/api", tags=["market"])


class ObservationIn(BaseModel):
    obs_date: str = Field(description="관측일 YYYY-MM-DD (KST)")
    field_key: str
    value: float
    note: str | None = None

    @field_validator("obs_date")
    @classmethod
    def _valid_date(cls, raw: str) -> str:
        return canonical_date(raw)


def _validate_date(raw: str) -> str:
    try:
        return canonical_date(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/fields")
def list_fields(conn: Conn) -> list[dict[str, Any]]:
    """필드 사전. 표시 순서·단위·소수자리·자동 수집 여부가 전부 여기 있다."""
    return [dict(row) for row in db.field_defs(conn, active_only=False)]


@router.get("/snapshot/{obs_date}")
def snapshot(obs_date: str, conn: Conn) -> dict[str, Any]:
    """그 날짜 기준 스냅샷. 저장값 + 파생값 + 전일 대비.

    값이 없는 필드는 status='miss' 로 내려간다. 0 으로 채우지 않는다 (CLAUDE.md 1).
    """
    day = _validate_date(obs_date)
    stored = db.latest_on_or_before(conn, day)

    fields: list[dict[str, Any]] = []
    values: dict[str, float | None] = {}

    for definition in db.field_defs(conn):
        key = definition["field_key"]
        if definition["is_derived"]:
            continue

        obs = stored.get(key)
        values[key] = obs["value"] if obs else None

        entry: dict[str, Any] = {
            "field_key": key,
            "label_ko": definition["label_ko"],
            "label_short": definition["label_short"],
            "category": definition["category"],
            "unit": definition["unit"],
            "decimals": definition["decimals"],
            "delta_unit": definition["delta_unit"],
            "display_order": definition["display_order"],
            "auto_provider": definition["auto_provider"],
            "value": None,
            "source": None,
            "provider": None,
            "as_of": None,
            "captured_at": None,
            "delta": None,
            "stale": None,
            "status": "miss",
        }

        if obs is not None:
            prev = db.previous_observation(conn, key, obs["obs_date"])
            entry.update(
                value=obs["value"],
                source=obs["source"],
                provider=obs["provider"],
                as_of=obs["obs_date"],
                captured_at=obs["captured_at"],
                delta=derived.delta_in_display_unit(
                    obs["value"],
                    prev["value"] if prev else None,
                    definition["delta_unit"],
                ),
                stale=obs["obs_date"] != day,
                status="ok",
            )
        fields.append(entry)

    derived_entries = []
    for key, spec in derived.REGISTRY.items():
        result = derived.compute(key, values)
        derived_entries.append({
            "field_key": key,
            "label_ko": spec.label_ko,
            "label_short": spec.label_short,
            "unit": spec.unit,
            "decimals": spec.decimals,
            "inputs": list(spec.inputs),
            "value": result,
            "missing_inputs": derived.missing_inputs(key, values),
            "status": "ok" if result is not None else "miss",
        })

    return {"obs_date": day, "fields": fields, "derived": derived_entries}


@router.put("/observation")
def put_observation(payload: ObservationIn, conn: Conn) -> dict[str, Any]:
    """수동 저장·덮어쓰기. 자동 수집값도 여기서 덮어쓸 수 있다.

    응답에 화면이 되그릴 셀(cells)과 상단 바 카운트(header)를 함께 싣는다.
    포맷은 서버가 한다 — 자릿수 규칙이 클라이언트에도 있으면 언젠가 어긋난다.
    """
    definition = db.field_def(conn, payload.field_key)
    if definition is None:
        raise HTTPException(422, f"모르는 field_key: {payload.field_key}")
    if definition["is_derived"] or derived.is_derived(payload.field_key):
        spec = derived.REGISTRY.get(payload.field_key)
        inputs = ", ".join(spec.inputs) if spec else (definition["derived_from"] or "")
        raise HTTPException(
            422,
            f"{payload.field_key} 는 파생값이다. 저장하지 않고 조회 시 계산한다."
            + (f" 구성 필드({inputs})를 입력하라." if inputs else ""),
        )

    action = db.upsert_observation(
        conn, payload.obs_date, payload.field_key, payload.value,
        source="manual", provider="user", note=payload.note,
    )
    row = conn.execute(
        "SELECT * FROM market_observation WHERE obs_date = ? AND field_key = ?",
        (payload.obs_date, payload.field_key),
    ).fetchone()

    cells, counts = builder.cell_updates(conn, payload.obs_date, payload.field_key)
    return {
        "action": action,
        "observation": dict(row),
        "cells": {key: formatting.cell_payload(cell) for key, cell in cells.items()},
        "header": counts,
    }


@router.get("/observation/{obs_date}/{field_key}/log")
def observation_history(obs_date: str, field_key: str, conn: Conn) -> list[dict[str, Any]]:
    """덮어쓰기 이력. 잘못 넣은 값을 되돌릴 때 여기서 이전 값을 찾는다."""
    day = _validate_date(obs_date)
    return [dict(row) for row in db.observation_log(conn, field_key, day)]


@router.get("/ingest/last")
def last_ingest(conn: Conn) -> dict[str, Any]:
    """마지막 수집 실행과 필드별 사유. 화면의 'MISS n' 표시가 여기서 나온다."""
    result = db.last_run(conn)
    if result is None:
        return {"run": None, "results": []}
    return result
