select
    change_id,
    doc_id,
    from_version,
    to_version,
    section_key,
    coalesce(old_section_key, section_key) as old_section_key,
    section_type,
    change_type,
    old_text,
    new_text,
    similarity,
    diff_html,
    coalesce(is_synthetic, false) as is_synthetic
from {{ source('raw', 'changes') }}
