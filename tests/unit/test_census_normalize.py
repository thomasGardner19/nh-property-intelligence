from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nh_property_intelligence.ingestion.census.contract import ACS_VARIABLES, RunContext
from nh_property_intelligence.ingestion.census.normalize import normalize_response


def _context() -> RunContext:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    return RunContext(
        ingestion_run_id="run-1",
        source_requested_at=now,
        ingested_at=now,
        source_endpoint="https://api.census.gov/data/2024/acs/acs5?example=1",
    )


def _payload(**overrides: str) -> list[list[str]]:
    header = ["NAME", *ACS_VARIABLES.keys(), "state", "county", "county subdivision"]
    values = {
        "NAME": "Salem town, Rockingham County, New Hampshire",
        "state": "33",
        "county": "015",
        "county subdivision": "66660",
        **{code: "100" for code in ACS_VARIABLES},
    }
    values.update(overrides)
    return [header, [values[column] for column in header]]


def test_normalize_builds_geoid_and_typed_measures() -> None:
    row = normalize_response(_payload(), _context())[0]

    assert row.county_subdivision_geoid == "3301566660"
    assert row.total_population_estimate == 100
    assert row.raw_payload["B01003_001E"] == "100"
    assert len(row.row_hash) == 32


def test_controlled_moe_maps_to_zero_but_raw_literal_is_preserved() -> None:
    row = normalize_response(_payload(B01003_001M="-555555555"), _context())[0]

    assert row.total_population_moe == 0
    assert row.raw_payload["B01003_001M"] == "-555555555"


def test_standard_sentinel_maps_to_none() -> None:
    row = normalize_response(_payload(B19013_001E="-666666666"), _context())[0]

    assert row.median_household_income_estimate is None
    assert row.raw_payload["B19013_001E"] == "-666666666"


def test_controlled_sentinel_in_estimate_field_fails() -> None:
    with pytest.raises(ValueError, match="only valid for MOE"):
        normalize_response(_payload(B19013_001E="-555555555"), _context())


def test_invalid_fips_fails() -> None:
    with pytest.raises(ValueError, match="Invalid county FIPS"):
        normalize_response(_payload(county="15"), _context())


def test_duplicate_natural_key_fails() -> None:
    payload = _payload()
    payload.append(payload[1].copy())

    with pytest.raises(ValueError, match="Duplicate Census natural key"):
        normalize_response(payload, _context())


def test_row_hash_ignores_run_metadata() -> None:
    payload = _payload()
    first = normalize_response(payload, _context())[0]
    later = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    second_context = RunContext(
        ingestion_run_id="run-2",
        source_requested_at=later,
        ingested_at=later,
        source_endpoint="https://api.census.gov/data/2024/acs/acs5?different=metadata",
    )
    second = normalize_response(payload, second_context)[0]

    assert first.row_hash == second.row_hash
