"""config/sources.py 는 '확인된 것만' 담는다.

CLAUDE.md 3 을 테스트로 못박는다. 추측한 코드가 슬며시 들어오면 여기서 걸린다.
"""

from __future__ import annotations

from ficc import db
from ficc.config import sources


def test_every_entry_records_when_it_was_verified() -> None:
    """확인 날짜 없는 항목은 확인되지 않은 항목이다."""
    for registry in (sources.ECOS_SERIES, sources.FRED_SERIES, sources.KRX_SERIES):
        for key, spec in registry.items():
            assert spec.verified_on, f"{key} 에 verified_on 이 없다"


def test_no_placeholder_leaked_in() -> None:
    for key, spec in sources.ECOS_SERIES.items():
        assert spec.stat_code and "확인" not in spec.stat_code, key
        assert all(code and "확인" not in code for code in spec.item_codes), key
    for key, spec in sources.KRX_SERIES.items():
        assert spec.product_name and "확인" not in spec.product_name, key


def test_field_def_auto_provider_matches_confirmed_registries(conn) -> None:
    """field_def 가 '자동'이라고 말하는 필드는 실제로 등록된 코드가 있어야 한다.

    둘이 어긋나면 화면은 '수집 실패'로 보이는데 원인은 소스가 아니라 시드다.
    """
    registries = {
        "ecos": sources.ECOS_SERIES,
        "fred": sources.FRED_SERIES,
        "krx": sources.KRX_SERIES,
    }
    for row in db.field_defs(conn):
        provider = row["auto_provider"]
        if not provider:
            continue
        assert provider in registries, f"{row['field_key']}: 모르는 provider {provider}"
        assert row["field_key"] in registries[provider], (
            f"{row['field_key']} 는 auto_provider={provider} 인데 "
            f"config/sources.py 에 코드가 없다"
        )


def test_confirmed_series_are_actually_seeded_as_auto(conn) -> None:
    """반대 방향 — 확인해 놓고 시드에 반영을 잊는 경우."""
    seeded = {
        row["field_key"]: row["auto_provider"] for row in db.field_defs(conn)
    }
    for provider, registry in [("ecos", sources.ECOS_SERIES),
                               ("fred", sources.FRED_SERIES),
                               ("krx", sources.KRX_SERIES)]:
        for key in registry:
            assert seeded.get(key) == provider, (
                f"{key} 는 {provider} 로 확인됐는데 field_def.auto_provider 가 "
                f"{seeded.get(key)!r} 이다"
            )
