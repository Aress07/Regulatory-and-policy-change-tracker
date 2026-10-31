-- A "modified" change must differ after normalization (whitespace is irrelevant).
select change_id
from {{ ref('stg_changes') }}
where change_type = 'modified'
  and regexp_replace(old_text, '\s+', ' ', 'g') = regexp_replace(new_text, '\s+', ' ', 'g')
