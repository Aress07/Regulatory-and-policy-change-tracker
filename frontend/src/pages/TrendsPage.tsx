import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "../api";
import { AiBadge, Card, ErrorMessage, Loading, PageHeader } from "../components/ui";

const PALETTE = [
  "#2e90fa", "#12b76a", "#f04438", "#9e77ed", "#f79009",
  "#06aed4", "#eaaa08", "#ee46bc", "#667085", "#66c61c",
];

export default function TrendsPage() {
  const trends = useApi(api.trends);
  if (trends.error) return <ErrorMessage error={trends.error} />;
  if (!trends.data) return <Loading />;
  const rows = trends.data;

  if (rows.length === 0) {
    return (
      <>
        <PageHeader eyebrow="Analyse" title="Topic trends" />
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
      <PageHeader
        eyebrow="Analyse"
        title="Topic trends"
        lede={
          <>
            Which areas of digital law are moving. Topics are assigned by the LLM <AiBadge />{" "}
            Synthetic test changes are excluded.
          </>
        }
      />
      <Card title="Changes per topic over time" icon="trends">
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={yearData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
              <XAxis dataKey="year" tick={{ fill: "var(--muted)", fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 12 }} />
              <Tooltip
                cursor={{ fill: "var(--surface-2)" }}
                contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }}
              />
              <Legend
                iconType="circle"
                wrapperStyle={{ fontSize: 12 }}
                formatter={(v: string) => v.replace(/_/g, " ")}
              />
              {topics.map((t, i) => (
                <Bar key={t} dataKey={t} stackId="a" fill={PALETTE[i % PALETTE.length]} maxBarSize={48} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Instrument by topic" icon="layers">
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
                        background: n ? `rgb(46 144 250 / ${alpha})` : "var(--surface-2)",
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
