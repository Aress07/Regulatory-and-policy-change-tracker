select
    max(finished_at) filter (where stage = 'ingest' and status = 'success') as last_successful_ingest,
    max(finished_at) filter (where stage = 'ingest' and status = 'failed') as last_failed_ingest,
    count(*) filter (where status = 'failed' and finished_at > now() - interval 7 day)
        as failures_last_7_days,
    datediff(
        'day',
        max(finished_at) filter (where stage = 'ingest' and status = 'success'),
        now()
    ) as days_since_ingest
from {{ ref('stg_pipeline_runs') }}
