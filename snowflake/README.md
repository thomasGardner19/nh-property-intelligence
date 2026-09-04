# Snowflake

The `setup/` scripts are ordered foundations for the project warehouse.

## Current setup sequence

1. `01_roles.sql` — role/grant design remains intentionally deferred; use an existing role with the required privileges for now.
2. `02_database.sql` — creates `NH_PROPERTY_INTELLIGENCE`.
3. `03_schemas.sql` — creates the `RAW` schema.
4. `04_census_raw.sql` — creates `RAW.CENSUS_ACS_MUNICIPALITY` using the contract in [`docs/data-model.md`](../docs/data-model.md).
5. `05_dra_raw.sql` — creates `RAW.DRA_MUNICIPAL_TAX_RATES` for published NH DRA municipal tax-rate snapshots.

Run the scripts with a Snowflake role that can create the database/schema/table objects. Credentials belong in environment variables or `.env` and must not be committed.

## Raw landing behavior

The Census loader stages normalized rows in a temporary table compatible with `RAW.CENSUS_ACS_MUNICIPALITY`, validates row count, vintage, state, key nullability, and natural-key uniqueness, then transactionally replaces one ACS vintage.

The DRA loader follows the same snapshot pattern for `RAW.DRA_MUNICIPAL_TAX_RATES`, using `(tax_year, municipality_name_raw)` as the RAW source natural key until a downstream crosswalk maps the published DRA name to the canonical Census county-subdivision GEOID.

Snowflake standard tables do not enforce ordinary primary/unique constraints, so loaders validate their source-level natural keys before commit and dbt tests them again downstream.

Both permanent targets keep a hybrid raw representation: typed relational columns plus `raw_payload VARIANT` for source fidelity. Loaders serialize Python raw payloads to JSON and bind them through `PARSE_JSON` rather than interpolating source values into SQL.

## Integration testing

Normal CI uses mocked loader tests and does not require Snowflake credentials. Opt-in integration tests are available with:

```bash
RUN_SNOWFLAKE_INTEGRATION=1 pytest -m snowflake_integration -q
```

The integration tests create and target temporary Snowflake tables, so they do not replace data in the permanent raw tables. The permanent table definitions must already exist because each temporary target is created with `LIKE`.

Role hierarchy, least-privilege grants, warehouse sizing, clustering, streams, tasks, and retention policy remain future decisions. At New Hampshire municipality scale, clustering or a generic semi-structured landing framework would add complexity without measurable benefit at this stage.
