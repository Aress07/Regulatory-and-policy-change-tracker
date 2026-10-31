# Labeling guide

Gold labels for `eval/datasets/changes_labeled.csv`. One row per change; read the old and new
text (or the diff) and the official source before labeling.

## Impact
- **low**: wording fix, clarification, formatting, cross-reference or numbering update.
- **medium**: changes obligations, scope or definitions for a subset of actors; new exemptions.
- **high**: new or removed obligations, penalties, deadlines, or scope that affects many actors.
- When unsure between two levels, choose the lower one and say why in `notes`.

## Topics and sectors
- 1-3 topics and 1-3 sectors; list the primary one first, separated by `|`.
- Topics: data_protection, ai_governance, cybersecurity, platform_liability, competition,
  data_sharing, transparency, enforcement_penalties, scope_definitions, other.
- Sectors: all, healthcare, finance, public_sector, online_platforms, manufacturing, telecom,
  education, other. Use `all` when the change applies regardless of sector.

## Status column
- `draft`: proposed by Claude (an LLM) from the diff; **not** a human judgment. Metrics computed
  on draft rows are provisional and must be labeled as such.
- `verified`: checked (and corrected if needed) by a human. Only verified rows count as gold.

## Agreement check
Re-label a 20-row subset a week later without looking at the first labels and report agreement
(plan section 14).
