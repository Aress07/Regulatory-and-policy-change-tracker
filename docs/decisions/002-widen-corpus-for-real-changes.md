# ADR-002: Widen the corpus so there are real versions to diff

**Status:** accepted (2026-10-31)

## Context
Diffing needs at least two English consolidated versions of the same act. Querying Cellar on
2026-10-31 (see `docs/sources.md`) showed that the original six instruments have none:
five have a single consolidated version, and the AI Act's second English version has no English
first version to compare with (`02024R1689-20240712` exists in 11 languages, not English).

Treating the original Official Journal act as "version 0" does not help: the first consolidated
version carries the OJ publication date and is the original text.

## Decision
Add three digital-policy instruments that have at least two English consolidated versions:
eIDAS (`32014R0910`), the ePrivacy Directive (`32002L0058`) and the European Electronic
Communications Code (`32018L1972`). Keep the original six for search and Q&A.

Rejected: MiFID II and CRR (many versions, but off-theme), proposal-vs-adopted text
(different markup and numbering; possible later), synthetic changes as primary data (only allowed
as flagged test fixtures).

## Consequences
+ Real version pairs for the diff, enrichment and evaluation stages.
- Still few real changes; if fewer than ~40 after enrichment, widen further (plan section 9).
- Version counts change over time; discovery is re-run on every ingest, so new versions appear
  automatically.

## Update (same day): second widening
The trio yielded 15 real changes (verified by hand). Added five electronic-communications and
media instruments with at least three English consolidated versions each: the Open Internet
Regulation (`32015R2120`), the Audiovisual Media Services Directive (`32010L0013`), the Roaming
Regulation (`32012R0531`), the Framework Directive (`32002L0021`, repealed by the EECC; kept for
its history) and the Universal Service Directive (`32002L0022`, likewise).
