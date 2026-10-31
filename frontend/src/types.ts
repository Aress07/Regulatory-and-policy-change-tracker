// Mirrors the response models in src/regtracker/api/main.py.

export type Impact = "low" | "medium" | "high";

export interface Change {
  change_id: string;
  doc_id: string;
  instrument: string;
  section_key: string;
  old_section_key: string | null;
  section_type: string | null;
  heading: string | null;
  change_type: "added" | "removed" | "modified" | "renumbered";
  from_version: string;
  to_version: string;
  from_date: string;
  to_date: string;
  is_synthetic: boolean;
  source_url: string;
  summary: string | null;
  topics: string[] | null;
  sectors: string[] | null;
  impact: Impact | null;
  impact_rationale: string | null;
  enrichment_model: string | null;
  prompt_version: string | null;
  enriched_at: string | null;
  is_enriched: boolean;
  enrichment_failed: boolean;
  similarity: number | null;
}

export interface ChangeDetail extends Change {
  old_text: string | null;
  new_text: string | null;
  diff_html: string | null;
}

export interface DocumentInfo {
  doc_id: string;
  instrument: string;
  title: string | null;
  celex_base: string;
  doc_type: string | null;
  versions: number;
  latest_version: string | null;
  repealed: boolean;
  changes: number;
  source_url: string;
}

export interface Freshness {
  last_successful_ingest: string | null;
  days_since_ingest: number | null;
  failures_last_7_days: number;
}

export interface Overview {
  instruments: number;
  versions_parsed: number;
  changes: number;
  high_impact: number;
  enriched: number;
  latest_change_date: string | null;
  changes_by_instrument_and_type: { instrument: string; change_type: string; changes: number }[];
  freshness: Freshness;
}

export interface TopicCount {
  instrument: string;
  year: number;
  topic: string;
  changes: number;
}

export interface Run {
  stage: string;
  subject: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  seconds: number | null;
  rows_in: number | null;
  rows_out: number | null;
  error: string | null;
  run_id: string;
}

export interface LlmUsage {
  model: string;
  prompt_version: string;
  succeeded: number;
  failed: number;
  tokens_in: number | null;
  tokens_out: number | null;
  tokens_per_change: number | null;
  shadow_cost_usd: number | null;
  shadow_cost_per_1000_changes: number | null;
  median_latency_ms: number | null;
}

export interface Meta {
  topics: string[];
  sectors: string[];
  impacts: string[];
  change_types: string[];
  disclaimer: string;
  ask_enabled: boolean;
}

export interface Citation {
  n: number;
  section_id: string;
  breadcrumb: string;
  source_url: string;
}

export interface Passage {
  section_id: string;
  breadcrumb: string;
  text: string;
  score: number;
  cosine: number;
}

export interface AskResponse {
  status:
    | "answered"
    | "not_found"
    | "not_enough_evidence"
    | "rejected_invalid_citations"
    | "retrieval_only";
  answer: string | null;
  citations: Citation[];
  confidence: "high" | "medium" | "low" | "none";
  retrieved: Passage[];
  note: string | null;
  disclaimer: string;
}
