with latest_housing as (

    select *
    from {{ ref('fact_municipal_housing') }}
    qualify row_number() over (
        partition by municipality_geoid
        order by acs_vintage desc
    ) = 1

),

latest_tax as (

    select *
    from {{ ref('fact_municipal_tax') }}
    qualify row_number() over (
        partition by municipality_geoid
        order by tax_year desc
    ) = 1

),

latest_county_hpi as (

    select *
    from {{ ref('int_county_hpi_metrics') }}
    qualify row_number() over (
        partition by county_fips
        order by year desc
    ) = 1

),

municipality as (

    select *
    from {{ ref('dim_municipality') }}

)

select
    m.municipality_geoid,
    m.municipality_name_raw,
    m.state_fips,
    m.county_fips,
    h.acs_vintage,
    t.tax_year,
    ch.year as county_hpi_year,
    h.total_population,
    h.median_household_income,
    h.median_owner_occupied_home_value,
    h.median_gross_rent,
    h.home_value_to_income_ratio,
    h.annual_rent_to_income_ratio,
    h.owner_occupancy_rate,
    h.vacancy_proxy_rate,
    t.municipal_tax_rate,
    t.county_tax_rate,
    t.state_education_tax_rate,
    t.local_education_tax_rate,
    t.total_tax_rate,
    case
        when h.median_owner_occupied_home_value is not null
            and t.total_tax_rate is not null
            then h.median_owner_occupied_home_value * t.total_tax_rate / 1000.0
    end as estimated_annual_property_tax_on_median_home,
    case
        when h.median_household_income > 0
            and h.median_owner_occupied_home_value is not null
            and t.total_tax_rate is not null
            then (
                h.median_owner_occupied_home_value * t.total_tax_rate / 1000.0
            ) / h.median_household_income::float
    end as estimated_property_tax_to_income_ratio,
    ch.county_name_raw as county_hpi_county_name_raw,
    ch.hpi as county_hpi,
    ch.annual_change_pct as county_hpi_annual_change_pct,
    ch.appreciation_1y as county_hpi_appreciation_1y,
    ch.appreciation_3y as county_hpi_appreciation_3y,
    ch.appreciation_5y as county_hpi_appreciation_5y,
    ch.appreciation_10y as county_hpi_appreciation_10y,
    ch.cagr_5y as county_hpi_cagr_5y,
    h.total_population_moe,
    h.median_household_income_moe,
    h.median_owner_occupied_home_value_moe,
    h.median_gross_rent_moe,
    t.dra_municipality_name_raw,
    t.match_method as dra_match_method
from municipality m
left join latest_housing h
    on m.municipality_geoid = h.municipality_geoid
left join latest_tax t
    on m.municipality_geoid = t.municipality_geoid
left join latest_county_hpi ch
    on m.state_fips || m.county_fips = ch.county_fips
