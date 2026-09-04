select *
from {{ ref('stg_census__municipality') }}
where (occupied_housing_units is not null and total_housing_units is not null
       and occupied_housing_units > total_housing_units)
   or (owner_occupied_housing_units is not null and occupied_housing_units is not null
       and owner_occupied_housing_units > occupied_housing_units)
