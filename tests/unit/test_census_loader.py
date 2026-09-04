from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from nh_property_intelligence.ingestion.census.contract import ACS_VARIABLES, RunContext
from nh_property_intelligence.ingestion.census.loader import replace_vintage
from nh_property_intelligence.ingestion.census.normalize import normalize_response


def _row(subdivision: str = "66660"):
    header = ["NAME", *ACS_VARIABLES.keys(), "state", "county", "county subdivision"]
    values = {
        "NAME": "Salem town, Rockingham County, New Hampshire",
        "state": "33",
        "county": "015",
        "county subdivision": subdivision,
        **{code: "100" for code in ACS_VARIABLES},
    }
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    context = RunContext(
        ingestion_run_id="run-1",
        source_requested_at=now,
        ingested_at=now,
        source_endpoint="https://api.census.gov/data/2024/acs/acs5?example=1",
    )
    return normalize_response([header, [values[column] for column in header]], context)[0]


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.executed: list[tuple[str, Any]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self._fetch_value = 0
        self.closed = False

    def execute(self, sql: str, params: Any = None) -> "FakeCursor":
        self.executed.append((sql, params))
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("SELECT COUNT(*) FROM TEMP_CENSUS"):
            if "GROUP BY" in normalized:
                self._fetch_value = self.connection.duplicate_count
            elif "WHERE ACS_VINTAGE <>" in normalized:
                self._fetch_value = self.connection.invalid_count
            else:
                self._fetch_value = self.connection.staged_count
        elif normalized.startswith("SELECT COUNT(*) FROM RAW.CENSUS_ACS_MUNICIPALITY"):
            self._fetch_value = self.connection.inserted_count
        return self

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        self.executemany_calls.append((sql, rows))
        self.connection.staged_count = len(rows)
        if self.connection.inserted_count is None:
            self.connection.inserted_count = len(rows)

    def fetchone(self) -> tuple[int]:
        return (self._fetch_value,)

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.staged_count = 0
        self.inserted_count: int | None = None
        self.invalid_count = 0
        self.duplicate_count = 0
        self.committed = False
        self.rolled_back = False
        self.cursor_instance = FakeCursor(self)

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_replace_vintage_stages_validates_and_commits() -> None:
    connection = FakeConnection()

    result = replace_vintage([_row()], 2024, connection)

    assert result.rows_staged == 1
    assert result.rows_inserted == 1
    assert connection.committed is True
    assert connection.rolled_back is False
    insert_sql = connection.cursor_instance.executemany_calls[0][0]
    assert "PARSE_JSON(%s)" in insert_sql
    assert connection.cursor_instance.closed is True


def test_replace_vintage_rejects_duplicate_batch_before_snowflake() -> None:
    connection = FakeConnection()
    row = _row()

    with pytest.raises(ValueError, match="Duplicate Census natural key"):
        replace_vintage([row, row], 2024, connection)

    assert connection.cursor_instance.executed == []


def test_replace_vintage_rolls_back_on_insert_count_mismatch() -> None:
    connection = FakeConnection()
    connection.inserted_count = 0

    with pytest.raises(RuntimeError, match="Inserted row count mismatch"):
        replace_vintage([_row()], 2024, connection)

    assert connection.committed is False
    assert connection.rolled_back is True


def test_replace_vintage_fails_staged_validation_before_transaction() -> None:
    connection = FakeConnection()
    connection.invalid_count = 1

    with pytest.raises(RuntimeError, match="failed vintage/state/key validation"):
        replace_vintage([_row()], 2024, connection)

    assert connection.committed is False
    assert connection.rolled_back is False
