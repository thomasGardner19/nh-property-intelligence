# Planned architecture

```text
Census ACS API ─┐
NH DRA files ───┼─> Python ingestion ─> Snowflake raw schemas
FHFA files/API ─┘          │                    │
                           └─ Prefect           v
                                          dbt transformations
                                                │
                                                v
                                         Analytics marts ─> Power BI
```

Python adapters will isolate source-specific retrieval and validation. Prefect will orchestrate observable, retryable flows without containing transformation logic. Snowflake will retain raw source data and provide separate transformed schemas. dbt will own SQL transformation, testing, documentation, and lineage. Power BI will query curated marts rather than raw objects.

Docker will standardize local commands, and GitHub Actions will enforce Python quality checks and dbt parsing before changes merge.
