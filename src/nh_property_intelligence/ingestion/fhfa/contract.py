"""Contracts for FHFA annual county HPI ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

SOURCE_SYSTEM = "FHFA"
SOURCE_DATASET = "Annual County House Price Index"
STATE_CODE = "NH"

EXPECTED_FIELDS = (
    "State",
    "County",
    "FIPS code",
    "Year",
    "Annual Change (%)",
    "HPI",
    "HPI with 1990 base",
    "HPI with 2000 base",
)


@dataclass(frozen=True)
class RunContext:
    source_file_name: str
    source_url: str
    source_requested_at: datetime
    ingested_at: datetime
    ingestion_run_id: str


@dataclass(frozen=True)
class RawCountyHpiRow:
    state_code: str
    county_name_raw: str
    county_fips: str
    year: int
    annual_change_pct: Decimal | None
    hpi: Decimal | None
    hpi_1990_base: Decimal | None
    hpi_2000_base: Decimal | None
    raw_payload: dict[str, Any]
    source_system: str
    source_dataset: str
    source_file_name: str
    source_url: str
    source_requested_at: datetime
    ingested_at: datetime
    ingestion_run_id: str
    row_hash: bytes
