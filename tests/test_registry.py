"""Field registry: 41 stored fields, and no series wired to two fields."""

from __future__ import annotations

from collections import Counter

from ficc import db
from ficc.config import sources as srcs


def test_forty_one_stored_fields(conn) -> None:
    stored = [f for f in db.field_defs(conn) if not f["is_derived"]]
    assert len(stored) == 41
    assert len({f["field_key"] for f in stored}) == 41


def test_no_field_is_collected_by_two_providers() -> None:
    keys = [*srcs.ECOS_SERIES, *srcs.FRED_SERIES, *srcs.KRX_SERIES]
    assert len(keys) == len(set(keys)) == 34
    assert (len(srcs.ECOS_SERIES), len(srcs.FRED_SERIES), len(srcs.KRX_SERIES)) == (16, 13, 5)


def _duplicates(ids) -> list:
    return [i for i, n in Counter(ids).items() if n > 1]


def test_no_source_id_is_used_twice() -> None:
    # A copy-pasted code (e.g. KTB 3Y 010200000 vs 5Y 010200001) would silently
    # show the same number under two labels.
    assert _duplicates((s.stat_code, s.item_codes) for s in srcs.ECOS_SERIES.values()) == []
    assert _duplicates(s.series_id for s in srcs.FRED_SERIES.values()) == []
    assert _duplicates((s.endpoint, s.product_name, s.value_field)
                       for s in srcs.KRX_SERIES.values()) == []


def test_data_dictionary_is_up_to_date(conn) -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import data_dictionary

    committed = data_dictionary.OUT.read_text(encoding="utf-8")
    assert data_dictionary.render(conn) == committed, \
        "run scripts/data_dictionary.py and commit docs/data-dictionary.md"
