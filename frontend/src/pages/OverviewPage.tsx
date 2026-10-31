import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "../api";
import {
  Card,
  ChangeListItem,
  ErrorMessage,
  FreshnessBanner,
  Icon,
  Loading,
  Stars,
  formatDate,
  type IconName,
} from "../components/ui";

const TYPE_COLORS: Record<string, string> = {
  added: "#12b76a",
  modified: "#2e90fa",
  removed: "#f04438",
  renumbered: "#9e77ed",
};

const STEPS: { icon: IconName; title: string; text: string }[] = [
  {
    icon: "diff",
    title: "Detect, deterministically",
    text: "Consecutive consolidated versions are compared article by article. No AI decides what changed.",
  },
  {
    icon: "sparkle",
    title: "Explain with AI",
    text: "A language model summarises each change, tags topics and sectors, and rates its impact.",
  },
  {
    icon: "quote",
    title: "Ask, with citations",
    text: "Questions are answered only from retrieved articles, and every sentence cites its source.",
  },
];

export default function OverviewPage() {
  const overview = useApi(api.overview);
  const docs = useApi(api.documents);
  const recent = useApi(() => api.changes({ impact: ["high"], limit: 5 }));

  if (overview.error) return <ErrorMessage error={overview.error} />;
  if (!overview.data) return <Loading />;
  const o = overview.data;

  // One row per instrument with a column per change type, for a stacked bar chart.
  // Every row needs every type (0 when absent): recharts cannot stack undefined values.
  const types = [...new Set(o.changes_by_instrument_and_type.map((r) => r.change_type))];
  const byInstrument = new Map<string, Record<string, number | string>>();
  for (const r of o.changes_by_instrument_and_type) {
    const row =
      byInstrument.get(r.instrument) ??
      Object.fromEntries([["instrument", r.instrument], ...types.map((t) => [t, 0])]);
    row[r.change_type] = r.changes;
    byInstrument.set(r.instrument, row);
  }
  const chartData = [...byInstrument.values()];
  const enrichedPct = o.changes ? Math.round((100 * o.enriched) / o.changes) : 0;

  return (
    <>
      <section className="hero">
        <Stars className="hero-stars" />
        <h1>Know what changed in EU digital law, and why it matters</h1>
        <p>
          Tracks consolidated versions of EU digital and telecom regulation, pinpoints every changed
          article, and explains it in plain language with a link to the official text.
        </p>
        <div className="hero-actions">
          <Link to="/changes" className="button">
            Browse changes <Icon name="arrow" size={16} />
          </Link>
          <Link to="/ask" className="button ghost">
            Ask a question
          </Link>
        </div>
      </section>

      <FreshnessBanner freshness={o.freshness} />

      <div className="kpis">
        <Kpi icon="layers" label="Instruments tracked" value={o.instruments} />
        <Kpi icon="file" label="Versions parsed" value={o.versions_parsed} />
        <Kpi icon="diff" label="Changes detected" value={o.changes} />
        <Kpi icon="warning" label="High-impact changes" value={o.high_impact} hint="AI-rated" />
        <div className="card kpi">
          <div className="label">
            <Icon name="sparkle" size={15} />
            Changes enriched
          </div>
          <div className="value">{`${o.enriched} / ${o.changes}`}</div>
          <div className="meter" aria-label={`${enrichedPct}% enriched`}>
            <span style={{ width: `${enrichedPct}%` }} />
          </div>
        </div>
      </div>

      <div className="steps">
        {STEPS.map((s) => (
          <div key={s.title} className="card step" style={{ marginBottom: 0 }}>
            <span className="step-icon">
              <Icon name={s.icon} />
            </span>
            <div>
              <strong>{s.title}</strong>
              <p>{s.text}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2">
        <Card
          title="Changes per instrument"
          icon="trends"
          aside={
            o.latest_change_date && (
              <span className="muted small">latest: {formatDate(o.latest_change_date)}</span>
            )
          }
        >
          {chartData.length === 0 ? (
            <p className="empty">No changes detected yet.</p>
          ) : (
            <div style={{ width: "100%", height: 60 + chartData.length * 34 }}>
              <ResponsiveContainer>
                <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border)" />
                  <XAxis type="number" allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 12 }} />
                  <YAxis
                    type="category"
                    dataKey="instrument"
                    width={170}
                    tick={{ fill: "var(--text-2)", fontSize: 12 }}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--surface-2)" }}
                    contentStyle={{
                      background: "var(--surface)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                    }}
                  />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  {types.map((t) => (
                    <Bar key={t} dataKey={t} stackId="a" isAnimationActive={false} fill={TYPE_COLORS[t] ?? "#64748b"} barSize={18} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="muted small" style={{ margin: "0.5rem 0 0" }}>
            EU acts are amended rarely, so most changes are years old.
          </p>
        </Card>

        <Card
          title="High-impact changes"
          icon="warning"
          aside={
            <Link to="/changes?impact=high" className="small">
              View all
            </Link>
          }
        >
          {recent.error && <ErrorMessage error={recent.error} />}
          {!recent.data && !recent.error && <Loading />}
          {recent.data && recent.data.length === 0 && (
            <p className="empty">No changes rated high impact yet.</p>
          )}
          {recent.data && recent.data.length > 0 && (
            <ul className="change-list">
              {recent.data.map((c) => (
                <ChangeListItem key={c.change_id} change={c} />
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Instruments" icon="layers" className="flush">
        {docs.error && <ErrorMessage error={docs.error} />}
        {!docs.data && !docs.error && <Loading />}
        {docs.data && (
          <div className="table-wrap" style={{ marginTop: "0.9rem" }}>
            <table>
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th>CELEX</th>
                  <th className="num">Versions</th>
                  <th>Latest version</th>
                  <th className="num">Changes</th>
                  <th>Status</th>
                  <th>Official text</th>
                </tr>
              </thead>
              <tbody>
                {docs.data.map((d) => (
                  <tr key={d.doc_id}>
                    <td>
                      <div className="cell-title">{d.instrument}</div>
                      <div className="cell-sub">
                        {d.doc_type}
                        {d.title && ` · ${d.title.length > 60 ? `${d.title.slice(0, 60)}…` : d.title}`}
                      </div>
                    </td>
                    <td className="nowrap">
                      <code>{d.celex_base}</code>
                    </td>
                    <td className="num">{d.versions}</td>
                    <td className="nowrap tabular">{formatDate(d.latest_version)}</td>
                    <td className="num">{d.changes}</td>
                    <td>
                      {d.repealed ? (
                        <span className="badge">repealed</span>
                      ) : (
                        <span className="badge ok">in force</span>
                      )}
                    </td>
                    <td className="nowrap">
                      <a href={d.source_url} target="_blank" rel="noreferrer">
                        EUR-Lex <Icon name="external" size={13} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

function Kpi({
  icon,
  label,
  value,
  hint,
}: {
  icon: IconName;
  label: string;
  value: number | string;
  hint?: string;
}) {
  return (
    <div className="card kpi">
      <div className="label">
        <Icon name={icon} size={15} />
        {label}
      </div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}
