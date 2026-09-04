# Snowflake

The `setup/` scripts are ordered foundations for roles, database objects, and schemas. They are
placeholders until naming, ownership, grants, and environment strategy are finalized; review every
script before execution.

## Proposed Census raw object (design only)

No executable DDL is added in this change. The future `RAW.CENSUS_ACS_MUNICIPALITY` object must
implement the exact columns, nullability, semantics, and natural key documented in
[`docs/data-model.md`](../docs/data-model.md). Snowflake standard tables do not enforce ordinary
primary/unique constraints, so uniqueness of `(acs_vintage, county_subdivision_geoid)` must be
validated by the loader before its atomic vintage replacement and tested again by dbt.

The loader should use a temporary staging table compatible with the target schema, bulk-bind rows,
then execute the vintage delete and insert in a single explicit transaction. DDL, grants, warehouse
sizing, clustering, streams, tasks, and retention policies are intentionally outside this contract.
At New Hampshire municipality scale, clustering or a generic semi-structured landing framework would
add complexity without a measurable benefit.
