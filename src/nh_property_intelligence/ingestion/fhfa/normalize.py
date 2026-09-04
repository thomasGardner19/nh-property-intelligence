"""Normalize FHFA annual county HPI records."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from .contract import SOURCE_DATASET, SOURCE_SYSTEM, STATE_CODE, RawCountyHpiRow, RunContext


def _text(value: Any, field: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"FHFA field {field!r} must be non-empty")
    return str(value).strip()


def _decimal(value: Any, field: str) -> Decimal | None:
    if value is None or str(value).strip() in {"", ".", "NA", "N/A"}:
        return None
    try:
        return Decimal(str(value).replace("%", "").replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"FHFA field {field!r} is not numeric: {value!r}") from exc


def _year(value: Any) -> int:
    year = int(Decimal(str(value)))
    if year < 1970 or year > 2100:
        raise ValueError(f"FHFA Year out of range: {year}")
    return year


def _fips(value: Any) -> str:
    text = str(value).strip().removesuffix(".0").zfill(5)
    if len(text) != 5 or not text.isdigit():
        raise ValueError(f"Invalid FHFA county FIPS: {value!r}")
    return text


def _hash(payload: dict[str, Any], year: int, county_fips: str) -> bytes:
    canonical = {"year": year, "county_fips": county_fips, "payload": payload}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).digest()


def normalize_records(records: list[dict[str, Any]], context: RunContext) -> list[RawCountyHpiRow]:
    normalized: list[RawCountyHpiRow] = []
    seen: set[tuple[str, int]] = set()
    for record in records:
        state = _text(record.get("State"), "State").upper()
        if state != STATE_CODE:
            continue
        county_fips = _fips(record.get("FIPS code"))
        year = _year(record.get("Year"))
        key = (county_fips, year)
        if key in seen:
            raise ValueError(f"Duplicate FHFA county/year natural key: {key}")
        seen.add(key)
        raw_payload = dict(record)
        normalized.append(
            RawCountyHpiRow(
                state_code=state,
                county_name_raw=_text(record.get("County"), "County"),
                county_fips=county_fips,
                year=year,
                annual_change_pct=_decimal(record.get("Annual Change (%)"), "Annual Change (%)"),
                hpi=_decimal(record.get("HPI"), "HPI"),
                hpi_1990_base=_decimal(record.get("HPI with 1990 base"), "HPI with 1990 base"),
                hpi_2000_base=_decimal(record.get("HPI with 2000 base"), "HPI with 2000 base"),
                raw_payload=raw_payload,
                source_system=SOURCE_SYSTEM,
                source_dataset=SOURCE_DATASET,
                source_file_name=context.source_file_name,
                source_url=context.source_url,
                source_requested_at=context.source_requested_at,
                ingested_at=context.ingested_at,
                ingestion_run_id=context.ingestion_run_id,
                row_hash=_hash(raw_payload, year, county_fips),
            )
        )
    if not normalized:
        raise ValueError("FHFA workbook contained no New Hampshire county records")
    return normalized
