"""단일 화면 라우트.

기본값은 실제 DB 다. `?data=demo` / `?data=empty` 는 Phase 2 의 코드 픽스처를 그대로
그린다 — 레이아웃 회귀를 눈으로 확인하기 위한 것이고, DB 를 건드리지 않는다.

포맷팅은 템플릿이 아니라 ficc/formatting.py 에 둔다. Jinja 안에 숫자 규칙이 흩어지면
'값 없음'과 '0' 이 언젠가 섞인다 (CLAUDE.md 1). 인라인 저장 응답도 같은 함수를 쓴다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import dashboard as builder
from .. import db, demo, formatting
from ..config.settings import REPO_ROOT
from .deps import Conn

router = APIRouter(tags=["dashboard"])

templates = Jinja2Templates(directory=str(REPO_ROOT / "ficc" / "templates"))

for _name, _fn in formatting.FILTERS:
    templates.env.filters[_name] = _fn


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    conn: Conn,
    data: Annotated[str, Query(pattern="^(live|demo|empty)$")] = "live",
) -> HTMLResponse:
    """오늘(KST)의 화면. demo/empty 는 레이아웃 회귀 확인용 픽스처다."""
    convention = db.setting(conn, "color_convention", "kr")
    if convention not in {"kr", "bbg"}:
        convention = "kr"

    if data == "demo":
        view = demo.build_demo(convention)
    elif data == "empty":
        view = demo.build_empty(convention)
    else:
        view = builder.build(conn, color_convention=convention)

    return templates.TemplateResponse(request, "dashboard.html", {
        "vm": view,
        "mode": data,
        # 아이디어 모달의 '손익 기준' 선택지. 표시 순서·라벨은 코드가 아니라 데이터다.
        "field_defs": db.field_defs(conn),
    })
