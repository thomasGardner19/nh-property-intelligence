USE ROLE NHPI_ENGINEER;
USE DATABASE NH_PROPERTY_INTELLIGENCE;
USE SCHEMA RAW;

CREATE TABLE IF NOT EXISTS DRA_MUNICIPAL_TAX_RATES (
    municipality_name_raw VARCHAR NOT NULL,
    tax_year NUMBER(4,0) NOT NULL,
    rate_date DATE NOT NULL,
    valuation NUMBER(38,0) NOT NULL,
    valuation_including_utilities NUMBER(38,0) NOT NULL,
    municipal_tax_rate NUMBER(18,6) NOT NULL,
    county_tax_rate NUMBER(18,6) NOT NULL,
    state_education_tax_rate NUMBER(18,6) NOT NULL,
    local_education_tax_rate NUMBER(18,6) NOT NULL,
    total_tax_rate NUMBER(18,6) NOT NULL,
    total_commitment NUMBER(38,0) NOT NULL,
    raw_payload VARIANT NOT NULL,
    source_system VARCHAR NOT NULL,
    source_file_name VARCHAR NOT NULL,
    source_url VARCHAR NOT NULL,
    source_requested_at TIMESTAMP_TZ NOT NULL,
    ingested_at TIMESTAMP_TZ NOT NULL,
    ingestion_run_id VARCHAR NOT NULL,
    row_hash BINARY(32) NOT NULL
);
