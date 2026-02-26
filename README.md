# Local AI Agent Infrastructure — Case Study

A production AI agent system built on consumer/prosumer hardware, running fully local LLM inference. Zero cloud API costs. Responds to natural language over Telegram with multi-model routing, tool use, and a connected knowledge base.

---

> **Public-safety note:** This repository is a sanitized case study and template. It intentionally omits real endpoints, secrets, and full working configs. A private, complete implementation can be shared upon request.

## What This Is

A personal AI agent ("Jarvis") that:
- Runs entirely on-premise — no OpenAI, no Anthropic, no external inference
- Routes requests to the right model based on complexity (6-tier routing matrix)
- Uses tools: web fetch, shell execution, memory read/write, knowledge base search
- Integrates with an external knowledge base via MCP (Model Context Protocol) over SSE
- Is accessible 24/7 via Telegram on any device

---

## Hardware

| Role | Machine | CPU | RAM | Notes |
|------|---------|-----|-----|-------|
| Primary inference | Ubuntu PC | Intel i7-6700 (Skylake, AVX2+FMA) | 16 GB DDR4 | ~25 GB/s memory bandwidth |
| Heavy reasoning | Xeon workstation | 2× Intel X5670 (Westmere, SSE4.2) | 64 GB DDR3 | 24 threads, numactl interleave |
| Dev / orchestration | MacBook Air | M-series | — | Source of truth, never runs inference |

All inference is CPU-only. Token generation speed is DRAM bandwidth-bound — hardware ceiling, not a software problem.

---

## Model Stack (Ollama)

| Tier | Model | Host | Speed | Use case |
|------|-------|------|-------|----------|
| 0 | qwen3:0.6b | PC | ~28 tok/s | Simple greetings, fast ack |
| 1 | qwen3:4b | PC | ~13 tok/s | Standard queries, tool calls |
| 2 | qwen2.5:7b | PC | ~5.5 tok/s | Heavy tool use, multi-step |
| 3 | qwen3:14b | Xeon | ~2.5 tok/s | Deep reasoning |
| 4 | deepseek-r1:7b | Xeon | ~2.9 tok/s | Chain-of-thought reasoning |
| 5 | deepseek-r1:14b | Xeon | ~1.4 tok/s | Max reasoning, fallback |

`OLLAMA_MAX_LOADED_MODELS=3` keeps top 3 PC models resident simultaneously — no model swap penalty on consecutive messages.

---

## Architecture Overview

```
User (Telegram) ──▶ grammY Bot ──▶ Agent Loop
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼             ▼
                    Classifier    Tool Registry   Router
                    (3 tiers)     (5 tools)    (PC / Xeon)
                          │
                    ┌─────┴──────┐
                    ▼            ▼
               PC Ollama    Xeon Ollama
               (fast)       (deep)
```

See [`diagrams/architecture.mmd`](diagrams/architecture.mmd) for the full Mermaid diagram.

---

## Key Engineering Decisions

### 1. Complexity-tiered routing
One flat model would either be too slow for simple messages or too weak for complex ones. A 3-stage classifier (`SIMPLE_RE → REASONING_RE → default`) picks the right tier without a round-trip.

### 2. Tool call gating
Small models (≤4B) hallucinate tool calls when given the full schema unnecessarily. A `TOOL_RE` regex gates whether tools are passed at all — not whether the model decides to use them.

### 3. MCP over SSE (not EventSource)
The MCP server uses SSE + custom `Authorization` headers. The browser `EventSource` API doesn't forward custom headers. The npm `eventsource` package silently ignores the `headers` option despite TypeScript accepting it. Solution: native `fetch()` with `ReadableStream` and a hand-written SSE parser.

### 4. Fresh session per search
Long-lived SSE connections hit server idle timeout. Opening a fresh session per knowledge base query eliminates this class of bug entirely.

### 5. Single source of truth for model config
`src/config/models.ts` defines every model with `warmOnStartup` and `keepWarm` flags. The router, heartbeat cron, startup validator, and system prompt builder all derive from this one file — no drift.

---

## Tools Available to Agent

| Tool | What it does |
|------|-------------|
| `web_fetch` | Fetches and extracts text from any URL |
| `shell_run` | Runs shell commands on the host (sandboxed to allowlist) |
| `memory_read` | Reads from daily markdown memory files |
| `memory_write` | Appends to daily memory file |
| `search_knowledge_base` | Semantic search against MCP knowledge base (SSE/JSON-RPC) |

---

## Project Structure

```
src/
  config/
    models.ts          # Model definitions + routing flags
    validate.ts        # Startup validator — fail fast on misconfiguration
  core/
    agent.ts           # Agent loop: classify → route → tool chain → respond
    router.ts          # PC vs Xeon routing logic
    context.ts         # System prompt builder with dynamic runtime block
    types.ts           # Shared TypeScript types
  providers/
    ollama.ts          # Ollama provider: per-model host, warmModel(), health cache
  interfaces/
    telegram.ts        # grammY bot: typing indicator, /status /clear /model
    twilio.ts          # SMS interface (wired, not yet active)
  tools/
    web-fetch.ts
    shell-run.ts
    memory.ts
    mcp-client.ts      # MCP SSE client (fetch + ReadableStream)
    registry.ts        # Tool registry and executor
  cron/
    jobs/heartbeat.ts  # Keep-alive pings derived from models.ts keepWarm flags
workspace/
  SOUL.md              # Agent personality and operating rules
scripts/
  kb-digest.py         # Knowledge base topic digest → Telegram
```

---

## Deployment

Docker Compose on Ubuntu PC. `network_mode: host` gives zero-hop access to Ollama (no port forwarding, no NAT overhead). Single `npm run build && docker compose up -d --build` deploy cycle.

See [`docs/deployment.md`](docs/deployment.md) for the full workflow.

---

## What I Learned

- **Token generation speed is physics, not software.** Every optimization attempt confirmed the same ceiling: DRAM bandwidth / model weight size = tok/s. The only real lever is model choice.
- **Small models fail at tool schemas differently than large models.** You can't just give them the same system prompt and expect the same behavior.
- **SSE is underspecified enough that every client implementation has edge cases.** Tested npm `eventsource`, Python `requests`, and native `fetch` — each had a different failure mode.
- **Personality prompts compound.** One sentence in a system prompt ("monitor the SEC pipeline") overrides hundreds of lines of other instructions at inference time.

---

## Status

Working in daily use. Ongoing improvements to knowledge base integration, response latency, and proactive outreach scheduling.
