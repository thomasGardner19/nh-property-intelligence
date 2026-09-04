with ranked as (

    select
        county_fips,
        state_code,
        county_name_raw,
        year,
        row_number() over (
            partition by county_fips
            order by year desc
        ) as row_number_latest
    from {{ ref('stg_fhfa__county_hpi') }}

)

select
    county_fips as county_key,
    county_fips,
    state_code,
    county_name_raw,
    year as latest_hpi_year
from ranked
where row_number_latest = 1
