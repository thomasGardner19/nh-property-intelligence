from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from nh_property_intelligence.ingestion.fhfa.contract import RunContext
from nh_property_intelligence.ingestion.fhfa.normalize import normalize_records


def _context() -> RunContext:
    now = datetime.now(UTC)
    return RunContext(
        source_file_name="hpi_at_county.xlsx",
        source_url="https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx",
        source_requested_at=now,
        ingested_at=now,
        ingestion_run_id=str(uuid4()),
    )


def _record(state: str = "NH") -> dict[str, object]:
    return {
        "State": state,
        "County": "Rockingham County",
        "FIPS code": 33015,
        "Year": 2025,
        "Annual Change (%)": "3.25",
        "HPI": "420.50",
        "HPI with 1990 base": "385.10",
        "HPI with 2000 base": "250.20",
    }


def test_normalize_filters_to_new_hampshire_and_preserves_fips() -> None:
    rows = normalize_records([_record("MA"), _record("NH")], _context())
    assert len(rows) == 1
    assert rows[0].county_fips == "33015"
    assert rows[0].county_name_raw == "Rockingham County"


def test_hash_is_independent_of_run_metadata() -> None:
    first = normalize_records([_record()], _context())[0]
    second = normalize_records([_record()], _context())[0]
    assert first.row_hash == second.row_hash


def test_missing_rebased_hpi_is_nullable() -> None:
    record = _record()
    record["HPI with 1990 base"] = "."
    row = normalize_records([record], _context())[0]
    assert row.hpi_1990_base is None
