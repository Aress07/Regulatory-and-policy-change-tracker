select
    run_id,
    split_part(stage, ':', 1) as stage,
    nullif(split_part(stage, ':', 2), '') as subject,
    started_at,
    finished_at,
    datediff('millisecond', started_at, finished_at) as duration_ms,
    status,
    rows_in,
    rows_out,
    error
from {{ source('raw', 'pipeline_runs') }}
