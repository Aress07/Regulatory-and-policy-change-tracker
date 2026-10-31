# Evaluation report

Run date: 2026-10-31. Machine-readable results: `eval/reports/results*.json`; reproduce with
`python eval/run_eval.py --suite all --out eval/reports/` (add `--with-llm` for the answers suite).

> **Read this first.** The gold labels for classification (`eval/datasets/changes_labeled.csv`)
> and the QA set (`eval/datasets/qa_set.jsonl`) were drafted by an LLM (Claude), not by a human
> expert, and are marked `status = draft`. They were written blind to the enrichment output
> (except one row, noted in the file) and committed before any scoring. Until a human verifies
> them, every number that depends on them is **provisional**. QA gold sections were verified
> mechanically: each gold section exists in the parsed text and contains the expected phrase.

## 1. Corpus

| | Count |
|---|---|
| Instruments configured | 14 (12 with at least one English consolidated version) |
| Consolidated versions stored | 27 (24 parsed, 3 repeal notices) |
| Sections (articles + annexes), all versions | 1,261 |
| Real changes detected | 107 (69 modified, 26 added, 12 removed, 0 renumbered) |
| Changes enriched so far | 82 of 107 (the daily token budget stopped the run; the rest resume next run) |
| Chunks indexed for Q&A (latest, non-repealed versions) | 1,475 |

Changes per instrument: Framework Directive 33, AVMSD 28, Roaming Regulation 25, ePrivacy 10,
Open Internet 5, eIDAS 3, EECC 2, Universal Service 1. GDPR, AI Act, DMA and NIS2 have no pair of
English consolidated versions yet (see `docs/sources.md`).

## 2. Diff quality

There is no external ground truth for "what changed", so diff quality was checked three ways:

| Check | Result |
|---|---|
| Unchanged articles across markup generations (ePrivacy 2006 legacy vs 2009 modern) | 13 of 13 unamended articles hash identically (regression test) |
| Article counts vs an independent count of "Article N" titles, all 27 versions | 27 / 27 match; GDPR = 99, matching the Official Journal text |
| Manual audit of all near-identical "modified" changes (similarity ≥ 0.98) and all pairs with both additions and removals | found 3 false positives (chapter headings leaking into legacy articles) and 2 (inline amendment markers); all fixed with regression tests; re-audit: 0 false positives among the audited changes |

Renumbering: the corpus contains no detected renumbering (added and removed sections in the same
pair never reach 0.9 similarity), so the renumbering false-positive rate on real data is 0 of 0;
behaviour is covered by unit and property tests (swapping versions inverts every change).

## 3. Classification (enrichment vs draft labels)

Model `openai/gpt-oss-120b`, prompt `v1`, on the 37 labeled changes that are enriched so far
(8 of the 45 labeled changes are among the 25 not yet enriched). **Provisional: draft labels.**

| Metric | Value |
|---|---|
| Topic micro F1 (precision / recall) | 0.624 (0.567 / 0.694) |
| Topic macro F1 | 0.646 |
| Primary topic accuracy | 0.595 |
| Sector micro F1 | 0.253 |
| Sector macro F1 | 0.277 |
| Impact accuracy | 0.568 (21 / 37) |
| Impact within one level | 0.973 (36 / 37) |

Impact confusion matrix (rows = draft label, columns = model):

| | low | medium | high |
|---|---|---|---|
| **low** | 7 | 8 | 1 |
| **medium** | 1 | 9 | 0 |
| **high** | 0 | 6 | 5 |

Per-topic F1: data_protection 0.93, cybersecurity 0.86, enforcement_penalties 0.80,
competition 0.67, transparency 0.60, scope_definitions 0.55, other 0.48, platform_liability 0.29.

## 4. Retrieval

Section-level hit@k and MRR on the 40 in-scope questions (20 dev, 20 test), for three
retrieval modes and three chunk sizes (tokens). Full table in `eval/reports/summary.md`.

| Setting | hit@1 (all) | hit@3 (all) | hit@5 (all) | MRR (dev) | MRR (test) | MRR (all) |
|---|---|---|---|---|---|---|
| BM25 @ 300 | 0.775 | 0.975 | 0.975 | 0.896 | 0.842 | 0.869 |
| Vector (E5) @ 300 | 0.875 | 0.975 | 1.000 | 0.904 | 0.950 | 0.927 |
| **Hybrid (RRF) @ 300** (deployed) | 0.950 | 1.000 | 1.000 | 0.975 | 0.975 | 0.975 |
| Hybrid @ 200 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Hybrid @ 400 | 0.950 | 1.000 | 1.000 | 0.942 | 1.000 | 0.971 |

Hybrid beats either ranking alone at every chunk size. Hybrid @ 200 is best on every number, but
on dev it differs from 300 by a single question (one rank-2 hit), which is within noise for 20
questions; 300 stays deployed. Re-chunking at 200 is a cheap follow-up once the QA set is
verified and larger.

## 5. Refusal gate and answers

**Refusal gate** (no LLM involved): the threshold on the best E5 cosine similarity of the
hybrid top 5 was tuned on dev only and applied unchanged to test.

| Split | Threshold | Accuracy | In-scope answered | Out-of-scope refused |
|---|---|---|---|---|
| dev (20 + 5) | 0.8313 | 1.000 | 1.000 | 1.000 |
| test (20 + 5) | 0.8313 | 1.000 | 1.000 | 1.000 |

The threshold is the midpoint of the dev gap between the highest out-of-scope score (0.8168) and
the lowest in-scope score (0.8458). The tuner first picked the lowest in-scope score itself, which
leaves zero margin; it now centres the threshold in the widest gap. On test the margin is thin:
the highest out-of-scope question scores 0.8285, only 0.003 below the threshold. Separation is
perfect here, but the out-of-scope questions are far from the corpus (bread, football, US visas). Near-miss questions (e.g. a GDPR-style question about a non-EU law) would be a
harder test and are not in the set yet.

**End-to-end answers with the LLM (citation validity, refusal accuracy with generation): not run
yet.** The daily token budget was used by enrichment; run
`python eval/run_eval.py --suite answers` on a fresh budget. By construction, every answer the
system returns has passed the citation validator (citations outside the retrieved set reject the
answer), which unit and API tests cover.

## 6. System

| Metric | Value |
|---|---|
| Enrichment tokens per change (input + output) | 1,810 |
| Median enrichment latency (API time) | 717 ms |
| Shadow cost per 1,000 changes (gpt-oss-120b list price) | $0.37 |
| Shadow cost of the 82 enrichments | $0.03 |
| Actual cost (Groq free tier) | $0 |
| Validation failures after one retry | 0 of 82 |
| Real LLM calls / tokens on the run day | 82 calls, 148,437 tokens (budget 150,000) |

The first real run also surfaced two robustness bugs that are now fixed and tested: a Groq
`400 Failed to validate JSON` aborted the whole batch (now handled per change via the
validation-retry path), and invalid answers were cached (now never cached).

## 7. Failure analysis

1. **Sector labels: definition mismatch, not comprehension.** The model chose `all` for 62 of 83
   sector slots. In 19 of 37 labeled changes the label is `telecom` and the model said `all`: it
   reads "applies regardless of sector" as "applies to everyone in the instrument's scope", while
   the labeling guide treats a telecom-only directive as `telecom`. Fix: prompt `v2` stating that
   sector-specific instruments take their sector. Written as `src/regtracker/enrich/prompts/v2.md`
   (with invented impact examples for removed obligations and procedural changes) but not run yet
   (budget). Because v2 was written after seeing v1's errors on these draft labels, its score on
   them will be a tuned result, not a blind one.
2. **Impact: central tendency.** The model predicts `medium` for 57 of 82 changes. It upgrades
   procedural or wording changes to `medium` (8 low -> medium) and rates 6 changes `medium` that
   the labels call `high`. Its rationales for those 6 correctly name the trigger ("creates new
   enforcement and penalty obligations", "eliminates mandatory security and breach-notification
   obligations", "shifts ... to a consent requirement") yet stop at `medium`, contradicting the
   prompt's own scale, where new or removed obligations and penalties are `high`. Fix candidates:
   few-shot examples of removed obligations and new penalties, and of purely procedural changes;
   within-one accuracy is already 0.97.
3. **A label error found by the model.** For Open Internet Art. 5a the draft label says `low`, the
   model says `high`. The model is right: the change adds a ban on different retail prices for
   domestic and intra-EU communications from 2029. The labeling view truncated each passage to
   420 characters, which hid that paragraph. The frozen label file was not edited; the error is
   reported here. Lesson: label from the full diff, not excerpts.
4. **QA set is optimistic.** The questions were written with knowledge of the target articles, so
   they share vocabulary with them; retrieval numbers are likely higher than for real users.
5. **Corpus gaps.** Headline acts (GDPR, DSA, Data Act, AI Act's first version) lack English
   consolidated version pairs in Cellar, so the change set is dominated by telecom and media law.

## 8. Limitations

- Labels are LLM drafts (see the note at the top); the "model vs labels" comparison partly measures
  agreement between two LLMs.
- Small evaluation sets (45 labeled changes, 40 + 10 questions): differences of a few points are
  within noise.
- Retrieval gold is one section per question; answers that correctly cite a different, equally
  valid article count as misses.
