"""HTTP retrieval for NH DRA municipal tax reports."""

from __future__ import annotations

import time

import httpx

# The official endpoint accepts this honest application identity. Generic HTTP
# tool identities can receive an edge-layer 403; do not impersonate a browser.
USER_AGENT = "nh-property-intelligence/0.1"
REPORT_PAGE_URL = (
    "https://www.revenue.nh.gov/about-dra/municipal-and-property-division/"
    "municipal-and-property-reports/municipal-and-village"
)


def fetch_report(
    url: str,
    client: httpx.Client,
    *,
    max_attempts: int = 3,
    base_backoff_seconds: float = 0.25,
) -> bytes:
    """Fetch a DRA report, retrying only transient transport/server failures."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/pdf",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": REPORT_PAGE_URL,
                },
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
            if 400 <= response.status_code < 500:
                response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError("DRA municipal tax report response is not a PDF")
            return response.content
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
            delay = (
                float(retry_after)
                if retry_after and retry_after.isdigit()
                else (base_backoff_seconds * (2 ** (attempt - 1)))
            )
            time.sleep(delay)

    raise RuntimeError("DRA report request failed") from last_error
