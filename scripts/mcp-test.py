#!/usr/bin/env python3
"""
MCP SSE Client — Standalone test script.

Tests connectivity to an MCP-compatible knowledge base server.
Uses the SSE JSON-RPC protocol (MCP spec 2024-11-05).

Usage:
    MCP_URL=https://your-server.com MCP_TOKEN=your_token python3 scripts/mcp-test.py
    python3 scripts/mcp-test.py "your search query"

Requirements:
    pip install requests
"""

import json
import os
import sys
import threading
import uuid
import requests


MCP_BASE  = os.environ.get("MCP_URL", "https://your-mcp-server.example.com").rstrip("/sse").rstrip("/")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
QUERY     = sys.argv[1] if len(sys.argv) > 1 else "test query"
TOP_K     = 5


def parse_sse(resp):
    """Yield (event_type, data) from SSE response stream."""
    buf = ""
    ev_type = ev_data = ""
    for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
        if chunk:
            buf += chunk
        lines = buf.split("\n")
        buf = lines.pop()
        for line in lines:
            line = line.rstrip("\r")  # critical: strip \r from \r\n line endings
            if line.startswith("event:"):
                ev_type = line[6:].strip()
            elif line.startswith("data:"):
                ev_data = line[5:].strip()
            elif line == "":
                if ev_data:
                    yield (ev_type or "message", ev_data)
                ev_type = ev_data = ""


def mcp_search(query: str, top_k: int = 5) -> str:
    """
    Opens a fresh MCP SSE session, performs the handshake,
    runs search_kb, and returns the result text.

    Architecture:
    - Background thread reads SSE stream and dispatches events
    - Main thread sends POSTs and waits on threading.Event
    - Never block inside the reader thread (deadlock risk)
    """
    result_box = {"text": None, "error": None}
    done = threading.Event()

    def reader():
        resp = requests.get(
            f"{MCP_BASE}/sse",
            headers={"Authorization": f"Bearer {MCP_TOKEN}", "Accept": "text/event-stream"},
            stream=True,
            timeout=None,
        )
        if resp.status_code != 200:
            result_box["error"] = f"SSE connect failed: {resp.status_code}"
            done.set()
            return

        session_path = ""
        init_id = search_id = ""
        phase = "await_endpoint"

        def post(body):
            requests.post(
                f"{MCP_BASE}{session_path}",
                json=body,
                headers={"Authorization": f"Bearer {MCP_TOKEN}"},
                timeout=15,
            )

        for ev_type, data in parse_sse(resp):
            if ev_type == "endpoint":
                session_path = data.strip()
                print(f"[mcp] session assigned: {session_path[-36:]}")
                phase = "init"
                init_id = str(uuid.uuid4())
                post({
                    "jsonrpc": "2.0", "id": init_id, "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "mcp-test", "version": "1.0"},
                    },
                })

            elif data and not data.startswith(":"):
                try:
                    msg = json.loads(data)
                    msg_id = str(msg.get("id", ""))

                    if msg_id == init_id and phase == "init":
                        phase = "search"
                        post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
                        search_id = str(uuid.uuid4())
                        post({
                            "jsonrpc": "2.0", "id": search_id, "method": "tools/call",
                            "params": {"name": "search_kb", "arguments": {"query": query, "top_k": top_k}},
                        })
                        print(f"[mcp] search sent: '{query}' (top_k={top_k})")

                    elif msg_id == search_id and phase == "search":
                        r = msg.get("result", {})
                        content = r.get("content", []) if isinstance(r, dict) else []
                        result_box["text"] = content[0].get("text", str(r)) if content else str(r)
                        done.set()
                        resp.close()
                        return

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    print(f"[mcp] waiting for result (can take 20-30s)...")
    if not done.wait(timeout=90):
        raise TimeoutError("search timed out after 90s")
    if result_box["error"]:
        raise RuntimeError(result_box["error"])
    return result_box["text"] or ""


if __name__ == "__main__":
    if not MCP_TOKEN:
        print("Error: MCP_TOKEN environment variable not set")
        sys.exit(1)

    print(f"[mcp-test] Querying '{QUERY}'")
    try:
        result = mcp_search(QUERY, TOP_K)
        print(f"\n[mcp-test] Got {len(result)} chars")
        print("-" * 60)
        print(result[:2000])
        if len(result) > 2000:
            print(f"\n... ({len(result) - 2000} chars truncated)")
    except Exception as e:
        print(f"[mcp-test] Failed: {e}")
        sys.exit(1)
