import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "../api";
import { AiBadge, Card, ErrorMessage, Loading } from "../components/ui";

const PALETTE = [
  "#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c",
  "#0891b2", "#ca8a04", "#db2777", "#4b5563", "#65a30d",
];

export default function TrendsPage() {
  const trends = useApi(api.trends);
  if (trends.error) return <ErrorMessage error={trends.error} />;
  if (!trends.data) return <Loading />;
  const rows = trends.data;

  if (rows.length === 0) {
    return (
      <>
        <h1>Topic trends</h1>
        <div className="banner">No enriched changes yet. Run `regtracker enrich`.</div>
      </>
    );
  }

  const topics = [...new Set(rows.map((r) => r.topic))].sort();
  const instruments = [...new Set(rows.map((r) => r.instrument))].sort();

  const perYear = new Map<number, Record<string, number>>();
  for (const r of rows) {
    // Zero-fill every topic so stacked bars line up (recharts cannot stack undefined).
    const y = perYear.get(r.year) ?? Object.fromEntries([["year", r.year], ...topics.map((t) => [t, 0])]);
    y[r.topic] = (y[r.topic] ?? 0) + r.changes;
    perYear.set(r.year, y);
  }
  const yearData = [...perYear.values()].sort((a, b) => a.year - b.year);

  const grid = new Map<string, number>();
  for (const r of rows) {
    const k = `${r.instrument}|${r.topic}`;
    grid.set(k, (grid.get(k) ?? 0) + r.changes);
  }
  const max = Math.max(...grid.values());

  return (
    <>
      <h1>Topic trends</h1>
      <p className="muted">
        Topics are assigned by the LLM <AiBadge /> Synthetic test changes are excluded.
      </p>
      <Card title="Changes per topic over time">
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={yearData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="year" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              {topics.map((t, i) => (
                <Bar key={t} dataKey={t} stackId="a" fill={PALETTE[i % PALETTE.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Instrument by topic">
        <div className="table-wrap">
          <div
            className="heatmap"
            role="table"
            aria-label="Changes by instrument and topic"
            style={{ gridTemplateColumns: `minmax(140px, 200px) repeat(${topics.length}, minmax(70px, 1fr))` }}
          >
            <div className="cell head" role="columnheader" />
            {topics.map((t) => (
              <div key={t} className="cell head" role="columnheader" title={t}>
                {t.replace(/_/g, " ")}
              </div>
            ))}
            {instruments.map((ins) => (
              <div key={ins} style={{ display: "contents" }} role="row">
                <div className="cell head" role="rowheader" style={{ textAlign: "left" }}>
                  {ins}
                </div>
                {topics.map((t) => {
                  const n = grid.get(`${ins}|${t}`) ?? 0;
                  const alpha = n ? 0.15 + 0.85 * (n / max) : 0;
                  return (
                    <div
                      key={t}
                      className="cell"
                      role="cell"
                      title={`${ins}, ${t}: ${n}`}
                      style={{
                        background: n ? `rgb(37 99 235 / ${alpha})` : "var(--surface-2)",
                        color: alpha > 0.55 ? "#fff" : "inherit",
                      }}
                    >
                      {n || ""}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </Card>
    </>
  );
}
