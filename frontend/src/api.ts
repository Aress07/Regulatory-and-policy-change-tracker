import { useEffect, useState } from "react";
import type {
  AskResponse,
  Change,
  ChangeDetail,
  DocumentInfo,
  LlmUsage,
  Meta,
  Overview,
  Run,
  TopicCount,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export type ChangeQuery = Partial<{
  doc_id: string[];
  topic: string[];
  sector: string[];
  impact: string[];
  change_type: string[];
  date_from: string;
  date_to: string;
  include_synthetic: boolean;
  limit: number;
}>;

export function toSearchParams(query: ChangeQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "" || value === false) continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else params.set(key, String(value));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const api = {
  meta: () => request<Meta>("/meta"),
  overview: () => request<Overview>("/overview"),
  documents: () => request<DocumentInfo[]>("/documents"),
  changes: (query: ChangeQuery = {}) => request<Change[]>(`/changes${toSearchParams(query)}`),
  change: (id: string) => request<ChangeDetail>(`/changes/${encodeURIComponent(id)}`),
  trends: () => request<TopicCount[]>("/trends"),
  runs: (onlyFailed = false) => request<Run[]>(`/runs${onlyFailed ? "?only_failed=true" : ""}`),
  llmUsage: () => request<LlmUsage[]>("/llm-usage"),
  ask: (question: string, docId?: string) =>
    request<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify({ question, doc_id: docId || null }),
    }),
};

export interface Loadable<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
}

/** Fetch on mount and whenever `key` changes; ignores responses that arrive after a newer request. */
export function useApi<T>(load: () => Promise<T>, key: string = ""): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({
    data: undefined,
    error: undefined,
    loading: true,
  });
  useEffect(() => {
    let current = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    load()
      .then((data) => current && setState({ data, error: undefined, loading: false }))
      .catch((error: Error) => current && setState({ data: undefined, error, loading: false }));
    return () => {
      current = false;
    };
  }, [key]);
  return state;
}
