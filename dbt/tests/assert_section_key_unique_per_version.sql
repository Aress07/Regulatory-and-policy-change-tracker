select version_id, section_key
from {{ ref('stg_sections') }}
group by all
having count(*) > 1
