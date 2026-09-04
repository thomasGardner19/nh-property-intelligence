"""NH DRA municipal tax ingestion support."""

from .client import fetch_report
from .contract import RawMunicipalTaxRateRow, RunContext
from .extract import extract_records
from .loader import LoadResult, replace_tax_year
from .normalize import normalize_records

__all__ = [
    "LoadResult",
    "RawMunicipalTaxRateRow",
    "RunContext",
    "extract_records",
    "fetch_report",
    "normalize_records",
    "replace_tax_year",
]
