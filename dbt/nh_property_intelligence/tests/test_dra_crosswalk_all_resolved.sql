select *
from {{ ref('int_municipality_crosswalk') }}
where municipality_geoid is null
   or match_method in ('unmatched', 'ambiguous')
