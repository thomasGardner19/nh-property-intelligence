# NH DRA Municipal Tax Rates ingestion

## Locked MVP source

- Publisher: New Hampshire Department of Revenue Administration
- Dataset: 2025 Municipal Tax Rates
- Grain: one published municipality per tax year
- Natural key in RAW: `(tax_year, municipality_name_raw)`

The DRA municipality name is preserved exactly as published. It is a source-record identifier only and must not become the canonical municipality key. Mapping to the Census county-subdivision GEOID is intentionally deferred to the downstream crosswalk work.

## Processing boundary

1. `client.py` retrieves the official PDF and verifies the response is PDF content.
2. `extract.py` extracts the published municipal tax table into source-string records.
3. `normalize.py` parses dates/numerics, preserves the original source values in `raw_payload`, validates the record contract, and computes a deterministic SHA-256 row hash.
4. `loader.py` stages a complete tax-year snapshot, validates it in Snowflake, and transactionally replaces only that tax year in `RAW.DRA_MUNICIPAL_TAX_RATES`.

## Locked source fields

- Municipality
- Date
- Valuation
- Valuation Including Utilities
- Municipal Tax Rate
- County Tax Rate
- State Education Tax Rate
- Local Education Tax Rate
- Total Tax Rate
- Total Commitment

Tax rates are retained as the DRA-published rate per $1,000 of assessed valuation. Estimated tax on an ACS median home value is a downstream analytical calculation and must be labeled as an estimate because it combines values from different source systems.

## Source fidelity and idempotency

`raw_payload` preserves the source-string values used for normalization. The row hash includes the tax year and the locked source fields but excludes ingestion timestamps, run IDs, file names, and URLs.

A load is idempotent at the tax-year snapshot level: stage and validate the complete snapshot, commit staging, then delete/insert the target tax year in one explicit transaction. A target failure rolls back to the previously committed tax-year snapshot.
