"""Snowflake landing loader for normalized Census ACS municipality rows."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, fields
from typing import Any
from uuid import uuid4

from .contract import RawMunicipalityRow

TARGET_TABLE = "RAW.CENSUS_ACS_MUNICIPALITY"


@dataclass(frozen=True)
class LoadResult:
    acs_vintage: int
    rows_staged: int
    rows_inserted: int


def _column_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(RawMunicipalityRow))


def _row_values(row: RawMunicipalityRow) -> tuple[Any, ...]:
    values: list[Any] = []
    for column in _column_names():
        value = getattr(row, column)
        if column == "raw_payload":
            value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        values.append(value)
    return tuple(values)


def _validate_batch(rows: list[RawMunicipalityRow], vintage: int) -> None:
    if not rows:
        raise ValueError("Cannot load an empty Census ACS batch")
    if any(row.acs_vintage != vintage for row in rows):
        raise ValueError("All Census rows must match the requested ACS vintage")

    seen: set[tuple[int, str]] = set()
    for row in rows:
        if row.state_fips != "33":
            raise ValueError(f"Unexpected state FIPS in load batch: {row.state_fips!r}")
        if not row.county_subdivision_geoid:
            raise ValueError("Census row is missing county_subdivision_geoid")
        key = (row.acs_vintage, row.county_subdivision_geoid)
        if key in seen:
            raise ValueError(f"Duplicate Census natural key in load batch: {key}")
        seen.add(key)


def replace_vintage(
    rows: Iterable[RawMunicipalityRow],
    vintage: int,
    connection: Any,
) -> LoadResult:
    """Stage and atomically replace one Census ACS vintage in Snowflake."""
    batch = list(rows)
    _validate_batch(batch, vintage)

    temp_table = f"TEMP_CENSUS_ACS_MUNICIPALITY_{uuid4().hex.upper()}"
    columns = _column_names()
    column_sql = ", ".join(columns)
    placeholders = ["%s"] * len(columns)
    raw_payload_index = columns.index("raw_payload")
    placeholders[raw_payload_index] = "PARSE_JSON(%s)"
    values_sql = ", ".join(placeholders)

    cursor = connection.cursor()
    try:
        cursor.execute(f"CREATE TEMP TABLE {temp_table} LIKE {TARGET_TABLE}")
        cursor.executemany(
            f"INSERT INTO {temp_table} ({column_sql}) VALUES ({values_sql})",
            [_row_values(row) for row in batch],
        )

        cursor.execute(f"SELECT COUNT(*) FROM {temp_table}")
        staged_count = int(cursor.fetchone()[0])
        if staged_count != len(batch):
            raise RuntimeError(
                f"Staged row count mismatch: expected {len(batch)}, found {staged_count}"
            )

        cursor.execute(
            f"SELECT COUNT(*) FROM {temp_table} "
            "WHERE acs_vintage <> %s OR state_fips <> '33' "
            "OR county_subdivision_geoid IS NULL",
            (vintage,),
        )
        if int(cursor.fetchone()[0]) != 0:
            raise RuntimeError("Staged Census batch failed vintage/state/key validation")

        cursor.execute(
            f"SELECT COUNT(*) FROM ("
            f"SELECT acs_vintage, county_subdivision_geoid FROM {temp_table} "
            "GROUP BY acs_vintage, county_subdivision_geoid HAVING COUNT(*) > 1"
            ")"
        )
        if int(cursor.fetchone()[0]) != 0:
            raise RuntimeError("Staged Census batch contains duplicate natural keys")

        # Close the staging DML transaction before beginning the atomic target replacement.
        connection.commit()

        cursor.execute("BEGIN")
        try:
            cursor.execute(f"DELETE FROM {TARGET_TABLE} WHERE acs_vintage = %s", (vintage,))
            cursor.execute(
                f"INSERT INTO {TARGET_TABLE} ({column_sql}) "
                f"SELECT {column_sql} FROM {temp_table}"
            )
            cursor.execute(
                f"SELECT COUNT(*) FROM {TARGET_TABLE} WHERE acs_vintage = %s",
                (vintage,),
            )
            inserted_count = int(cursor.fetchone()[0])
            if inserted_count != len(batch):
                raise RuntimeError(
                    f"Inserted row count mismatch: expected {len(batch)}, found {inserted_count}"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        return LoadResult(
            acs_vintage=vintage,
            rows_staged=staged_count,
            rows_inserted=inserted_count,
        )
    finally:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        finally:
            cursor.close()
