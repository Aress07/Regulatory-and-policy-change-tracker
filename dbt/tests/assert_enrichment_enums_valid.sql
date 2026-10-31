-- Every successful enrichment uses only the allowed topic and sector values.
select change_id
from {{ ref('stg_enrichments') }}
where status = 'success'
  and (
    len(list_filter(topics, lambda t: t not in (
        'data_protection', 'ai_governance', 'cybersecurity', 'platform_liability', 'competition',
        'data_sharing', 'transparency', 'enforcement_penalties', 'scope_definitions', 'other'
    ))) > 0
    or len(list_filter(sectors, lambda s: s not in (
        'all', 'healthcare', 'finance', 'public_sector', 'online_platforms', 'manufacturing',
        'telecom', 'education', 'other'
    ))) > 0
  )
