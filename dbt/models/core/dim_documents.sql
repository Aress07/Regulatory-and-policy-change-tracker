with versions as (
    select
        doc_id,
        count(*) filter (where parse_status = 'parsed') as parsed_versions,
        min(version_date) as first_version_date,
        max(version_date) filter (where parse_status = 'parsed') as latest_version_date,
        max(fetched_at) as last_fetched_at,
        bool_or(parse_status = 'repealed') as is_repealed,
        max(version_date) filter (where parse_status = 'repealed') as repealed_on
    from {{ ref('stg_document_versions') }}
    group by doc_id
)

select
    d.doc_id,
    d.celex_base,
    d.title,
    d.doc_type,
    d.language,
    coalesce(v.parsed_versions, 0) as parsed_versions,
    v.first_version_date,
    v.latest_version_date,
    v.last_fetched_at,
    coalesce(v.is_repealed, false) as is_repealed,
    v.repealed_on,
    'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:' || d.celex_base as eurlex_url
from {{ ref('stg_documents') }} as d
left join versions as v using (doc_id)
