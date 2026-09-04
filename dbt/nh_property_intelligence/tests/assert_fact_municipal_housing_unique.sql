select
    municipality_geoid,
    acs_vintage,
    count(*) as row_count
from {{ ref('fact_municipal_housing') }}
group by 1, 2
having count(*) > 1
