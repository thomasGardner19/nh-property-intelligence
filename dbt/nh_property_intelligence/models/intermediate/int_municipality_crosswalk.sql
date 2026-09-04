with dra_names as (

    select distinct
        municipality_name_raw as dra_municipality_name_raw,
        upper(
            trim(
                regexp_replace(
                    regexp_replace(municipality_name_raw, '^(Town|City) of\\s+', '', 1, 0, 'i'),
                    '\\s+(town|city)$',
                    '',
                    1,
                    0,
                    'i'
                )
            )
        ) as normalized_name
    from {{ ref('stg_dra__municipal_tax_rates') }}

),

census_names as (

    select
        municipality_geoid,
        municipality_name_raw as census_municipality_name_raw,
        upper(
            trim(
                regexp_replace(
                    split_part(municipality_name_raw, ',', 1),
                    '\\s+(town|city)$',
                    '',
                    1,
                    0,
                    'i'
                )
            )
        ) as normalized_name
    from {{ ref('dim_municipality') }}

),

automatic_candidates as (

    select
        d.dra_municipality_name_raw,
        d.normalized_name,
        c.municipality_geoid,
        c.census_municipality_name_raw,
        count(*) over (partition by d.dra_municipality_name_raw) as candidate_count
    from dra_names d
    left join census_names c
        on d.normalized_name = c.normalized_name

),

overrides as (

    select
        dra_municipality_name_raw,
        municipality_geoid,
        reason
    from {{ ref('dra_municipality_overrides') }}

),

resolved as (

    select
        a.dra_municipality_name_raw,
        a.normalized_name,
        coalesce(o.municipality_geoid, case when a.candidate_count = 1 then a.municipality_geoid end)
            as municipality_geoid,
        case
            when o.municipality_geoid is not null then 'override'
            when a.candidate_count = 1 and a.municipality_geoid is not null then 'normalized_name'
            when a.candidate_count = 0 or a.municipality_geoid is null then 'unmatched'
            else 'ambiguous'
        end as match_method,
        a.candidate_count,
        a.census_municipality_name_raw,
        o.reason as override_reason
    from automatic_candidates a
    left join overrides o
        on a.dra_municipality_name_raw = o.dra_municipality_name_raw
    qualify row_number() over (
        partition by a.dra_municipality_name_raw
        order by
            case when o.municipality_geoid is not null then 0 else 1 end,
            a.municipality_geoid
    ) = 1

)

select * from resolved
