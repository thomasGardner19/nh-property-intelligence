from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from nh_property_intelligence.ingestion.fhfa.extract import extract_records


def test_extract_records_locates_header_and_returns_rows() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["FHFA Annual County HPI"])
    worksheet.append(
        [
            "State",
            "County",
            "FIPS code",
            "Year",
            "Annual Change (%)",
            "HPI",
            "HPI with 1990 base",
            "HPI with 2000 base",
        ]
    )
    worksheet.append(["NH", "Rockingham County", 33015, 2025, 3.25, 420.5, 385.1, 250.2])
    stream = BytesIO()
    workbook.save(stream)

    records = extract_records(stream.getvalue())

    assert records[0]["State"] == "NH"
    assert records[0]["FIPS code"] == 33015
    assert records[0]["Year"] == 2025
