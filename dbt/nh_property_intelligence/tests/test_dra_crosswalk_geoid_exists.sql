select c.*
from {{ ref('int_municipality_crosswalk') }} c
left join {{ ref('dim_municipality') }} d
    on c.municipality_geoid = d.municipality_geoid
where c.municipality_geoid is not null
  and d.municipality_geoid is null
