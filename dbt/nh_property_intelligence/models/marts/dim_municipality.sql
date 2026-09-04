with ranked as (

    select
        county_subdivision_geoid as municipality_geoid,
        state_fips,
        county_fips,
        county_subdivision_fips,
        geography_name_raw as municipality_name_raw,
        acs_vintage,
        row_number() over (
            partition by county_subdivision_geoid
            order by acs_vintage desc
        ) as row_number_latest
    from {{ ref('stg_census__municipality') }}

)

select
    municipality_geoid,
    state_fips,
    county_fips,
    county_subdivision_fips,
    municipality_name_raw,
    acs_vintage as latest_acs_vintage
from ranked
where row_number_latest = 1
