# Ingestion

Source-specific Python adapters will live under `census/`, `dra/`, and `fhfa/`. They will retrieve public data, validate source responses, attach provenance, and load raw Snowflake objects. Implementations should avoid embedding analytics transformations that belong in dbt.
