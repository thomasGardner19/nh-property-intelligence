USE ROLE NHPI_ENGINEER;
USE DATABASE NH_PROPERTY_INTELLIGENCE;
USE SCHEMA RAW;

CREATE TABLE IF NOT EXISTS FHFA_COUNTY_HPI (
    state_code VARCHAR(2) NOT NULL,
    county_name_raw VARCHAR NOT NULL,
    county_fips VARCHAR(5) NOT NULL,
    year NUMBER(4,0) NOT NULL,
    annual_change_pct NUMBER(18,6),
    hpi NUMBER(18,6),
    hpi_1990_base NUMBER(18,6),
    hpi_2000_base NUMBER(18,6),
    raw_payload VARIANT NOT NULL,
    source_system VARCHAR NOT NULL,
    source_dataset VARCHAR NOT NULL,
    source_file_name VARCHAR NOT NULL,
    source_url VARCHAR NOT NULL,
    source_requested_at TIMESTAMP_TZ NOT NULL,
    ingested_at TIMESTAMP_TZ NOT NULL,
    ingestion_run_id VARCHAR NOT NULL,
    row_hash BINARY(32) NOT NULL
);
