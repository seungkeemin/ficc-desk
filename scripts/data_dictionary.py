"""Generate docs/data-dictionary.md from the migrations and the source registry.

    .venv\\Scripts\\python scripts\\data_dictionary.py

Builds a throwaway in-memory database from migrations/ (never opens data/ficc.db),
then joins field_def with ficc/config/sources.py so the table always matches what
the collector actually calls. Re-run after adding a migration or a series.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ficc import db  # noqa: E402
from ficc.config import sources as srcs  # noqa: E402
from ficc.config.settings import REPO_ROOT  # noqa: E402

OUT = REPO_ROOT / "docs" / "data-dictionary.md"


def source_code(field_key: str) -> tuple[str, str]:
    """(source identifier, verified_on) for an auto-collected field."""
    if field_key in srcs.ECOS_SERIES:
        s = srcs.ECOS_SERIES[field_key]
        return f"`{s.stat_code}` / `{'/'.join(s.item_codes)}`", s.verified_on
    if field_key in srcs.FRED_SERIES:
        s = srcs.FRED_SERIES[field_key]
        return f"`{s.series_id}`", s.verified_on
    if field_key in srcs.KRX_SERIES:
        s = srcs.KRX_SERIES[field_key]
        return f"`{s.endpoint}` {s.product_name} · `{s.value_field}`", s.verified_on
    return "", ""


def render(conn: sqlite3.Connection) -> str:
    fields = db.field_defs(conn)
    stored = [f for f in fields if not f["is_derived"]]
    derived = [f for f in fields if f["is_derived"]]

    lines = [
        "# 데이터 사전",
        "",
        "`scripts/data_dictionary.py`가 마이그레이션과 `ficc/config/sources.py`에서 생성한다. 직접 고치지 않는다.",
        "",
        f"저장 필드 {len(stored)}개, 조회 시 계산하는 파생 필드 {len(derived)}개.",
        "",
        "## 저장 필드",
        "",
        "| field_key | 이름 | 분류 | 단위 | 수집 | 소스 코드 | 확인일 |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in stored:
        code, verified = source_code(f["field_key"])
        provider = f["auto_provider"] or "수동"
        lines.append(f"| `{f['field_key']}` | {f['label_ko']} | {f['category']} | {f['unit']}"
                     f" | {provider} | {code} | {verified} |")

    lines += [
        "",
        "## 파생 필드",
        "",
        "구성 원본이 하나라도 없으면 `None`이다. DB에 저장하지 않는다.",
        "",
        "| field_key | 이름 | 단위 | 구성 |",
        "|---|---|---|---|",
    ]
    for f in derived:
        parts = ", ".join(f"`{p}`" for p in (f["derived_from"] or "").split(",") if p)
        lines.append(f"| `{f['field_key']}` | {f['label_ko']} | {f['unit']} | {parts} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    OUT.write_text(render(conn), encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
