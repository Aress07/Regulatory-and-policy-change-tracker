import type { ReactNode } from "react";
import type { Freshness, Impact } from "../types";

export function AiBadge() {
  return (
    <span className="badge ai" title="Written by a language model; may be wrong">
      AI-generated
    </span>
  );
}

export function SyntheticBadge() {
  return (
    <span className="badge synthetic" title="Test fixture, not a real legal change">
      Synthetic test data
    </span>
  );
}

export function ImpactBadge({ impact }: { impact: Impact | null }) {
  if (!impact) return <span className="badge">not rated</span>;
  return <span className={`badge ${impact}`}>{impact} impact</span>;
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="skeleton" role="status">
      {what}…
    </p>
  );
}

export function ErrorMessage({ error }: { error: Error }) {
  return (
    <div className="banner error" role="alert">
      Could not load data: {error.message}
    </div>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="card">
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}

export function FreshnessBanner({ freshness }: { freshness: Freshness }) {
  if (!freshness.last_successful_ingest) {
    return <div className="banner warn">No successful ingestion recorded yet.</div>;
  }
  const when = freshness.last_successful_ingest.replace("T", " ").slice(0, 16);
  const days = freshness.days_since_ingest ?? 0;
  if (days > 8) {
    return (
      <div className="banner warn">
        Last successful ingest: {when} UTC ({days} days ago). Data may be stale.
      </div>
    );
  }
  return (
    <p className="muted small">
      Last successful ingest: {when} UTC ({days} days ago)
    </p>
  );
}

/** Multi-select as toggle chips (good for a handful of options). */
export function ChipGroup({
  legend,
  options,
  selected,
  onChange,
}: {
  legend: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  return (
    <fieldset>
      <legend>{legend}</legend>
      <div className="chips">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            className="chip"
            aria-pressed={selected.includes(o)}
            onClick={() => toggle(o)}
          >
            {o.replace(/_/g, " ")}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export function formatDate(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "–";
}
