# FHFA Annual County HPI ingestion

Source: FHFA **Annual House Price Indexes — Counties (Developmental Index; Not Seasonally Adjusted)**.

Current published workbook URL:

`https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx`

## Grain

One row per `county_fips × year` after filtering to New Hampshire (`state_code = NH`).

## Raw contract

The loader preserves:

- state code
- county name as published
- five-digit county FIPS
- year
- annual change percent
- HPI
- HPI rebased to 1990
- HPI rebased to 2000
- raw workbook row
- source file/URL and ingestion metadata
- deterministic row hash

Missing FHFA index values represented as blank, `.`, `NA`, or `N/A` become null in typed columns while the extracted source value remains in `raw_payload`.

## Semantics

FHFA describes these local annual HPIs as developmental and not seasonally adjusted. The project uses this source only for **county-level market momentum**. County HPI must not be presented as municipality-level appreciation.

The dbt intermediate model derives 1-, 3-, 5-, and 10-year cumulative appreciation plus 5-year CAGR only when an observation exists for the exact required prior year. Missing years are not interpolated.
