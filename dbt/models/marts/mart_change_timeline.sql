select
    to_date as change_date,
    doc_id,
    change_type,
    coalesce(impact, 'unrated') as impact,
    count(*) as changes,
    count(*) filter (where is_synthetic) as synthetic_changes
from {{ ref('fct_changes') }}
group by all
