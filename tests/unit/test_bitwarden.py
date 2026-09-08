from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from nh_property_intelligence.bitwarden import read_item_password, run_with_bitwarden


def test_reads_secret_from_unlocked_vault_without_putting_it_in_arguments() -> None:
    completed = subprocess.CompletedProcess([], 0, stdout="census-secret\n", stderr="")
    with (
        patch("nh_property_intelligence.bitwarden.shutil.which", return_value="/usr/bin/bw"),
        patch("nh_property_intelligence.bitwarden.subprocess.run", return_value=completed) as run,
    ):
        secret = read_item_password("NHPI Census API Key", session="vault-session")

    assert secret == "census-secret"
    assert run.call_args.args[0] == ["bw", "get", "password", "NHPI Census API Key"]
    assert "census-secret" not in repr(run.call_args)


def test_locked_vault_fails_before_running_bitwarden() -> None:
    with (
        patch("nh_property_intelligence.bitwarden.shutil.which", return_value="/usr/bin/bw"),
        patch("nh_property_intelligence.bitwarden.subprocess.run") as run,
        pytest.raises(RuntimeError, match="vault is locked"),
    ):
        read_item_password("NHPI Census API Key")

    run.assert_not_called()


def test_injects_selected_secrets_only_into_child_environment() -> None:
    completed = subprocess.CompletedProcess([], 0)
    with (
        patch(
            "nh_property_intelligence.bitwarden.read_item_password",
            side_effect=["snowflake-secret", "census-secret"],
        ),
        patch("nh_property_intelligence.bitwarden.subprocess.run", return_value=completed) as run,
    ):
        exit_code = run_with_bitwarden(
            ["python", "pipeline.py"],
            snowflake_item="snowflake-item",
            census_item="census-item",
            session="session",
        )

    assert exit_code == 0
    assert run.call_args.args[0] == ["python", "pipeline.py"]
    assert run.call_args.kwargs["env"]["SNOWFLAKE_PASSWORD"] == "snowflake-secret"
    assert run.call_args.kwargs["env"]["CENSUS_API_KEY"] == "census-secret"


def test_census_secret_is_optional() -> None:
    completed = subprocess.CompletedProcess([], 0)
    with (
        patch(
            "nh_property_intelligence.bitwarden.read_item_password",
            return_value="snowflake-secret",
        ),
        patch("nh_property_intelligence.bitwarden.subprocess.run", return_value=completed) as run,
    ):
        run_with_bitwarden(
            ["dbt", "debug"], snowflake_item="snowflake-item", session="session"
        )

    assert "CENSUS_API_KEY" not in run.call_args.kwargs["env"]
