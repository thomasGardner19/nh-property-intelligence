"""Run project commands with credentials injected from Bitwarden."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from collections.abc import Sequence

DEFAULT_CENSUS_ITEM = "NHPI Census API Key"
DEFAULT_SNOWFLAKE_ITEM = "NHPI Snowflake"


def read_item_password(item: str, *, session: str | None = None) -> str:
    """Read an item password without echoing it or placing it in a command argument."""
    if shutil.which("bw") is None:
        raise RuntimeError("Bitwarden CLI is not installed")
    if not session:
        raise RuntimeError("Bitwarden vault is locked; set BW_SESSION after running 'bw unlock'")

    environment = os.environ.copy()
    environment["BW_SESSION"] = session
    result = subprocess.run(
        ["bw", "get", "password", item],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Bitwarden could not retrieve the configured item {item!r}")
    secret = result.stdout.strip()
    if not secret:
        raise RuntimeError(f"Bitwarden item {item!r} has an empty password field")
    return secret


def run_with_bitwarden(
    command: Sequence[str],
    *,
    snowflake_item: str,
    census_item: str | None = None,
    session: str | None = None,
) -> int:
    """Run a command with selected secrets available only in the child environment."""
    if not command:
        raise ValueError("A command is required")
    environment = os.environ.copy()
    environment["SNOWFLAKE_PASSWORD"] = read_item_password(snowflake_item, session=session)
    if census_item is not None:
        environment["CENSUS_API_KEY"] = read_item_password(census_item, session=session)
    return subprocess.run(list(command), check=False, env=environment).returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a command with credentials injected from an unlocked Bitwarden vault."
    )
    parser.add_argument(
        "--snowflake-item",
        default=os.getenv("BITWARDEN_SNOWFLAKE_ITEM", DEFAULT_SNOWFLAKE_ITEM),
        help="Bitwarden login item name or ID whose password field contains a Snowflake password or PAT.",
    )
    parser.add_argument(
        "--with-census",
        action="store_true",
        help="Also inject CENSUS_API_KEY from the configured Census item.",
    )
    parser.add_argument(
        "--census-item",
        default=os.getenv("BITWARDEN_CENSUS_ITEM", DEFAULT_CENSUS_ITEM),
        help="Bitwarden login item name or ID whose password field contains the Census API key.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args(argv)
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after '--'")
    try:
        return run_with_bitwarden(
            command,
            snowflake_item=arguments.snowflake_item,
            census_item=arguments.census_item if arguments.with_census else None,
            session=os.getenv("BW_SESSION"),
        )
    except RuntimeError as exc:
        parser.exit(1, f"error: {exc}\n")
