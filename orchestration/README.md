# Local Prefect refresh

The `refresh_property_intelligence` flow coordinates the existing production ingestion
modules and the real dbt project. Prefect supplies task states, operational logs,
selective retries, and failure propagation without requiring a deployed server or Cloud account.

```text
refresh_property_intelligence
  ingest_census (ACS 2024 → RAW.CENSUS_ACS_MUNICIPALITY)
    → ingest_dra (tax year 2025 → RAW.DRA_MUNICIPAL_TAX_RATES)
    → ingest_fhfa (complete NH annual series → RAW.FHFA_COUNTY_HPI)
    → dbt_build (dbt build → ANALYTICS, including mart_town_scorecard)
    → success summary
```

Implementation: `src/nh_property_intelligence/orchestration/refresh.py`.
Each source task calls the existing client, extractor where applicable, normalizer,
and snapshot loader. Source contracts remain locked to PR #12's vintages. FHFA
extracts the national workbook and normalizes only NH rows. Source data stays in
memory until the existing loader writes RAW; it is not saved as a local artifact.

The task owns its HTTP client and Snowflake connection and closes both on success
or failure. Existing loaders own cursor cleanup and transactional replacement.
The FHFA extractor now also closes its workbook on success and failure.

The master uses blocking task calls in source order. This is sufficient at the
current data scale and makes the dependency gate explicit: dbt cannot start until
all three required loads commit. Ingestion handles source fidelity and validation;
dbt handles relationships, transformations, and analytical tests. Neither duplicates
the other's responsibility. Tasks return only row-count summaries, never settings,
credentials, connections, or source records. Task caching and result persistence
are explicitly disabled so every invocation refreshes the sources.

## Run locally

From the repository root with Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
# Edit .env with non-secret account/user identifiers and the project role/warehouse.
export BW_SESSION="$(bw unlock --raw)"
nhpi-with-bitwarden -- python -m nh_property_intelligence.orchestration.refresh
```

The Snowflake role, warehouse, schemas, and RAW tables must already exist; follow
[`snowflake/README.md`](../snowflake/README.md) for PR #12's bootstrap. The required
settings are `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_ROLE`, and
`SNOWFLAKE_WAREHOUSE`. Use `SNOWFLAKE_DATABASE=NH_PROPERTY_INTELLIGENCE` and
`SNOWFLAKE_AUTHENTICATOR=snowflake` with the role-restricted PAT/password stored
in Bitwarden's `NHPI Snowflake` login-item password field. Bitwarden CLI must be
installed, signed in, and unlocked in the invoking shell. Custom item names can
be passed with the existing wrapper's `--snowflake-item` and `--census-item` options
or its `BITWARDEN_*_ITEM` environment variables.

Add `--with-census` before `--` to inject the optional `NHPI Census API Key` item.
Without it, the existing Census client's official summary-file fallback remains
available. The wrapper injects secrets only into the child environment. Run
`bw lock` afterward. Do not save the session token or credentials in the repository.
For an already configured runtime environment, the direct invocation is:

```bash
python -m nh_property_intelligence.orchestration.refresh
```

The dbt task resolves the same `Settings` used by ingestion (including local `.env`)
and passes those values to the dbt child. It copies the committed environment-only
`profiles.example.yml` into a temporary directory; no separate `profiles.yml` setup
is needed. Run from an editable repository checkout so the real dbt project is
present beside `src`. The dbt executable comes from the active Python environment.

Prefect starts its temporary local API automatically when `PREFECT_API_URL` is
unset. Its normal local metadata directory must be writable. `PREFECT_HOME` and
`PREFECT_LOCAL_STORAGE_PATH` can point to a writable directory outside the repo;
`PREFECT_SERVER_ANALYTICS_ENABLED=false` disables Prefect telemetry. No deployed
Prefect Server or Cloud infrastructure is introduced by this PR.

## Observability and failure behavior

Logs report source name, vintage/year or complete-series scope, extracted and
normalized row counts, loaded rows, and completion. Failures identify the source,
phase, exception class, and HTTP status when applicable. Low-level HTTP/connector
logging is suppressed during each sequential task because request URLs can contain
Census keys and connector debug logs can expose bound values. Caller logging is
restored afterward. Raw exception chains are discarded before Prefect receives
failures, since Prefect may serialize failed exceptions even with result persistence
disabled.

Only HTTP timeout/network errors, HTTP 429, and HTTP 5xx qualify for Prefect retries:
two retries after 5 and 20 seconds. Client-level retries are set to one attempt to
avoid multiplying retry policies. Schema/record validation, duplicate keys, HTTP
4xx other than 429, configuration/authentication, and Snowflake errors stop the
flow without automatic retries. Snowflake errors are deliberately conservative:
there is no broad retry of failures whose commit status may be uncertain.

The dbt task runs `dbt build` once. It captures the process return code and logs
the last 16,000 characters each of stdout/stderr after redacting runtime secrets
and their URL-encoded forms. File logging and JSON artifact writes are disabled;
temporary dbt files are removed. Nonzero exit codes and process-launch failures
fail the master flow. dbt test failures are never automatically retried.

Successful earlier source loads remain committed if a later task fails. There is
no cross-source transaction and dbt builds are not atomic across all models. Fix
the reported issue and rerun the complete flow; existing snapshot replacement
makes this repeatable. Run only one refresh at a time against this warehouse;
overlap coordination is deferred with deployment. A success summary is emitted
only after dbt succeeds.

## Validation

```bash
ruff check .
pytest -q
# Use the placeholder profile defined in .github/workflows/dbt-ci.yml:
dbt parse --project-dir dbt/nh_property_intelligence --profiles-dir /path/to/ci-profile --no-partial-parse
```

Unit tests use a temporary Prefect test API and mock all external source/Snowflake
I/O and the dbt subprocess. They cover source success, each source's failure gate,
resource cleanup, selective retries, secret-safe errors/output, dbt failure, and
source-before-dbt ordering across repeated refreshes. Existing loader tests cover
transaction and cursor behavior; existing live integration tests remain opt-in.

For a live acceptance run, check task loaded counts, dbt's successful build summary,
and query the three RAW table counts plus
`NH_PROPERTY_INTELLIGENCE.ANALYTICS.MART_TOWN_SCORECARD`. Confirm ingestion timestamps
and the mart's rebuild, not just pre-existing row counts. A parse-only check does
not establish a successful warehouse refresh.

## Deferred to PR #14

Scheduling and production deployment are intentionally deferred to PR #14. This
same module can later be invoked unattended on the VPS after runtime-secret access,
process supervision, and overlap policy are configured. This PR adds no VPS or
Hostinger changes, Docker changes, cron, Prefect deployment infrastructure, GitHub
deployment workflows, notifications, or analytical features.

## PR #13 local validation record (2026-09-08)

Ruff and the Python test suite passed; dbt parse passed with CI placeholder
credentials. The live Bitwarden-backed invocation exited before starting the flow
because this shell had no unlocked `BW_SESSION`. No RAW refresh or mart rebuild
is claimed for this validation. A direct DRA PDF request also returned HTTP 403
from this environment; the exact PDF link was confirmed on the official DRA
report page in a browser. Do not substitute cached data or a different source to
turn that into a successful live run. Repeat the live acceptance gate from an
unlocked runtime with working source access.
