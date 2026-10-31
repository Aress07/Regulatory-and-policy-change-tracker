# Demo video script (2-3 minutes)

Record at 1440x900 or larger with OBS (free). Prepare before recording: `make app` running on
http://localhost:8000 (or the public Space), a terminal in the repo, and `make dagster` running on
http://localhost:3000. Keep the Ask question short; it uses the LLM budget.

| Time | Show | Say (roughly) |
|---|---|---|
| 0:00-0:20 | Overview page | "EU digital law changes rarely and quietly. Compliance teams need to know what changed, why it matters, and where it is in the text. This tool tracks 14 EU acts article by article." |
| 0:20-0:45 | Terminal: `regtracker ingest --all`, `regtracker parse`, `regtracker diff` (rerun: everything is skipped, which shows idempotency) | "Versions come from the EU Publications Office. Raw files are immutable, and the diff is deterministic: no AI decides what changed." |
| 0:45-1:15 | Timeline, filter impact = high, open *Open Internet Regulation, Article 5a* | "Each change gets a plain-language summary, topics and an impact rating from an LLM, always labelled as AI-generated, next to the exact word-level diff and the official link." |
| 1:15-1:45 | Ask: "What are the roaming surcharge rules?"; open a citation | "Answers come only from retrieved articles. Every sentence cites a passage, invalid citations are rejected, and weak retrieval returns 'not enough evidence' instead of a guess." |
| 1:45-2:10 | Dagster lineage graph (assets and checks), then Pipeline health page | "The pipeline is orchestrated as assets with checks for freshness and failed enrichments; every run, token and shadow cost is logged." |
| 2:10-2:40 | `docs/eval-report.md` tables | "Hybrid retrieval reaches MRR 0.975 against 0.87 for keyword search alone; the refusal gate was 25 out of 25 on held-out questions; enrichment costs about 37 cents per thousand changes. Labels are still drafts, and the report says so." |
| 2:40-2:50 | README | "Everything runs on free infrastructure. Not legal advice." |

After recording: upload (YouTube unlisted works), link it at the top of the README, and tick the
item in `docs/execution-plan.md` section 0.4.
