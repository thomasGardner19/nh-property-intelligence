# Planned data model

The dbt project will use three layers:

- **Staging:** one-to-one, source-aligned models that rename fields, cast types, and expose provenance.
- **Intermediate:** reusable logic for geography mapping, temporal alignment, and metric normalization.
- **Marts:** business-facing facts and dimensions for affordability, taxation, valuations, and price trends.

Shared geography and date dimensions are expected to connect source facts. Model grain, keys,
accepted values, freshness expectations, and source caveats will be documented alongside each
implemented model.

## `RAW.CENSUS_ACS_MUNICIPALITY` contract (proposed)

This is a design contract, not an instruction to create a production object. The table is dedicated
to the selected ACS 5-Year Detailed Tables municipality extract. `NOT NULL` below means a rejected
row must not reach the committed vintage; it does not mean the source is guaranteed to be complete.

### Grain and identities

The source grain is **one Census county subdivision in New Hampshire per ACS 5-year vintage**.
The business/natural key and warehouse uniqueness expectation are
`(acs_vintage, county_subdivision_geoid)`. The GEOID is exactly the concatenation of the two-digit
state, three-digit county, and five-digit county-subdivision FIPS strings. For example, its contract
is ten digits, not a number.

Three identities must not be conflated:

- **Source record identity:** `(acs_vintage, county_subdivision_geoid)` for this dedicated ACS
  product table. `dataset_id` is constant but retained for traceability rather than added to the key.
- **Load identity:** `ingestion_run_id`, shared by every row attempted in one invocation. It is not
  part of the business key.
- **Warehouse identity:** exactly one committed row for each natural key. Successful reruns replace
  the complete vintage, so raw history is not represented by duplicate rows. Operational run history
  can be introduced later in a separate run table rather than weakening this table's grain.

### Column contract

Classification is one of **source data**, **derived metadata**, or **ingestion metadata**.

| Column | Snowflake type | Null? | Source field | Meaning | Classification |
| --- | --- | --- | --- | --- | --- |
| `geography_name_raw` | `VARCHAR` | No | `NAME` | Unmodified Census geography label | Source data |
| `state_fips` | `VARCHAR(2)` | No | `state` | Zero-padded state FIPS; must equal `33` | Source data |
| `county_fips` | `VARCHAR(3)` | No | `county` | Zero-padded county FIPS | Source data |
| `county_subdivision_fips` | `VARCHAR(5)` | No | `county subdivision` | Zero-padded county-subdivision FIPS | Source data |
| `county_subdivision_geoid` | `VARCHAR(10)` | No | Derived from `state` + `county` + `county subdivision` | Canonical municipal identifier | Derived metadata |
| `acs_vintage` | `NUMBER(4,0)` | No | Request dataset year (`2024`) | ACS data vintage, not load year | Derived metadata |
| `dataset_id` | `VARCHAR` | No | Request dataset path | Stable product identifier: `acs/acs5` | Derived metadata |
| `source_endpoint` | `VARCHAR` | No | Request URL without API key | Census endpoint and non-secret query parameters needed to reproduce the request | Derived metadata |
| `source_geography_type` | `VARCHAR` | No | Request `for` geography | Constant `county subdivision` | Derived metadata |
| `total_population_estimate` | `NUMBER(38,0)` | Yes | `B01003_001E` | Total population estimate | Source data |
| `total_population_moe` | `NUMBER(38,0)` | Yes | `B01003_001M` | Total population margin of error | Source data |
| `median_household_income_estimate` | `NUMBER(38,0)` | Yes | `B19013_001E` | Median household income, dollars | Source data |
| `median_household_income_moe` | `NUMBER(38,0)` | Yes | `B19013_001M` | Income margin of error, dollars | Source data |
| `median_owner_occupied_home_value_estimate` | `NUMBER(38,0)` | Yes | `B25077_001E` | Median owner-occupied home value, dollars | Source data |
| `median_owner_occupied_home_value_moe` | `NUMBER(38,0)` | Yes | `B25077_001M` | Home-value margin of error, dollars | Source data |
| `median_gross_rent_estimate` | `NUMBER(38,0)` | Yes | `B25064_001E` | Median gross rent, dollars | Source data |
| `median_gross_rent_moe` | `NUMBER(38,0)` | Yes | `B25064_001M` | Gross-rent margin of error, dollars | Source data |
| `total_housing_units_estimate` | `NUMBER(38,0)` | Yes | `B25001_001E` | Total housing units estimate | Source data |
| `total_housing_units_moe` | `NUMBER(38,0)` | Yes | `B25001_001M` | Total housing units margin of error | Source data |
| `occupied_housing_units_estimate` | `NUMBER(38,0)` | Yes | `B25003_001E` | Occupied housing units estimate | Source data |
| `occupied_housing_units_moe` | `NUMBER(38,0)` | Yes | `B25003_001M` | Occupied housing units margin of error | Source data |
| `owner_occupied_housing_units_estimate` | `NUMBER(38,0)` | Yes | `B25003_002E` | Owner-occupied housing units estimate | Source data |
| `owner_occupied_housing_units_moe` | `NUMBER(38,0)` | Yes | `B25003_002M` | Owner-occupied housing units margin of error | Source data |
| `raw_payload` | `VARIANT` | No | One response row mapped from header to values | Lossless per-row source object, including raw codes and geography fields | Source data |
| `source_system` | `VARCHAR` | No | Loader constant | Constant `US_CENSUS_BUREAU` | Ingestion metadata |
| `source_requested_at` | `TIMESTAMP_TZ` | No | Client clock | UTC instant immediately before the HTTP request | Ingestion metadata |
| `ingested_at` | `TIMESTAMP_TZ` | No | Client clock | UTC instant the normalized batch was prepared for loading | Ingestion metadata |
| `ingestion_run_id` | `VARCHAR` | No | Loader-generated UUID | Correlates rows, logs, and one load attempt | Ingestion metadata |
| `row_hash` | `BINARY(32)` | No | SHA-256 over canonical source content | Detects content changes independent of run timestamps | Ingestion metadata |

All 14 measures are nullable because the API may publish missing/suppressed values. Counts, dollar
medians, and their MOEs are integral for these Detailed Table variables, so `NUMBER(38,0)`/Python
`int | None` is more honest than floating point. Geography codes remain strings at every layer to
protect leading zeros. `acs_vintage` is numeric because it is a year, not an identifier.

The row hash is SHA-256 over a deterministic UTF-8 JSON serialization (sorted keys, compact
separators) of the raw `NAME`, geography fields, and all 14 requested variable/value pairs, plus
`acs_vintage` and `dataset_id`; it excludes URLs and all run timestamps/IDs. `raw_payload` preserves
the exact API strings before sentinel conversion, while typed measure columns contain valid integers
or SQL `NULL`. For MOE fields specifically, Census `-555555555` or `*****` denotes a controlled
estimate with effectively no sampling error, so the typed MOE is `0`; other explicitly contracted
missing/special values become SQL `NULL`. A request-level payload hash is deliberately omitted: it
would be repeated on every row, and API row ordering can create false changes. Add it once to a future
run-audit table if batch
artifact verification becomes necessary. A `record_load_status` is also omitted because only valid,
successfully committed rows belong in this table; rejected records belong in structured logs or a
future quarantine table.

### Expected staging handoff

`stg_census__municipality` should receive a unique, typed, traceable source record with original
payload available for investigation. Ingestion owns transport validation, exact field mapping,
field-aware sentinel coercion, GEOID construction, and load metadata—not analytics.

Staging should keep the descriptive warehouse names (or apply project-wide naming conventions),
standardize the source geography label into display-ready municipality/county names, expose useful
provenance fields, and apply any analytical null labels or semantic conventions. Ratios such as
homeownership or occupancy, affordability calculations, MOE interpretation, and cross-source joins
belong in downstream intermediate/mart models. Staging must not silently turn missing measures into
zero, and it should not discard the raw geography name or variable-code traceability.

### Future test contract

**Ingestion contract tests (Python)**

- Request generation produces the locked endpoint, all and only the locked requested variables,
  `for=county subdivision:*`, `in=state:33`, `in=county:*`, and no API key in
  logged/source URLs.
- Header order may vary, but missing/duplicate expected headers fail; additive unexpected headers are
  tolerated and remain in `raw_payload`.
- Response envelope, row widths, duplicate natural keys, fixed FIPS widths/digits, state `33`, and
  ten-digit derived GEOIDs are validated.
- Each ordinary measure accepts a base-10 integer string. In MOE fields, `-555555555` and `*****`
  become typed `0`; the other explicitly contracted Census special values become `None`. Every source
  literal remains in `raw_payload`, and unknown non-numeric values reject the row and fail the batch.
- Hashing is deterministic and metadata-independent. Unit tests cover request redaction, coercion,
  field-aware sentinel mapping (including controlled-MOE zero versus missing-value null), GEOID
  derivation, validation, and hash stability.
- An HTTP-client integration test uses a recorded/static fixture or mock server; a Snowflake
  integration test loads a temporary table twice and proves atomic replacement/idempotency. A
  separately marked live Census smoke test may detect upstream contract drift but must not be
  required for deterministic CI.

**dbt source/staging and business/data-quality tests**

- Source tests: not-null natural-key components and required metadata; unique combination of vintage
  and GEOID; GEOID regex `^[0-9]{10}$`; state FIPS accepted value `33`; and accepted constants for
  dataset, geography type, and source system.
- Staging contract tests: expected columns/types, preserved row count and natural-key uniqueness, and
  numeric measures either null or non-negative after sentinel handling.
- Business tests: `owner_occupied_housing_units_estimate <= occupied_housing_units_estimate` and
  `occupied_housing_units_estimate <= total_housing_units_estimate`, evaluating only non-null pairs.
  These are initially warnings because independent ACS estimates and sampling can produce edge-case
  inconsistencies; promote to errors only after profiling. Plausibility and cross-measure rules are
  analytics quality tests, not transport-contract failures.
