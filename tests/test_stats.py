"""scripts/stats.py counts runs and observations and never writes."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from ficc import db

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stats  # noqa: E402


def test_counts_match_what_was_written(conn, db_file) -> None:
    run = db.start_run(conn, "2026-08-10")
    db.record_result(conn, run, "ktb_3y", "ok")
    db.record_result(conn, run, "ust_10y", "miss", "not published")
    db.finish_run(conn, run, "partial")
    db.upsert_observation(conn, "2026-08-10", "ktb_3y", 3.815, "auto", "ecos")
    db.upsert_observation(conn, "2026-08-11", "ktb_3y", 3.808, "auto", "ecos")
    db.upsert_observation(conn, "2026-08-11", "ktb_3y", 3.80, "manual", "user")
    conn.commit()

    ro = stats.connect_readonly(db_file)
    s = stats.collect_stats(ro)
    ro.close()

    assert s["runs"] == 1 and s["runs_by_status"] == {"partial": 1}
    assert s["results_by_status"] == {"miss": 1, "ok": 1}
    assert s["observations"] == 2                       # one row per (date, field)
    assert s["observation_dates"] == 2 and s["observed_fields"] == 1
    assert s["observations_by_source"] == {"auto": 1, "manual": 1}
    assert s["log_rows"] == 3 and s["log_updates"] == 1  # the overwrite is kept
    assert (s["first_obs_date"], s["last_obs_date"]) == ("2026-08-10", "2026-08-11")
    assert "as of 2026-09-30" in stats.format_stats(s, "2026-09-30")


def test_connection_is_read_only(conn, db_file) -> None:
    ro = stats.connect_readonly(db_file)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM market_observation")
    ro.close()


def test_missing_db_is_an_error_not_a_new_file(tmp_path) -> None:
    missing = tmp_path / "nope.db"
    with pytest.raises(FileNotFoundError):
        stats.connect_readonly(missing)
    assert not missing.exists()
