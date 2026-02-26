# Lessons Learned

A running log of non-obvious decisions and the failures that led to them.

---

## SSE: Three Clients, Three Failure Modes

Building the MCP knowledge base integration required three complete rewrites of the SSE client.

**Browser EventSource:** Doesn't support custom headers. The `Authorization` header can't be sent — the connection is anonymous. Not usable for authenticated SSE.

**npm `eventsource` package:** The TypeScript types accept a `headers` option and it compiles without error with `as any`. At runtime, the headers are silently ignored. The connection is made without authorization. This cost significant debugging time because the failure mode was silent — no error, just unauthenticated responses.

**Native `fetch` + `ReadableStream`:** Works correctly. Headers are sent. The trade-off is writing a manual SSE line parser, which is ~30 lines of straightforward code.

Lesson: for anything involving custom HTTP headers and streaming, native `fetch` is the only reliable option in Node.js.

---

## Small Models and Tool Schemas

A tool call schema adds ~200–400 tokens to the system prompt. For a 4B model with a 4096-token context, that's a non-trivial fraction of the context window.

More importantly: passing a tool schema to a model that doesn't need to use tools causes it to hallucinate tool calls for queries that should be answered directly. "Hi" becomes a tool call. "Thanks" triggers a memory search.

The fix is a `needsTools` gate in the classifier — if the query doesn't contain tool-relevant keywords, the schema isn't passed at all. The model can't call tools it doesn't know exist.

This is not a model quality issue. It's an inference behavior that appears even in larger models when the schema is passed unnecessarily.

---

## Personality Prompts Are Powerful

The agent's `SOUL.md` personality file contained this line in an early version:

> *Monitor the SEC data pipeline and report on filing activity.*

This one sentence caused the agent to open every conversation by asking about the SEC pipeline — regardless of what the user actually sent. It overrode hundreds of lines of other instructions at inference time.

The fix: remove the action item entirely, not just soften the language. Instruction-tuned models execute specific verbs in system prompts literally.

More generally: every active imperative in a system prompt ("monitor X", "check Y", "report on Z") will be attempted at some point. Only include imperatives you want the model to act on.

---

## Python SSE: The \r\n Problem

Python's `requests` SSE streaming splits on `\n` but doesn't strip the trailing `\r` from Windows-style `\r\n` line endings. The SSE spec requires detecting blank lines to dispatch events — but `"\r"` != `""`, so events never dispatch.

```python
# Wrong — line might be "\r", not ""
elif line == "":
    dispatch_event()

# Correct
line = line.rstrip("\r")
elif line == "":
    dispatch_event()
```

This is a common enough SSE pitfall that it should be checked first when Python SSE parsing produces no events despite a seemingly valid stream.

---

## Python Threading: Don't Block Inside the Reader Thread

The MCP Python client uses a background thread to read the SSE stream. An early version called `event.wait()` inside the reader thread while waiting for POST responses to resolve — deadlock.

The SSE reader thread must be a pure event dispatcher. It receives a message → looks up the pending callback → calls it. Any blocking operations (waiting for responses, sleeping) must happen in the main thread or a separate worker.

---

## Token Generation Cannot Be Optimized Past Hardware

Every optimization attempt for inference speed confirmed the same result: token generation is memory-bandwidth bound. The formula is exact:

```
max_tok/s ≈ DRAM_bandwidth_GBps / model_size_GB
```

For the Ubuntu PC (25 GB/s DDR4, qwen3:4b at 2.3 GB):
```
25 / 2.3 ≈ 10.9 tok/s theoretical → 12-14 tok/s observed (flash attention efficiency)
```

Software optimizations (thread count, flash attention, quantization) move the number within a 20-30% band around this ceiling. The only way to go faster is: smaller model, faster RAM, or a GPU.

This understanding changed the optimization strategy from "how do I make this model faster" to "which model is fast enough while still being correct."

---

## Single Source of Truth Prevents Config Drift

Early in the project, model names were referenced in four places: the router, the heartbeat cron, the startup validator, and the system prompt builder. When a model was renamed or added, it was easy to update three of the four and leave one stale.

Moving to a single `models.ts` with structured model definitions (including `warmOnStartup`, `keepWarm`, `host` fields) and having every other component derive from it eliminated an entire class of configuration drift bugs. The router reads the model list. The heartbeat cron reads the model list. The validator checks the model list. There's one file to update.
