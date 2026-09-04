"""HTTP request construction and retrieval for Census ACS."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .contract import ACS_VARIABLES, ACS_VINTAGE, STATE_FIPS

BASE_URL = "https://api.census.gov"
USER_AGENT = "nh-property-intelligence/0.1"


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
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Census response must be a top-level JSON array")
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
