"""Refresh validated RAW snapshots before building the real dbt project."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, quote_plus
from uuid import uuid4

import httpx
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

from nh_property_intelligence.config import Settings
from nh_property_intelligence.ingestion.census import client as census_client
from nh_property_intelligence.ingestion.census import contract as census_contract
from nh_property_intelligence.ingestion.census import loader as census_loader
from nh_property_intelligence.ingestion.census.normalize import normalize_response
from nh_property_intelligence.ingestion.dra import client as dra_client
from nh_property_intelligence.ingestion.dra import contract as dra_contract
from nh_property_intelligence.ingestion.dra import extract as dra_extract
from nh_property_intelligence.ingestion.dra import loader as dra_loader
from nh_property_intelligence.ingestion.dra import normalize as dra_normalize
from nh_property_intelligence.ingestion.fhfa import client as fhfa_client
from nh_property_intelligence.ingestion.fhfa import contract as fhfa_contract
from nh_property_intelligence.ingestion.fhfa import extract as fhfa_extract
from nh_property_intelligence.ingestion.fhfa import loader as fhfa_loader
from nh_property_intelligence.ingestion.fhfa import normalize as fhfa_normalize
from nh_property_intelligence.snowflake import connect_snowflake

DRA_URL = (
    "https://www.revenue.nh.gov/sites/g/files/ehbemt736/files/documents/"
    "2025-municipal-tax-rates.pdf"
)
FHFA_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx"
DBT_PROJECT = Path(__file__).resolve().parents[3] / "dbt" / "nh_property_intelligence"


class RefreshError(RuntimeError):
    """Safe operational error, excluding raw third-party exception text."""


class TransientSourceError(RefreshError):
    """An HTTP failure for which repeating a snapshot load is appropriate."""


def safe_task_errors(function):
    """Drop exception chains before Prefect serializes failures, even with persistence off."""

    @wraps(function)
    def run(*args, **kwargs):
        failure = None
        # HTTP logs can include the Census query key; connector debug logs can include binds.
        # Flows are intentionally sequential. Restore caller logging after the task finishes.
        loggers = [
            logging.getLogger(name)
            for name in list(logging.Logger.manager.loggerDict)
            if name == "httpx" or name.startswith(("httpcore", "snowflake.connector"))
        ]
        previous = [(logger, logger.disabled) for logger in loggers]
        for logger in loggers:
            logger.disabled = True
        try:
            return function(*args, **kwargs)
        except RefreshError as exc:
            failure = type(exc)(str(exc))
        except Exception as exc:  # noqa: BLE001 - never expose third-party exception state
            failure = RefreshError(f"{function.__name__} failed: {type(exc).__name__}")
        finally:
            for logger, disabled in previous:
                logger.disabled = disabled
        raise failure

    return run


def retry_transient(task, task_run, state) -> bool:
    return isinstance(state.result(raise_on_failure=False), TransientSourceError)


@contextmanager
def source_step(source: str, phase: str):
    """Keep request URLs, settings, and connector credentials out of Prefect errors."""
    error = None
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - sanitize all external failures before Prefect
        transient = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or (
            isinstance(exc, httpx.HTTPStatusError)
            and (exc.response.status_code == 429 or 500 <= exc.response.status_code < 600)
        )
        kind = TransientSourceError if transient else RefreshError
        status = (
            f" HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else ""
        )
        error = kind(f"{source} failed during {phase}: {type(exc).__name__}{status}")
    # The task boundary strips the context attached by contextlib before Prefect sees it.
    if error is not None:
        get_run_logger().error(str(error))
        raise error


def summary(source: str, extracted: int, normalized: int, loaded: int) -> dict:
    result = {
        "source": source,
        "rows_extracted": extracted,
        "rows_normalized": normalized,
        "rows_loaded": loaded,
    }
    get_run_logger().info("%s completed: %s", source, result)
    return result


@task(
    retries=2,
    retry_delay_seconds=[5, 20],
    retry_condition_fn=retry_transient,
    persist_result=False,
    cache_policy=NO_CACHE,
)
@safe_task_errors
def ingest_census(vintage: int = census_contract.ACS_VINTAGE) -> dict:
    get_run_logger().info("Census starting: ACS vintage=%s", vintage)
    with source_step("Census", "configuration/extraction"):
        settings = Settings()
        key = settings.census_api_key.get_secret_value() if settings.census_api_key else None
        spec = census_client.build_request(vintage, key)
        requested = datetime.now(UTC)
        with httpx.Client(follow_redirects=True) as client:
            payload = census_client.fetch_response(spec, client, max_attempts=1)
    get_run_logger().info("Census rows_extracted=%s", max(0, len(payload) - 1))
    with source_step("Census", "normalization"):
        context = census_contract.RunContext(
            str(uuid4()), requested, datetime.now(UTC), spec.source_endpoint, acs_vintage=vintage
        )
        rows = normalize_response(payload, context)
    get_run_logger().info("Census rows_normalized=%s", len(rows))
    with (
        source_step("Census", "Snowflake load/cleanup"),
        closing(connect_snowflake(settings)) as connection,
    ):
        result = census_loader.replace_vintage(rows, vintage, connection)
    return summary("Census", len(payload) - 1, len(rows), result.rows_inserted)


@task(
    retries=2,
    retry_delay_seconds=[5, 20],
    retry_condition_fn=retry_transient,
    persist_result=False,
    cache_policy=NO_CACHE,
)
@safe_task_errors
def ingest_dra(tax_year: int = dra_contract.TAX_YEAR) -> dict:
    get_run_logger().info("NH DRA starting: tax_year=%s", tax_year)
    with source_step("NH DRA", "configuration/extraction"):
        if tax_year != dra_contract.TAX_YEAR:
            raise ValueError("Unsupported DRA tax year")
        settings = Settings()
        requested = datetime.now(UTC)
        with httpx.Client(follow_redirects=True) as client:
            payload = dra_client.fetch_report(DRA_URL, client, max_attempts=1)
        records = dra_extract.extract_records(payload)
    get_run_logger().info("NH DRA rows_extracted=%s", len(records))
    with source_step("NH DRA", "normalization"):
        context = dra_contract.RunContext(
            str(uuid4()), DRA_URL.rsplit("/", 1)[1], DRA_URL, requested, datetime.now(UTC)
        )
        rows = dra_normalize.normalize_records(records, context, tax_year=tax_year)
    get_run_logger().info("NH DRA rows_normalized=%s", len(rows))
    with (
        source_step("NH DRA", "Snowflake load/cleanup"),
        closing(connect_snowflake(settings)) as connection,
    ):
        result = dra_loader.replace_tax_year(rows, tax_year, connection)
    return summary("NH DRA", len(records), len(rows), result.rows_inserted)


@task(
    retries=2,
    retry_delay_seconds=[5, 20],
    retry_condition_fn=retry_transient,
    persist_result=False,
    cache_policy=NO_CACHE,
)
@safe_task_errors
def ingest_fhfa() -> dict:
    get_run_logger().info("FHFA starting: complete NH annual county series")
    with source_step("FHFA", "configuration/extraction"):
        settings = Settings()
        requested = datetime.now(UTC)
        with httpx.Client(follow_redirects=True) as client:
            payload = fhfa_client.fetch_workbook(FHFA_URL, client, max_attempts=1)
        records = fhfa_extract.extract_records(payload)
    get_run_logger().info("FHFA rows_extracted=%s (national workbook)", len(records))
    with source_step("FHFA", "normalization"):
        context = fhfa_contract.RunContext(
            FHFA_URL.rsplit("/", 1)[1], FHFA_URL, requested, datetime.now(UTC), str(uuid4())
        )
        rows = fhfa_normalize.normalize_records(records, context)
    get_run_logger().info("FHFA rows_normalized=%s (NH only)", len(rows))
    with (
        source_step("FHFA", "Snowflake load/cleanup"),
        closing(connect_snowflake(settings)) as connection,
    ):
        result = fhfa_loader.replace_all(rows, connection)
    return summary("FHFA", len(records), len(rows), result.rows_inserted)


def redact_output(output: str, environment: dict[str, str]) -> str:
    for name, value in environment.items():
        if value and any(
            part in name.upper() for part in ("PASSWORD", "TOKEN", "SECRET", "KEY", "BW_")
        ):
            for representation in (value, quote(value, safe=""), quote_plus(value)):
                output = output.replace(representation, "[REDACTED]")
    return output


@task(retries=0, persist_result=False, cache_policy=NO_CACHE)
@safe_task_errors
def dbt_build() -> dict:
    with source_step("dbt", "configuration/build"):
        settings = Settings()
        environment = os.environ.copy()
        # Settings also reads local .env; explicitly propagate the same resolved values to dbt.
        for name in ("account", "user", "authenticator", "role", "warehouse", "database"):
            environment[f"SNOWFLAKE_{name.upper()}"] = getattr(settings, f"snowflake_{name}")
        if settings.snowflake_password:
            environment["SNOWFLAKE_PASSWORD"] = settings.snowflake_password.get_secret_value()
        if settings.census_api_key:
            environment["CENSUS_API_KEY"] = settings.census_api_key.get_secret_value()
        # A temporary env-only profile avoids requiring a second local configuration file.
        with TemporaryDirectory(prefix="nhpi-dbt-") as directory:
            Path(directory, "profiles.yml").write_text(
                (DBT_PROJECT / "profiles.example.yml").read_text()
            )
            result = subprocess.run(
                [
                    str(Path(sys.executable).with_name("dbt")),
                    "build",
                    "--project-dir",
                    str(DBT_PROJECT),
                    "--profiles-dir",
                    directory,
                    "--target-path",
                    directory,
                    "--log-path",
                    directory,
                    "--log-level-file",
                    "none",
                    "--no-write-json",
                    "--no-use-colors",
                ],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        logger = get_run_logger()
        logger.info("dbt return_code=%s", result.returncode)
        for label, output in (("stdout", result.stdout), ("stderr", result.stderr)):
            logger.info(
                "dbt %s (last 16000 characters):\n%s",
                label,
                redact_output(output, environment)[-16000:],
            )
    if result.returncode != 0:
        raise RefreshError(f"dbt build failed with return code {result.returncode}; see task logs")
    return {"return_code": result.returncode}


@flow(name="refresh_property_intelligence", retries=0, persist_result=False, log_prints=False)
def refresh_property_intelligence() -> dict:
    """Blocking task calls enforce the required source-before-transformation dependency."""
    sources = [ingest_census(), ingest_dra(), ingest_fhfa()]
    dbt = dbt_build()
    result = {"sources": sources, "dbt": dbt}
    get_run_logger().info("Property intelligence refresh completed: %s", result)
    return result


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    refresh_property_intelligence()


if __name__ == "__main__":
    main()
