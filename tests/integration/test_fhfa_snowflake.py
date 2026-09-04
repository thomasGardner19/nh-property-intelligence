from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nh_property_intelligence.config import Settings
from nh_property_intelligence.ingestion.fhfa import loader as fhfa_loader
from nh_property_intelligence.ingestion.fhfa.contract import RunContext
from nh_property_intelligence.ingestion.fhfa.normalize import normalize_records
from nh_property_intelligence.snowflake import connect_snowflake

pytestmark = pytest.mark.snowflake_integration


def test_replace_all_uses_temporary_target() -> None:
    if os.getenv("RUN_SNOWFLAKE_INTEGRATION") != "1":
        pytest.skip("Set RUN_SNOWFLAKE_INTEGRATION=1 to run Snowflake integration tests")

    settings = Settings()
    connection = connect_snowflake(settings)
    cursor = connection.cursor()
    target = f"RAW.TEMP_FHFA_COUNTY_HPI_{uuid4().hex.upper()}"
    original_target = fhfa_loader.TARGET_TABLE
    now = datetime.now(UTC)
    context = RunContext(
        source_file_name="integration.xlsx",
        source_url="https://example.test/integration.xlsx",
        source_requested_at=now,
        ingested_at=now,
        ingestion_run_id=str(uuid4()),
    )
    record = {
        "State": "NH",
        "County": "Rockingham County",
        "FIPS code": 33015,
        "Year": 2025,
        "Annual Change (%)": "3.25",
        "HPI": "420.50",
        "HPI with 1990 base": "385.10",
        "HPI with 2000 base": "250.20",
    }

    try:
        cursor.execute(f"CREATE TEMP TABLE {target} LIKE RAW.FHFA_COUNTY_HPI")
        fhfa_loader.TARGET_TABLE = target
        result = fhfa_loader.replace_all(normalize_records([record], context), connection)
        assert result.rows_inserted == 1
    finally:
        fhfa_loader.TARGET_TABLE = original_target
        cursor.execute(f"DROP TABLE IF EXISTS {target}")
        cursor.close()
        connection.close()
