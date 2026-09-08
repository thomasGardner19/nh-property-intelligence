"""HTTP request construction and retrieval for Census ACS."""

from __future__ import annotations

import csv
import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from .contract import ACS_VARIABLES, ACS_VINTAGE, STATE_FIPS

BASE_URL = "https://api.census.gov"
USER_AGENT = "nh-property-intelligence/0.1"
SUMMARY_DATA_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/"
    "2024/table-based-SF/data/5YRData"
)
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer"
)


@dataclass(frozen=True)
class RequestSpec:
    url: str
    params: tuple[tuple[str, str], ...]
    source_endpoint: str


def build_request(vintage: int = ACS_VINTAGE, api_key: str | None = None) -> RequestSpec:
    if vintage != ACS_VINTAGE:
        raise ValueError(f"Unsupported ACS vintage: {vintage}")

    params: list[tuple[str, str]] = [
        ("get", ",".join(("NAME", *ACS_VARIABLES.keys()))),
        ("for", "county subdivision:*"),
        ("in", f"state:{STATE_FIPS}"),
        ("in", "county:*"),
    ]
    if api_key:
        params.append(("key", api_key))

    url = f"{BASE_URL}/data/{vintage}/acs/acs5"
    public_params = tuple((key, value) for key, value in params if key != "key")
    source_endpoint = f"{url}?{urlencode(public_params)}"
    return RequestSpec(url=url, params=tuple(params), source_endpoint=source_endpoint)


def _get_bytes(client: httpx.Client, url: str) -> bytes:
    response = client.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60.0, connect=10.0),
    )
    response.raise_for_status()
    return response.content


def _gazetteer_rows(client: httpx.Client, geography: str) -> list[dict[str, str]]:
    archive = _get_bytes(client, f"{GAZETTEER_URL}/2024_Gaz_{geography}_national.zip")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        names = zipped.namelist()
        if len(names) != 1:
            raise ValueError(f"Unexpected Census {geography} gazetteer archive layout")
        with zipped.open(names[0]) as source:
            text = io.TextIOWrapper(source, encoding="utf-8")
            return list(csv.DictReader(text, delimiter="\t"))


def _summary_variable_name(api_name: str) -> str:
    match = re.fullmatch(r"([A-Z][0-9]+)_([0-9]{3})([EM])", api_name)
    if match is None:
        raise ValueError(f"Unsupported ACS variable name: {api_name}")
    table, line, statistic = match.groups()
    return f"{table}_{statistic}{line}"


def _fetch_summary_response(client: httpx.Client) -> list[list[Any]]:
    """Reconstruct the locked API response from official keyless ACS summary files."""
    subdivisions = {
        row["GEOID"].strip(): row["NAME"].strip()
        for row in _gazetteer_rows(client, "cousubs")
        if row.get("USPS") == "NH"
    }
    counties = {
        row["GEOID"].strip(): row["NAME"].strip()
        for row in _gazetteer_rows(client, "counties")
        if row.get("USPS") == "NH"
    }
    if not subdivisions or not counties:
        raise ValueError("Official Census gazetteers contained no New Hampshire geographies")

    values: dict[str, dict[str, str]] = {geoid: {} for geoid in subdivisions}
    for table in dict.fromkeys(name.split("_", 1)[0] for name in ACS_VARIABLES):
        url = f"{SUMMARY_DATA_URL}/acsdt5y2024-{table.lower()}.dat"
        text = _get_bytes(client, url).decode("utf-8")
        reader = csv.DictReader(io.StringIO(text), delimiter="|")
        table_variables = [name for name in ACS_VARIABLES if name.startswith(f"{table}_")]
        for row in reader:
            geo_id = row.get("GEO_ID", "")
            if not geo_id.startswith("0600000US33"):
                continue
            geoid = geo_id.removeprefix("0600000US")
            if geoid not in values:
                continue
            for variable in table_variables:
                values[geoid][variable] = row[_summary_variable_name(variable)]

    header = ["NAME", *ACS_VARIABLES, "state", "county", "county subdivision"]
    payload: list[list[Any]] = [header]
    for geoid, subdivision_name in sorted(subdivisions.items()):
        county_fips = geoid[2:5]
        county_name = counties.get(geoid[:5])
        if county_name is None:
            raise ValueError(f"Census gazetteer is missing county {geoid[:5]}")
        missing = [name for name in ACS_VARIABLES if name not in values[geoid]]
        if missing:
            raise ValueError(f"ACS summary files are missing variables for geography {geoid}")
        payload.append(
            [
                f"{subdivision_name}, {county_name}, New Hampshire",
                *(values[geoid][name] for name in ACS_VARIABLES),
                geoid[:2],
                county_fips,
                geoid[5:],
            ]
        )
    return payload


def fetch_response(
    spec: RequestSpec,
    client: httpx.Client,
    *,
    max_attempts: int = 3,
    base_backoff_seconds: float = 0.25,
) -> list[list[Any]]:
    """Fetch one ACS response, retrying only transient transport/server failures."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(
                spec.url,
                params=list(spec.params),
                headers={"User-Agent": USER_AGENT},
                timeout=httpx.Timeout(20.0, connect=10.0),
            )
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
            if 400 <= response.status_code < 500:
                response.raise_for_status()
            try:
                payload = response.json()
            except json.JSONDecodeError:
                has_key = any(key == "key" for key, _ in spec.params)
                if has_key:
                    raise
                return _fetch_summary_response(client)
            if not isinstance(payload, list):
                raise TypeError("Census response must be a top-level JSON array")
            return payload
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                exc.response.status_code == 429 or exc.response.status_code >= 500
            )
            if not retryable or attempt == max_attempts:
                raise
            last_error = exc
            retry_after = None
            if isinstance(exc, httpx.HTTPStatusError):
                retry_after = exc.response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else (
                base_backoff_seconds * (2 ** (attempt - 1))
            )
            time.sleep(delay)

    raise RuntimeError("Census request failed") from last_error
