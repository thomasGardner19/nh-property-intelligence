"""Locked source contract for NH DRA municipal tax rates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

TAX_YEAR = 2025
SOURCE_SYSTEM = "NH_DRA"
EXPECTED_FIELDS = (
    "Municipality",
    "Date",
    "Valuation",
    "Valuation Including Utilities",
    "Municipal Tax Rate",
    "County Tax Rate",
    "State Education Tax Rate",
    "Local Education Tax Rate",
    "Total Tax Rate",
    "Total Commitment",
)


@dataclass(frozen=True)
class RunContext:
    ingestion_run_id: str
    source_file_name: str
    source_url: str
    source_requested_at: datetime
    ingested_at: datetime


@dataclass(frozen=True)
class RawMunicipalTaxRateRow:
    municipality_name_raw: str
    tax_year: int
    rate_date: date
    valuation: int
    valuation_including_utilities: int
    municipal_tax_rate: Decimal
    county_tax_rate: Decimal
    state_education_tax_rate: Decimal
    local_education_tax_rate: Decimal
    total_tax_rate: Decimal
    total_commitment: int
    raw_payload: dict[str, Any]
    source_system: str
    source_file_name: str
    source_url: str
    source_requested_at: datetime
    ingested_at: datetime
    ingestion_run_id: str
    row_hash: bytes
