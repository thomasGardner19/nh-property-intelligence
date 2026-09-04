from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from nh_property_intelligence.ingestion.dra.contract import RunContext
from nh_property_intelligence.ingestion.dra.loader import replace_tax_year
from nh_property_intelligence.ingestion.dra.normalize import normalize_records


def _row():
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    context = RunContext(
        ingestion_run_id="run-1",
        source_file_name="2025-municipal-tax-rates.pdf",
        source_url="https://example.test/2025-municipal-tax-rates.pdf",
        source_requested_at=now,
        ingested_at=now,
    )
    record = {
        "Municipality": "Salem",
        "Date": "10/15/2025",
        "Valuation": "5,000,000,000",
        "Valuation Including Utilities": "5,100,000,000",
        "Municipal Tax Rate": "4.25",
        "County Tax Rate": "0.95",
        "State Education Tax Rate": "1.55",
        "Local Education Tax Rate": "7.25",
        "Total Tax Rate": "14.00",
        "Total Commitment": "71,400,000",
    }
    return normalize_records([record], context)[0]


class FakeConnection:
    def __init__(self) -> None:
        self.staged_count = 0
        self.inserted_count: int | None = None
        self.invalid_count = 0
        self.duplicate_count = 0
        self.commit_count = 0
        self.rolled_back = False
        self.cursor_instance = FakeCursor(self)

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rolled_back = True


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.executed: list[tuple[str, Any]] = []
        self._fetch_value = 0
        self.closed = False

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        self.executed.append((sql, params))
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("SELECT COUNT(*) FROM TEMP_DRA"):
            if "GROUP BY" in normalized:
                self._fetch_value = self.connection.duplicate_count
            elif "WHERE TAX_YEAR <>" in normalized:
                self._fetch_value = self.connection.invalid_count
            else:
                self._fetch_value = self.connection.staged_count
        elif normalized.startswith("SELECT COUNT(*) FROM RAW.DRA_MUNICIPAL_TAX_RATES"):
            self._fetch_value = self.connection.inserted_count or 0
        return self

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        self.connection.staged_count = len(rows)
        if self.connection.inserted_count is None:
            self.connection.inserted_count = len(rows)

    def fetchone(self) -> tuple[int]:
        return (self._fetch_value,)

    def close(self) -> None:
        self.closed = True


def test_replace_tax_year_commits_staging_and_target() -> None:
    connection = FakeConnection()

    result = replace_tax_year([_row()], 2025, connection)

    assert result.rows_staged == 1
    assert result.rows_inserted == 1
    assert connection.commit_count == 2
    assert connection.rolled_back is False
    assert connection.cursor_instance.closed is True


def test_replace_tax_year_rejects_duplicate_batch() -> None:
    connection = FakeConnection()
    row = _row()

    with pytest.raises(ValueError, match="Duplicate DRA natural key"):
        replace_tax_year([row, row], 2025, connection)


def test_replace_tax_year_rolls_back_target_on_count_mismatch() -> None:
    connection = FakeConnection()
    connection.inserted_count = 0

    with pytest.raises(RuntimeError, match="Inserted row count mismatch"):
        replace_tax_year([_row()], 2025, connection)

    assert connection.commit_count == 1
    assert connection.rolled_back is True
