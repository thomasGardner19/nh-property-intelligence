"""Snowflake landing loader for normalized FHFA county HPI rows."""
from __future__ import annotations
import json
from collections.abc import Iterable
from dataclasses import dataclass, fields
from typing import Any
from uuid import uuid4
from .contract import RawCountyHpiRow
TARGET_TABLE = "RAW.FHFA_COUNTY_HPI"
@dataclass(frozen=True)
class LoadResult:
    rows_staged: int
    rows_inserted: int

def _columns() -> tuple[str, ...]:
    return tuple(field.name for field in fields(RawCountyHpiRow))
def _values(row: RawCountyHpiRow) -> tuple[Any, ...]:
    values = []
    for column in _columns():
        value = getattr(row, column)
        if column == "raw_payload":
            value = json.dumps(value, separators=(",", ":"), default=str)
        values.append(value)
    return tuple(values)
def replace_all(rows: Iterable[RawCountyHpiRow], connection: Any) -> LoadResult:
    batch = list(rows)
    if not batch:
        raise ValueError("Cannot load an empty FHFA batch")
    if any(row.state_code != "NH" for row in batch):
        raise ValueError("FHFA load batch must contain only NH rows")
    keys = [(row.county_fips, row.year) for row in batch]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate FHFA county/year keys in load batch")
    temp_table = f"TEMP_FHFA_COUNTY_HPI_{uuid4().hex.upper()}"
    columns = _columns()
    column_sql = ", ".join(columns)
    placeholders = ["%s"] * len(columns)
    placeholders[columns.index("raw_payload")] = "PARSE_JSON(%s)"
    cursor = connection.cursor()
    try:
        cursor.execute(f"CREATE TEMP TABLE {temp_table} LIKE {TARGET_TABLE}")
        cursor.executemany(
            f"INSERT INTO {temp_table} ({column_sql}) VALUES ({', '.join(placeholders)})",
            [_values(row) for row in batch],
        )
        cursor.execute(f"SELECT COUNT(*) FROM {temp_table}")
        staged = int(cursor.fetchone()[0])
        if staged != len(batch):
            raise RuntimeError("FHFA staged row count mismatch")
        connection.commit()
        cursor.execute("BEGIN")
        try:
            cursor.execute(f"DELETE FROM {TARGET_TABLE}")
            cursor.execute(f"INSERT INTO {TARGET_TABLE} ({column_sql}) SELECT {column_sql} FROM {temp_table}")
            cursor.execute(f"SELECT COUNT(*) FROM {TARGET_TABLE}")
            inserted = int(cursor.fetchone()[0])
            if inserted != len(batch):
                raise RuntimeError("FHFA inserted row count mismatch")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return LoadResult(rows_staged=staged, rows_inserted=inserted)
    finally:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        finally:
            cursor.close()
