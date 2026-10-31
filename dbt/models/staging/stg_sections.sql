select
    section_id,
    version_id,
    section_key,
    section_type,
    number,
    heading,
    text,
    text_hash,
    position,
    coalesce(amended_by, []::varchar[]) as amended_by
from {{ source('raw', 'sections') }}
