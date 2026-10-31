import { Link, useParams } from "react-router-dom";
import { ApiError, api, useApi } from "../api";
import {
  AiBadge,
  Card,
  ChangeTypeBadge,
  ErrorMessage,
  Icon,
  ImpactBadge,
  Loading,
  SyntheticBadge,
  formatDate,
  sectionLabel,
} from "../components/ui";

const label = (values: string[] | null) =>
  values && values.length ? values.map((v) => v.replace(/_/g, " ")) : [];

export default function ChangeDetailPage() {
  const { changeId = "" } = useParams();
  const change = useApi(() => api.change(changeId), changeId);

  if (change.error) {
    if (change.error instanceof ApiError && change.error.status === 404) {
      return (
        <div className="banner warn">
          <Icon name="warning" />
          <span>
            This change no longer exists. <Link to="/changes">Back to the timeline</Link>
          </span>
        </div>
      );
    }
    return <ErrorMessage error={change.error} />;
  }
  if (!change.data) return <Loading />;
  const c = change.data;

  return (
    <>
      <Link to="/changes" className="back-link">
        <Icon name="back" size={15} /> Change timeline
      </Link>

      <header className="detail-head">
        <p className="eyebrow">{c.instrument}</p>
        <h1>
          {sectionLabel(c.section_key)}
          {c.heading && <span className="heading"> · {c.heading}</span>}
        </h1>
        <div className="badges">
          <ChangeTypeBadge type={c.change_type} />
          <ImpactBadge impact={c.impact} />
          {c.is_synthetic && <SyntheticBadge />}
          {c.similarity !== null && <span className="badge">word similarity {c.similarity.toFixed(2)}</span>}
        </div>
        <div className="version-path">
          <span className="version-chip">
            <small>From</small>
            <b>{formatDate(c.from_date)}</b>
          </span>
          <Icon name="arrow" size={16} />
          <span className="version-chip">
            <small>To</small>
            <b>{formatDate(c.to_date)}</b>
          </span>
          <a className="button" href={c.source_url} target="_blank" rel="noreferrer" style={{ marginLeft: "auto" }}>
            Official text on EUR-Lex <Icon name="external" size={15} />
          </a>
        </div>
      </header>

      <Card title="What changed" icon="sparkle" aside={<AiBadge />} className="ai">
        {c.summary ? (
          <>
            <p className="summary-text">{c.summary}</p>
            <dl className="facts">
              <div className="fact">
                <dt>Impact</dt>
                <dd>
                  <ImpactBadge impact={c.impact} />
                  <p className="small" style={{ margin: "0.35rem 0 0", color: "var(--text-2)" }}>
                    {c.impact_rationale}
                  </p>
                </dd>
              </div>
              <div className="fact">
                <dt>Topics</dt>
                <dd>
                  {label(c.topics).map((t) => (
                    <span key={t} className="badge">
                      {t}
                    </span>
                  ))}
                </dd>
              </div>
              <div className="fact">
                <dt>Sectors</dt>
                <dd>
                  {label(c.sectors).map((s) => (
                    <span key={s} className="badge">
                      {s}
                    </span>
                  ))}
                </dd>
              </div>
            </dl>
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
          <div className="banner warn" style={{ marginBottom: 0 }}>
            <Icon name="warning" />
            The AI explanation failed validation for this change; see the diff below.
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            No AI explanation yet. The diff below is complete.
          </p>
        )}
      </Card>

      <Card
        title="Text comparison"
        icon="diff"
        aside={
          <span className="legend">
            <del>removed</del>
            <ins>added</ins>
          </span>
        }
      >
        <p className="muted small" style={{ marginTop: 0 }}>
          Deterministic word-level diff of the normalised text.
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
        <Card title="Before" aside={<span className="muted small">{formatDate(c.from_date)}</span>}>
          <pre className="text">{c.old_text ?? "(not present in the earlier version)"}</pre>
        </Card>
        <Card title="After" aside={<span className="muted small">{formatDate(c.to_date)}</span>}>
          <pre className="text">{c.new_text ?? "(removed in the later version)"}</pre>
        </Card>
      </div>
    </>
  );
}
