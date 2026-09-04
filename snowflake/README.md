# Snowflake

The `setup/` scripts provision the project warehouse foundation for real execution.

## Personal-account bootstrap

Run these scripts in Snowsight in order:

1. `01_roles.sql` as `ACCOUNTADMIN` — creates `NHPI_ENGINEER` and the auto-suspending `NHPI_XS` warehouse.
2. Grant the project role to your user once:
   ```sql
   GRANT ROLE NHPI_ENGINEER TO USER <YOUR_USER_NAME>;
   ```
3. `02_database.sql` as `ACCOUNTADMIN` — creates `NH_PROPERTY_INTELLIGENCE` and grants the project role database usage/schema-creation rights.
4. `03_schemas.sql` — switches to `NHPI_ENGINEER` and creates `RAW` and `ANALYTICS`.
5. `04_census_raw.sql` — creates `RAW.CENSUS_ACS_MUNICIPALITY`.
6. `05_dra_raw.sql` — creates `RAW.DRA_MUNICIPAL_TAX_RATES`.
7. `06_fhfa_raw.sql` — creates `RAW.FHFA_COUNTY_HPI`.
8. `07_verify_environment.sql` — verifies account context, schemas, tables, and current raw row counts.

The project role is deliberately small for a portfolio/personal account: it can use the dedicated X-Small warehouse and create project schemas/tables inside the project database, but normal pipeline execution does not require `ACCOUNTADMIN`.

## Environment configuration

Copy `.env.example` to `.env` locally and populate only the account/user/password values unless you intentionally rename project objects:

```text
SNOWFLAKE_ACCOUNT=<account identifier>
SNOWFLAKE_USER=<user name>
SNOWFLAKE_PASSWORD=<password>
SNOWFLAKE_ROLE=NHPI_ENGINEER
SNOWFLAKE_WAREHOUSE=NHPI_XS
SNOWFLAKE_DATABASE=NH_PROPERTY_INTELLIGENCE
```

Do not commit `.env` or credentials.

For dbt, copy `dbt/nh_property_intelligence/profiles.example.yml` to your dbt profiles directory (or pass it through `--profiles-dir`). It uses the same environment variables and writes models to `ANALYTICS`.

A useful connectivity check is:

```bash
dbt debug \
  --project-dir dbt/nh_property_intelligence \
  --profiles-dir dbt/nh_property_intelligence
```

If you use the repository's example profile directly, first copy it to `profiles.yml`; the committed file remains `profiles.example.yml` so credentials are never stored in Git.

## Raw landing behavior

The Census loader stages normalized rows in a temporary table compatible with `RAW.CENSUS_ACS_MUNICIPALITY`, validates row count, vintage, state, key nullability, and natural-key uniqueness, then transactionally replaces one ACS vintage.

The DRA loader follows the same snapshot pattern for `RAW.DRA_MUNICIPAL_TAX_RATES`, using `(tax_year, municipality_name_raw)` as the RAW source natural key until a downstream crosswalk maps the published DRA name to the canonical Census county-subdivision GEOID.

The FHFA loader snapshot-replaces the New Hampshire annual county HPI series in `RAW.FHFA_COUNTY_HPI`, keyed downstream by county FIPS and year.

Snowflake standard tables do not enforce ordinary primary/unique constraints, so loaders validate their source-level natural keys before commit and dbt tests them again downstream.

The permanent targets keep a hybrid raw representation: typed relational columns plus `raw_payload VARIANT` for source fidelity. Loaders serialize Python raw payloads to JSON and bind them through `PARSE_JSON` rather than interpolating source values into SQL.

## Live validation sequence

After raw data has been loaded, run dbt against the real warehouse:

```bash
dbt build \
  --project-dir dbt/nh_property_intelligence \
  --profiles-dir dbt/nh_property_intelligence
```

The live gate for this project is stronger than parse-only CI: setup scripts must execute in Snowflake, all three RAW tables must contain source data, `dbt build` must execute successfully, and `mart_town_scorecard` must materialize in `NH_PROPERTY_INTELLIGENCE.ANALYTICS`.

## Integration testing

Normal CI uses mocked loader tests and does not require Snowflake credentials. Opt-in integration tests are available with:

```bash
RUN_SNOWFLAKE_INTEGRATION=1 pytest -m snowflake_integration -q
```

The integration tests create and target temporary Snowflake tables, so they do not replace data in the permanent raw tables. The permanent table definitions must already exist because each temporary target is created with `LIKE`.

Clustering, streams, tasks, and advanced retention policy remain future decisions. At New Hampshire municipality scale, they would add complexity without measurable benefit at this stage.
