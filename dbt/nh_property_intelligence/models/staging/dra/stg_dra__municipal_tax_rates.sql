with source as (

    select *
    from {{ source('dra', 'dra_municipal_tax_rates') }}

),

renamed as (

    select
        tax_year,
        municipality_name_raw,
        upper(trim(municipality_name_raw)) as municipality_name_normalized,
        rate_date,
        valuation,
        valuation_including_utilities,
        municipal_tax_rate,
        county_tax_rate,
        state_education_tax_rate,
        local_education_tax_rate,
        total_tax_rate,
        total_commitment,
        raw_payload,
        source_system,
        source_file_name,
        source_url,
        source_requested_at,
        ingested_at,
        ingestion_run_id,
        row_hash
    from source

)

select * from renamed
