from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nh_property_intelligence.config import Settings
from nh_property_intelligence.ingestion.census import contract
from nh_property_intelligence.ingestion.census import loader as census_loader
from nh_property_intelligence.ingestion.census.normalize import normalize_response
from nh_property_intelligence.snowflake import connect_snowflake

pytestmark = pytest.mark.snowflake_integration


def _normalized_row():
    header = [
        "NAME",
        *contract.ACS_VARIABLES.keys(),
        "state",
        "county",
        "county subdivision",
    ]
    values = {
        "NAME": "Salem town, Rockingham County, New Hampshire",
        "state": "33",
        "county": "015",
        "county subdivision": "66660",
        **{code: "100" for code in contract.ACS_VARIABLES},
    }
    now = datetime.now(UTC)
    context = contract.RunContext(
        ingestion_run_id=f"integration-{uuid4().hex}",
        source_requested_at=now,
        ingested_at=now,
        source_endpoint="https://api.census.gov/data/2024/acs/acs5?integration=1",
    )
    return normalize_response([header, [values[column] for column in header]], context)[0]


def test_replace_vintage_against_temporary_snowflake_target(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("RUN_SNOWFLAKE_INTEGRATION") != "1":
        pytest.skip("Set RUN_SNOWFLAKE_INTEGRATION=1 to enable Snowflake integration tests")

    settings = Settings()
    connection = connect_snowflake(settings)
    target = f"TEMP_CENSUS_TARGET_{uuid4().hex.upper()}"
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"CREATE TEMP TABLE {target} LIKE RAW.CENSUS_ACS_MUNICIPALITY"
        )
        monkeypatch.setattr(census_loader, "TARGET_TABLE", target)

        result = census_loader.replace_vintage([_normalized_row()], 2024, connection)

        cursor.execute(f"SELECT COUNT(*) FROM {target} WHERE acs_vintage = 2024")
        assert cursor.fetchone()[0] == 1
        assert result.rows_inserted == 1
    finally:
        cursor.close()
        connection.close()
