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

## DRA unattended retrieval and the 403 investigation

The current source is the PDF linked by the official
[Municipal and Village District Tax Rates page](https://www.revenue.nh.gov/about-dra/municipal-and-property-division/municipal-and-property-reports/municipal-and-village):

`https://www.revenue.nh.gov/sites/g/files/ehbemt736/files/documents/2025-municipal-tax-rates.pdf`

On 2026-09-08, ordinary HTTPX requests to both the report page and PDF succeeded
with the existing transparent `nh-property-intelligence/0.1` User-Agent. The PDF
returned HTTP 200, `application/pdf`, 270,660 bytes, no redirects, and no cookies.
Three separate fresh HTTPX sessions returned the same SHA-256:
`db6459b6a1168cddc99759c2bdb4ba0c218b104d6d9f509f20d6977dd8a45338`.
The production extractor and normalizer accepted 260 records for tax year 2025.
This hash is an observation, not a pinned artifact or cache requirement.

A controlled HTTPX request with its default User-Agent instead returned HTTP 403
and an Akamai/EdgeSuite Access Denied response. curl also received 403, including
with the application's User-Agent. Consequently the evidence identifies
request-dependent edge filtering; it does not reveal DRA's private edge-policy
rules or establish that User-Agent is the only factor. The original curl-based
check did not reproduce a failure in `fetch_report` itself. No source URL change
was necessary. The official page also lists a combined municipal/village XLSX;
there is no reason to add a second parser while the contracted PDF works.

The client preserves its honest application identity and explicitly sends PDF
Accept, English Accept-Language, and the official report-page Referer. It follows
ordinary redirects even with a default HTTPX client. Fresh sessions need no login,
cookies, JavaScript, or browser. No TLS impersonation, CAPTCHA handling, browser
fallback, cache, or rehosted copy is used. RAW `source_url` and `source_file_name`
continue to identify the original official PDF; existing extraction and normalization
validate the source contract. A changed schema, HTML challenge, or permanent HTTP
403 fails loudly rather than silently substituting data. 403 is not retried.

This strategy uses a normal Python HTTP client suitable for unattended execution.
The eventual VPS must still run the same acceptance check from its own network:
local success cannot guarantee that a publisher's edge policy accepts every
future hosting IP. If it denies access, obtain a publisher-supported access route;
do not conceal the client or route around the denial.

Unit tests cover the exact request identity/headers, redirects, permanent 403,
HTML instead of PDF, transient server retry, and source-schema rejection.

## PR #13 live acceptance status

The DRA source-only check succeeded, but is not a warehouse refresh. A complete
Bitwarden-backed live run requires the local vault to be unlocked. Until the
three RAW snapshots have fresh ingestion timestamps, `dbt build` succeeds, and
`MART_TOWN_SCORECARD` is confirmed rebuilt, the live acceptance gate remains open.
