"""Offline operation tests: all configuration, connections and refresh calls are fake."""

import logging
import socket
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from nh_property_intelligence import config, ops, snowflake

DUMMY_SECRET = "dummy-password-must-not-appear"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Operations tests must never open network connections")

    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def io(monkeypatch):
    settings = SimpleNamespace(
        snowflake_database='dummy"database',
        snowflake_password=SecretStr(DUMMY_SECRET),
        census_api_key=SecretStr("dummy-census-key"),
    )
    settings_factory = MagicMock(return_value=settings)
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.side_effect = [
        ("dummy-account", "dummy-role", "dummy-database", "dummy-warehouse"),
        (10,),
        (20,),
        (30,),
        (1,),
        (40,),
    ]
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(config, "Settings", settings_factory)
    monkeypatch.setattr(snowflake, "connect_snowflake", connect)
    refresh = MagicMock()
    monkeypatch.setattr(ops, "run_refresh", refresh)
    return SimpleNamespace(
        settings=settings,
        settings_factory=settings_factory,
        connection=connection,
        cursor=cursor,
        connect=connect,
        refresh=refresh,
    )


@pytest.mark.parametrize("command,queries", [("check", 4), ("validate", 6)])
def test_read_commands_only_select_and_close(io, capsys, command, queries):
    assert ops.main([command]) == 0
    output = capsys.readouterr()
    assert "account: dummy-account" in output.out
    assert "RAW.CENSUS_ACS_MUNICIPALITY: 10 rows" in output.out
    assert not output.err
    calls = io.cursor.execute.call_args_list
    assert len(calls) == queries
    assert calls[0].args == (
        "SELECT CURRENT_ACCOUNT(), CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_WAREHOUSE()",
    )
    for call, table in zip(calls[1:4], ops.RAW_TABLES, strict=True):
        assert call.args == (
            "SELECT COUNT(*) FROM IDENTIFIER(%s)",
            (f'"dummy""database"."RAW"."{table}"',),
        )
    if command == "validate":
        assert calls[4].args == (
            "SELECT COUNT(*) FROM IDENTIFIER(%s) WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            ('"dummy""database"."INFORMATION_SCHEMA"."TABLES"', "ANALYTICS", "MART_TOWN_SCORECARD"),
        )
        assert calls[5].args == (
            "SELECT COUNT(*) FROM IDENTIFIER(%s)",
            ('"dummy""database"."ANALYTICS"."MART_TOWN_SCORECARD"',),
        )
        assert ops.QUALITY_CAVEAT in output.out
    assert [call[0] for call in io.connection.method_calls] == ["cursor", "close"]
    assert {call[0] for call in io.cursor.method_calls} == {"execute", "fetchone", "close"}
    io.cursor.close.assert_called_once()
    io.connection.close.assert_called_once()
    io.refresh.assert_not_called()


@pytest.mark.parametrize("counts", [(0, 20, 30, 1, 40), (10, 20, 30, 1, 0), (10, 20, 30, 0)])
def test_validate_empty_or_missing_is_nonzero(io, capsys, counts):
    io.cursor.fetchone.side_effect = [("a", "r", "d", "w"), *((n,) for n in counts)]
    assert ops.main(["validate"]) == 1
    output = capsys.readouterr()
    assert ops.QUALITY_CAVEAT in output.out
    if len(counts) == 4:
        assert "missing or not visible" in output.out
        assert io.cursor.execute.call_count == 5  # never count an invisible mart
    io.cursor.close.assert_called_once()
    io.connection.close.assert_called_once()


def test_check_reports_zero_without_writing(io, capsys):
    io.cursor.fetchone.side_effect = [("a", "r", "d", "w"), (0,), (0,), (0,)]
    assert ops.main(["check"]) == 0
    assert "0 rows" in capsys.readouterr().out
    io.connection.commit.assert_not_called()


@pytest.mark.parametrize("command", ["check", "validate"])
@pytest.mark.parametrize("stage", ["settings", "connect", "cursor", "execute", "fetch", "close"])
def test_failures_redacted_and_resources_closed(io, capsys, command, stage):
    target = {
        "settings": io.settings_factory,
        "connect": io.connect,
        "cursor": io.connection.cursor,
        "execute": io.cursor.execute,
        "fetch": io.cursor.fetchone,
        "close": io.cursor.close,
    }[stage]
    target.side_effect = RuntimeError(f"credentials={DUMMY_SECRET}")
    assert ops.main([command]) == 1
    output = capsys.readouterr()
    assert DUMMY_SECRET not in output.out + output.err
    assert "Sensitive diagnostics omitted" in output.err
    if stage not in {"settings", "connect"}:
        io.connection.close.assert_called_once()
    if stage not in {"settings", "connect", "cursor"}:
        io.cursor.close.assert_called_once()


def test_context_redacts_known_secret_values(io, capsys):
    io.cursor.fetchone.side_effect = [
        (DUMMY_SECRET, "dummy-census-key", "d", "w"),
        (1,),
        (2,),
        (3,),
    ]
    assert ops.main(["check"]) == 0
    output = capsys.readouterr().out
    assert DUMMY_SECRET not in output
    assert "dummy-census-key" not in output
    assert "[REDACTED]" in output


def test_connector_logging_suppressed_and_restored(io, caplog):
    logger = logging.getLogger("snowflake.connector.connection")
    previous = logger.disabled

    def fail(settings):
        logger.warning(DUMMY_SECRET)
        raise RuntimeError(DUMMY_SECRET)

    io.connect.side_effect = fail
    assert ops.main(["check"]) == 1
    assert DUMMY_SECRET not in caplog.text
    assert logger.disabled == previous


def test_refresh_requires_approval_before_any_configuration_or_io(io, capsys):
    assert ops.main(["refresh"]) == 2
    assert "--approve-raw-writes" in capsys.readouterr().err
    io.refresh.assert_not_called()
    io.settings_factory.assert_not_called()
    io.connect.assert_not_called()


def test_approved_refresh_is_injectable(io, capsys):
    assert ops.main(["refresh", "--approve-raw-writes"]) == 0
    io.refresh.assert_called_once_with()
    assert "APPROVED" in capsys.readouterr().out
    io.connect.assert_not_called()


def test_refresh_errors_do_not_echo_exception(io, capsys):
    io.refresh.side_effect = RuntimeError(DUMMY_SECRET)
    assert ops.main(["refresh", "--approve-raw-writes"]) == 1
    output = capsys.readouterr()
    assert DUMMY_SECRET not in output.out + output.err


def test_refresh_delegates_to_existing_flow(monkeypatch):
    module = ModuleType("nh_property_intelligence.orchestration.refresh")
    module.refresh_property_intelligence = MagicMock()
    monkeypatch.setitem(sys.modules, module.__name__, module)
    ops.run_refresh()
    module.refresh_property_intelligence.assert_called_once_with()


def test_help_needs_no_configuration_or_io(io, capsys):
    with pytest.raises(SystemExit) as result:
        ops.main(["--help"])
    assert result.value.code == 0
    assert "check" in capsys.readouterr().out
    io.settings_factory.assert_not_called()
    io.connect.assert_not_called()
    io.refresh.assert_not_called()
