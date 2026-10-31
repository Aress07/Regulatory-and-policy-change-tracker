"""Index stage: chunk sections of each document's latest parsed version and embed them.

Repealed instruments are not "latest": by default they are left out of Q&A so answers never
come from law that is no longer in force.

Rebuilds the `chunks` table each run (cheap: unchanged text hits the embedding cache).
`include_history=True` also indexes older versions, flagged `is_latest = false`.
"""

from dataclasses import dataclass

import duckdb

from regtracker.common.runs import log_run, new_run_id, utcnow
from regtracker.index.chunk import DEFAULT_MAX_TOKENS, Chunk, breadcrumb, chunk_section
from regtracker.index.embed import Embedder, embed_passages_cached


@dataclass
class IndexReport:
    sections: int
    chunks: int
    embedded: int  # cache misses actually computed


def build_index(
    con: duckdb.DuckDBPyConnection,
    embedder: Embedder,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    include_history: bool = False,
) -> IndexReport:
    started = utcnow()
    rows = con.execute(
        """
        WITH repealed AS (
          SELECT DISTINCT doc_id FROM document_versions WHERE parse_status = 'repealed'
        ),
        versions AS (
          SELECT v.version_id, v.doc_id, v.version_date,
                 v.version_date = max(v.version_date) OVER (PARTITION BY v.doc_id)
                   AND v.doc_id NOT IN (SELECT doc_id FROM repealed) AS is_latest
          FROM document_versions v WHERE v.parse_status = 'parsed'
        )
        SELECT s.section_id, s.version_id, v.doc_id, v.version_date, v.is_latest, s.section_key,
               s.section_type, s.number, s.heading, s.text,
               coalesce(d.short_name, upper(d.doc_id)) AS doc_name
        FROM sections s
        JOIN versions v USING (version_id)
        JOIN documents d ON d.doc_id = v.doc_id
        WHERE v.is_latest OR ?
        ORDER BY v.doc_id, v.version_date, s.position
        """,
        [include_history],
    ).fetchall()

    chunks: list[tuple[Chunk, tuple[object, ...]]] = []
    for sid, vid, doc, vdate, latest, key, stype, number, heading, text, name in rows:
        crumb = breadcrumb(name, stype, number, heading)
        meta = (doc, vid, vdate, key, stype, latest)
        chunks.extend((c, meta) for c in chunk_section(sid, crumb, text, max_tokens))

    vectors, misses = embed_passages_cached(con, embedder, [c.text for c, _ in chunks])

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM chunks")
        if chunks:
            con.executemany(
                "INSERT INTO chunks (chunk_id, section_id, text, embedding, doc_id, version_id, "
                "version_date, section_key, section_type, breadcrumb, is_latest, text_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [c.chunk_id, c.section_id, c.text, v.tolist(), *meta[:5], c.breadcrumb, meta[5],
                     c.text_hash]
                    for (c, meta), v in zip(chunks, vectors, strict=True)
                ],
            )  # fmt: skip
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    report = IndexReport(sections=len(rows), chunks=len(chunks), embedded=misses)
    log_run(
        con,
        run_id=new_run_id(),
        stage="index",
        started_at=started,
        finished_at=utcnow(),
        status="success",
        rows_in=report.sections,
        rows_out=report.chunks,
    )
    return report
