from __future__ import annotations

import httpx

from nh_property_intelligence.ingestion.dra.client import fetch_report


def test_fetch_report_returns_pdf_bytes() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"%PDF-test"))
    with httpx.Client(transport=transport) as client:
        result = fetch_report("https://example.test/report.pdf", client)

    assert result == b"%PDF-test"
