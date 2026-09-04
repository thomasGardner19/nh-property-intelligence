"""Normalize extracted NH DRA municipal tax records."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .contract import EXPECTED_FIELDS, SOURCE_SYSTEM, TAX_YEAR, RawMunicipalTaxRateRow, RunContext


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"DRA field {field!r} must be a non-empty string")
    return value.strip()


def _integer(value: Any, field: str) -> int:
    text = _require_text(value, field).replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"DRA field {field!r} is not numeric: {value!r}") from exc
    if number != number.to_integral_value():
        raise ValueError(f"DRA field {field!r} must be a whole-dollar value: {value!r}")
    return int(number)


def _decimal(value: Any, field: str) -> Decimal:
    text = _require_text(value, field).replace("$", "").replace(",", "")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"DRA field {field!r} is not numeric: {value!r}") from exc
    if number < 0:
        raise ValueError(f"DRA field {field!r} cannot be negative: {value!r}")
    return number


def _rate_date(value: Any) -> date:
    text = _require_text(value, "Date")
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"DRA Date has unsupported format: {value!r}")


def _row_hash(raw_payload: dict[str, Any], tax_year: int) -> bytes:
    canonical = {
        "tax_year": tax_year,
        **{field: raw_payload.get(field) for field in EXPECTED_FIELDS},
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).digest()


def normalize_records(
    records: list[dict[str, Any]],
    context: RunContext,
    *,
    tax_year: int = TAX_YEAR,
) -> list[RawMunicipalTaxRateRow]:
    if not records:
        raise ValueError("Cannot normalize an empty DRA municipal tax batch")

    normalized: list[RawMunicipalTaxRateRow] = []
    seen: set[tuple[int, str]] = set()
    for index, source in enumerate(records, start=1):
        missing = [field for field in EXPECTED_FIELDS if field not in source]
        if missing:
            raise ValueError(f"DRA row {index} is missing expected fields: {missing}")

        raw_payload = dict(source)
        municipality = _require_text(source["Municipality"], "Municipality")
        key = (tax_year, municipality)
        if key in seen:
            raise ValueError(f"Duplicate DRA municipality natural key: {key}")
        seen.add(key)

        row = RawMunicipalTaxRateRow(
            municipality_name_raw=municipality,
            tax_year=tax_year,
            rate_date=_rate_date(source["Date"]),
            valuation=_integer(source["Valuation"], "Valuation"),
            valuation_including_utilities=_integer(
                source["Valuation Including Utilities"], "Valuation Including Utilities"
            ),
            municipal_tax_rate=_decimal(source["Municipal Tax Rate"], "Municipal Tax Rate"),
            county_tax_rate=_decimal(source["County Tax Rate"], "County Tax Rate"),
            state_education_tax_rate=_decimal(
                source["State Education Tax Rate"], "State Education Tax Rate"
            ),
            local_education_tax_rate=_decimal(
                source["Local Education Tax Rate"], "Local Education Tax Rate"
            ),
            total_tax_rate=_decimal(source["Total Tax Rate"], "Total Tax Rate"),
            total_commitment=_integer(source["Total Commitment"], "Total Commitment"),
            raw_payload=raw_payload,
            source_system=SOURCE_SYSTEM,
            source_file_name=context.source_file_name,
            source_url=context.source_url,
            source_requested_at=context.source_requested_at,
            ingested_at=context.ingested_at,
            ingestion_run_id=context.ingestion_run_id,
            row_hash=_row_hash(raw_payload, tax_year),
        )
        if row.valuation_including_utilities < row.valuation:
            raise ValueError(
                f"DRA row {index} valuation including utilities is below base valuation"
            )
        normalized.append(row)

    return normalized
