import { Link, useParams } from "react-router-dom";
import { ApiError, api, useApi } from "../api";
import {
  AiBadge,
  Card,
  ErrorMessage,
  ImpactBadge,
  Loading,
  SyntheticBadge,
  formatDate,
} from "../components/ui";

export default function ChangeDetailPage() {
  const { changeId = "" } = useParams();
  const change = useApi(() => api.change(changeId), changeId);

  if (change.error) {
    if (change.error instanceof ApiError && change.error.status === 404) {
      return (
        <div className="banner warn">
          This change no longer exists. <Link to="/changes">Back to the timeline</Link>
        </div>
      );
    }
    return <ErrorMessage error={change.error} />;
  }
  if (!change.data) return <Loading />;
  const c = change.data;

  return (
    <>
      <p className="small">
        <Link to="/changes">← Change timeline</Link>
      </p>
      <h1>
        {c.instrument} · {c.section_key}
        {c.heading && <span className="muted"> · {c.heading}</span>}
      </h1>
      <p>
        <span className="badge">{c.change_type}</span>
        <ImpactBadge impact={c.impact} />
        {c.is_synthetic && <SyntheticBadge />}
      </p>
      <p className="muted small">
        From {c.from_version} ({formatDate(c.from_date)}) to {c.to_version} (
        {formatDate(c.to_date)})
        {c.similarity !== null && ` · word similarity ${c.similarity.toFixed(2)}`}
      </p>
      <p>
        <a className="button" href={c.source_url} target="_blank" rel="noreferrer">
          Official consolidated text on EUR-Lex ↗
        </a>
      </p>

      <Card>
        <h2>
          What changed <AiBadge />
        </h2>
        {c.summary ? (
          <>
            <p>{c.summary}</p>
            <p>
              <strong>Impact:</strong> <ImpactBadge impact={c.impact} />
              <br />
              {c.impact_rationale}
            </p>
            <p className="small">
              <strong>Topics:</strong> {(c.topics ?? []).join(", ").replace(/_/g, " ")}
              <br />
              <strong>Sectors:</strong> {(c.sectors ?? []).join(", ").replace(/_/g, " ")}
            </p>
            <details>
              <summary>How was this generated?</summary>
              <ul className="small">
                <li>The change itself was found by a deterministic text diff, not by AI.</li>
                <li>
                  The explanation was written by <code>{c.enrichment_model}</code> with prompt{" "}
                  <code>{c.prompt_version}</code> on {formatDate(c.enriched_at)}, from the old
                  and new text only.
                </li>
                <li>It can be wrong or incomplete. The official text is authoritative.</li>
              </ul>
            </details>
          </>
        ) : c.enrichment_failed ? (
          <div className="banner warn">
            The AI explanation failed validation for this change; see the diff below.
          </div>
        ) : (
          <p className="muted">No AI explanation yet. The diff below is complete.</p>
        )}
      </Card>

      <Card title="Text comparison">
        <p className="muted small">
          Deterministic word-level diff: removed words struck through, added words highlighted.
        </p>
        {c.diff_html ? (
          // diff_html is generated server-side by regtracker.diff: all source text is
          // HTML-escaped and the only tags are <del> and <ins>.
          <div className="diff" dangerouslySetInnerHTML={{ __html: c.diff_html }} />
        ) : (
          <p className="muted">
            {c.change_type === "added" ? "New section; see the text below." : "Section removed."}
          </p>
        )}
      </Card>

      <div className="side-by-side">
        <Card title="Before">
          <pre className="text">{c.old_text ?? "(not present in the earlier version)"}</pre>
        </Card>
        <Card title="After">
          <pre className="text">{c.new_text ?? "(removed in the later version)"}</pre>
        </Card>
      </div>
    </>
  );
}
