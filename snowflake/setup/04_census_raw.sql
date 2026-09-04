USE DATABASE NH_PROPERTY_INTELLIGENCE;
USE SCHEMA RAW;

CREATE TABLE IF NOT EXISTS CENSUS_ACS_MUNICIPALITY (
    geography_name_raw VARCHAR NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    county_fips VARCHAR(3) NOT NULL,
    county_subdivision_fips VARCHAR(5) NOT NULL,
    county_subdivision_geoid VARCHAR(10) NOT NULL,
    acs_vintage NUMBER(4,0) NOT NULL,
    dataset_id VARCHAR NOT NULL,
    source_endpoint VARCHAR NOT NULL,
    source_geography_type VARCHAR NOT NULL,
    total_population_estimate NUMBER(38,0),
    total_population_moe NUMBER(38,0),
    median_household_income_estimate NUMBER(38,0),
    median_household_income_moe NUMBER(38,0),
    median_owner_occupied_home_value_estimate NUMBER(38,0),
    median_owner_occupied_home_value_moe NUMBER(38,0),
    median_gross_rent_estimate NUMBER(38,0),
    median_gross_rent_moe NUMBER(38,0),
    total_housing_units_estimate NUMBER(38,0),
    total_housing_units_moe NUMBER(38,0),
    occupied_housing_units_estimate NUMBER(38,0),
    occupied_housing_units_moe NUMBER(38,0),
    owner_occupied_housing_units_estimate NUMBER(38,0),
    owner_occupied_housing_units_moe NUMBER(38,0),
    raw_payload VARIANT NOT NULL,
    source_system VARCHAR NOT NULL,
    source_requested_at TIMESTAMP_TZ NOT NULL,
    ingested_at TIMESTAMP_TZ NOT NULL,
    ingestion_run_id VARCHAR NOT NULL,
    row_hash BINARY(32) NOT NULL
);
