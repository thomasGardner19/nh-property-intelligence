from __future__ import annotations

import httpx
import pytest

from nh_property_intelligence.ingestion.census.client import build_request, fetch_response


def test_build_request_excludes_api_key_from_source_endpoint() -> None:
    spec = build_request(api_key="secret-key")

    assert ("key", "secret-key") in spec.params
    assert "secret-key" not in spec.source_endpoint
    assert "key=" not in spec.source_endpoint
    assert "county+subdivision%3A%2A" in spec.source_endpoint
    assert "state%3A33" in spec.source_endpoint


def test_fetch_response_returns_json_array() -> None:
    payload = [["NAME", "state"], ["Salem town", "33"]]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_response(build_request(), client)

    assert result == payload


def test_fetch_response_does_not_retry_nonretryable_400() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, request=request, json={"error": "bad request"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_response(build_request(), client, base_backoff_seconds=0)

    assert calls == 1
