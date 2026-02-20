<div align="center">

# NotebookLM MCP

**Let agent harness (Claude, Cursor, Codex...) chats directly with your NotebookLM project**

Credits to the original [NotebookLM MCP](https://github.com/PleasePrompto/notebooklm-mcp) (TypeScript). This is a Python port.

[Installation](#installation) · [Quick Start](#quick-start-in-claude-code) · [Configuration](#configuration) · [Architecture](#architecture) · [Examples](#examples) · [FAQ](#faq) · [Disclaimer](#disclaimer)

</div>

---

## The Problem

When you ask Claude Code or Cursor to “search through my collections of documents” you often get:

- **Heavy token use** — Reading many files over and over is expensive and slow.
- **Infra overhead** — Building and maintaining a local RAG stack is time-consuming and brittle.
- **Hallucinations** — When the model can't find something, it may invent plausible-sounding answers.
- **Why not leverage google's ecosystem** — NotebookLM can process a wide range of multimedia sources such as PDFs, websites, GitHub repos, YouTube videos, etc.

## The Solution

Let your local agents chat directly with [**NotebookLM**](https://notebooklm.google/) — Google's **zero-hallucination knowledge base** powered by Gemini that provides intelligent, synthesized answers from designated documents.

**The real advantage**: No more manual copy-paste between NotebookLM and your editor. Your agent asks NotebookLM directly and gets answers straight back in the CLI. It builds deep understanding through automatic follow-ups — Claude asks multiple questions in sequence, each building on the last, getting specific implementation details, edge cases, and best practices. You can save NotebookLM links to your local library with tags and descriptions, and Claude automatically selects the relevant notebook based on your current task. And you can use the `ask_question` tool to ask NotebookLM anything you want.

![notebooklm-tools](docs/notebooklm-tools.png)

---

## Why NotebookLM, Not Local RAG?

| Approach            | Token Cost              | Setup Time | Hallucinations              | Answer Quality   |
|---------------------|-------------------------|------------|-----------------------------|------------------|
| Feed docs to Claude  | Very high               | Instant    | Yes (fills gaps)            | Variable         |
| Web search           | Medium                  | Instant    | High (unreliable sources)   | Hit or miss      |
| Local RAG            | Medium–high             | Hours      | Medium (retrieval gaps)     | Depends on setup |
| **NotebookLM MCP**   | **Minimal**             | **~5 min** | **Low** (refuses when unsure) | **Expert Synthesized**  |

---

## Installation

### Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Chrome installed

### Setup

```bash
git clone <this repository>
cd notebooklm-mcp
uv sync
uv run playwright install chromium
```

### Add to Claude Code

```bash
claude mcp add notebooklm -- uv run --directory /path/to/notebooklm-mcp python main.py
```

### Add to Cursor / other MCP clients

Add to your MCP config (e.g. `.mcp.json` or Cursor MCP settings):


---

## Quick Start in Claude Code

### 1. Authenticate (one-time)

In chat, say:

> **"Log me in to NotebookLM"**

A Chrome window will open; sign in with your Google account.

### 2. Create your knowledge base

1. Go to [notebooklm.google.com](https://notebooklm.google.com).
2. Create a notebook and add sources: PDFs, Google Docs, markdown, websites, GitHub repos, YouTube videos.
3. Share it: **Settings → Share → Anyone with link** and copy the link.

### 3. Use it from Claude

Say something like:

> **"I'm building with [library]. Here's my NotebookLM: [link]"**

Claude will ask for any metadata it needs and then use the notebook.

---

## Configuration

Settings are via environment variables. Copy `.env.example` to `.env` and edit:

```bash
# Default notebook URL (optional)
NOTEBOOK_URL=https://notebooklm.google.com/notebook/...

# Browser behavior
HEADLESS=true          # Run Chrome headlessly (default: true)

# Session management
MAX_SESSIONS=10        # Max concurrent sessions (default: 10)
SESSION_TIMEOUT=900    # Session timeout in seconds (default: 900)

# Auto-login (optional)
AUTO_LOGIN_ENABLED=false
LOGIN_EMAIL=you@gmail.com
LOGIN_PASSWORD=yourpassword

# Tool profile
NOTEBOOKLM_PROFILE=full
```

---

## Architecture

```
Your request  →  Claude / Cursor / Codex
                        ↕
                 notebooklm-mcp
                        ↕
            Playwright + humanized Chrome
                        ↕
                   NotebookLM UI
                        ↕
         Your docs, sites, repos, videos, etc.
```

Browwer state, chrome profiles are stored in `~/Library/Application Support/notebooklm-mcp/` (macOS) or the platform equivalent via `platformdirs`.

---

## Examples

| Intent          | Say | Result |
|-----------------|-----|--------|
| Authenticate    | *"Log me in to NotebookLM"* | Chrome opens for login |
| Add notebook    | *"Add [notebooklm link] to library"* | Saves notebook with metadata |
| List notebooks  | *"Show our notebooks"* | Lists saved notebooks |
| Research first  | *"Research this in NotebookLM before planning"* | Multi-question session |
| Select notebook | *"Use the React notebook"* | Sets active notebook |
| View browser    | *"Show me the browser"* | Watch live NotebookLM chat |
| Fix auth        | *"Repair NotebookLM authentication"* | Clears and re-authenticates |
| Switch account  | *"Re-authenticate with different Google account"* | Changes Google account |
| Clean restart   | *"Run NotebookLM cleanup"* | Removes all data for fresh start |

---

## FAQ

**Is it really zero hallucinations?** \
NotebookLM is specifically designed to only answer from uploaded sources. If it doesn't know, it says so.

**What about rate limits?** \
Free tier has daily query limits ~50 per Google account.

**How secure is this?** \
Chrome runs locally. Your credentials never leave your machine. Use a dedicated Google account if preferred.

**Can I see what's happening?** \
Yes — headless mode is enabled by default. however, say *"Ask NotebookLM '[your question]' and show me the browser"* to pass `show_browser: true` to any tool call.

![notebooklm-browser](docs/with_browser_on.png)

---

## Disclaimer

This tool automates browser interactions with NotebookLM using Playwright. Chrome runs in stealth mode — it disguises itself as a regular human-controlled browser by patching automation signals that websites use to detect bots. This is not illegal, but Google may still detect automated usage and rate-limit or block the account. Use a dedicated Google account rather than your primary account.

### Are there alternatives?

Google does not offer a public API for NotebookLM. As of early 2026, the only official programmatic access is the [NotebookLM Enterprise API](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks) (released September 2025, alpha), which requires a paid Google Cloud enterprise contract and covers only notebook/source management — not querying notebooks for answers. Developer forums have been [requesting a consumer API since mid-2024](https://discuss.ai.google.dev/t/how-to-access-notebooklm-via-api/5084) with no concrete timeline from Google.

The restriction is intentional: Google uses API access as the primary differentiator for its enterprise tier, and opening a consumer API would require substantially different data-handling infrastructure to meet GDPR/HIPAA obligations for personal data.

**Alternatives and their trade-offs:**

| Approach | Example | Reliability | Risk |
|---|---|---|---|
| Browser automation (Playwright) | This project | High — mirrors real user behavior | Low — follows ToS spirit |
| Reverse-engineered internal APIs | [notebooklm-py](https://github.com/teng-lin/notebooklm-py) | Medium — breaks on Google deploys | High — unsupported, undocumented |
| Enterprise API | [Google Cloud](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/overview) | High | None — but requires enterprise license $$$ |
| Other open-source implementation | [open-notebook](https://github.com/lfnovo/open-notebook), [SurfSense](https://github.com/Decentralised-AI/SurfSense-Open-Source-Alternative-to-NotebookLM) | Medium | None — but no NotebookLM-specific features |

Browser automation is the pragmatic solution for free-tier access. Multiple independent projects — [notebooklm_source_automation](https://github.com/DataNath/notebooklm_source_automation), [notebooklm-podcast-automator](https://github.com/upamune/notebooklm-podcast-automator) — use the same approach, as does this project. See also [this community discussion](https://news.ycombinator.com/item?id=41756808) and [the case for a public API](https://medium.com/@kombib/public-notebooklm-api-why-we-need-it-now-7244a5371f57).
