# Model Routing

## The Problem

A single model is always the wrong choice:
- Small models (0.6B–4B) are fast but weak on complex tasks
- Large models (14B–32B) are capable but 10–20× slower
- Tool call schemas confuse small models when passed unnecessarily

The solution is a 3-stage classifier that routes to the right tier before the first token is generated.

---

## Classifier Logic

```typescript
// Regex-based fast classification — no LLM round-trip
const SIMPLE_RE   = /^(hi|hello|hey|thanks|ok|okay|sure|yes|no|bye)[\s!?.]*$/i;
const REASONING_RE = /\b(analyze|debug|implement|architect|compare|evaluate|design|explain why|root cause)\b/i;
const TOOL_RE     = /\b(search|fetch|find|check|run|test|docker|logs|news|current|latest|look up)\b/i;

function classifyTask(text: string): { tier: Tier; needsTools: boolean } {
  if (SIMPLE_RE.test(text.trim()))   return { tier: "simple",    needsTools: false };
  if (REASONING_RE.test(text))       return { tier: "reasoning", needsTools: TOOL_RE.test(text) };
  return                                    { tier: "standard",  needsTools: TOOL_RE.test(text) };
}
```

Key insight: `needsTools` gates whether the tool schema is passed to the model at all — not whether the model *decides* to use tools. Passing tools to llama3.2 / qwen3:0.6b when not needed causes hallucinated tool calls.

---

## Routing Matrix

| Tier | needsTools | Model | Host | Why |
|------|-----------|-------|------|-----|
| simple | false | qwen3:0.6b | PC | 28 tok/s, greetings don't need power |
| standard | false | qwen3:4b | PC | 13 tok/s, good general reasoning |
| standard | true | qwen3:4b | PC | Best tool-calling at this speed |
| reasoning | false | qwen3:14b | Xeon | Deep thinking, no tool overhead |
| reasoning | true | qwen2.5:7b | PC | Tool-capable, faster than Xeon for tool loops |
| any (PC down) | — | qwen3:4b | Xeon | Last resort fallback |

---

## Model Residency

`OLLAMA_MAX_LOADED_MODELS=3` keeps the top 3 PC models simultaneously resident in RAM:

```
qwen3:0.6b  (0.5 GB)  ─┐
qwen3:4b    (2.3 GB)   ├── always warm, ~3 GB total
qwen2.5:7b  (4.1 GB)  ─┘
```

Total: ~7 GB of 15 GB available RAM. Model swap penalty is eliminated for the common cases.

---

## Heartbeat / Keep-Alive

A cron job pings each model every 20 minutes to prevent Ollama from evicting them from memory. The list of models to keep warm is derived directly from `src/config/models.ts` (the `keepWarm: true` flag) — no separate config to drift.

---

## Why Not a Router Model?

Running a small LLM to classify inputs before routing to another LLM adds latency and another failure surface. Regex classification is deterministic, ~0ms, and handles 95% of cases correctly. The 5% edge cases fall to the `standard` tier by default, which is acceptable.
