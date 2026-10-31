import { useNavigate, useSearchParams } from "react-router-dom";
import { api, useApi, type ChangeQuery } from "../api";
import {
  Card,
  ChangeTypeBadge,
  ChipGroup,
  ErrorMessage,
  Icon,
  ImpactBadge,
  Loading,
  PageHeader,
  SyntheticBadge,
  formatDate,
  sectionLabel,
} from "../components/ui";

// Filters live in the URL so a filtered view can be bookmarked and shared.
const LIST_KEYS = ["doc_id", "topic", "sector", "impact", "change_type"] as const;

export default function TimelinePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const meta = useApi(api.meta);
  const docs = useApi(api.documents);

  const query: ChangeQuery = {
    doc_id: params.getAll("doc_id"),
    topic: params.getAll("topic"),
    sector: params.getAll("sector"),
    impact: params.getAll("impact"),
    change_type: params.getAll("change_type"),
    date_from: params.get("date_from") ?? undefined,
    date_to: params.get("date_to") ?? undefined,
    include_synthetic: params.get("include_synthetic") === "true",
  };
  const changes = useApi(() => api.changes(query), params.toString());
  const active = [...params.keys()].length;

  const setList = (key: (typeof LIST_KEYS)[number], values: string[]) => {
    const next = new URLSearchParams(params);
    next.delete(key);
    values.forEach((v) => next.append(key, v));
    setParams(next, { replace: true });
  };
  const setValue = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  const open = (id: string) => navigate(`/changes/${id}`);

  return (
    <>
      <PageHeader
        eyebrow="Monitor"
        title="Change timeline"
        lede="Every article-level change between consecutive consolidated versions, newest first. Filters are kept in the URL, so a view can be bookmarked."
      />

      <Card>
        <details open className="filter-panel">
          <summary>
            <Icon name="filter" size={16} /> Filters
            {active > 0 && <span className="badge low">{active} active</span>}
          </summary>
          <div className="filters">
            <div style={{ display: "grid", gap: "0.9rem", alignContent: "start" }}>
              <label className="field">
                Instrument
                <select
                  multiple
                  size={5}
                  value={query.doc_id}
                  onChange={(e) =>
                    setList(
                      "doc_id",
                      [...e.target.selectedOptions].map((o) => o.value),
                    )
                  }
                >
                  {docs.data
                    ?.filter((d) => d.changes > 0)
                    .map((d) => (
                      <option key={d.doc_id} value={d.doc_id}>
                        {d.instrument} ({d.changes})
                      </option>
                    ))}
                </select>
              </label>
              <div style={{ display: "grid", gap: "0.6rem", alignContent: "start" }}>
                <div>
                  <label className="field" htmlFor="from">
                    Version date from
                  </label>
                  <input
                    id="from"
                    type="date"
                    value={query.date_from ?? ""}
                    onChange={(e) => setValue("date_from", e.target.value)}
                  />
                </div>
                <div>
                  <label className="field" htmlFor="to">
                    Version date to
                  </label>
                  <input
                    id="to"
                    type="date"
                    value={query.date_to ?? ""}
                    onChange={(e) => setValue("date_to", e.target.value)}
                  />
                </div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={query.include_synthetic}
                    onChange={(e) => setValue("include_synthetic", e.target.checked ? "true" : "")}
                  />
                  Include synthetic test changes
                </label>
                {active > 0 && (
                  <button
                    type="button"
                    className="link"
                    style={{ justifySelf: "start" }}
                    onClick={() => setParams(new URLSearchParams(), { replace: true })}
                  >
                    Clear all filters
                  </button>
                )}
              </div>
            </div>
            {meta.data && (
              <>
                <div style={{ display: "grid", gap: "1rem" }}>
                  <ChipGroup
                    legend="Impact (AI-generated)"
                    options={meta.data.impacts}
                    selected={query.impact ?? []}
                    onChange={(v) => setList("impact", v)}
                  />
                  <ChipGroup
                    legend="Change type"
                    options={meta.data.change_types}
                    selected={query.change_type ?? []}
                    onChange={(v) => setList("change_type", v)}
                  />
                </div>
                <ChipGroup
                  legend="Topic (AI-generated)"
                  options={meta.data.topics}
                  selected={query.topic ?? []}
                  onChange={(v) => setList("topic", v)}
                />
                <ChipGroup
                  legend="Sector (AI-generated)"
                  options={meta.data.sectors}
                  selected={query.sector ?? []}
                  onChange={(v) => setList("sector", v)}
                />
              </>
            )}
          </div>
        </details>
      </Card>

      {changes.error && <ErrorMessage error={changes.error} />}
      {changes.loading && !changes.data && <Loading what="Loading changes" />}
      {changes.data && (
        <Card
          className="flush"
          title={`${changes.data.length} changes`}
          aside={<span className="muted small">Select a row to open its detail</span>}
        >
          {changes.data.length === 0 ? (
            <p className="empty">No changes match these filters.</p>
          ) : (
            <div className="table-wrap" style={{ marginTop: "0.9rem" }}>
              <table>
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Section</th>
                    <th>Type</th>
                    <th>Impact (AI)</th>
                    <th>Summary (AI-generated)</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.data.map((c) => (
                    <tr
                      key={c.change_id}
                      className="clickable"
                      tabIndex={0}
                      onClick={() => open(c.change_id)}
                      onKeyDown={(e) => e.key === "Enter" && open(c.change_id)}
                    >
                      <td className="nowrap tabular">{formatDate(c.to_date)}</td>
                      <td>
                        <div className="cell-title">
                          {c.instrument} · {sectionLabel(c.section_key)}
                        </div>
                        {c.heading && <div className="cell-sub">{c.heading}</div>}
                      </td>
                      <td>
                        <ChangeTypeBadge type={c.change_type} />
                      </td>
                      <td>
                        <ImpactBadge impact={c.impact} />
                      </td>
                      <td className="summary-cell">
                        {c.is_synthetic && <SyntheticBadge />}
                        {c.summary ?? <span className="muted">No AI summary yet</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
