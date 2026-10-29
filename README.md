# NH Property Intelligence Platform

NH Property Intelligence Platform is a portfolio analytics project for bringing New Hampshire housing, property-tax, demographic, and market data into one reliable analytical foundation.

## Project purpose

The project will collect public data, preserve source-level history in Snowflake, transform it into documented analytics models with dbt, and expose decision-ready measures for Power BI. The repository is intended to demonstrate a maintainable, testable data-platform workflow rather than a one-off dashboard.

## Business problem

Housing affordability and property-market conditions are difficult to evaluate when demographic, municipal finance, assessment, and price-index data live in separate systems and use different geographic and time grains. This platform aims to make those signals comparable so analysts can answer questions about affordability, tax burden, valuation, and market trends across New Hampshire.

## Planned architecture

1. Python ingestion jobs retrieve and validate source data from public APIs and published files.
2. Prefect flows schedule ingestion and record operational outcomes.
3. Raw data lands in source-aligned Snowflake schemas.
4. dbt builds staging, intermediate, and mart models with tests and documentation.
5. Power BI consumes curated marts for analysis and reporting.
6. Docker provides consistent local tooling, while GitHub Actions runs Python and dbt checks.

See [`docs/architecture.md`](docs/architecture.md) for the planned component boundaries.

## Initial data sources

- **U.S. Census American Community Survey (ACS):** population, household, income, housing-cost, tenure, and vacancy measures.
- **New Hampshire Department of Revenue Administration (DRA):** municipal valuation, tax-rate, and related property-tax publications.
- **Federal Housing Finance Agency (FHFA):** house price indexes and market trends.

## Planned stack

| Area | Technology |
| --- | --- |
| Ingestion and utilities | Python |
| Cloud data warehouse | Snowflake |
| Transformation and testing | dbt |
| Orchestration | Prefect |
| Local runtime | Docker |
| Continuous integration | GitHub Actions |
| Business intelligence | Power BI |

## MVP goals

- Ingest a defined initial dataset from each source with repeatable, idempotent workflows.
- Establish Snowflake roles, database objects, and source-oriented schemas.
- Standardize geographic and time dimensions across sources.
- Build tested dbt marts for affordability, property-tax, and house-price trends.
- Publish a Power BI report backed only by curated marts.
- Document lineage, assumptions, data quality checks, and local setup.

## Current project status

**Initial scaffold.** The repository currently defines the intended structure, configuration contracts, CI entry points, and design documentation. Source integrations, warehouse objects, dbt models, orchestration flows, and reports remain planned work; no production deployment or credentials are included.

## Repository map

- `ingestion/` — source-specific ingestion packages and guidance.
- `src/nh_property_intelligence/` — shared Python package.
- `dbt/nh_property_intelligence/` — dbt project and model layers.
- `orchestration/` — Prefect flows.
- `snowflake/setup/` — ordered warehouse setup scripts.
- `docs/` and `architecture/` — product and technical design documentation.
- `powerbi/` — report documentation and future artifacts.

## Getting started

Copy `.env.example` to `.env` and supply the non-secret local identifiers. Snowflake credentials and the optional Census API key can be injected from Bitwarden at runtime; see `snowflake/README.md`. Never commit `.env` or credentials.

## Local town comparison

Generate a concise Markdown comparison from an approved local `MART_TOWN_SCORECARD`
CSV export. This stdlib-only command does not connect to Snowflake or any other
service and needs no credentials or environment file. From the repository root:

```bash
PYTHONPATH=src python -m nh_property_intelligence.town_comparison \
  --csv /path/to/scorecard.csv --town Salem --town Windham
```

Repeat `--town` for 2–5 distinct municipalities, in the desired report order. Use
an exact canonical ten-digit NH `municipality_geoid` or a municipality name.
Names ignore case and collapse whitespace. Explicit Census `town`/`city` suffixes
are recognized, including names such as `Salem town, Rockingham County, New Hampshire`;
both `Salem town` and `Salem` can select that row. Other suffixes, punctuation,
abbreviations and partial/fuzzy matches are not inferred. Ambiguous names fail
with candidate GEOIDs; repeat the command using an exact GEOID. Selecting the same
municipality by both name and GEOID is an error.

Output defaults to stdout. Add `--output comparison.md` to create a **new** UTF-8
Markdown file with LF newlines; existing paths (including the input CSV) are
never overwritten. Choose a new filename for each saved report. Shell redirection
uses your shell's overwrite rules instead. Invalid input or file errors exit
nonzero and print a diagnostic to stderr.

The UTF-8 CSV must have a header and use the mart's actual column names
(uppercase Snowflake headers and a UTF-8 BOM are accepted). Required columns are:

- `municipality_geoid`, `municipality_name_raw`, `county_hpi_county_name_raw`
- `median_household_income`, `median_owner_occupied_home_value`
- `estimated_annual_property_tax_on_median_home`, `home_value_to_income_ratio`
- `estimated_property_tax_to_income_ratio`, `county_hpi_appreciation_5y`
- `acs_vintage`, `tax_year`, `county_hpi_year`

Other export columns are ignored. The entire CSV is checked for duplicate or
invalid identities, missing municipality names, malformed required numbers,
duplicate headers and inconsistent record lengths. GEOIDs must remain ten-digit
text beginning with NH state FIPS `33`. Indicator cells may be blank, `NULL`,
`N/A` or `\N` (case-insensitive); these display as `N/A`, never zero. A missing
FHFA county name also displays as `N/A`. Numbers must be raw finite machine
numbers, without currency signs, grouping commas or percent signs; magnitudes
above 10^15 are rejected. Source years must be four-digit integers when present.

The report uses the scorecard's existing indicators without recalculating them.
Currency is displayed in dollars to two decimals; home value/income as a multiple;
tax/income and five-year cumulative county HPI appreciation as percentages
(the mart stores these as fractions, so `0.25` displays as `25.00%`). Missing
indicators are not inferred from other cells. FHFA appreciation is **county
context, not town appreciation**. Estimated property tax is not a parcel bill.
Census ACS vintage, DRA tax year and FHFA county HPI year need not align and are
shown separately.

The tiny fixture at `tests/unit/fixtures/synthetic_town_scorecard.csv` contains
explicitly synthetic municipality identities and fictional numeric indicators;
it is not an NHPI export. To exercise the command locally:

```bash
PYTHONPATH=src python -m nh_property_intelligence.town_comparison \
  --csv tests/unit/fixtures/synthetic_town_scorecard.csv \
  --town 'Synthetic Alpha' --town 'Synthetic Beta'
```

Python callers can use
`generate_comparison(csv_path, towns)` from
`nh_property_intelligence.town_comparison`; it returns Markdown ending in a
single newline and raises `ComparisonError` for validation failures. File and
CSV decoding exceptions propagate to Python callers; the CLI handles these as
safe diagnostics.
