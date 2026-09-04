"""Census ACS ingestion support."""

from .client import RequestSpec, build_request, fetch_response
from .contract import ACS_VARIABLES, RawMunicipalityRow, RunContext
from .loader import LoadResult, replace_vintage
from .normalize import normalize_response

__all__ = [
    "ACS_VARIABLES",
    "LoadResult",
    "RawMunicipalityRow",
    "RequestSpec",
    "RunContext",
    "build_request",
    "fetch_response",
    "normalize_response",
    "replace_vintage",
]
