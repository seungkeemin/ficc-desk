"""덮어쓰기 이력 — 이 프로젝트의 복구 장치.

CLAUDE.md 4: market_observation_log 는 append-only. 어떤 경우에도 UPDATE/DELETE 하지 않는다.
실수로 덮어쓴 값이 여기서 되살아나지 않으면 시계열이 유실된다.
"""

from __future__ import annotations

import pytest

from ficc import db

DAY = "2026-08-11"


def test_insert_then_manual_overwrite(conn) -> None:
    assert db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos") == "insert"
    assert db.upsert_observation(conn, DAY, "ktb_3y", 2.860, "manual", "user") == "update"

    rows = list(conn.execute(
        "SELECT * FROM market_observation WHERE field_key='ktb_3y'"))
    assert len(rows) == 1                     # (날짜, 필드) 당 최신 1행
    assert rows[0]["value"] == 2.860
    assert rows[0]["source"] == "manual"      # 덮어쓴 값은 manual 로 기록된다
    assert rows[0]["provider"] == "user"

    log = db.observation_log(conn, "ktb_3y", DAY)
    assert [entry["action"] for entry in log] == ["insert", "update"]
    assert log[0]["prev_value"] is None
    assert log[1]["prev_value"] == 2.845      # 자동 수집값이 보존된다
    assert log[1]["prev_source"] == "auto"
    assert log[1]["new_value"] == 2.860


def test_log_survives_repeated_overwrites(conn) -> None:
    for value in (2.845, 2.850, 2.855, 2.860):
        db.upsert_observation(conn, DAY, "ktb_10y", value, "manual", "user")

    log = db.observation_log(conn, "ktb_10y", DAY)
    assert len(log) == 4
    assert [entry["prev_value"] for entry in log] == [None, 2.845, 2.850, 2.855]
    # 되돌리기: 로그의 prev_value 로 원래 값을 복구할 수 있다
    assert log[1]["prev_value"] == 2.845


def test_captured_at_is_kst_iso8601(conn) -> None:
    db.upsert_observation(conn, DAY, "usdkrw", 1382.40, "auto", "ecos")
    row = conn.execute(
        "SELECT captured_at FROM market_observation WHERE field_key='usdkrw'"
    ).fetchone()
    assert row["captured_at"].endswith("+09:00")


def test_unknown_field_key_is_rejected(conn) -> None:
    """field_def 에 없는 키는 외래키 제약에 걸린다. 오타로 유령 필드가 생기지 않는다."""
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_observation(conn, DAY, "ktb_7y", 3.0, "manual", "user")


def test_bad_source_is_rejected(conn) -> None:
    with pytest.raises(ValueError):
        db.upsert_observation(conn, DAY, "ktb_3y", 2.8, "guess", "user")


@pytest.mark.parametrize("bad", ["2026-8-11", "20260811", "2026/08/11", "11-08-2026"])
def test_non_canonical_date_is_rejected(conn, bad: str) -> None:
    """obs_date 는 문자열로 비교·정렬된다. 0 패딩이 빠진 값 하나가 시계열을 어긋나게 한다.

    strptime('%Y-%m-%d') 은 '2026-8-11' 을 통과시키므로 쓰기 경로에서 따로 막는다.
    """
    with pytest.raises(ValueError):
        db.upsert_observation(conn, bad, "ktb_3y", 2.845, "manual", "user")


def test_string_ordering_matches_chronology(conn) -> None:
    for day, value in [("2026-08-09", 2.80), ("2026-08-10", 2.83), ("2026-09-01", 2.90)]:
        db.upsert_observation(conn, day, "ktb_3y", value, "auto", "ecos")
    latest = db.latest_on_or_before(conn, "2026-08-31")
    assert latest["ktb_3y"]["obs_date"] == "2026-08-10"  # 9/1 을 끌어오지 않는다


def test_missing_value_creates_no_row(conn) -> None:
    """미수집은 NULL 행이 아니라 행 부재다 (CLAUDE.md 1)."""
    db.upsert_observation(conn, DAY, "ktb_3y", 2.845, "auto", "ecos")
    stored = db.observations_on(conn, DAY)
    assert set(stored) == {"ktb_3y"}
    assert "irs_3y" not in stored


def test_latest_on_or_before_prefers_most_recent(conn) -> None:
    """ECOS 가 T+1 이면 오늘 자 행이 없다. 가장 최근 게시분과 그 날짜를 함께 본다."""
    db.upsert_observation(conn, "2026-08-07", "ktb_3y", 2.830, "auto", "ecos")
    db.upsert_observation(conn, "2026-08-10", "ktb_3y", 2.845, "auto", "ecos")

    latest = db.latest_on_or_before(conn, "2026-08-11")
    assert latest["ktb_3y"]["obs_date"] == "2026-08-10"
    assert latest["ktb_3y"]["value"] == 2.845

    earlier = db.latest_on_or_before(conn, "2026-08-08")
    assert earlier["ktb_3y"]["obs_date"] == "2026-08-07"


def test_previous_observation_for_delta(conn) -> None:
    db.upsert_observation(conn, "2026-08-10", "ktb_3y", 2.833, "auto", "ecos")
    db.upsert_observation(conn, "2026-08-11", "ktb_3y", 2.845, "auto", "ecos")

    prev = db.previous_observation(conn, "ktb_3y", "2026-08-11")
    assert prev["value"] == 2.833
    assert db.previous_observation(conn, "ktb_3y", "2026-08-10") is None
