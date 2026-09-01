"""인라인 입력 API.

화면이 저장 버튼 없이 쓰는 경로들이다. 여기서 지켜야 할 것은 두 가지 —
서버가 최종 방어선이고(무효화 최소 1건, 파생값 거부), 응답만으로 화면을 맞출 수 있어야 한다
(저장한 셀 + 딸린 파생 셀 + 상단 바 카운트).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ficc import db
from ficc.app import app
from ficc.routes import deps

DAY = "2026-08-11"

IDEA = {
    "position": "국고 3-10 스티프너",
    "strategy": "momentum",
    "dv01_krw": 30_000_000,
    "holding_days": 10,
    "level_unit": "bp",
    "entry_level": 45.0,
    "target_level": 60.0,
    "stop_level": 38.0,
    "opened_on": DAY,
    "pricing_key": "curve_3s10s",
    "theses": ["논리"],
    "invalidations": ["금통위가 매파로 선회"],
}


@pytest.fixture
def client(conn, db_file: Path) -> Iterator[TestClient]:
    """테스트 DB 를 쓰는 클라이언트. get_conn 이 한 곳이라 갈아끼우기가 한 줄이다.

    요청마다 새로 연결한다 — TestClient 는 동기 라우트를 스레드풀에서 돌리고,
    sqlite3 커넥션은 만든 스레드 밖에서 쓸 수 없다. 운영에서도 요청당 1 커넥션이다.
    """
    def override():
        connection = db.connect(db_file)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[deps.get_conn] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ 화면


def test_dashboard_renders_on_empty_db(client) -> None:
    """처음 켠 날 화면이 깨지면 이 도구는 그날로 끝난다."""
    response = client.get("/")
    assert response.status_code == 200
    assert "마켓 스냅샷" in response.text
    assert 'data-mode="live"' in response.text


@pytest.mark.parametrize("mode", ["demo", "empty"])
def test_fixture_modes_still_render(client, mode: str) -> None:
    """레이아웃 회귀 확인용 픽스처는 살아 있어야 하고, 저장을 연결하지 않는다."""
    response = client.get(f"/?data={mode}")
    assert response.status_code == 200
    assert f'data-mode="{mode}"' in response.text


def test_unknown_mode_is_rejected(client) -> None:
    assert client.get("/?data=prod").status_code == 422


# -------------------------------------------------------------- 관측값


def test_put_observation_returns_cell_and_header(client) -> None:
    response = client.put("/api/observation", json={
        "obs_date": DAY, "field_key": "irs_3y", "value": 2.910,
    })
    assert response.status_code == 200
    body = response.json()

    assert body["action"] == "insert"
    assert body["observation"]["source"] == "manual"
    assert body["cells"]["irs_3y"]["value"] == "2.910"
    assert body["cells"]["irs_3y"]["mark"] == "ᴹ"
    assert body["cells"]["irs_3y"]["delta"] == "—"      # 전일 값이 없으면 0 이 아니다
    assert body["header"]["manual_count"] == 1
    assert body["header"]["miss_count"] == 40


def test_put_observation_includes_dependent_derived_cell(client) -> None:
    """irs_3y 를 넣으면 bond_swap_3y 가 같이 살아나야 한다 — 새로고침 없이."""
    client.put("/api/observation", json={
        "obs_date": DAY, "field_key": "ktb_3y", "value": 2.845})
    body = client.put("/api/observation", json={
        "obs_date": DAY, "field_key": "irs_3y", "value": 2.910}).json()

    assert set(body["cells"]) == {"irs_3y", "bond_swap_3y"}
    assert body["cells"]["bond_swap_3y"]["value"] == "-6.5"
    assert body["cells"]["bond_swap_3y"]["derived"] is True


def test_derived_key_cannot_be_stored(client) -> None:
    response = client.put("/api/observation", json={
        "obs_date": DAY, "field_key": "curve_3s10s", "value": 27.5})
    assert response.status_code == 422
    assert "파생값" in response.json()["detail"]


def test_non_numeric_value_is_rejected(client) -> None:
    response = client.put("/api/observation", json={
        "obs_date": DAY, "field_key": "irs_3y", "value": "어제쯤"})
    assert response.status_code == 422


def test_unknown_field_key_is_rejected(client) -> None:
    response = client.put("/api/observation", json={
        "obs_date": DAY, "field_key": "ktb_7y", "value": 3.0})
    assert response.status_code == 422


# ---------------------------------------------------------------- 저널


def test_put_journal_stores_one_column(client, conn) -> None:
    assert client.put("/api/journal", json={
        "obs_date": DAY, "column": "why_moved", "text": "CPI 프리뷰"}).status_code == 200
    assert db.journal_on(conn, DAY)["why_moved"] == "CPI 프리뷰"


def test_blank_journal_text_becomes_null(client, conn) -> None:
    client.put("/api/journal", json={"obs_date": DAY, "column": "brief_en", "text": "x"})
    client.put("/api/journal", json={"obs_date": DAY, "column": "brief_en", "text": "   "})
    assert db.journal_on(conn, DAY)["brief_en"] is None


def test_unknown_journal_column_is_rejected(client) -> None:
    response = client.put("/api/journal", json={
        "obs_date": DAY, "column": "updated_at", "text": "x"})
    assert response.status_code == 422


# ---------------------------------------------------------------- 루틴


def test_put_routine_returns_streak_and_counts(client) -> None:
    body = client.put("/api/routine", json={
        "task_date": DAY, "routine_key": "daily_snapshot", "done": True}).json()

    assert body["done"] is True
    assert body["header"]["undone_today"] == 4        # 화요일 = 일간 5 종
    assert body["header"]["total_today"] == 5
    assert body["header"]["streak_days"] == 0        # 아직 5 종을 다 못 채웠다


def test_completing_every_daily_routine_starts_the_streak(client) -> None:
    keys = ("daily_overnight", "daily_snapshot", "daily_why",
            "daily_brief_en", "daily_invalidation")
    for key in keys:
        body = client.put("/api/routine", json={
            "task_date": DAY, "routine_key": key, "done": True}).json()

    assert body["header"]["undone_today"] == 0
    assert body["header"]["streak_days"] == 1


def test_unknown_routine_is_rejected(client) -> None:
    response = client.put("/api/routine", json={
        "task_date": DAY, "routine_key": "daily_meditation", "done": True})
    assert response.status_code == 422


# ------------------------------------------------------------ 아이디어


def test_post_idea_creates_it(client) -> None:
    response = client.post("/api/idea", json=IDEA)
    assert response.status_code == 201
    assert response.json()["code"] == "IDEA-001"


def test_post_idea_without_invalidation_is_rejected(client, conn) -> None:
    """서버가 권위다. 화면의 required 를 우회해도 통과하지 않는다 (CLAUDE.md 7)."""
    payload = dict(IDEA, invalidations=[])
    response = client.post("/api/idea", json=payload)

    assert response.status_code == 422
    assert "무효화 조건" in response.json()["detail"]
    assert conn.execute("SELECT COUNT(*) AS n FROM idea").fetchone()["n"] == 0


def test_post_idea_with_blank_invalidation_is_rejected(client) -> None:
    response = client.post("/api/idea", json=dict(IDEA, invalidations=["   ", ""]))
    assert response.status_code == 422


def test_post_idea_rejects_unknown_pricing_key(client) -> None:
    response = client.post("/api/idea", json=dict(IDEA, pricing_key="ktb_7y"))
    assert response.status_code == 422


def test_new_idea_appears_in_blotter_and_watch(client) -> None:
    client.post("/api/idea", json=IDEA)
    page = client.get("/").text

    assert "IDEA-001" in page
    assert "국고 3-10 스티프너" in page
    assert "금통위가 매파로 선회" in page       # 워치 패널에 자동 반영된다


def test_manual_mark_updates_pnl(client) -> None:
    idea_id = client.post("/api/idea", json=dict(IDEA, pricing_key=None)).json()["id"]
    body = client.put(f"/api/idea/{idea_id}/mark", json={
        "mark_date": DAY, "level": 27.5}).json()

    assert body["current_level"] == "27.5"
    assert body["pnl_bp"] == "-17.5"
    assert body["dir"] == "down"


def test_manual_mark_is_refused_when_pricing_key_exists(client) -> None:
    """자동 산출되는 포지션에 손으로 값을 꽂아 넣지 않는다."""
    idea_id = client.post("/api/idea", json=IDEA).json()["id"]
    response = client.put(f"/api/idea/{idea_id}/mark", json={
        "mark_date": DAY, "level": 27.5})
    assert response.status_code == 422


# ------------------------------------------------------ 무효화 조건 점검


def test_check_updates_unchecked_count_and_position_state(client, conn) -> None:
    client.post("/api/idea", json=dict(IDEA, invalidations=["조건1", "조건2"]))
    ids = [row["id"] for row in conn.execute("SELECT id FROM invalidation ORDER BY id")]

    body = client.put(f"/api/invalidation/{ids[0]}/check", json={
        "check_date": DAY, "state": "broken"}).json()

    assert body["unchecked_count"] == 1
    assert body["positions"][0]["worst_state"] == "broken"

    body = client.put(f"/api/invalidation/{ids[1]}/check", json={
        "check_date": DAY, "state": "valid"}).json()
    assert body["unchecked_count"] == 0
    assert body["positions"][0]["worst_state"] == "broken"   # 가장 나쁜 상태가 이긴다


def test_bad_check_state_is_rejected(client, conn) -> None:
    client.post("/api/idea", json=IDEA)
    cid = conn.execute("SELECT id FROM invalidation LIMIT 1").fetchone()["id"]
    response = client.put(f"/api/invalidation/{cid}/check", json={
        "check_date": DAY, "state": "괜찮음"})
    assert response.status_code == 422


def test_unknown_invalidation_is_404(client) -> None:
    response = client.put("/api/invalidation/999/check", json={
        "check_date": DAY, "state": "valid"})
    assert response.status_code == 404


# ---------------------------------------------------------------- 이벤트


def test_create_and_patch_event(client, conn) -> None:
    event_id = client.post("/api/event", json={
        "event_date": "2026-08-12", "region": "KR", "name": "금통위"}).json()["id"]

    assert client.patch(f"/api/event/{event_id}", json={
        "column": "my_expectation", "value": "동결, 인하 소수의견 1"}).status_code == 200

    row = conn.execute("SELECT * FROM event WHERE id = ?", (event_id,)).fetchone()
    assert row["my_expectation"] == "동결, 인하 소수의견 1"


def test_patch_event_column_whitelist(client, conn) -> None:
    event_id = client.post("/api/event", json={
        "event_date": "2026-08-12", "region": "KR", "name": "금통위"}).json()["id"]
    response = client.patch(f"/api/event/{event_id}", json={
        "column": "created_at", "value": "x"})
    assert response.status_code == 422


def test_patch_event_rejects_bad_call(client, conn) -> None:
    event_id = client.post("/api/event", json={
        "event_date": "2026-08-12", "region": "KR", "name": "금통위"}).json()["id"]
    response = client.patch(f"/api/event/{event_id}", json={
        "column": "my_call", "value": "거의맞음"})
    assert response.status_code == 422


def test_unknown_region_is_rejected(client) -> None:
    response = client.post("/api/event", json={
        "event_date": "2026-08-12", "region": "MARS", "name": "x"})
    assert response.status_code == 422


def test_patch_unknown_event_is_404(client) -> None:
    response = client.patch("/api/event/999", json={"column": "actual", "value": "x"})
    assert response.status_code == 404


# ---------------------------------------------------------------- 설정


def test_color_convention_round_trips(client, conn) -> None:
    assert client.put("/api/setting/color_convention", json={
        "value": "bbg"}).status_code == 200
    assert db.setting(conn, "color_convention") == "bbg"
    assert 'data-color-convention="bbg"' in client.get("/").text


def test_bad_convention_is_rejected(client) -> None:
    response = client.put("/api/setting/color_convention", json={"value": "dark"})
    assert response.status_code == 422
