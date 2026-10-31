select
    s.section_id,
    s.version_id,
    v.doc_id,
    v.version_date,
    s.section_key,
    s.section_type,
    s.number,
    s.heading,
    s.text,
    s.text_hash,
    s.position,
    s.amended_by,
    length(s.text) as text_chars,
    v.version_date = max(v.version_date) over (partition by v.doc_id) as is_latest
from {{ ref('stg_sections') }} as s
join {{ ref('stg_document_versions') }} as v using (version_id)
