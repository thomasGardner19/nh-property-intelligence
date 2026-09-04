select *
from {{ ref('mart_town_scorecard') }}
where estimated_annual_property_tax_on_median_home < 0
   or estimated_property_tax_to_income_ratio < 0
   or estimated_property_tax_to_income_ratio > 1
