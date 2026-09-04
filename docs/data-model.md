# Planned data model

The dbt project will use three layers:

- **Staging:** one-to-one, source-aligned models that rename fields, cast types, and expose provenance.
- **Intermediate:** reusable logic for geography mapping, temporal alignment, and metric normalization.
- **Marts:** business-facing facts and dimensions for affordability, taxation, valuations, and price trends.

Shared geography and date dimensions are expected to connect source facts. Model grain, keys, accepted values, freshness expectations, and source caveats will be documented alongside each implemented model.
