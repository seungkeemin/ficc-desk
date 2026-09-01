"""서술형 4칸의 저장.

칸마다 따로 쓰는 것이 핵심이다. 통째 저장이면 야간장 메모와 영문 브리핑의 디바운스가
겹칠 때 늦게 도착한 요청이 다른 칸을 옛 값으로 되돌린다 — 하루치 기록이 조용히 사라진다.
"""

from __future__ import annotations

import pytest

from ficc import db

DAY = "2026-08-11"


def test_insert_then_update(conn) -> None:
    assert db.journal_on(conn, DAY) is None

    db.upsert_journal_field(conn, DAY, "why_moved", "CPI 프리뷰로 금리 상승")
    row = db.journal_on(conn, DAY)
    assert row["why_moved"] == "CPI 프리뷰로 금리 상승"
    assert row["updated_at"].endswith("+09:00")

    db.upsert_journal_field(conn, DAY, "why_moved", "3년 입찰 소화로 되돌림")
    assert db.journal_on(conn, DAY)["why_moved"] == "3년 입찰 소화로 되돌림"

    rows = list(conn.execute("SELECT * FROM journal WHERE obs_date = ?", (DAY,)))
    assert len(rows) == 1


def test_writing_one_column_preserves_the_others(conn) -> None:
    db.upsert_journal_field(conn, DAY, "review_ny", "뉴욕장 메모")
    db.upsert_journal_field(conn, DAY, "brief_en", "US rates sold off.")
    db.upsert_journal_field(conn, DAY, "review_ldn", "런던장 메모")

    row = db.journal_on(conn, DAY)
    assert row["review_ny"] == "뉴욕장 메모"
    assert row["brief_en"] == "US rates sold off."
    assert row["review_ldn"] == "런던장 메모"
    assert row["why_moved"] is None                 # 안 쓴 칸은 NULL 로 남는다


def test_none_is_stored_as_null(conn) -> None:
    """'안 썼다'와 '빈 문자열'을 섞지 않는다 (viewmodel.JournalVM)."""
    db.upsert_journal_field(conn, DAY, "why_moved", "한 문장")
    db.upsert_journal_field(conn, DAY, "why_moved", None)
    assert db.journal_on(conn, DAY)["why_moved"] is None


def test_days_are_independent(conn) -> None:
    db.upsert_journal_field(conn, DAY, "why_moved", "오늘")
    db.upsert_journal_field(conn, "2026-08-12", "why_moved", "내일")
    assert db.journal_on(conn, DAY)["why_moved"] == "오늘"
    assert db.journal_on(conn, "2026-08-12")["why_moved"] == "내일"


@pytest.mark.parametrize("column", ["updated_at", "obs_date", "why_moved; DROP TABLE journal--"])
def test_column_whitelist(conn, column: str) -> None:
    """컬럼명이 SQL 에 문자열로 들어가는 유일한 곳이다. 화이트리스트 밖은 통과할 수 없다."""
    with pytest.raises(ValueError):
        db.upsert_journal_field(conn, DAY, column, "x")


def test_non_canonical_date_is_rejected(conn) -> None:
    with pytest.raises(ValueError):
        db.upsert_journal_field(conn, "2026-8-11", "why_moved", "x")
