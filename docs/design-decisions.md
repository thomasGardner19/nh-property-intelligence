# Design decisions

## Initial decisions

1. **Keep ingestion and transformation separate.** Python retrieves source data; dbt owns warehouse transformations.
2. **Preserve raw source fidelity.** Raw records and provenance remain available so transformations are reproducible and auditable.
3. **Model source layers independently.** Census, DRA, and FHFA staging paths avoid prematurely combining unlike grains.
4. **Expose only curated marts to reporting.** Power BI should not recreate business logic already governed in dbt.
5. **Configure through environment variables.** Credentials remain outside version control; `.env.example` documents names only.

Future architecture decision records will capture material trade-offs as implementation proceeds.
