select
    acs_vintage,
    county_subdivision_geoid,
    count(*) as row_count
from {{ ref('stg_census__municipality') }}
group by 1, 2
having count(*) > 1
