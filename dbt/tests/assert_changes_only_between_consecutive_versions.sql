-- from_version must be the version immediately before to_version among parsed versions.
with ordered as (
    select
        version_id,
        lag(version_id) over (partition by doc_id order by version_date) as prev
    from {{ ref('stg_document_versions') }}
    where parse_status = 'parsed'
)
select c.change_id
from {{ ref('stg_changes') }} as c
left join ordered as o on o.version_id = c.to_version
where o.prev is distinct from c.from_version
