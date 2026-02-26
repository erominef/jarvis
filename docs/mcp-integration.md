# MCP Knowledge Base Integration

## What MCP Is

MCP (Model Context Protocol) is an open protocol for connecting LLMs to external data sources via a standardized JSON-RPC interface. The server exposes tools (like `search_kb`) that the client can call.

The transport layer is SSE (Server-Sent Events) — the server pushes responses asynchronously over a long-lived HTTP connection.

---

## Protocol Flow

```
Client                          MCP Server
  │                                  │
  ├─── GET /sse ────────────────────▶│
  │◀── event: endpoint ─────────────┤  (session path assigned)
  │                                  │
  ├─── POST /messages/?session_id=X  │
  │    { method: "initialize", ... } │
  │◀── (on SSE stream) result ───────┤
  │                                  │
  ├─── POST notifications/initialized│
  ├─── POST tools/call search_kb ───▶│  (query + top_k)
  │◀── (on SSE stream) result ───────┤  (text chunks, 20-30s wait)
  │                                  │
  ╳   (session closed)
```

Key detail: **responses come back on the SSE stream, not in the POST response body.** POST responses are always 202 Accepted with empty body.

---

## Why Not `EventSource`?

Three approaches tried, each with a different failure mode:

### Attempt 1: Browser `EventSource`
```typescript
const es = new EventSource(url);
// ❌ EventSource doesn't support custom request headers (Authorization)
// The connection is made as an anonymous request → 401
```

### Attempt 2: npm `eventsource` package
```typescript
import EventSource from "eventsource";
const es = new EventSource(url, { headers: { Authorization: `Bearer ${token}` } } as any);
// ❌ The package accepts the option in its TypeScript types but silently ignores
//    the headers at runtime. Connection succeeds but server returns 401 data.
```

### Attempt 3: Native `fetch` + `ReadableStream` ✓
```typescript
const resp = await fetch(`${base}/sse`, {
  headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
});
// ✓ Headers are actually sent. Works correctly.

async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  // Hand-written SSE line parser — handles \r\n, chunked delivery, etc.
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // ... parse lines, yield events
  }
}
```

---

## Fresh Session Per Search

Initial implementation reused a single SSE session for all searches. This hit server-side idle timeout (~60s) between searches, killing the stream mid-session.

Solution: open a fresh SSE session for every search call. The overhead is one HTTP handshake (~50ms) — negligible compared to the 20-30s search time.

```typescript
// One search = one complete session lifecycle
export async function searchKnowledgeBase(query: string): Promise<string> {
  return runSearch(query, 5);  // opens SSE, handshakes, searches, closes
}
```

---

## Latency Expectations

MCP search latency depends on your knowledge-base backend and whether caches are warm. A reasonable baseline for a local-first setup is:

1. Query normalization / expansion (local model or rules, ~0.2–2s)
2. Retrieval (local vector store or index, ~0.1–2s)
3. Optional reranking (local model, ~0.5–3s)
4. Response assembly and SSE delivery (~0.1–1s)

The agent should send a typing indicator (`⏳`) immediately upon receiving the request to signal it’s working.

> Note: This repo intentionally avoids naming or depending on any specific third-party vendors. The goal is to demonstrate the integration pattern, not the exact service choices.


---

## Python Implementation

For standalone scripts (not running inside the Node.js agent), a Python implementation exists at `scripts/mcp-test.py` using `requests` with `stream=True`.

Critical Python pitfall: `requests` SSE parsing must strip `\r` from line endings before comparing to `""`:

```python
for line in lines:
    line = line.rstrip("\r")   # ← required — otherwise "\r" != "" and events never fire
    if line.startswith("event:"):
        ev_type = line[6:].strip()
    elif line.startswith("data:"):
        ev_data = line[5:].strip()
    elif line == "":            # ← this only matches after rstrip
        if ev_data:
            yield (ev_type or "message", ev_data)
```

Also: never do `pending_event.wait()` inside the SSE reader thread. The reader thread must be a pure dispatcher; the main thread waits on `threading.Event`.
