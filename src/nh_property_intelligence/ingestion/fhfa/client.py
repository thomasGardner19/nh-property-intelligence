"""HTTP retrieval for the FHFA annual county HPI workbook."""

from __future__ import annotations

import time

import httpx

USER_AGENT = "nh-property-intelligence/0.1"


def fetch_workbook(url: str, client: httpx.Client, *, max_attempts: int = 3) -> bytes:
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
            if 400 <= response.status_code < 500:
                response.raise_for_status()
            if response.content[:2] != b"PK":
                raise ValueError("FHFA response is not an XLSX workbook")
            return response.content
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
            if attempt == max_attempts:
                raise
            time.sleep(0.25 * (2 ** (attempt - 1)))
    raise RuntimeError("FHFA workbook request failed")
