from __future__ import annotations

import httpx

from nh_property_intelligence.ingestion.dra.client import fetch_report


def test_fetch_report_returns_pdf_bytes() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"%PDF-test"))
    with httpx.Client(transport=transport) as client:
        result = fetch_report("https://example.test/report.pdf", client)

    assert result == b"%PDF-test"


def test_official_request_contract_without_browser_or_session() -> None:
    from nh_property_intelligence.ingestion.dra.client import REPORT_PAGE_URL, USER_AGENT

    url = (
        "https://www.revenue.nh.gov/sites/g/files/ehbemt736/files/documents/"
        "2025-municipal-tax-rates.pdf"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == url
        assert request.headers["User-Agent"] == USER_AGENT == "nh-property-intelligence/0.1"
        assert request.headers["Accept"] == "application/pdf"
        assert request.headers["Accept-Language"] == "en-US,en;q=0.9"
        assert request.headers["Referer"] == REPORT_PAGE_URL
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"%PDF-official-report")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_report(url, client) == b"%PDF-official-report"


def test_report_follows_redirect_with_default_client() -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/report.pdf":
            return httpx.Response(302, headers={"Location": "/current-report.pdf"})
        return httpx.Response(200, content=b"%PDF-current")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_report("https://example.test/report.pdf", client) == b"%PDF-current"
    assert paths == ["/report.pdf", "/current-report.pdf"]


def test_access_denied_fails_without_retry_or_alternate_source() -> None:
    import pytest

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403, text="Access Denied")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError) as caught,
    ):
        fetch_report("https://example.test/report.pdf", client, base_backoff_seconds=0)
    assert caught.value.response.status_code == 403
    assert calls == ["https://example.test/report.pdf"]


def test_html_challenge_with_success_status_is_not_a_report() -> None:
    import pytest

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, text="<html>Verification required</html>")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="not a PDF"),
    ):
        fetch_report("https://example.test/report.pdf", client, base_backoff_seconds=0)
    assert len(calls) == 1


def test_transient_service_failure_can_retry() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"%PDF-recovered")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert (
            fetch_report("https://example.test/report.pdf", client, base_backoff_seconds=0)
            == b"%PDF-recovered"
        )
    assert len(calls) == 2


def test_source_schema_change_fails_loudly(monkeypatch) -> None:
    import pytest

    from nh_property_intelligence.ingestion.dra import extract

    class Page:
        def extract_tables(self):
            return [[["Municipality", "Total Tax Rate"], ["Example Town", "12.00"]]]

    class PDF:
        pages = (Page(),)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(extract.pdfplumber, "open", lambda *args: PDF())
    with pytest.raises(ValueError, match="missing one or more expected columns"):
        extract.extract_records(b"%PDF-changed-schema")
