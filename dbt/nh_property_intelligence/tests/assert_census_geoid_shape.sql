select *
from {{ ref('stg_census__municipality') }}
where length(county_subdivision_geoid) <> 10
   or not regexp_like(county_subdivision_geoid, '^[0-9]{10}$')
