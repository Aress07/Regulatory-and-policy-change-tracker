select
    change_id,
    model,
    prompt_version,
    status,
    summary,
    topics,
    sectors,
    impact,
    impact_rationale,
    error,
    tokens_in,
    tokens_out,
    latency_ms,
    shadow_cost_usd,
    created_at
from {{ source('raw', 'enrichments') }}
