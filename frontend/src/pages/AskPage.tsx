import { useState, type FormEvent } from "react";
import { ApiError, api } from "../api";
import { AiBadge, Card } from "../components/ui";
import type { AskResponse } from "../types";

const STATUS_MESSAGE: Record<AskResponse["status"], string> = {
  answered: "",
  not_found: "The retrieved passages do not answer this question.",
  not_enough_evidence: "Not enough evidence in the tracked texts to answer.",
  rejected_invalid_citations:
    "The generated answer was rejected because its citations could not be verified.",
  retrieval_only: "Answer generation is unavailable right now.",
};

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(undefined);
    try {
      setResult(await api.ask(question.trim()));
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

  return (
    <>
      <h1>Ask</h1>
      <p className="muted">
        Answers are <AiBadge /> from the latest consolidated texts only, and every sentence must
        cite a passage. When the evidence is weak, you get the closest passages instead.
      </p>
      <Card>
        <form onSubmit={submit}>
          <label className="field" htmlFor="question">
            Question
          </label>
          <input
            id="question"
            type="text"
            maxLength={500}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Within how many hours must a personal data breach be notified?"
          />
          <div style={{ marginTop: 10 }}>
            <button className="primary" type="submit" disabled={busy || !question.trim()}>
              {busy ? "Searching…" : "Ask"}
            </button>
          </div>
        </form>
      </Card>

      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}

      {result && result.status === "answered" && result.answer && (
        <Card>
          <p className="answer">{result.answer}</p>
          <p>
            <AiBadge />
            <span className="badge">confidence: {result.confidence}</span>
          </p>
          <ol className="small" style={{ paddingLeft: "1.2rem" }}>
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
        <div className="banner" role="status">
          {result.note && result.status === "retrieval_only" ? result.note : STATUS_MESSAGE[result.status]}{" "}
          Here are the closest passages.
        </div>
      )}
      {result && result.retrieved.length > 0 && (
        <Card>
          <details open={result.status !== "answered"}>
            <summary>Retrieved passages</summary>
            {result.retrieved.map((p, i) => (
              <div key={p.section_id + i} style={{ margin: "0.8rem 0" }}>
                <strong>
                  [{i + 1}] {p.breadcrumb}
                </strong>{" "}
                <span className="badge">similarity {p.cosine.toFixed(2)}</span>
                <pre className="text small">{p.text.split("\n").slice(1).join("\n")}</pre>
              </div>
            ))}
          </details>
        </Card>
      )}
    </>
  );
}
