with census as (

    select *
    from {{ ref('stg_census__municipality') }}

),

metrics as (

    select
        acs_vintage,
        county_subdivision_geoid,
        state_fips,
        county_fips,
        county_subdivision_fips,
        geography_name_raw,
        total_population,
        median_household_income,
        median_owner_occupied_home_value,
        median_gross_rent,
        total_housing_units,
        occupied_housing_units,
        owner_occupied_housing_units,
        total_population_moe,
        median_household_income_moe,
        median_owner_occupied_home_value_moe,
        median_gross_rent_moe,
        total_housing_units_moe,
        occupied_housing_units_moe,
        owner_occupied_housing_units_moe,
        case
            when median_household_income > 0
                then median_owner_occupied_home_value / median_household_income::float
        end as home_value_to_income_ratio,
        case
            when median_household_income > 0
                then (median_gross_rent * 12) / median_household_income::float
        end as annual_rent_to_income_ratio,
        case
            when occupied_housing_units > 0
                then owner_occupied_housing_units / occupied_housing_units::float
        end as owner_occupancy_rate,
        case
            when total_housing_units > 0
                then (total_housing_units - occupied_housing_units) / total_housing_units::float
        end as vacancy_proxy_rate,
        source_system,
        source_endpoint,
        source_requested_at,
        ingested_at,
        ingestion_run_id,
        row_hash
    from census

)

select * from metrics
