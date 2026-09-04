select
    municipality_geoid,
    tax_year,
    count(*) as row_count
from {{ ref('fact_municipal_tax') }}
group by 1, 2
having count(*) > 1
