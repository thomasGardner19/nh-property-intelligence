"""Snowflake landing loader for normalized NH DRA municipal tax rows."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, fields
from typing import Any
from uuid import uuid4

from .contract import RawMunicipalTaxRateRow

TARGET_TABLE = "RAW.DRA_MUNICIPAL_TAX_RATES"


@dataclass(frozen=True)
class LoadResult:
    tax_year: int
    rows_staged: int
    rows_inserted: int


def _column_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(RawMunicipalTaxRateRow))


def _row_values(row: RawMunicipalTaxRateRow) -> tuple[Any, ...]:
    values: list[Any] = []
    for column in _column_names():
        value = getattr(row, column)
        if column == "raw_payload":
            value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        values.append(value)
    return tuple(values)


def _validate_batch(rows: list[RawMunicipalTaxRateRow], tax_year: int) -> None:
    if not rows:
        raise ValueError("Cannot load an empty DRA municipal tax batch")
    if any(row.tax_year != tax_year for row in rows):
        raise ValueError("All DRA rows must match the requested tax year")

    seen: set[tuple[int, str]] = set()
    for row in rows:
        if not row.municipality_name_raw:
            raise ValueError("DRA row is missing municipality_name_raw")
        key = (row.tax_year, row.municipality_name_raw)
        if key in seen:
            raise ValueError(f"Duplicate DRA natural key in load batch: {key}")
        seen.add(key)


def replace_tax_year(
    rows: Iterable[RawMunicipalTaxRateRow],
    tax_year: int,
    connection: Any,
) -> LoadResult:
    """Stage and atomically replace one DRA municipal tax year in Snowflake."""
    batch = list(rows)
    _validate_batch(batch, tax_year)

    temp_table = f"TEMP_DRA_MUNICIPAL_TAX_RATES_{uuid4().hex.upper()}"
    columns = _column_names()
    column_sql = ", ".join(columns)
    placeholders = ["%s"] * len(columns)
    placeholders[columns.index("raw_payload")] = "PARSE_JSON(%s)"
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
            "WHERE tax_year <> %s OR municipality_name_raw IS NULL",
            (tax_year,),
        )
        if int(cursor.fetchone()[0]) != 0:
            raise RuntimeError("Staged DRA batch failed tax-year/key validation")

        cursor.execute(
            f"SELECT COUNT(*) FROM ("
            f"SELECT tax_year, municipality_name_raw FROM {temp_table} "
            "GROUP BY tax_year, municipality_name_raw HAVING COUNT(*) > 1"
            ")"
        )
        if int(cursor.fetchone()[0]) != 0:
            raise RuntimeError("Staged DRA batch contains duplicate natural keys")

        connection.commit()
        cursor.execute("BEGIN")
        try:
            cursor.execute(f"DELETE FROM {TARGET_TABLE} WHERE tax_year = %s", (tax_year,))
            cursor.execute(
                f"INSERT INTO {TARGET_TABLE} ({column_sql}) "
                f"SELECT {column_sql} FROM {temp_table}"
            )
            cursor.execute(
                f"SELECT COUNT(*) FROM {TARGET_TABLE} WHERE tax_year = %s",
                (tax_year,),
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
            tax_year=tax_year,
            rows_staged=staged_count,
            rows_inserted=inserted_count,
        )
    finally:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        finally:
            cursor.close()
