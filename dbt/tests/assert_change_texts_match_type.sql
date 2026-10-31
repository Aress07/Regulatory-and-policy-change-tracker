-- added: no old text; removed: no new text; modified/renumbered: both.
select change_id
from {{ ref('stg_changes') }}
where (change_type = 'added' and (old_text is not null or new_text is null))
   or (change_type = 'removed' and (new_text is null) is false)
   or (change_type in ('modified', 'renumbered') and (old_text is null or new_text is null))
