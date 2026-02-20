# Multi-Tenant MCP Server: End-to-End Tutorial

This tutorial walks through the complete lifecycle of a user session against the notebooklm-mcp multi-tenant HTTP server. Every HTTP step shows both a `curl` command and an equivalent Python `requests` snippet, and an example output.

## Prerequisites

- `uv` installed and dependencies synced (`uv sync --prerelease=allow`)
- A Google account for NotebookLM authentication
- A NotebookLM notebook project or share URL

---

## Shared Python Setup

All Python examples assume these definitions exist at the top of your script:

```python
import requests

BASE_URL = "http://localhost:8000"
USER_ID = "new-session-1"
HEADERS = {
    "Content-Type": "application/json",
    "X-User-ID": USER_ID,
}

def mcp(req_id, method, params=None):
    """Send a raw JSON-RPC 2.0 request to the MCP endpoint."""
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    resp = requests.post(f"{BASE_URL}/mcp", json=payload, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

def tool(req_id, name, arguments=None):
    """Shorthand for tools/call."""
    return mcp(req_id, "tools/call", {"name": name, "arguments": arguments or {}})
```

---

## Start the Server

Server startup is a CLI operation with no Python equivalent — run it in a separate terminal.

**Bash**
```bash
uv run notebooklm-mcp --transport http --multi-tenant --host 0.0.0.0 --port 8000
```

The server logs confirmation and begins accepting connections:

```
Starting multi-tenant HTTP server on 0.0.0.0:8000
Uvicorn running on http://0.0.0.0:8000
```

Verify it is healthy before proceeding:

**Bash**
```bash
curl -s http://localhost:8000/health
```

**Python**
```python
resp = requests.get(f"{BASE_URL}/health")
print(resp.json())
```

```json
{
  "status": "healthy",
  "service": "notebooklm-mcp",
  "active_tenants": 0
}
```

`active_tenants: 0` confirms no user sessions exist yet. Every subsequent request identifies itself with an `X-User-ID` header; each unique value gets its own isolated auth state, library, and browser sessions.

---

## Step 1 — Check Health for a New User

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_health","arguments":{}}}'
```

**Python**
```python
result = tool(1, "get_health")
print(result)
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "success": true,
    "data": {
      "status": "ok",
      "authenticated": false,
      "notebook_url": "not configured",
      "active_sessions": 0,
      "max_sessions": 10,
      "session_timeout": 900,
      "total_messages": 0,
      "headless": true,
      "auto_login_enabled": false,
      "stealth_enabled": true
    }
  }
}
```

`authenticated: false` means this user has no saved Google credentials yet. The tenant is freshly created with an empty library and no active browser sessions.

---

## Step 2 — Authenticate with Google

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"setup_auth","arguments":{"show_browser":true}}}'
```

**Python**
```python
result = tool(2, "setup_auth", {"show_browser": True})
print(result)
```

A Chromium browser window opens on your machine. Sign in to your Google account. The call blocks until login completes (or times out after 10 minutes). Once you finish:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "success": true,
    "data": {
      "status": "authenticated",
      "message": "Successfully authenticated and saved browser state",
      "authenticated": true,
      "duration_seconds": 150.6
    }
  }
}
```

The browser state (cookies, session tokens) is saved to this user's isolated directory and reused for all future requests from `new-session-1`.

---

## Step 3 — Add a Notebook

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"add_notebook","arguments":{"url":"https://notebooklm.google.com/notebook/b69417f1-2232-4def-82d4-e0a901069978","name":"Context Graph","description":"YouTube experts explaining what context graphs are and why they are relevant now.","topics":["context graphs","knowledge graphs","AI/ML"]}}}'
```

**Python**
```python
result = tool(3, "add_notebook", {
    "url": "https://notebooklm.google.com/notebook/b69417f1-2232-4def-82d4-e0a901069978",
    "name": "Context Graph",
    "description": "YouTube experts explaining what context graphs are and why they are relevant now.",
    "topics": ["context graphs", "knowledge graphs", "AI/ML"],
})
print(result)
```

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "success": true,
    "data": {
      "notebook": {
        "id": "context-graph",
        "url": "https://notebooklm.google.com/notebook/b69417f1-2232-4def-82d4-e0a901069978",
        "name": "Context Graph",
        "description": "YouTube experts explaining what context graphs are and why they are relevant now.",
        "topics": ["context graphs", "knowledge graphs", "AI/ML"],
        "added_at": "2026-02-20T14:48:44.644500+00:00",
        "use_count": 0,
        "tags": []
      }
    }
  }
}
```

This is a pure library write — no browser automation involved. The notebook metadata is persisted to `new-session-1`'s `library.json`.

---

## Step 4 — List Notebooks

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"list_notebooks","arguments":{}}}'
```

**Python**
```python
result = tool(4, "list_notebooks")
notebooks = result["result"]["data"]["notebooks"]
for nb in notebooks:
    print(nb["id"], "-", nb["name"])
```

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "success": true,
    "data": {
      "notebooks": [
        {
          "id": "context-graph",
          "name": "Context Graph",
          "url": "https://notebooklm.google.com/notebook/b69417f1-2232-4def-82d4-e0a901069978",
          "topics": ["context graphs", "knowledge graphs", "AI/ML"]
        }
      ]
    }
  }
}
```

The notebook added in Step 3 appears in the library. Only notebooks belonging to `new-session-1` are returned — other users' libraries are not visible.

---

## Step 5 — Select the Active Notebook

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"select_notebook","arguments":{"id":"context-graph"}}}'
```

**Python**
```python
result = tool(5, "select_notebook", {"id": "context-graph"})
print(result)
```

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "success": true,
    "data": {
      "notebook": {
        "id": "context-graph",
        "name": "Context Graph"
      }
    }
  }
}
```

Sets `context-graph` as the default for this user. Subsequent `ask_question` calls that omit `notebook_id` will automatically use this notebook.

---

## Step 6 — Ask a Question

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"ask_question","arguments":{"question":"What is in this notebook? Give me a brief overview of the main topics and key insights covered."}}}'
```

**Python**
```python
result = tool(6, "ask_question", {
    "question": "What is in this notebook? Give me a brief overview of the main topics and key insights covered.",
})
data = result["result"]["data"]
session_id = data["session_id"]   # save this for follow-up questions
print("session_id:", session_id)
print(data["answer"])
```

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "result": {
    "success": true,
    "data": {
      "session_id": "fd879d02",
      "answer": "This notebook provides a comprehensive look at context graphs, exploring them both as a technical data structure optimized for AI and as a strategic enterprise framework for business automation.\n\n1. The Dual Definition of Context Graphs — as institutional memory capturing the 'why' behind decisions, and as an AI-optimized data structure that retains in-situ context lost during LLM chunking.\n\n2. Decision Traces and the Write Path — the atomic unit of an enterprise context graph, capturing automated actions, human overrides, and dark data from Slack, Zoom, and email.\n\n3. Powering Systems of Agents — context graphs provide episodic, semantic, and procedural memory so agent teams learn from past projects rather than starting from scratch.\n\n4. Structural Engineering and Ontologies — rely on mature ontologies like schema.org or FIBO; feeding RDF triples to LLMs yields far better results than plain text.\n\n5. Organic Growth vs. Universal Graphs — build vertical, workflow-specific graphs that emerge naturally from automation rather than attempting one universal enterprise graph."
    }
  }
}
```

The browser opens NotebookLM, submits the question to Gemini, and returns a source-grounded answer. Save the `session_id` — it must be passed to all follow-up questions to maintain conversation context.

---

## Step 7 — Continue the Conversation

Pass the `session_id` from Step 6 to stay in the same thread:

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"ask_question","arguments":{"question":"How many sources are in this notebook?","session_id":"fd879d02"}}}'
```

**Python**
```python
result = tool(7, "ask_question", {
    "question": "How many sources are in this notebook?",
    "session_id": session_id,   # from Step 6
})
print(result["result"]["data"]["answer"])
```

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "success": true,
    "data": {
      "session_id": "fd879d02",
      "answer": "Based on the provided sources and our conversation history, there is no information regarding the exact number of sources included in this notebook."
    }
  }
}
```

The same `session_id` is returned, confirming the conversation continues in the same thread. No new browser session is created — the existing one is reused.

---

## Tenant Isolation Verification

At any point, inspect how many users are active:

**Bash**
```bash
curl -s http://localhost:8000/health
```

**Python**
```python
resp = requests.get(f"{BASE_URL}/health")
print(resp.json())
```

```json
{
  "status": "healthy",
  "service": "notebooklm-mcp",
  "active_tenants": 1
}
```

Calling the same tools with a different `X-User-ID` (e.g., `bob`) creates a completely separate tenant — its own library, auth state, and sessions — with no overlap with `new-session-1`.

---

## MCP Protocol Methods

Beyond `tools/call`, the server implements the full MCP JSON-RPC 2.0 protocol.

### Initialize Handshake

Called once by MCP clients on connect:

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","clientInfo":{"name":"my-client","version":"1.0"},"capabilities":{}}}'
```

**Python**
```python
# No X-User-ID needed for initialize
result = requests.post(f"{BASE_URL}/mcp", json={
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "clientInfo": {"name": "my-client", "version": "1.0"},
        "capabilities": {},
    },
}, headers={"Content-Type": "application/json"}).json()
print(result)
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": { "tools": {}, "logging": {} },
    "serverInfo": { "name": "notebooklm-mcp", "version": "1.0.0" }
  }
}
```

### Tool Discovery

Returns all 16 tools with their input schemas. If `X-User-ID` is provided, `ask_question`'s description reflects the user's active notebook:

**Bash**
```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-User-ID: new-session-1" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

**Python**
```python
result = mcp(2, "tools/list")
for t in result["result"]["tools"]:
    print(t["name"])
```

### Notifications

Acknowledged with `204 No Content`, no response body:

**Bash**
```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
# 204
```

**Python**
```python
resp = requests.post(f"{BASE_URL}/mcp", json={
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {},
}, headers={"Content-Type": "application/json"})
print(resp.status_code)  # 204
```
