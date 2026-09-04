with source as (

    select *
    from {{ source('fhfa', 'fhfa_county_hpi') }}

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
    source_system,
    source_dataset,
    source_file_name,
    source_url,
    source_requested_at,
    ingested_at,
    ingestion_run_id,
    row_hash
from source
