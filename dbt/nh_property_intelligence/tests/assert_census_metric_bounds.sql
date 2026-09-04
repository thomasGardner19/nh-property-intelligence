select *
from {{ ref('int_acs_housing_metrics') }}
where
    (owner_occupancy_rate is not null and (owner_occupancy_rate < 0 or owner_occupancy_rate > 1))
    or (vacancy_proxy_rate is not null and (vacancy_proxy_rate < 0 or vacancy_proxy_rate > 1))
    or (home_value_to_income_ratio is not null and home_value_to_income_ratio < 0)
    or (annual_rent_to_income_ratio is not null and annual_rent_to_income_ratio < 0)
