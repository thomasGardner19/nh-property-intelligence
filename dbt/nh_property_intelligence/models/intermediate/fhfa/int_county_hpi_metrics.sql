with base as (

    select *
    from {{ ref('stg_fhfa__county_hpi') }}

),

lagged as (

    select
        *,
        lag(hpi, 1) over (partition by county_fips order by year) as hpi_1_year_prior,
        lag(hpi, 3) over (partition by county_fips order by year) as hpi_3_year_prior,
        lag(hpi, 5) over (partition by county_fips order by year) as hpi_5_year_prior,
        lag(hpi, 10) over (partition by county_fips order by year) as hpi_10_year_prior,
        lag(year, 1) over (partition by county_fips order by year) as year_1_prior,
        lag(year, 3) over (partition by county_fips order by year) as year_3_prior,
        lag(year, 5) over (partition by county_fips order by year) as year_5_prior,
        lag(year, 10) over (partition by county_fips order by year) as year_10_prior
    from base

)

select
    state_code,
    county_name_raw,
    county_fips,
    year,
    annual_change_pct,
    hpi,
    hpi_1990_base,
    hpi_2000_base,
    case when year_1_prior = year - 1 and hpi_1_year_prior > 0 and hpi is not null
        then (hpi / hpi_1_year_prior) - 1 end as appreciation_1y,
    case when year_3_prior = year - 3 and hpi_3_year_prior > 0 and hpi is not null
        then (hpi / hpi_3_year_prior) - 1 end as appreciation_3y,
    case when year_5_prior = year - 5 and hpi_5_year_prior > 0 and hpi is not null
        then (hpi / hpi_5_year_prior) - 1 end as appreciation_5y,
    case when year_10_prior = year - 10 and hpi_10_year_prior > 0 and hpi is not null
        then (hpi / hpi_10_year_prior) - 1 end as appreciation_10y,
    case when year_5_prior = year - 5 and hpi_5_year_prior > 0 and hpi is not null
        then power(hpi / hpi_5_year_prior, 1.0 / 5.0) - 1 end as cagr_5y,
    source_system,
    source_dataset,
    source_file_name,
    source_url,
    source_requested_at,
    ingested_at,
    ingestion_run_id,
    row_hash
from lagged
