import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { toSearchParams } from "../api";
import type { AskResponse, Change, ChangeDetail } from "../types";

const change: Change = {
  change_id: "c1",
  doc_id: "eprivacy",
  instrument: "ePrivacy Directive",
  section_key: "art_5",
  old_section_key: "art_5",
  section_type: "article",
  heading: "Confidentiality of the communications",
  change_type: "modified",
  from_version: "eprivacy@2006-05-03",
  to_version: "eprivacy@2009-12-19",
  from_date: "2006-05-03",
  to_date: "2009-12-19",
  is_synthetic: false,
  source_url: "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02002L0058-20091219",
  summary: "Cookies now require prior consent.",
  topics: ["data_protection"],
  sectors: ["all"],
  impact: "high",
  impact_rationale: "New consent obligation.",
  enrichment_model: "openai/gpt-oss-120b",
  prompt_version: "v1",
  enriched_at: "2026-10-31T12:00:00",
  is_enriched: true,
  enrichment_failed: false,
  similarity: 0.88,
};

const detail: ChangeDetail = {
  ...change,
  old_text: "offered the right to refuse",
  new_text: "has given his or her consent",
  diff_html: "<del>offered the right to refuse</del><ins>has given his or her consent</ins>",
};

const routes: Record<string, unknown> = {
  "/api/meta": {
    topics: ["data_protection", "other"],
    sectors: ["all", "telecom"],
    impacts: ["high", "medium", "low", "unrated"],
    change_types: ["added", "removed", "modified", "renumbered"],
    disclaimer: "Not legal advice.",
    ask_enabled: true,
  },
  "/api/overview": {
    instruments: 14,
    versions_parsed: 24,
    changes: 107,
    high_impact: 12,
    enriched: 82,
    latest_change_date: "2026-07-27",
    changes_by_instrument_and_type: [
      { instrument: "ePrivacy Directive", change_type: "modified", changes: 8 },
    ],
    freshness: { last_successful_ingest: "2026-10-31T10:00:00", days_since_ingest: 0, failures_last_7_days: 0 },
  },
  "/api/documents": [
    {
      doc_id: "eprivacy",
      instrument: "ePrivacy Directive",
      title: "DIRECTIVE 2002/58/EC",
      celex_base: "32002L0058",
      doc_type: "directive",
      versions: 2,
      latest_version: "2009-12-19",
      repealed: false,
      changes: 10,
      source_url: "https://eur-lex.europa.eu/",
    },
  ],
  "/api/changes/c1": detail,
  "/api/trends": [{ instrument: "ePrivacy Directive", year: 2009, topic: "data_protection", changes: 3 }],
  "/api/llm-usage": [],
};

let fetchMock: ReturnType<typeof vi.fn>;
let askResponse: { status: number; body: unknown };

beforeEach(() => {
  askResponse = { status: 200, body: {} };
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const json = (status: number, body: unknown) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (url.pathname === "/api/ask") return json(askResponse.status, askResponse.body);
    if (url.pathname === "/api/changes") return json(200, [change]);
    if (url.pathname === "/api/runs") return json(200, []);
    if (url.pathname in routes) return json(200, routes[url.pathname]);
    return json(404, { detail: "change not found" });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("every page", () => {
  it.each(["/", "/changes", "/changes/c1", "/trends", "/since", "/ask", "/health"])(
    "%s renders with the disclaimer",
    async (path) => {
      renderAt(path);
      expect(screen.getByRole("note")).toHaveTextContent("Not legal advice");
      await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );
});

describe("overview", () => {
  it("shows KPIs", async () => {
    renderAt("/");
    expect(await screen.findByText("107")).toBeInTheDocument();
    expect(screen.getByText("82 / 107")).toBeInTheDocument();
  });
});

describe("change detail", () => {
  it("shows the AI badge, official link and the diff", async () => {
    const { container } = renderAt("/changes/c1");
    expect(await screen.findByText("Cookies now require prior consent.")).toBeInTheDocument();
    expect(screen.getAllByText("AI-generated").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /EUR-Lex/ })).toHaveAttribute("href", change.source_url);
    expect(container.querySelector(".diff del")).toHaveTextContent("offered the right to refuse");
    expect(container.querySelector(".diff ins")).toHaveTextContent("has given his or her consent");
  });

  it("handles a missing change", async () => {
    renderAt("/changes/nope");
    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument();
  });
});

describe("timeline", () => {
  it("sends filters to the API", async () => {
    const user = userEvent.setup();
    renderAt("/changes");
    await user.click(await screen.findByRole("button", { name: "high" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("impact=high"))).toBe(true),
    );
  });
});

describe("ask", () => {
  async function ask(question: string) {
    const user = userEvent.setup();
    renderAt("/ask");
    await user.type(screen.getByLabelText("Question"), question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
  }

  it("renders an answer with citation links", async () => {
    const body: AskResponse = {
      status: "answered",
      answer: "Consent is required [1].",
      citations: [{ n: 1, section_id: "s", breadcrumb: "ePrivacy > Article 5", source_url: "https://x" }],
      confidence: "high",
      retrieved: [{ section_id: "s", breadcrumb: "ePrivacy > Article 5", text: "crumb\ntext", score: 1, cosine: 0.9 }],
      note: null,
      disclaimer: "Not legal advice.",
    };
    askResponse = { status: 200, body };
    await ask("Do cookies need consent?");
    expect(await screen.findByText("Consent is required [1].")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ePrivacy > Article 5" })).toHaveAttribute("href", "https://x");
  });

  it("explains refusals and shows passages", async () => {
    askResponse = {
      status: 200,
      body: { status: "not_enough_evidence", answer: null, citations: [], confidence: "none", retrieved: [], note: null, disclaimer: "" },
    };
    await ask("How do I bake bread?");
    expect(await screen.findByText(/Not enough evidence/)).toBeInTheDocument();
  });

  it("reports rate limiting", async () => {
    askResponse = { status: 429, body: { detail: "too many questions" } };
    await ask("Anything?");
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many questions");
  });
});

describe("toSearchParams", () => {
  it("repeats list values and drops empty ones", () => {
    expect(toSearchParams({ impact: ["high", "low"], topic: [], date_from: "", include_synthetic: false })).toBe(
      "?impact=high&impact=low",
    );
    expect(toSearchParams({})).toBe("");
  });
});
