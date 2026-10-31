-- One row per detected change, with the dates of both versions and the latest successful
-- enrichment (if any). Diffing is deterministic; enrichment columns are AI-generated.
with latest_enrichment as (
    select *
    from {{ ref('stg_enrichments') }}
    where status = 'success'
    qualify row_number() over (partition by change_id order by created_at desc) = 1
)

select
    c.change_id,
    c.doc_id,
    c.from_version,
    c.to_version,
    fv.version_date as from_date,
    tv.version_date as to_date,
    c.section_key,
    c.old_section_key,
    c.section_type,
    c.change_type,
    c.old_text,
    c.new_text,
    c.similarity,
    c.diff_html,
    c.is_synthetic,
    tv.source_url as source_url,
    e.summary,
    e.topics,
    e.sectors,
    e.impact,
    e.impact_rationale,
    e.model as enrichment_model,
    e.prompt_version,
    e.change_id is not null as is_enriched
from {{ ref('stg_changes') }} as c
join {{ ref('stg_document_versions') }} as fv on fv.version_id = c.from_version
join {{ ref('stg_document_versions') }} as tv on tv.version_id = c.to_version
left join latest_enrichment as e using (change_id)
