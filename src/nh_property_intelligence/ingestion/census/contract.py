"""Immutable contracts for the Census ACS municipality extract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

ACS_VINTAGE = 2024
DATASET_ID = "acs/acs5"
STATE_FIPS = "33"
SOURCE_SYSTEM = "US_CENSUS_BUREAU"
SOURCE_GEOGRAPHY_TYPE = "county subdivision"

ACS_VARIABLES: dict[str, str] = {
    "B01003_001E": "total_population_estimate",
    "B01003_001M": "total_population_moe",
    "B19013_001E": "median_household_income_estimate",
    "B19013_001M": "median_household_income_moe",
    "B25077_001E": "median_owner_occupied_home_value_estimate",
    "B25077_001M": "median_owner_occupied_home_value_moe",
    "B25064_001E": "median_gross_rent_estimate",
    "B25064_001M": "median_gross_rent_moe",
    "B25001_001E": "total_housing_units_estimate",
    "B25001_001M": "total_housing_units_moe",
    "B25003_001E": "occupied_housing_units_estimate",
    "B25003_001M": "occupied_housing_units_moe",
    "B25003_002E": "owner_occupied_housing_units_estimate",
    "B25003_002M": "owner_occupied_housing_units_moe",
}

REQUIRED_HEADERS = (
    "NAME",
    *ACS_VARIABLES.keys(),
    "state",
    "county",
    "county subdivision",
)

NULL_SENTINELS = {
    "-222222222",
    "-333333333",
    "-666666666",
    "-888888888",
    "-999999999",
}
CONTROLLED_MOE_SENTINELS = {"-555555555", "*****"}


@dataclass(frozen=True)
class RunContext:
    ingestion_run_id: str
    source_requested_at: datetime
    ingested_at: datetime
    source_endpoint: str
    acs_vintage: int = ACS_VINTAGE
    dataset_id: str = DATASET_ID


@dataclass(frozen=True)
class RawMunicipalityRow:
    geography_name_raw: str
    state_fips: str
    county_fips: str
    county_subdivision_fips: str
    county_subdivision_geoid: str
    acs_vintage: int
    dataset_id: str
    source_endpoint: str
    source_geography_type: str
    total_population_estimate: int | None
    total_population_moe: int | None
    median_household_income_estimate: int | None
    median_household_income_moe: int | None
    median_owner_occupied_home_value_estimate: int | None
    median_owner_occupied_home_value_moe: int | None
    median_gross_rent_estimate: int | None
    median_gross_rent_moe: int | None
    total_housing_units_estimate: int | None
    total_housing_units_moe: int | None
    occupied_housing_units_estimate: int | None
    occupied_housing_units_moe: int | None
    owner_occupied_housing_units_estimate: int | None
    owner_occupied_housing_units_moe: int | None
    raw_payload: dict[str, Any]
    source_system: str
    source_requested_at: datetime
    ingested_at: datetime
    ingestion_run_id: str
    row_hash: bytes
