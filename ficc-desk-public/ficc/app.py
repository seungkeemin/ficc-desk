"""FastAPI 엔트리.

  .venv\\Scripts\\python -m uvicorn ficc.app:app --port 8787 --reload

Phase 1 이 데이터 레이어를, Phase 2 가 단일 화면 셸을, Phase 3 이 둘을 연결했다.
화면의 모든 입력은 저장 버튼 없이 여기 API 로 곧장 들어온다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .config.settings import REPO_ROOT
from .routes import (
    dashboard, events, ideas, journal, observations, routines, settings, watch,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """기동 시 마이그레이션을 적용한다. 빈 DB 에서 처음 켜도 깨지지 않아야 한다."""
    conn = db.connect()
    try:
        db.migrate(conn)
    finally:
        conn.close()
    yield


app = FastAPI(
    title="ficc-desk",
    description="FICC 데스크 루틴 대시보드 — 데이터 연결 · 인라인 입력",
    version="0.3.0",
    lifespan=lifespan,
)
app.mount(
    "/static",
    StaticFiles(directory=REPO_ROOT / "ficc" / "static"),
    name="static",
)
app.include_router(dashboard.router)
app.include_router(observations.router)
app.include_router(journal.router)
app.include_router(routines.router)
app.include_router(watch.router)
app.include_router(ideas.router)
app.include_router(events.router)
app.include_router(settings.router)
