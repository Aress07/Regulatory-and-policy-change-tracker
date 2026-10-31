-- Empty until enrichment has run; topics come from the LLM and are labeled as AI-generated.
with exploded as (
    select
        date_trunc('year', to_date) as period,
        doc_id,
        unnest(topics) as topic
    from {{ ref('fct_changes') }}
    where is_enriched and not is_synthetic
)

select period, doc_id, topic, count(*) as changes
from exploded
group by all
