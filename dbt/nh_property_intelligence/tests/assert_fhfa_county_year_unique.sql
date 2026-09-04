select
    county_fips,
    year,
    count(*) as row_count
from {{ ref('fact_county_hpi') }}
group by 1, 2
having count(*) > 1
