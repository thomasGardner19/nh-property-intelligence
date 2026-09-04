with expected_latest as (

    select
        county_fips,
        max(year) as latest_year
    from {{ ref('int_county_hpi_metrics') }}
    group by county_fips

),

scorecard as (

    select
        municipality_geoid,
        state_fips || county_fips as county_fips,
        county_hpi_year
    from {{ ref('mart_town_scorecard') }}

)

select
    s.municipality_geoid,
    s.county_fips,
    s.county_hpi_year,
    e.latest_year
from scorecard s
left join expected_latest e
    on s.county_fips = e.county_fips
where e.county_fips is null
    or s.county_hpi_year is null
    or s.county_hpi_year <> e.latest_year
