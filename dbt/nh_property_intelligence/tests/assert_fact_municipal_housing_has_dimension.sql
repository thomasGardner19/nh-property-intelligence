select fact.municipality_geoid
from {{ ref('fact_municipal_housing') }} as fact
left join {{ ref('dim_municipality') }} as dim
    on fact.municipality_geoid = dim.municipality_geoid
where dim.municipality_geoid is null
