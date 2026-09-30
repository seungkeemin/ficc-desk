"""Operating statistics for the README: collection runs and stored observations.

    .venv\\Scripts\\python scripts\\stats.py
    .venv\\Scripts\\python scripts\\stats.py --db path\\to\\ficc.db

Opens the database read-only (mode=ro) and reads only the ingest and observation
tables. Journal, ideas and positions are never touched, so the output is safe to
paste into a public README. Every number is printed with the date it was taken.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ficc.config.settings import db_path, today_kst  # noqa: E402


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def collect_stats(conn: sqlite3.Connection) -> dict:
    """Aggregate run and observation counts. Pure SQL, no writes."""
    one = lambda sql: conn.execute(sql).fetchone()  # noqa: E731
    grouped = lambda sql: {r[0]: r[1] for r in conn.execute(sql)}  # noqa: E731

    runs = one("SELECT COUNT(*) AS n, MIN(started_at) AS first, MAX(started_at) AS last,"
               " COUNT(DISTINCT substr(started_at, 1, 10)) AS days FROM ingest_run")
    obs = one("SELECT COUNT(*) AS n, COUNT(DISTINCT obs_date) AS dates,"
              " COUNT(DISTINCT field_key) AS fields,"
              " MIN(obs_date) AS first, MAX(obs_date) AS last FROM market_observation")

    return {
        "runs": runs["n"],
        "run_days": runs["days"],
        "first_run": runs["first"],
        "last_run": runs["last"],
        "runs_by_status": grouped(
            "SELECT status, COUNT(*) FROM ingest_run GROUP BY status ORDER BY status"),
        "results_by_status": grouped(
            "SELECT status, COUNT(*) FROM ingest_result GROUP BY status ORDER BY status"),
        "observations": obs["n"],
        "observation_dates": obs["dates"],
        "observed_fields": obs["fields"],
        "first_obs_date": obs["first"],
        "last_obs_date": obs["last"],
        "observations_by_source": grouped(
            "SELECT source, COUNT(*) FROM market_observation GROUP BY source ORDER BY source"),
        "observations_by_provider": grouped(
            "SELECT COALESCE(provider, '-'), COUNT(*) FROM market_observation"
            " GROUP BY provider ORDER BY provider"),
        "log_rows": one("SELECT COUNT(*) FROM market_observation_log")[0],
        "log_updates": one(
            "SELECT COUNT(*) FROM market_observation_log WHERE action = 'update'")[0],
    }


def format_stats(stats: dict, as_of: str) -> str:
    def kv(d: dict) -> str:
        return ", ".join(f"{k} {v:,}" for k, v in d.items()) or "-"

    lines = [
        f"as of {as_of}",
        f"collection runs      {stats['runs']:,} on {stats['run_days']:,} days"
        f"  ({stats['first_run']} .. {stats['last_run']})",
        f"  by status          {kv(stats['runs_by_status'])}",
        f"field results        {kv(stats['results_by_status'])}",
        f"observations         {stats['observations']:,} rows, {stats['observed_fields']} fields,"
        f" {stats['observation_dates']:,} dates ({stats['first_obs_date']} .. {stats['last_obs_date']})",
        f"  by source          {kv(stats['observations_by_source'])}",
        f"  by provider        {kv(stats['observations_by_provider'])}",
        f"overwrite log        {stats['log_rows']:,} rows ({stats['log_updates']:,} updates)",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=None, help="default: FICC_DB_PATH or data/ficc.db")
    args = parser.parse_args()

    path = args.db or db_path()
    try:
        conn = connect_readonly(path)
    except FileNotFoundError:
        print(f"DB not found: {path}", file=sys.stderr)
        return 1
    try:
        print(format_stats(collect_stats(conn), today_kst().isoformat()))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
