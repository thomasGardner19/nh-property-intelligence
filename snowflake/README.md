# Snowflake

The `setup/` scripts are ordered foundations for the project warehouse.

## Current setup sequence

1. `01_roles.sql` — role/grant design remains intentionally deferred; use an existing role with the required privileges for now.
2. `02_database.sql` — creates `NH_PROPERTY_INTELLIGENCE`.
3. `03_schemas.sql` — creates the `RAW` schema.
4. `04_census_raw.sql` — creates `RAW.CENSUS_ACS_MUNICIPALITY` using the contract in [`docs/data-model.md`](../docs/data-model.md).

Run the scripts with a Snowflake role that can create the database/schema/table objects. Credentials belong in environment variables or `.env` and must not be committed.

## Census raw landing behavior

The Census loader stages normalized rows in a temporary table compatible with `RAW.CENSUS_ACS_MUNICIPALITY`, validates row count, vintage, state, key nullability, and natural-key uniqueness, then transactionally replaces one ACS vintage.

The consumer grain remains one row per `(acs_vintage, county_subdivision_geoid)`. Snowflake standard tables do not enforce ordinary primary/unique constraints, so the loader validates this contract before commit and dbt will test it again downstream.

The permanent target keeps the hybrid raw representation: typed relational columns plus `raw_payload VARIANT` for source fidelity. The loader serializes the Python raw payload to JSON and binds it through `PARSE_JSON` rather than interpolating source values into SQL.

## Integration testing

Normal CI uses mocked loader tests and does not require Snowflake credentials. An opt-in integration test is available with:

```bash
RUN_SNOWFLAKE_INTEGRATION=1 pytest -m snowflake_integration -q
```

The integration test creates and targets a temporary Snowflake table, so it does not replace data in the permanent Census raw table. It expects the permanent table definition to exist because the temporary table is created with `LIKE RAW.CENSUS_ACS_MUNICIPALITY`.

Role hierarchy, least-privilege grants, warehouse sizing, clustering, streams, tasks, and retention policy remain future decisions. At New Hampshire municipality scale, clustering or a generic semi-structured landing framework would add complexity without measurable benefit at this stage.
