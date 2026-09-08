"""Exercise real Prefect execution with mocked I/O; no APIs or warehouse required."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from prefect.testing.utilities import prefect_test_harness

from nh_property_intelligence.orchestration import refresh as r


@pytest.fixture(scope="module", autouse=True)
def prefect_runtime():
    with prefect_test_harness():
        yield


@pytest.fixture
def io(monkeypatch):
    settings = SimpleNamespace(
        census_api_key=None,
        snowflake_password=None,
        snowflake_account="account",
        snowflake_user="user",
        snowflake_authenticator="externalbrowser",
        snowflake_role="role",
        snowflake_warehouse="warehouse",
        snowflake_database="database",
    )
    monkeypatch.setattr(r, "Settings", lambda: settings)
    client = MagicMock()
    connection = MagicMock()
    monkeypatch.setattr(r.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(r, "connect_snowflake", MagicMock(return_value=connection))
    monkeypatch.setattr(
        r.census_client, "fetch_response", MagicMock(return_value=[["header"], ["row"]])
    )
    monkeypatch.setattr(r, "normalize_response", MagicMock(return_value=["normalized"]))
    monkeypatch.setattr(r.dra_client, "fetch_report", MagicMock(return_value=b"pdf"))
    monkeypatch.setattr(r.dra_extract, "extract_records", MagicMock(return_value=["row"]))
    monkeypatch.setattr(
        r.dra_normalize, "normalize_records", MagicMock(return_value=["normalized"])
    )
    monkeypatch.setattr(r.fhfa_client, "fetch_workbook", MagicMock(return_value=b"xlsx"))
    monkeypatch.setattr(r.fhfa_extract, "extract_records", MagicMock(return_value=["row"]))
    monkeypatch.setattr(
        r.fhfa_normalize, "normalize_records", MagicMock(return_value=["normalized"])
    )
    loaders = [MagicMock(return_value=SimpleNamespace(rows_inserted=1)) for _ in range(3)]
    for module, name, loader in zip(
        [r.census_loader, r.dra_loader, r.fhfa_loader],
        ["replace_vintage", "replace_tax_year", "replace_all"],
        loaders,
        strict=True,
    ):
        monkeypatch.setattr(module, name, loader)
    process = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="PASS", stderr=""))
    monkeypatch.setattr(r.subprocess, "run", process)
    return SimpleNamespace(
        client=client, connection=connection, loaders=loaders, process=process, settings=settings
    )


@pytest.mark.parametrize("index", range(3))
def test_source_success_and_cleanup(io, index):
    source = [r.ingest_census, r.ingest_dra, r.ingest_fhfa][index]
    result = source()
    assert result["rows_extracted"] == result["rows_normalized"] == result["rows_loaded"] == 1
    io.loaders[index].assert_called_once()
    io.client.__exit__.assert_called_once()
    io.connection.close.assert_called_once()


@pytest.mark.parametrize("index", range(3))
def test_required_source_failure_stops_dbt_and_closes_connection(io, index):
    io.loaders[index].side_effect = ValueError("duplicate natural keys")
    with pytest.raises(r.RefreshError, match="Snowflake load/cleanup: ValueError"):
        r.refresh_property_intelligence()
    io.process.assert_not_called()
    assert io.connection.close.call_count == index + 1
    assert io.client.__exit__.call_count == index + 1
    io.loaders[index].assert_called_once()  # deterministic failures are not retried
    for later in io.loaders[index + 1 :]:
        later.assert_not_called()


def test_master_orders_ingestion_before_dbt(io):
    events = []
    for name, loader in zip(["census", "dra", "fhfa"], io.loaders, strict=True):

        def record(*args, name=name):
            events.append(name)
            return SimpleNamespace(rows_inserted=1)

        loader.side_effect = record

    def build(*args, **kwargs):
        events.append("dbt")
        return SimpleNamespace(returncode=0, stdout="PASS", stderr="")

    io.process.side_effect = build
    assert r.refresh_property_intelligence()["dbt"] == {"return_code": 0}
    assert events == ["census", "dra", "fhfa", "dbt"]
    # A second refresh must not restore a cached successful task result.
    r.refresh_property_intelligence()
    assert events == ["census", "dra", "fhfa", "dbt"] * 2


def test_dbt_nonzero_fails_master_without_retry(io):
    io.process.return_value.returncode = 1
    with pytest.raises(r.RefreshError, match="return code 1"):
        r.refresh_property_intelligence()
    io.process.assert_called_once()


def test_dbt_uses_real_project_and_resolved_settings(io, monkeypatch, caplog):
    from pydantic import SecretStr

    secret = "private-token/value"
    io.settings.snowflake_password = SecretStr(secret)
    io.process.return_value.stdout = f"failure: {secret} private-token%2Fvalue"
    io.process.return_value.stderr = secret
    monkeypatch.setenv("BW_SESSION", "vault-session")
    r.dbt_build()
    args, kwargs = io.process.call_args
    assert args[0][1] == "build"
    assert str(r.DBT_PROJECT) in args[0]
    assert kwargs["env"]["SNOWFLAKE_PASSWORD"] == secret
    assert kwargs["env"]["SNOWFLAKE_ACCOUNT"] == "account"
    assert "--no-write-json" in args[0]
    assert secret not in caplog.text
    assert "private-token%2Fvalue" not in caplog.text
    assert r.redact_output("vault-session", kwargs["env"]) == "[REDACTED]"


@pytest.mark.parametrize("status,retries", [(429, 3), (503, 3), (400, 1), (401, 1)])
def test_http_retry_policy_and_safe_exception(io, status, retries):
    secret = "never-log-this-key"
    response = httpx.Response(status, request=httpx.Request("GET", f"https://test/?key={secret}"))
    r.census_client.fetch_response.side_effect = httpx.HTTPStatusError(
        secret,
        request=response.request,
        response=response,
    )
    with pytest.raises(r.RefreshError) as caught:
        r.ingest_census.with_options(retry_delay_seconds=0)()
    assert secret not in str(caught.value)
    assert caught.value.__context__ is None
    assert r.census_client.fetch_response.call_count == retries
    assert io.client.__exit__.call_count == retries
    r.connect_snowflake.assert_not_called()


def test_normalization_failure_not_retried(io):
    r.normalize_response.side_effect = ValueError("invalid normalized record")
    with pytest.raises(r.RefreshError, match="normalization: ValueError"):
        r.ingest_census()
    r.normalize_response.assert_called_once()
    r.connect_snowflake.assert_not_called()
    io.client.__exit__.assert_called_once()


def test_connection_failure_not_blindly_retried(io):
    r.connect_snowflake.side_effect = RuntimeError("sensitive connector diagnostics")
    with pytest.raises(r.RefreshError, match="Snowflake load/cleanup: RuntimeError"):
        r.ingest_fhfa()
    r.connect_snowflake.assert_called_once()
    io.client.__exit__.assert_called_once()


def test_fhfa_workbook_closed_on_invalid_schema(monkeypatch):
    from nh_property_intelligence.ingestion.fhfa import extract

    workbook = MagicMock()
    workbook.active.iter_rows.return_value = [("invalid",)]
    monkeypatch.setattr(extract, "load_workbook", lambda *a, **kw: workbook)
    with pytest.raises(ValueError, match="header"):
        extract.extract_records(b"xlsx")
    workbook.close.assert_called_once()


def test_transport_retry_recovers(io):
    r.census_client.fetch_response.side_effect = [
        httpx.ConnectError("network unavailable"),
        [["header"], ["row"]],
    ]
    assert r.ingest_census.with_options(retry_delay_seconds=0)()["rows_loaded"] == 1
    assert r.census_client.fetch_response.call_count == 2
    io.loaders[0].assert_called_once()
    assert io.client.__exit__.call_count == 2


def test_http_logs_and_serialized_failure_exclude_secrets(io, caplog):
    import logging
    import pickle

    logger = logging.getLogger("httpx")
    previous = logger.disabled

    def fail(*args, **kwargs):
        logger.warning("request?key=private-key")
        raise ValueError("private-key")

    r.census_client.fetch_response.side_effect = fail
    with pytest.raises(r.RefreshError) as caught:
        r.ingest_census()
    assert "private-key" not in caplog.text
    assert b"private-key" not in pickle.dumps(caught.value)
    assert logger.disabled == previous


def test_dbt_temporary_profile_removed_on_process_failure(io):
    from pathlib import Path

    locations = []

    def fail(command, **kwargs):
        location = Path(command[command.index("--profiles-dir") + 1])
        assert (location / "profiles.yml").is_file()
        locations.append(location)
        raise OSError("private process details")

    io.process.side_effect = fail
    with pytest.raises(r.RefreshError, match="configuration/build: OSError"):
        r.dbt_build()
    assert not locations[0].exists()
