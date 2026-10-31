import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, useApi } from "../api";
import { Card, ErrorMessage, FreshnessBanner, Loading, formatDate } from "../components/ui";

const TYPE_COLORS: Record<string, string> = {
  added: "#16a34a",
  modified: "#2563eb",
  removed: "#dc2626",
  renumbered: "#9333ea",
};

export default function OverviewPage() {
  const overview = useApi(api.overview);
  const docs = useApi(api.documents);

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

  return (
    <>
      <h1>Overview</h1>
      <FreshnessBanner freshness={o.freshness} />
      <div className="kpis">
        <Kpi label="Instruments tracked" value={o.instruments} />
        <Kpi label="Versions parsed" value={o.versions_parsed} />
        <Kpi label="Changes detected" value={o.changes} />
        <Kpi label="High-impact changes" value={o.high_impact} />
        <Kpi label="Changes enriched" value={`${o.enriched} / ${o.changes}`} />
      </div>
      {o.latest_change_date && (
        <p className="muted small">
          EU acts are amended rarely; the most recent consolidated change in this corpus is from{" "}
          {formatDate(o.latest_change_date)}.
        </p>
      )}

      <Card title="Changes per instrument">
        {chartData.length === 0 ? (
          <p className="muted">No changes detected yet.</p>
        ) : (
          <div style={{ width: "100%", height: 40 + chartData.length * 36 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="instrument" width={180} />
                <Tooltip />
                <Legend />
                {types.map((t) => (
                  <Bar key={t} dataKey={t} stackId="a" fill={TYPE_COLORS[t] ?? "#64748b"} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card title="Instruments">
        {docs.error && <ErrorMessage error={docs.error} />}
        {!docs.data && !docs.error && <Loading />}
        {docs.data && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th>Type</th>
                  <th>CELEX</th>
                  <th>Versions</th>
                  <th>Latest version</th>
                  <th>Changes</th>
                  <th>Status</th>
                  <th>Official text</th>
                </tr>
              </thead>
              <tbody>
                {docs.data.map((d) => (
                  <tr key={d.doc_id}>
                    <td title={d.title ?? undefined}>{d.instrument}</td>
                    <td>{d.doc_type}</td>
                    <td>{d.celex_base}</td>
                    <td>{d.versions}</td>
                    <td>{formatDate(d.latest_version)}</td>
                    <td>{d.changes}</td>
                    <td>{d.repealed ? <span className="badge">repealed</span> : "in force"}</td>
                    <td>
                      <a href={d.source_url} target="_blank" rel="noreferrer">
                        EUR-Lex
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

function Kpi({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card kpi" style={{ marginBottom: 0 }}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
