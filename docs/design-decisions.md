# Design decisions

## Initial decisions

1. **Keep ingestion and transformation separate.** Python retrieves source data; dbt owns warehouse transformations.
2. **Preserve raw source fidelity.** Raw records and provenance remain available so transformations are reproducible and auditable.
3. **Model source layers independently.** Census, DRA, and FHFA staging paths avoid prematurely combining unlike grains.
4. **Expose only curated marts to reporting.** Power BI should not recreate business logic already governed in dbt.
5. **Configure through environment variables.** Credentials remain outside version control; `.env.example` documents names only.

## DD-001: Census ACS municipal raw contract

**Status:** Accepted for v0.1 design; implementation and executable DDL are intentionally deferred.

### Raw-layer pattern

Three patterns were considered:

| Pattern | Benefits | Costs |
| --- | --- | --- |
| A. Typed relational columns only | Cheapest and clearest for dbt; easy constraints and profiling | Less direct evidence when coercion or an upstream representation changes; adding variables changes the table |
| B. `VARIANT` payload plus metadata | Maximum source flexibility and lowest response-shape coupling | Every dbt model must parse/cast JSON; weaker discoverability and tests; obscures the portfolio's data contract |
| C. Typed columns plus per-row `VARIANT` | Typed, testable dbt interface with exact raw values retained for audit/debug | Small storage duplication and two representations must be kept consistent |

**Decision:** use **C, the hybrid pattern**. ACS Detailed Table variables are explicitly locked and
stable enough to deserve typed columns, while a small per-row `raw_payload` makes sentinel conversion
and upstream drift diagnosable. Snowflake's compressed storage makes the duplication modest at New
Hampshire municipality scale. This is clearer in a portfolio and less complex than a generic schema
registry or payload-only parsing, while preserving a migration path if variables are added later.

Schema drift is handled deliberately: absence or duplication of contracted fields fails the batch;
new response fields do not fail it and are preserved in `raw_payload`, but are not promoted to typed
columns without a reviewed contract change. This favors reliable dbt usage over pretending the API
is schemaless.

### Idempotency and history

Append-only would create duplicate business records after every rerun. `MERGE` would be efficient,
but can leave stale municipalities when the upstream vintage snapshot removes a row. Keeping every
run in the same table would support audits, but forces downstream consumers to select a winning run
and adds orchestration complexity before run-history requirements exist.

**Decision:** v0.1 uses **transactional delete-and-reload of the requested vintage**. Load and
validate all rows in a temporary/staging table; in one Snowflake transaction delete that
`acs_vintage`, insert its complete replacement, and commit. Roll back on any failure. The result is
repeatable, removes stale rows, and provides an unambiguous natural-key constraint. `row_hash` exposes
content changes, while `ingestion_run_id` identifies the winning load. A future operational run table
or immutable landing archive can record every attempt without changing consumer grain.

### Type and transformation boundary

Ingestion performs lossless mechanical work needed to satisfy the raw contract: keep FIPS as fixed
width strings, validate integer syntax, map only documented Census numeric sentinel codes to null,
derive the canonical GEOID, retain literal values in `raw_payload`, and generate provenance. It must
not impute values, parse display names into business dimensions, calculate ratios, interpret MOEs, or
join other sources. Snowflake receives already bound typed values rather than relying on permissive
SQL casts. dbt staging owns presentation normalization and analytical semantics, and downstream
models own derived metrics.

### Metadata decisions

- Keep both request and ingestion timestamps: they distinguish source-contact time from batch
  preparation/load time and make latency and log correlation explainable.
- Keep a run UUID and deterministic row hash: together they answer “which load wrote this?” and “did
  source content change?” without using unstable metadata in change detection.
- Store a redacted reproducible endpoint and an explicit source-system constant; never persist or log
  the Census API key.
- Do not add a repeated response-payload hash or row status. Batch hashes belong in a future run table;
  status belongs in logs/quarantine, not the successful-record relation.

Future architecture decision records will capture material trade-offs as implementation proceeds.
