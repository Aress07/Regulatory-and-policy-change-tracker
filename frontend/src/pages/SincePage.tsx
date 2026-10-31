import { useState } from "react";
import { api, useApi } from "../api";
import { AiBadge, Card, ChangeListItem, ErrorMessage, Icon, Loading, PageHeader } from "../components/ui";
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
      <PageHeader
        eyebrow="Monitor"
        title="Since I last looked"
        lede="Pick the date you last checked; changes in later versions are grouped by instrument."
      />
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
        <p className="muted small" style={{ marginBottom: 0 }}>
          Your date is remembered in this browser.
        </p>
      </Card>
      {changes.error && <ErrorMessage error={changes.error} />}
      {changes.loading && <Loading />}
      {changes.data && changes.data.length === 0 && (
        <div className="banner">
          <Icon name="check" />
          No changes since {since}.
        </div>
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
                <strong style={{ color: "var(--text)", fontSize: "0.95rem" }}>{instrument}</strong>{" "}
                <span className="badge">{items.length} changes</span>
              </summary>
              <ul className="change-list">
                {items.map((c) => (
                  <ChangeListItem key={c.change_id} change={c} showInstrument={false} />
                ))}
              </ul>
            </details>
          </Card>
        ))}
    </>
  );
}
