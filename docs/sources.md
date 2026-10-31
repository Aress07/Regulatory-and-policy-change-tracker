# Data sources

All legal texts come from **Cellar**, the Publications Office's open repository behind EUR-Lex.
No API key or payment is needed. Reuse conditions are summarized in the README; check the
[EUR-Lex legal notice](https://eur-lex.europa.eu/content/legal-notice/legal-notice.html) for the
authoritative wording.

## Endpoints

| Purpose | Endpoint | Notes |
|---|---|---|
| Version discovery | `https://publications.europa.eu/webapi/rdf/sparql` | `Accept: application/sparql-results+json`, query in the `query` parameter |
| Document download | `http://publications.europa.eu/resource/celex/{CELEX}` | `Accept: application/xhtml+xml`, `Accept-Language: eng`; answers `303` to a `/resource/cellar/{uuid}/DOC_1` URL, then `200` |

Sources: [Cellar: publications](https://op.europa.eu/en/web/cellar/cellar-data/publications),
[Cellar: knowledge graph](https://op.europa.eu/en/web/cellar/cellar-data/metadata/knowledge-graph).
Verified with live requests on 2026-10-31.

## How versions are modelled

- A consolidated version is its own Cellar work, linked to the base act by
  `cdm:act_consolidated_based_on_resource_legal`.
- Its CELEX is the base CELEX with sector `0` and a `-YYYYMMDD` suffix:
  `32016R0679` → `02016R0679-20160504`. The suffix equals `cdm:work_date_document`; discovery
  checks this and fails loudly if they ever disagree.
- The first consolidated version carries the original Official Journal publication date, so it
  *is* the original text. Treating the base act as a separate "version 0" would only duplicate it.
- Consolidated versions can be dated in the future (e.g. `02013R0575-20270101`): consolidation
  follows the date provisions apply, not the date they were adopted.

## Quirks

- **Language codes are ISO 639-3** (`eng`, `fra`). Two-letter codes return 404.
- **Not every consolidated version exists in English.** Some are published in only a handful of
  languages (on 2026-10-31: `02024R1689-20240712` in 11, `02022R2065-20221027` in 8,
  `02023R2854-20231222` in 5, none of them English). Cellar answers `404` for English XHTML.
  Ingestion records these as *unavailable* in `pipeline_runs.error` and continues; a later run
  picks them up if an English version is added.
- Each English version we checked is available as `xhtml`, `fmx4` (Formex XML) and PDF/A.
- The XHTML is UTF-8. Parse the bytes, not a decoded guess (lxml's HTML parser mis-guesses).
- Discovery responses are never cached, so new versions cannot be hidden by a stale cache.
  Document downloads are cached in `data/cache/http/` (gitignored); version content is immutable.

## Corpus coverage (2026-10-31)

| doc_id | Base CELEX | Consolidated versions | With English XHTML |
|---|---|---|---|
| gdpr | 32016R0679 | 1 | 1 |
| ai_act | 32024R1689 | 2 | 1 |
| data_act | 32023R2854 | 1 | 0 |
| dsa | 32022R2065 | 1 | 0 |
| dma | 32022R1925 | 1 | 1 |
| nis2 | 32022L2555 | 1 | 1 |

The current corpus has **no instrument with two English versions**, so it yields no real
version pairs to diff. Candidates checked the same way:

| Instrument | Base CELEX | Versions | With English XHTML |
|---|---|---|---|
| Capital Requirements Regulation (CRR) | 32013R0575 | 23 | 23 |
| MiFID II | 32014L0065 | 14 | 14 |
| eIDAS | 32014R0910 | 3 | 2 |
| ePrivacy Directive | 32002L0058 | 2 | 2 |
| European Electronic Communications Code | 32018L1972 | 2 | 2 |
| Cybersecurity Act | 32019R0881 | 2 | 1 |
| Platform-to-Business Regulation | 32019R1150 | 1 | 0 |
| EU institutions data protection (EUDPR) | 32018R1725 | 1 | 0 |
| Data Governance Act | 32022R0868 | 1 | 0 |
