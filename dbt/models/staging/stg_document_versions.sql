select
    version_id,
    doc_id,
    celex,
    version_date,
    source_url,
    fetched_at,
    content_hash,
    raw_path,
    coalesce(parse_status, 'pending') as parse_status,
    repealed_by
from {{ source('raw', 'document_versions') }}
