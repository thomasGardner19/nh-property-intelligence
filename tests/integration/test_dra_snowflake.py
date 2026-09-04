from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nh_property_intelligence.config import Settings
from nh_property_intelligence.ingestion.dra import loader as dra_loader
from nh_property_intelligence.ingestion.dra.contract import RunContext
from nh_property_intelligence.ingestion.dra.normalize import normalize_records
from nh_property_intelligence.snowflake import connect_snowflake

pytestmark = pytest.mark.snowflake_integration


def test_replace_tax_year_uses_temporary_target() -> None:
    if os.getenv("RUN_SNOWFLAKE_INTEGRATION") != "1":
        pytest.skip("Set RUN_SNOWFLAKE_INTEGRATION=1 to run Snowflake integration tests")

    settings = Settings()
    connection = connect_snowflake(settings)
    cursor = connection.cursor()
    target = f"RAW.TEMP_DRA_MUNICIPAL_TAX_RATES_{uuid4().hex.upper()}"
    original_target = dra_loader.TARGET_TABLE
    now = datetime.now(UTC)
    context = RunContext(
        ingestion_run_id=str(uuid4()),
        source_file_name="integration.pdf",
        source_url="https://example.test/integration.pdf",
        source_requested_at=now,
        ingested_at=now,
    )
    record = {
        "Municipality": "Integration Test Town",
        "Date": "10/15/2025",
        "Valuation": "1000000",
        "Valuation Including Utilities": "1000100",
        "Municipal Tax Rate": "4.25",
        "County Tax Rate": "0.95",
        "State Education Tax Rate": "1.55",
        "Local Education Tax Rate": "7.25",
        "Total Tax Rate": "14.00",
        "Total Commitment": "14000",
    }

    try:
        cursor.execute(f"CREATE TEMP TABLE {target} LIKE RAW.DRA_MUNICIPAL_TAX_RATES")
        dra_loader.TARGET_TABLE = target
        result = dra_loader.replace_tax_year(normalize_records([record], context), 2025, connection)
        assert result.rows_inserted == 1
    finally:
        dra_loader.TARGET_TABLE = original_target
        cursor.execute(f"DROP TABLE IF EXISTS {target}")
        cursor.close()
        connection.close()
