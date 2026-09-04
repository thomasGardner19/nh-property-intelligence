select f.*
from {{ ref('fact_county_hpi') }} f
left join {{ ref('dim_county') }} d
    on f.county_key = d.county_key
where d.county_key is null
