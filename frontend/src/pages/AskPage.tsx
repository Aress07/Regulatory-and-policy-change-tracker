import { useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import { AiBadge, Card, Icon, PageHeader } from "../components/ui";
import type { AskResponse } from "../types";

const STATUS_MESSAGE: Record<AskResponse["status"], string> = {
  answered: "",
  not_found: "The retrieved passages do not answer this question.",
  not_enough_evidence: "Not enough evidence in the tracked texts to answer.",
  rejected_invalid_citations:
    "The generated answer was rejected because its citations could not be verified.",
  retrieval_only: "Answer generation is unavailable right now.",
};

const EXAMPLES = [
  "When may cookies be stored on a user's device?",
  "What are the roaming surcharge rules?",
  "What must a qualified trust service provider do?",
];

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    if (!q.trim()) return;
    setBusy(true);
    setError(undefined);
    try {
      setResult(await api.ask(q.trim()));
    } catch (err) {
      setResult(undefined);
      setError(
        err instanceof ApiError && err.status === 429
          ? "Too many questions; please wait a minute."
          : `Something went wrong: ${(err as Error).message}`,
      );
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  return (
    <>
      <PageHeader
        eyebrow="Analyse"
        title="Ask the law"
        lede={
          <>
            Answers are <AiBadge /> from the latest consolidated texts only, and every sentence must
            cite a passage. When the evidence is weak, you get the closest passages instead.
          </>
        }
      />
      <Card>
        <form onSubmit={submit}>
          <label className="field" htmlFor="question">
            Question
          </label>
          <div className="ask-box">
            <input
              id="question"
              type="text"
              maxLength={500}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Within how many hours must a personal data breach be notified?"
            />
            <button className="primary" type="submit" disabled={busy || !question.trim()}>
              {busy ? "Searching…" : "Ask"}
            </button>
          </div>
        </form>
        <div className="examples">
          <span className="muted small">Try:</span>
          {EXAMPLES.map((q) => (
            <button
              key={q}
              type="button"
              className="chip"
              disabled={busy}
              onClick={() => {
                setQuestion(q);
                void ask(q);
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </Card>

      {error && (
        <div className="banner error" role="alert">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}

      {result && result.status === "answered" && result.answer && (
        <Card
          title="Answer"
          icon="sparkle"
          className="ai"
          aside={
            <span>
              <AiBadge />
              <span className="badge">confidence: {result.confidence}</span>
            </span>
          }
        >
          <p className="answer">{result.answer}</p>
          <h2 className="small muted" style={{ marginBottom: "0.4rem" }}>
            Sources
          </h2>
          <ol className="citations">
            {result.citations.map((c) => (
              <li key={c.n} value={c.n}>
                <a href={c.source_url} target="_blank" rel="noreferrer">
                  {c.breadcrumb}
                </a>
              </li>
            ))}
          </ol>
        </Card>
      )}
      {result && result.status !== "answered" && (
        <div className="banner warn" role="status">
          <Icon name="warning" />
          <span>
            {result.note && result.status === "retrieval_only" ? result.note : STATUS_MESSAGE[result.status]}{" "}
            Here are the closest passages.
          </span>
        </div>
      )}
      {result && result.retrieved.length > 0 && (
        <Card>
          <details open={result.status !== "answered"}>
            <summary>Retrieved passages ({result.retrieved.length})</summary>
            {result.retrieved.map((p, i) => (
              <div key={p.section_id + i} className="passage">
                <div className="passage-head">
                  <strong>
                    [{i + 1}] {p.breadcrumb}
                  </strong>
                  <span className="badge">similarity {p.cosine.toFixed(2)}</span>
                </div>
                <pre className="text small">{p.text.split("\n").slice(1).join("\n")}</pre>
              </div>
            ))}
          </details>
        </Card>
      )}
    </>
  );
}
