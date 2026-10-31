select doc_id, celex_base, title, doc_type, language
from {{ source('raw', 'documents') }}
