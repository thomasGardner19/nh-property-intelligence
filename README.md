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

Copy `.env.example` to `.env` and supply local values. Never commit `.env` or credentials. Implementation and detailed setup instructions will be added as each platform component is introduced.
