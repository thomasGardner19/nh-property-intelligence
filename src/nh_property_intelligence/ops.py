"""Owner-operated check / refresh / validate commands; no scheduled execution."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from contextlib import closing, contextmanager

RAW_TABLES = (
    "CENSUS_ACS_MUNICIPALITY",
    "DRA_MUNICIPAL_TAX_RATES",
    "FHFA_COUNTY_HPI",
)
QUALITY_CAVEAT = "Counts alone do not prove quality; review loader checks and dbt build/tests."


@contextmanager
def quiet_connector():
    """Match refresh's policy of suppressing sensitive connector diagnostics."""
    names = {"snowflake.connector"} | {
        name
        for name in logging.Logger.manager.loggerDict
        if name.startswith("snowflake.connector.")
    }
    previous = [(logging.getLogger(name), logging.getLogger(name).disabled) for name in names]
    for logger, _ in previous:
        logger.disabled = True
    try:
        yield
    finally:
        for logger, disabled in previous:
            logger.disabled = disabled


def qualified(database: str, schema: str, table: str) -> str:
    """Quote each identifier component; the resulting name is passed as a bind."""
    return ".".join('"' + part.replace('"', '""') + '"' for part in (database, schema, table))


def inspect_warehouse(*, validate: bool = False) -> tuple[list[str], bool]:
    """Read context and aggregate counts, always closing acquired resources."""
    from .config import Settings
    from .snowflake import connect_snowflake

    settings = Settings()
    lines = []
    healthy = True
    with (
        quiet_connector(),
        closing(connect_snowflake(settings)) as connection,
        closing(connection.cursor()) as cursor,
    ):
        cursor.execute(
            "SELECT CURRENT_ACCOUNT(), CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_WAREHOUSE()"
        )
        context = cursor.fetchone()
        secrets = [
            value.get_secret_value()
            for value in (settings.snowflake_password, settings.census_api_key)
            if value is not None and value.get_secret_value()
        ]
        for label, value in zip(("account", "role", "database", "warehouse"), context, strict=True):
            text = str(value)
            for secret in secrets:
                text = text.replace(secret, "[REDACTED]")
            lines.append(f"{label}: {text}")
        for table in RAW_TABLES:
            cursor.execute(
                "SELECT COUNT(*) FROM IDENTIFIER(%s)",
                (qualified(settings.snowflake_database, "RAW", table),),
            )
            count = int(cursor.fetchone()[0])
            lines.append(f"RAW.{table}: {count} rows")
            healthy = healthy and count > 0
        if validate:
            cursor.execute(
                "SELECT COUNT(*) FROM IDENTIFIER(%s) WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (
                    qualified(settings.snowflake_database, "INFORMATION_SCHEMA", "TABLES"),
                    "ANALYTICS",
                    "MART_TOWN_SCORECARD",
                ),
            )
            if int(cursor.fetchone()[0]) == 0:
                lines.append("ANALYTICS.MART_TOWN_SCORECARD: missing or not visible to this role")
                healthy = False
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM IDENTIFIER(%s)",
                    (qualified(settings.snowflake_database, "ANALYTICS", "MART_TOWN_SCORECARD"),),
                )
                count = int(cursor.fetchone()[0])
                lines.append(f"ANALYTICS.MART_TOWN_SCORECARD: {count} rows")
                healthy = healthy and count > 0
            lines.append(QUALITY_CAVEAT)
    return lines, healthy


def run_refresh() -> None:
    """Import Prefect only after the CLI's explicit approval gate."""
    from .orchestration.refresh import refresh_property_intelligence

    refresh_property_intelligence()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Read account context and RAW counts (SELECT only).")
    refresh = commands.add_parser(
        "refresh", help="Replace RAW snapshots and build analytics using the existing Prefect flow."
    )
    refresh.add_argument(
        "--approve-raw-writes",
        action="store_true",
        help="Approve source downloads, RAW snapshot replacement, and dbt analytics writes.",
    )
    commands.add_parser("validate", help="Read RAW counts and mart visibility/count (SELECT only).")
    args = parser.parse_args(argv)
    if args.command == "refresh" and not args.approve_raw_writes:
        print(
            "error: refresh requires --approve-raw-writes; it downloads sources, replaces RAW "
            "snapshots and runs dbt build (analytics writes).",
            file=sys.stderr,
        )
        return 2
    try:
        if args.command == "refresh":
            print("APPROVED: replacing RAW snapshots and building analytics via Prefect.")
            run_refresh()
        else:
            lines, healthy = inspect_warehouse(validate=args.command == "validate")
            print("\n".join(lines))
            if args.command == "validate" and not healthy:
                print(
                    "error: validation found empty tables or an unavailable mart.", file=sys.stderr
                )
                return 1
    except Exception:  # noqa: BLE001 - never print settings or third-party exception text
        print(
            "error: operation failed. Check nonsecret configuration, owner-controlled "
            "authentication, role grants and object availability. Sensitive diagnostics omitted.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
