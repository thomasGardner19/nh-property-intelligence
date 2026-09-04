# Census ACS ingestion contract

This document defines the interface for a future implementation. It contains no working API call or
loader. The first adapter targets the 2024 ACS 5-Year Detailed Tables endpoint and New Hampshire
county subdivisions only.

## Configuration and request

Configuration supplies the Census base URL, optional API key (from environment/secret injection),
ACS vintage (default/allowed v0.1 value `2024`), Snowflake connection settings, and bounded timeout
and retry settings. Secrets must never be arguments included in errors, metadata, or logs. Dataset,
variable list, geography predicate, state FIPS, and destination table are code-level contract
constants for v0.1 rather than freely configurable strings.

The request builder constructs `/data/{vintage}/acs/acs5`, requests `NAME` plus the 14 locked
variables, and supplies `for=county subdivision:*` with both `in=state:33` and
`in=county:*`, so the request covers every NH county rather than relying on an implicit API default.
`source_endpoint` is a canonical, reproducible URL with non-secret query parameters and with `key`
removed. The HTTP boundary accepts an injected `httpx.Client`-like client so unit tests need no
network. It sets explicit connect/read/write/pool timeouts and a Census-identifying user agent.

Retry only transient connection/time-out failures, HTTP `429`, and `5xx`, using capped exponential
backoff with jitter and honoring `Retry-After`. Use a small fixed attempt limit (three is the proposed
default). Do not retry other `4xx`, malformed successful responses, validation failures, or
Snowflake SQL failures inside the HTTP retry loop.

## Proposed module boundaries

Keep the first adapter functional and explicit; no framework or source-base-class is justified yet.

| Future module | Public responsibility | Conceptual interface |
| --- | --- | --- |
| `contract.py` | Immutable dataset/geography/variable-to-column contract, sentinel set, and row model/type definitions | constants plus `RawMunicipalityRow` |
| `client.py` | Build a redacted request description; execute one request through an injected HTTP client with retry policy | `build_request(vintage, api_key) -> RequestSpec`; `fetch_response(spec, client) -> ResponseEnvelope` |
| `normalize.py` | Validate the complete header/row envelope; map by header name; coerce types; derive GEOID; attach metadata and hashes | `normalize_response(envelope, run_context) -> list[RawMunicipalityRow]` |
| `loader.py` | Create/use a temporary load target, bulk-bind typed rows, validate the staged batch, and atomically replace one vintage | `replace_vintage(rows, vintage, connection) -> LoadResult` |
| `service.py` | Generate one run context and orchestrate fetch → normalize → load with structured logs and exit status | `ingest_vintage(config, client, connection) -> LoadResult` |

Helpers such as `derive_geoid`, `coerce_acs_integer`, and `canonical_row_hash` should be private or
small pure functions in `normalize.py` and directly unit tested. Validation and normalization are one
boundary because the Census API returns a header row followed by positional string arrays; splitting
them into stateful classes would add ceremony without isolating another external system. The loader
does not know HTTP or Census parsing, and the client does not know Snowflake.

`RunContext` conceptually contains a UUID `ingestion_run_id`, one UTC `source_requested_at` captured
immediately before the attempt that succeeds, one UTC `ingested_at` captured before load, the
vintage/dataset/source identity, and the redacted endpoint. All timestamps must be timezone-aware.

## Response, coercion, and hashing contract

The normalizer first requires a JSON top-level array with a string header row and at least one data
row. It maps positions using the returned headers rather than assuming order. Every contracted header
must occur exactly once and every data row must match the header width. Additive unknown headers are
allowed and retained only in each `raw_payload`.

FIPS components accept digits of exactly 2/3/5 characters; never parse, pad, or cast them as numbers.
The state must be exactly `33`. `county_subdivision_geoid` is direct string concatenation and must
match `^[0-9]{10}$`. The batch must have no duplicate `(vintage, GEOID)`.

Sentinel coercion is field-aware and occurs before ordinary numeric parsing:

- In an MOE field, Census `-555555555` or its display-form equivalent `*****` means the corresponding
  estimate is controlled and has effectively no sampling error. Convert that typed MOE to Python `0`,
  not `None`, while retaining the original literal in `raw_payload`.
- Outside an MOE field, do not treat `-555555555` as an ordinary negative measure. Reject it as
  unexpected contract drift unless a reviewed, source-documented rule is added for that field.
- The other explicit v0.1 special values—`-222222222`, `-333333333`, `-666666666`, `-888888888`, and
  `-999999999`—represent source-documented open-ended intervals, insufficient sample cases,
  unavailable/uncomparable estimates, or not-applicable values. Convert them to `None` while retaining
  the original literal in `raw_payload`.
- Treat an empty or JSON-null measure as `None`. Any additional symbolic or numeric sentinel requires
  a reviewed contract update supported by the locked-vintage Census documentation; do not infer its
  meaning from being negative.

After those rules, accept only an optional leading minus followed by ASCII digits and convert with
Python `int`. A numeric value outside Snowflake `NUMBER(38,0)` or any unknown non-numeric literal is
invalid. The implementation must fixture-test the sentinel set and its field-specific outcomes
against the locked vintage metadata before release. No value is imputed, and only the controlled-MOE
rule maps a source special value to zero.

The row SHA-256 input is the canonical compact, sorted-key JSON object defined in the data-model
contract. Hash source strings before typed sentinel replacement so a change between distinct source
sentinels is detectable. Encode as UTF-8 and load the 32 digest bytes into `BINARY(32)`.

## Failure behavior

The MVP treats the Census result as one snapshot: it never commits a partial vintage.

| Condition | Behavior |
| --- | --- |
| Timeout/connection error, `429`, or `5xx` | Warn with attempt metadata, retry within policy; fail run after exhaustion |
| Non-retryable HTTP `4xx` | Fail run immediately; redact credentials and truncate any response excerpt |
| Malformed JSON/envelope, empty data set, mismatched row width | Fail run before Snowflake work |
| Missing or duplicate expected column | Fail run: contracted schema drift |
| Unexpected new column | Log at info/warning, preserve in `raw_payload`, continue |
| Duplicate natural key | Fail whole run; do not select an arbitrary winner |
| Invalid FIPS/GEOID or wrong state | Reject the record in structured diagnostics and fail whole run |
| Unknown non-numeric measure or numeric overflow | Reject the record in structured diagnostics and fail whole run |
| Controlled-estimate MOE (`-555555555` or `*****`) | Preserve literal payload, set typed MOE to `0`, count/log summary, continue |
| Other contracted sentinel, empty value, or JSON null | Preserve literal payload, set typed measure to null, count/log summary, continue |
| Cross-measure inequality | Load; let dbt business-quality test warn rather than rewriting source data |
| Failure while staging/loading or validating staged row count/keys | Roll back; fail run; leave prior vintage intact |
| Failure during delete/insert/commit | Roll back transaction, fail run, and leave prior committed vintage intact |

“Reject” above means include GEOID/row index, field, and non-secret reason in structured error output;
v0.1 does not need a persistent quarantine table. Because a single bad source row makes the snapshot
incomplete, any rejected record fails the batch. Logs must contain run ID, vintage, endpoint without
key, attempt, HTTP status, received/normalized/sentinel-null/controlled-MOE counts, staged/inserted
counts, duration, and final outcome. Logs must not contain credentials or full response payloads.

## Atomic idempotent load contract

The loader stages all rows first and validates expected vintage, row count, non-null keys, uniqueness,
and state. Only then does one transaction delete `acs_vintage = :vintage` from the target and insert
the staged snapshot. It verifies inserted count equals normalized count before committing. Temporary
resources are cleaned up best-effort after commit/rollback. Repeating identical source data changes
only load metadata; it never increases target row count. The loader must bind parameters/bulk rows,
not interpolate values into SQL.

Append-only is rejected because it breaks the consumer grain. `MERGE` is deferred because it cannot
remove stale records without extra reconciliation. A run-history table is a sensible future addition
for audit history, but is independent of this current-state raw relation.
