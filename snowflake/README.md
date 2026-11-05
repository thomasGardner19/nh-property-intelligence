# Snowflake

The `setup/` scripts provision the project warehouse foundation for real execution.

## Personal-account bootstrap

Run these scripts in Snowsight in order:

1. `01_roles.sql` as `ACCOUNTADMIN` — creates `NHPI_ENGINEER` and the auto-suspending `NHPI_XS` warehouse.
2. Grant the project role to your user once:
   ```sql
GRANT ROLE NHPI_ENGINEER TO USER "<YOUR_USER_NAME>";
   ```
3. `02_database.sql` as `ACCOUNTADMIN` — creates `NH_PROPERTY_INTELLIGENCE` and grants the project role database usage/schema-creation rights.
4. `03_schemas.sql` — switches to `NHPI_ENGINEER` and creates `RAW` and `ANALYTICS`.
5. `04_census_raw.sql` — creates `RAW.CENSUS_ACS_MUNICIPALITY`.
6. `05_dra_raw.sql` — creates `RAW.DRA_MUNICIPAL_TAX_RATES`.
7. `06_fhfa_raw.sql` — creates `RAW.FHFA_COUNTY_HPI`.
8. `07_verify_environment.sql` — verifies account context, schemas, tables, and current raw row counts.

The project role is deliberately small for a portfolio/personal account: it can use the dedicated X-Small warehouse and create project schemas/tables inside the project database, but normal pipeline execution does not require `ACCOUNTADMIN`.

## Environment configuration

Copy `.env.example` to `.env` locally and populate the non-secret account and login identifiers unless you intentionally rename project objects. For noninteractive local execution, use a role-restricted programmatic access token (PAT) injected from Bitwarden:

```text
SNOWFLAKE_ACCOUNT=<account identifier>
SNOWFLAKE_USER=<user name>
SNOWFLAKE_AUTHENTICATOR=snowflake
SNOWFLAKE_ROLE=NHPI_ENGINEER
SNOWFLAKE_WAREHOUSE=NHPI_XS
SNOWFLAKE_DATABASE=NH_PROPERTY_INTELLIGENCE
```

The Python connector and dbt accept the PAT through their password field with `SNOWFLAKE_AUTHENTICATOR=snowflake`. Accounts with federated SSO may use `SNOWFLAKE_AUTHENTICATOR=externalbrowser` and omit the secret. Do not commit `.env` or credentials.

## Bitwarden-backed credentials

Store the Snowflake PAT (or native password) in the password field of a Bitwarden login item named `NHPI Snowflake` (or set `BITWARDEN_SNOWFLAKE_ITEM` to another item name or ID). The optional Census key can similarly use an item named `NHPI Census API Key`. The owner installs and authenticates the Bitwarden Password Manager CLI locally: run `bw login` interactively once (or again after logout), then unlock it in the current shell. Never send the master password, PAT, or session value to an agent or paste them into chat/logs. Disable shell tracing before unlocking:

```bash
set +x
bw login  # owner only; skip if already logged in
export BW_SESSION="$(bw unlock --raw)"
```

Run Snowflake commands through the project wrapper. It captures the PAT or password from Bitwarden and exposes it as `SNOWFLAKE_PASSWORD` only to the child process:

```bash
nhpi-with-bitwarden -- dbt debug
```

Add `--with-census` before `--` for a command that also needs `CENSUS_API_KEY`. The wrapper never writes or echoes retrieved values. Run `bw lock` and `unset BW_SESSION` when the session is complete.

## Local operations: check / refresh / validate

From the clone root, create an environment and install this checkout using that
environment's Python. These are owner-run setup commands; installing dependencies
requires an approved package source (or a complete local wheelhouse):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
env -u PYTHONPATH .venv/bin/python -c 'import nh_property_intelligence; print(nh_property_intelligence.__file__)'
env -u PYTHONPATH .venv/bin/nhpi-with-bitwarden --help
env -u PYTHONPATH .venv/bin/python -m nh_property_intelligence.ops --help
```

The import should resolve to this clone's `src/nh_property_intelligence`. The
tracked Hatch wheel configuration already declares that source package. The
reported editable-install `ModuleNotFoundError` has **not been reproduced or
proven fixed**: the supervised offline clean-venv experiment stopped before
installation because the required `hatchling` build backend was unavailable.
Installed distribution metadata alone does not establish that an editable source
path still exists or belongs to the interpreter running the command. A stale
editable path or interpreter mismatch remains a hypothesis, not a diagnosis.
If the fresh install fails, retain its nonsecret installation diagnostics and
the import result for review; do not treat a `PYTHONPATH` runner as a packaging fix.

Keep `.env` limited to the nonsecret settings above; no `.env.secrets` is needed.
Role and warehouse must be configured explicitly in current `Settings` (the
documented project values are `NHPI_ENGINEER` and `NHPI_XS`); the database defaults
to `NH_PROPERTY_INTELLIGENCE`. Authenticate locally as described above, then use
the same venv for the wrapper and child Python:

```bash
.venv/bin/nhpi-with-bitwarden --snowflake-item '<SNOWFLAKE_ITEM_NAME_OR_ID>' -- \
  .venv/bin/python -m nh_property_intelligence.ops check

# Owner-approved writes: downloads publisher data, replaces RAW snapshots,
# then runs dbt build, which also writes analytics objects.
.venv/bin/nhpi-with-bitwarden --snowflake-item '<SNOWFLAKE_ITEM_NAME_OR_ID>' \
  --with-census --census-item '<CENSUS_ITEM_NAME_OR_ID>' -- \
  .venv/bin/python -m nh_property_intelligence.ops refresh --approve-raw-writes

.venv/bin/nhpi-with-bitwarden --snowflake-item '<SNOWFLAKE_ITEM_NAME_OR_ID>' -- \
  .venv/bin/python -m nh_property_intelligence.ops validate
```

Omit `--with-census --census-item ...` if no Census key is used. `check` issues
only SELECTs for current account/role/database/warehouse and aggregate counts of
the three known RAW tables. `validate` adds a role-visible metadata existence
check and count for `ANALYTICS.MART_TOWN_SCORECARD`. Both close cursors and
connections, perform no automatic repairs or writes, and return 1 on operational
failure with a generic diagnostic that omits raw exception messages. SELECTs may
still resume the configured warehouse and incur compute charges.

`check` returns 0 after successful reads, even for empty RAW tables. `validate`
returns 1 for any empty target or a missing/invisible mart. Metadata invisibility
cannot distinguish an absent object from insufficient role privileges. Counts
alone do not prove data quality, freshness, coverage or correct transformations;
the existing loader checks and dbt build/tests remain necessary.

`refresh` returns 2 without `--approve-raw-writes`, before loading configuration
or importing Prefect. With that flag it calls the existing sequential Prefect
flow, including its error/redaction policy and dbt build; it does not implement
ingestion itself or create a schedule. The flag only gates this operations CLI;
the existing direct orchestration entrypoint remains callable. A refresh can
partially complete source loads before a later task fails. No command exports
private rows or automatically runs town comparison.

For offline verification, with test dependencies already installed:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_ops.py -q
ruff check src/nh_property_intelligence/ops.py tests/unit/test_ops.py
```

The operations tests mock settings, connections and refresh, block socket
connections, and use dummy secrets. They do not contact Snowflake, Bitwarden or
publisher APIs. Live connection and refresh success require separate owner
verification after independent review; no live success is established here.

For dbt, copy `dbt/nh_property_intelligence/profiles.example.yml` to your dbt profiles directory (or pass it through `--profiles-dir`). It uses the same environment variables and writes models to `ANALYTICS`.

A useful connectivity check is:

```bash
dbt debug \
  --project-dir dbt/nh_property_intelligence \
  --profiles-dir dbt/nh_property_intelligence
```

If you use the repository's example profile directly, first copy it to `profiles.yml`; the committed file remains `profiles.example.yml` so credentials are never stored in Git.

## Raw landing behavior

The Census client uses the API when a key is supplied. If a keyless request is redirected to the Census missing-key page, it reconstructs the same locked response fields from the Census Bureau's official ACS table-based summary files and gazetteers. The loader then stages normalized rows in a temporary table compatible with `RAW.CENSUS_ACS_MUNICIPALITY`, validates row count, vintage, state, key nullability, and natural-key uniqueness, and transactionally replaces one ACS vintage.

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

The integration tests create and target temporary Snowflake tables, so they do not replace data in the permanent raw tables. The permanent table definitions must already exist because each temporary target derives its columns from the corresponding RAW table.

Clustering, streams, tasks, and advanced retention policy remain future decisions. At New Hampshire municipality scale, they would add complexity without measurable benefit at this stage.
