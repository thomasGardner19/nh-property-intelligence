from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nh_property_intelligence.ingestion.dra.contract import RunContext
from nh_property_intelligence.ingestion.dra.normalize import normalize_records


def _context() -> RunContext:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    return RunContext(
        ingestion_run_id="run-1",
        source_file_name="2025-municipal-tax-rates.pdf",
        source_url="https://example.test/2025-municipal-tax-rates.pdf",
        source_requested_at=now,
        ingested_at=now,
    )


def _record(**overrides: str) -> dict[str, str]:
    record = {
        "Municipality": "Salem",
        "Date": "10/15/2025",
        "Valuation": "5,000,000,000",
        "Valuation Including Utilities": "5,100,000,000",
        "Municipal Tax Rate": "4.25",
        "County Tax Rate": "0.95",
        "State Education Tax Rate": "1.55",
        "Local Education Tax Rate": "7.25",
        "Total Tax Rate": "14.00",
        "Total Commitment": "71,400,000",
    }
    record.update(overrides)
    return record


def test_normalize_preserves_name_and_parses_values() -> None:
    row = normalize_records([_record()], _context())[0]

    assert row.municipality_name_raw == "Salem"
    assert row.tax_year == 2025
    assert row.total_tax_rate == Decimal("14.00")
    assert row.valuation == 5_000_000_000
    assert row.raw_payload["Valuation"] == "5,000,000,000"
    assert len(row.row_hash) == 32


def test_duplicate_raw_municipality_fails() -> None:
    with pytest.raises(ValueError, match="Duplicate DRA municipality natural key"):
        normalize_records([_record(), _record()], _context())


def test_invalid_numeric_value_fails() -> None:
    with pytest.raises(ValueError, match="not numeric"):
        normalize_records([_record(**{"Total Tax Rate": "unknown"})], _context())


def test_valuation_including_utilities_cannot_be_lower() -> None:
    with pytest.raises(ValueError, match="below base valuation"):
        normalize_records(
            [_record(**{"Valuation Including Utilities": "4,900,000,000"})], _context()
        )


def test_hash_ignores_run_metadata() -> None:
    first = normalize_records([_record()], _context())[0]
    later = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    second_context = RunContext(
        ingestion_run_id="run-2",
        source_file_name="renamed.pdf",
        source_url="https://example.test/renamed.pdf",
        source_requested_at=later,
        ingested_at=later,
    )
    second = normalize_records([_record()], second_context)[0]

    assert first.row_hash == second.row_hash
