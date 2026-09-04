"""Validation and normalization for Census ACS municipality rows."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import re
from typing import Any

from .contract import (
    ACS_VARIABLES,
    CONTROLLED_MOE_SENTINELS,
    NULL_SENTINELS,
    REQUIRED_HEADERS,
    SOURCE_GEOGRAPHY_TYPE,
    SOURCE_SYSTEM,
    RawMunicipalityRow,
    RunContext,
)

_FIPS_PATTERNS = {
    "state": re.compile(r"^[0-9]{2}$"),
    "county": re.compile(r"^[0-9]{3}$"),
    "county subdivision": re.compile(r"^[0-9]{5}$"),
}


def _derive_geoid(state: str, county: str, subdivision: str) -> str:
    for field, value in (
        ("state", state),
        ("county", county),
        ("county subdivision", subdivision),
    ):
        if not _FIPS_PATTERNS[field].fullmatch(value):
            raise ValueError(f"Invalid {field} FIPS: {value!r}")
    if state != "33":
        raise ValueError(f"Expected New Hampshire state FIPS '33', got {state!r}")
    return state + county + subdivision


def _coerce_measure(raw: Any, *, is_moe: bool) -> int | None:
    if raw is None or raw == "":
        return None
    text = str(raw)
    if is_moe and text in CONTROLLED_MOE_SENTINELS:
        return 0
    if text in NULL_SENTINELS:
        return None
    if text == "-555555555":
        raise ValueError("Controlled-estimate sentinel is only valid for MOE fields")
    if not re.fullmatch(r"-?[0-9]+", text):
        raise ValueError(f"Invalid ACS numeric literal: {text!r}")
    return int(text)


def _canonical_hash(raw_payload: dict[str, Any], context: RunContext) -> bytes:
    source_content = {
        "acs_vintage": context.acs_vintage,
        "dataset_id": context.dataset_id,
        "NAME": raw_payload["NAME"],
        "state": raw_payload["state"],
        "county": raw_payload["county"],
        "county subdivision": raw_payload["county subdivision"],
        **{code: raw_payload.get(code) for code in ACS_VARIABLES},
    }
    canonical = json.dumps(source_content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def normalize_response(payload: list[list[Any]], context: RunContext) -> list[RawMunicipalityRow]:
    if len(payload) < 2:
        raise ValueError("Census response must contain a header and at least one data row")
    header = payload[0]
    if not isinstance(header, list) or not all(isinstance(item, str) for item in header):
        raise ValueError("Census header must be a list of strings")
    if len(set(header)) != len(header):
        raise ValueError("Census response contains duplicate header names")

    missing = [field for field in REQUIRED_HEADERS if field not in header]
    if missing:
        raise ValueError(f"Census response missing required headers: {missing}")

    index = {name: pos for pos, name in enumerate(header)}
    rows: list[RawMunicipalityRow] = []
    seen_keys: set[tuple[int, str]] = set()

    for row_number, row in enumerate(payload[1:], start=1):
        if not isinstance(row, list) or len(row) != len(header):
            raise ValueError(f"Census row {row_number} does not match header width")
        raw_payload = {name: row[pos] for name, pos in index.items()}

        state = str(raw_payload["state"])
        county = str(raw_payload["county"])
        subdivision = str(raw_payload["county subdivision"])
        geoid = _derive_geoid(state, county, subdivision)
        natural_key = (context.acs_vintage, geoid)
        if natural_key in seen_keys:
            raise ValueError(f"Duplicate Census natural key: {natural_key}")
        seen_keys.add(natural_key)

        measures: dict[str, int | None] = {}
        for code, column_name in ACS_VARIABLES.items():
            measures[column_name] = _coerce_measure(raw_payload.get(code), is_moe=code.endswith("M"))

        rows.append(
            RawMunicipalityRow(
                geography_name_raw=str(raw_payload["NAME"]),
                state_fips=state,
                county_fips=county,
                county_subdivision_fips=subdivision,
                county_subdivision_geoid=geoid,
                acs_vintage=context.acs_vintage,
                dataset_id=context.dataset_id,
                source_endpoint=context.source_endpoint,
                source_geography_type=SOURCE_GEOGRAPHY_TYPE,
                raw_payload=raw_payload,
                source_system=SOURCE_SYSTEM,
                source_requested_at=context.source_requested_at,
                ingested_at=context.ingested_at,
                ingestion_run_id=context.ingestion_run_id,
                row_hash=_canonical_hash(raw_payload, context),
                **measures,
            )
        )

    return rows
