# Orchestration

Prefect deployments and flows will coordinate source ingestion, warehouse loading, and dbt runs. Flow code belongs in `flows/`; credentials and environment-specific deployment settings must remain outside version control.
