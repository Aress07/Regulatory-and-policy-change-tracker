---
name: regtracker-enrichment-groq
description: How to build the LLM enrichment layer of the EU Regulation Change Tracker using the Groq API (OpenAI-compatible) with local Ollama for development. Use this skill whenever working on the LLM client, prompts, Pydantic output schemas, summaries, topic, sector, or impact classification, rate limiting, token budgets, caching, model routing, shadow cost, or batch enrichment jobs, or when the user mentions Groq, Ollama, 429 errors, or free-tier limits.
---

# Enrichment with Groq

Follow `regtracker-conventions`. The LLM explains changes the diff already found; it never decides what changed.

## Client
- Use the `openai` SDK with `base_url=https://api.groq.com/openai/v1` and `api_key` from the environment (`LLM_API_KEY`). Ollama uses `http://localhost:11434/v1` through the same code path; switch by env vars only.
- Never print, log, commit, or paste the key. If a key appears in chat or a file, tell the user to rotate it.
- Model names come from config (`LLM_MODEL_CLASSIFY`, `LLM_MODEL_SUMMARY`), never hardcoded. Groq retires models; check the current console model list.
- `temperature=0`. Timeouts on every call.

## Free-tier discipline
- Limits are per model and per organization and change; read the console limits page. Token limits (per minute and per day) usually bind before request limits.
- Implement a token-aware throttle (rolling 60 s window, `LLM_TPM` set a little under the real limit) and a daily budget (`LLM_DAILY_TOKEN_BUDGET`). On 429, back off with `tenacity` and honor `retry-after` if present.
- The batch job must be **resumable**: process unenriched changes, stop cleanly near the daily budget, continue next run.
- Cache on disk keyed by `(model, prompt_version, input_hash)`; reruns must make zero LLM calls.
- Develop prompts against Ollama; use Groq for official runs and evaluation experiments to save quota.

## Output contract
Validate with Pydantic; request JSON (JSON mode, or JSON schema where the chosen model supports it; check the docs). On validation failure retry once including the error message, then store an explicit failure row. Never silently drop.

```python
class ChangeAnalysis(BaseModel):
    summary: str = Field(max_length=500)  # plain language, 1-3 sentences
    topics: list[Topic] = Field(min_length=1, max_length=3)
    sectors: list[Sector] = Field(min_length=1, max_length=3)
    impact: Literal["low", "medium", "high"]
    impact_rationale: str = Field(max_length=300)
```

## Prompt rules (version in `src/regtracker/enrich/prompts/vN.md`)
- Input: instrument, article title, `old_text`, `new_text` (changed passages only, to save tokens).
- Describe only what the text shows; no speculation, no legal advice.
- Explicit impact scale: low = wording/clarification; medium = obligation or scope change for some actors; high = new or removed obligations, penalties, or deadlines affecting many actors.
- Few-shot examples come from labeled data and must be excluded from the eval set.
- Bump `prompt_version` on any prompt change.

## Record per enrichment
model, prompt_version, tokens_in/out, latency_ms, `shadow_cost_usd` (computed from public per-token prices of reference models), created_at.

## Tests
Unit tests use a mock LLM returning canned JSON. Test: schema validation failure path, cache hit makes no call, budget stop, throttle behavior with a fake clock.
