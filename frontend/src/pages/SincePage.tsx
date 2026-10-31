import { Link } from "react-router-dom";
import { useState } from "react";
import { api, useApi } from "../api";
import { AiBadge, Card, ErrorMessage, ImpactBadge, Loading } from "../components/ui";
import type { Change } from "../types";

const STORAGE_KEY = "regtracker.lastLooked";

function defaultSince(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
  } catch {
    /* storage unavailable */
  }
  const d = new Date();
  d.setFullYear(d.getFullYear() - 3);
  return d.toISOString().slice(0, 10);
}

export default function SincePage() {
  const [since, setSince] = useState(defaultSince);
  const changes = useApi(() => api.changes({ date_from: since }), since);

  const update = (value: string) => {
    setSince(value);
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch {
      /* storage unavailable */
    }
  };

  const groups = new Map<string, Change[]>();
  for (const c of changes.data ?? []) {
    groups.set(c.instrument, [...(groups.get(c.instrument) ?? []), c]);
  }

  return (
    <>
      <h1>Since I last looked</h1>
      <Card>
        <label className="field" htmlFor="since">
          Show changes in versions dated on or after
        </label>
        <input
          id="since"
          type="date"
          value={since}
          max={new Date().toISOString().slice(0, 10)}
          onChange={(e) => e.target.value && update(e.target.value)}
          style={{ maxWidth: 220 }}
        />
        <p className="muted small">Your date is remembered in this browser.</p>
      </Card>
      {changes.error && <ErrorMessage error={changes.error} />}
      {changes.loading && <Loading />}
      {changes.data && changes.data.length === 0 && (
        <div className="banner">No changes since {since}.</div>
      )}
      {changes.data && changes.data.length > 0 && (
        <p className="muted small">
          {changes.data.length} changes since {since}. Summaries are <AiBadge />
        </p>
      )}
      {[...groups.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([instrument, items]) => (
          <Card key={instrument}>
            <details open={(changes.data?.length ?? 0) <= 20}>
              <summary>
                <strong>{instrument}</strong> ({items.length} changes)
              </summary>
              <ul style={{ paddingLeft: "1.1rem" }}>
                {items.map((c) => (
                  <li key={c.change_id} style={{ margin: "0.6rem 0" }}>
                    <Link to={`/changes/${c.change_id}`}>
                      {c.section_key}
                      {c.heading ? ` ${c.heading}` : ""}
                    </Link>{" "}
                    <span className="badge">{c.change_type}</span>
                    <ImpactBadge impact={c.impact} />
                    <div className="muted small">{c.summary ?? "No AI summary yet."}</div>
                  </li>
                ))}
              </ul>
            </details>
          </Card>
        ))}
    </>
  );
}
