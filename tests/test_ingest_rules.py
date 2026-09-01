"""수집 재실행 규칙.

SPEC 5 는 평일 07:00·16:00 두 번 수집을 예고한다. 재실행이 사람이 고친 값을
되돌리면 '자동 수집된 값도 수동으로 덮어쓸 수 있다'는 요구사항이 무의미해진다.
"""

from __future__ import annotations

from datetime import date

import pytest

from ficc import db, ingest
from ficc.sources.base import Failed, Fetched, Missing

TARGET = date(2026, 8, 11)
DAY = "2026-08-11"


@pytest.fixture
def fake_source(monkeypatch):
    """provider 를 가짜 fetcher 로 바꿔 네트워크 없이 collect() 를 돌린다."""
    def install(results: dict[str, object]):
        def fetcher(field_key: str, target: date):
            return results.get(field_key, Missing(field_key, "테스트 미설정"))
        monkeypatch.setattr(ingest, "PROVIDERS",
                            {"ecos": fetcher, "fred": fetcher, "krx": fetcher})
    return install


def test_manual_value_survives_reingest(conn, fake_source) -> None:
    fake_source({"ktb_3y": Fetched("ktb_3y", 3.808, TARGET, "ecos")})

    run1 = db.start_run(conn, DAY)
    ingest.collect(conn, TARGET, run1)
    assert conn.execute(
        "SELECT source FROM market_observation WHERE field_key='ktb_3y'"
    ).fetchone()["source"] == "auto"

    # 사용자가 장중에 손으로 정정
    db.upsert_observation(conn, DAY, "ktb_3y", 3.815, "manual", "user")

    # 16:00 재수집 — 자동값이 수동 정정을 덮지 않아야 한다
    run2 = db.start_run(conn, DAY)
    statuses = ingest.collect(conn, TARGET, run2)

    row = conn.execute(
        "SELECT value, source FROM market_observation WHERE field_key='ktb_3y'"
    ).fetchone()
    assert row["value"] == 3.815
    assert row["source"] == "manual"
    assert statuses["ktb_3y"] == "skipped"

    message = conn.execute(
        "SELECT message FROM ingest_result WHERE run_id=? AND field_key='ktb_3y'",
        (run2,),
    ).fetchone()["message"]
    assert "수동" in message


def test_unchanged_value_does_not_grow_the_log(conn, fake_source) -> None:
    """같은 값을 다시 써서 덮어쓰기 로그를 부풀리지 않는다."""
    fake_source({"ktb_3y": Fetched("ktb_3y", 3.808, TARGET, "ecos")})

    for _ in range(3):
        ingest.collect(conn, TARGET, db.start_run(conn, DAY))

    assert len(db.observation_log(conn, "ktb_3y", DAY)) == 1


def test_changed_value_is_written_and_logged(conn, fake_source) -> None:
    fake_source({"ktb_3y": Fetched("ktb_3y", 3.808, TARGET, "ecos")})
    ingest.collect(conn, TARGET, db.start_run(conn, DAY))

    fake_source({"ktb_3y": Fetched("ktb_3y", 3.822, TARGET, "ecos")})
    ingest.collect(conn, TARGET, db.start_run(conn, DAY))

    log = db.observation_log(conn, "ktb_3y", DAY)
    assert [e["action"] for e in log] == ["insert", "update"]
    assert log[1]["prev_value"] == 3.808


def test_one_failing_source_does_not_stop_the_others(conn, fake_source) -> None:
    """CLAUDE.md 6 — 수집 실패는 정상 상황이다."""
    fake_source({
        "ktb_3y": Fetched("ktb_3y", 3.808, TARGET, "ecos"),
        "ktb_10y": Failed("ktb_10y", "HTTP 500"),
        "cd_91d": Missing("cd_91d", "휴장"),
    })
    statuses = ingest.collect(conn, TARGET, db.start_run(conn, DAY))

    assert statuses["ktb_3y"] == "ok"
    assert statuses["ktb_10y"] == "error"
    assert statuses["cd_91d"] == "miss"
    # 성공한 필드만 저장된다. 실패한 필드는 행이 생기지 않는다.
    assert set(db.observations_on(conn, DAY)) == {"ktb_3y"}


def test_source_exception_becomes_error_not_crash(conn, monkeypatch) -> None:
    """소스가 잡지 못한 예외까지 수집 루프에서 막는다."""
    def boom(field_key: str, target: date):
        raise RuntimeError("예상 못 한 예외")

    monkeypatch.setattr(ingest, "PROVIDERS",
                        {"ecos": boom, "fred": boom, "krx": boom})
    statuses = ingest.collect(conn, TARGET, db.start_run(conn, DAY))

    assert set(statuses.values()) == {"error"}
    assert db.observations_on(conn, DAY) == {}


def test_observation_date_is_the_real_one_not_today(conn, fake_source) -> None:
    """FRED 가 T+1 이면 08-11 실행이 08-07 행을 만든다 (SPEC 4-2)."""
    fake_source({"ust_2y": Fetched("ust_2y", 4.19, date(2026, 8, 7), "fred")})
    ingest.collect(conn, TARGET, db.start_run(conn, DAY))

    row = conn.execute(
        "SELECT obs_date FROM market_observation WHERE field_key='ust_2y'"
    ).fetchone()
    assert row["obs_date"] == "2026-08-07"
    assert db.observations_on(conn, DAY) == {}   # 오늘 자로 밀어 넣지 않는다
