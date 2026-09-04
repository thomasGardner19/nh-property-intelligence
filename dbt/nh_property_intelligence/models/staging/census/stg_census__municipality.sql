with source as (

    select *
    from {{ source('census', 'census_acs_municipality') }}

),

renamed as (

    select
        acs_vintage,
        county_subdivision_geoid,
        state_fips,
        county_fips,
        county_subdivision_fips,
        geography_name_raw,
        dataset_id,
        source_geography_type,
        total_population_estimate as total_population,
        total_population_moe,
        median_household_income_estimate as median_household_income,
        median_household_income_moe,
        median_owner_occupied_home_value_estimate as median_owner_occupied_home_value,
        median_owner_occupied_home_value_moe,
        median_gross_rent_estimate as median_gross_rent,
        median_gross_rent_moe,
        total_housing_units_estimate as total_housing_units,
        total_housing_units_moe,
        occupied_housing_units_estimate as occupied_housing_units,
        occupied_housing_units_moe,
        owner_occupied_housing_units_estimate as owner_occupied_housing_units,
        owner_occupied_housing_units_moe,
        raw_payload,
        source_system,
        source_endpoint,
        source_requested_at,
        ingested_at,
        ingestion_run_id,
        row_hash
    from source

)

select * from renamed
