"""PDF table extraction for NH DRA municipal tax reports."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pdfplumber

from .contract import EXPECTED_FIELDS


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split())


def extract_records(pdf_bytes: bytes) -> list[dict[str, str]]:
    """Extract source-string records from the published DRA PDF."""
    records: list[dict[str, str]] = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table:
                    continue
                header_index = None
                for index, row in enumerate(table):
                    cleaned = [_clean_cell(cell) for cell in row]
                    if cleaned and cleaned[0] == "Municipality" and "Total Tax Rate" in cleaned:
                        header_index = index
                        break
                if header_index is None:
                    continue

                header = [_clean_cell(cell) for cell in table[header_index]]
                if any(field not in header for field in EXPECTED_FIELDS):
                    raise ValueError("DRA tax table is missing one or more expected columns")

                for row in table[header_index + 1 :]:
                    cleaned = [_clean_cell(cell) for cell in row]
                    if not any(cleaned):
                        continue
                    payload = dict(zip(header, cleaned, strict=False))
                    municipality = payload.get("Municipality", "")
                    if not municipality or municipality.lower().startswith("municipality"):
                        continue
                    records.append(payload)

    if not records:
        raise ValueError("No municipal tax records were extracted from the DRA PDF")
    return records
