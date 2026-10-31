import { useState } from "react";
import { api, useApi } from "../api";
import { Card, ErrorMessage, FreshnessBanner, Loading } from "../components/ui";

export default function HealthPage() {
  const [onlyFailed, setOnlyFailed] = useState(false);
  const overview = useApi(api.overview);
  const usage = useApi(api.llmUsage);
  const runs = useApi(() => api.runs(onlyFailed), String(onlyFailed));

  return (
    <>
      <h1>Pipeline health</h1>
      {overview.data && <FreshnessBanner freshness={overview.data.freshness} />}
      {overview.data && (
        <div className="kpis">
          <div className="card kpi" style={{ marginBottom: 0 }}>
            <div className="label">Failures (last 7 days)</div>
            <div className="value">{overview.data.freshness.failures_last_7_days}</div>
          </div>
        </div>
      )}

      <Card title="LLM usage and shadow cost">
        <p className="muted small">
          Shadow cost = tokens priced at public list prices (configs/llm.yml). The free tier
          actually costs $0.
        </p>
        {usage.error && <ErrorMessage error={usage.error} />}
        {!usage.data && !usage.error && <Loading />}
        {usage.data && usage.data.length === 0 && <p className="muted">No enrichment runs yet.</p>}
        {usage.data && usage.data.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Prompt</th>
                  <th>Succeeded</th>
                  <th>Failed</th>
                  <th>Tokens / change</th>
                  <th>Median latency</th>
                  <th>Shadow cost</th>
                  <th>Per 1,000 changes</th>
                </tr>
              </thead>
              <tbody>
                {usage.data.map((u) => (
                  <tr key={u.model + u.prompt_version}>
                    <td>{u.model}</td>
                    <td>{u.prompt_version}</td>
                    <td>{u.succeeded}</td>
                    <td>{u.failed}</td>
                    <td>{u.tokens_per_change ?? "–"}</td>
                    <td>{u.median_latency_ms !== null ? `${u.median_latency_ms} ms` : "–"}</td>
                    <td>{u.shadow_cost_usd !== null ? `$${u.shadow_cost_usd}` : "–"}</td>
                    <td>
                      {u.shadow_cost_per_1000_changes !== null
                        ? `$${u.shadow_cost_per_1000_changes}`
                        : "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Recent stage runs">
        <label className="small">
          <input
            type="checkbox"
            checked={onlyFailed}
            onChange={(e) => setOnlyFailed(e.target.checked)}
          />{" "}
          Failures only
        </label>
        {runs.error && <ErrorMessage error={runs.error} />}
        {runs.loading && <Loading />}
        {runs.data && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Stage</th>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Seconds</th>
                  <th>In</th>
                  <th>Out</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r, i) => (
                  <tr key={r.run_id + i}>
                    <td>{r.started_at?.replace("T", " ").slice(0, 16)}</td>
                    <td>{r.stage}</td>
                    <td>{r.subject}</td>
                    <td>
                      <span className={`badge ${r.status === "failed" ? "high" : ""}`}>
                        {r.status}
                      </span>
                    </td>
                    <td>{r.seconds?.toFixed(1)}</td>
                    <td>{r.rows_in}</td>
                    <td>{r.rows_out}</td>
                    <td className="small">{r.error}</td>
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
