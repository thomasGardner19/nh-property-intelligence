select *
from {{ ref('mart_town_scorecard') }}
where median_owner_occupied_home_value is not null
  and total_tax_rate is not null
  and abs(
      estimated_annual_property_tax_on_median_home
      - (median_owner_occupied_home_value * total_tax_rate / 1000.0)
  ) > 0.01
