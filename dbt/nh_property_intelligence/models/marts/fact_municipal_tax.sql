with tax as (

    select *
    from {{ ref('stg_dra__municipal_tax_rates') }}

),

crosswalk as (

    select *
    from {{ ref('int_municipality_crosswalk') }}

)

select
    c.municipality_geoid,
    t.tax_year,
    t.municipality_name_raw as dra_municipality_name_raw,
    c.match_method,
    t.rate_date,
    t.valuation,
    t.valuation_including_utilities,
    t.municipal_tax_rate,
    t.county_tax_rate,
    t.state_education_tax_rate,
    t.local_education_tax_rate,
    t.total_tax_rate,
    t.total_commitment,
    t.source_system,
    t.source_file_name,
    t.source_url,
    t.source_requested_at,
    t.ingested_at,
    t.ingestion_run_id,
    t.row_hash
from tax t
inner join crosswalk c
    on t.municipality_name_raw = c.dra_municipality_name_raw
