from mcp.types import Tool

from ..library.notebook_library import NotebookLibrary


def build_ask_question_description(library: NotebookLibrary) -> str:
    active = library.get_active_notebook()
    bt = "`"

    if active:
        topics = ", ".join(active["topics"])
        use_cases = "\n".join(f"  - {uc}" for uc in active["use_cases"])

        return f"""# Conversational Research Partner (NotebookLM \u2022 Gemini 2.5 \u2022 Session RAG)

**Active Notebook:** {active["name"]}
**Content:** {active["description"]}
**Topics:** {topics}

> Auth tip: If login is required, use the prompt 'notebooklm.auth-setup' and then verify with the 'get_health' tool. If authentication later fails (e.g., expired cookies), use the prompt 'notebooklm.auth-repair'.

## What This Tool Is
- Full conversational research with Gemini (LLM) grounded on your notebook sources
- Session-based: each follow-up uses prior context for deeper, more precise answers
- Source-cited responses designed to minimize hallucinations

## When To Use
{use_cases}

## Rules (Important)
- Always prefer continuing an existing session for the same task
- If you start a new thread, create a new session and keep its session_id
- Ask clarifying questions before implementing; do not guess missing details
- If multiple notebooks could apply, propose the top 1\u20132 and ask which to use
- If task context changes, ask to reset the session or switch notebooks
- If authentication fails, use the prompts 'notebooklm.auth-repair' (or 'notebooklm.auth-setup') and verify with 'get_health'
- After every NotebookLM answer: pause, compare with the user\u2019s goal, and only respond if you are 100% sure the information is complete. Otherwise, plan the next NotebookLM question in the same session.

## Session Flow (Recommended)
{bt}{bt}{bt}javascript
// 1) Start broad (no session_id \u2192 creates one)
ask_question({{ question: "Give me an overview of [topic]" }})
// \u2190 Save: result.session_id

// 2) Go specific (same session)
ask_question({{ question: "Key APIs/methods?", session_id }})

// 3) Cover pitfalls (same session)
ask_question({{ question: "Common edge cases + gotchas?", session_id }})

// 4) Ask for production example (same session)
ask_question({{ question: "Show a production-ready example", session_id }})
{bt}{bt}{bt}

## Automatic Multi-Pass Strategy (Host-driven)
- Simple prompts return once-and-done answers.
- For complex prompts, the host should issue follow-up calls:
  1. Implementation plan (APIs, dependencies, configuration, authentication).
  2. Pitfalls, gaps, validation steps, missing prerequisites.
- Keep the same session_id for all follow-ups, review NotebookLM\u2019s answer, and ask more questions until the problem is fully resolved.
- Before replying to the user, double-check: do you truly have everything? If not, queue another ask_question immediately.

## Notebook Selection
- Default: active notebook ({active["id"]})
- Or set notebook_id to use a library notebook
- Or set notebook_url for ad-hoc notebooks (not in library)
- If ambiguous which notebook fits, ASK the user which to use"""
    else:
        return """# Conversational Research Partner (NotebookLM \u2022 Gemini 2.5 \u2022 Session RAG)

## No Active Notebook
- Visit https://notebooklm.google to create a notebook and get a share link
- Use **add_notebook** to add it to your library (explains how to get the link)
- Use **list_notebooks** to show available sources
- Use **select_notebook** to set one active

> Auth tip: If login is required, use the prompt 'notebooklm.auth-setup' and then verify with the 'get_health' tool. If authentication later fails (e.g., expired cookies), use the prompt 'notebooklm.auth-repair'.

Tip: Tell the user you can manage NotebookLM library and ask which notebook to use for the current task."""


_ASK_QUESTION_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "The question to ask NotebookLM",
        },
        "session_id": {
            "type": "string",
            "description": "Optional session ID for contextual conversations. If omitted, a new session is created.",
        },
        "notebook_id": {
            "type": "string",
            "description": (
                "Optional notebook ID from your library. If omitted, uses the active notebook. "
                "Use list_notebooks to see available notebooks."
            ),
        },
        "notebook_url": {
            "type": "string",
            "description": "Optional notebook URL (overrides notebook_id). Use this for ad-hoc queries to notebooks not in your library.",
        },
        "show_browser": {
            "type": "boolean",
            "description": (
                "Show browser window for debugging (simple version). "
                "For advanced control (typing speed, stealth, etc.), use browser_options instead."
            ),
        },
        "browser_options": {
            "type": "object",
            "description": (
                "Optional browser behavior settings. Claude can control everything: "
                "visibility, typing speed, stealth mode, timeouts. Useful for debugging or fine-tuning."
            ),
            "properties": {
                "show": {"type": "boolean", "description": "Show browser window (default: from ENV or false)"},
                "headless": {"type": "boolean", "description": "Run browser in headless mode (default: true)"},
                "timeout_ms": {"type": "number", "description": "Browser operation timeout in milliseconds (default: 30000)"},
                "stealth": {
                    "type": "object",
                    "description": "Human-like behavior settings to avoid detection",
                    "properties": {
                        "enabled": {"type": "boolean", "description": "Master switch for all stealth features (default: true)"},
                        "random_delays": {"type": "boolean", "description": "Random delays between actions (default: true)"},
                        "human_typing": {"type": "boolean", "description": "Human-like typing patterns (default: true)"},
                        "mouse_movements": {"type": "boolean", "description": "Realistic mouse movements (default: true)"},
                        "typing_wpm_min": {"type": "number", "description": "Minimum typing speed in WPM (default: 160)"},
                        "typing_wpm_max": {"type": "number", "description": "Maximum typing speed in WPM (default: 240)"},
                        "delay_min_ms": {"type": "number", "description": "Minimum delay between actions in ms (default: 100)"},
                        "delay_max_ms": {"type": "number", "description": "Maximum delay between actions in ms (default: 400)"},
                    },
                },
                "viewport": {
                    "type": "object",
                    "description": "Browser viewport size",
                    "properties": {
                        "width": {"type": "number", "description": "Viewport width in pixels (default: 1920)"},
                        "height": {"type": "number", "description": "Viewport height in pixels (default: 1080)"},
                    },
                },
            },
        },
    },
    "required": ["question"],
}

_NOTEBOOK_MANAGEMENT_TOOLS = [
    Tool(
        name="add_notebook",
        description="""PERMISSION REQUIRED \u2014 Only when user explicitly asks to add a notebook.

## Conversation Workflow (Mandatory)
When the user says: "I have a NotebookLM with X"

1) Ask URL: "What is the NotebookLM URL?"
2) Ask content: "What knowledge is inside?" (1\u20132 sentences)
3) Ask topics: "Which topics does it cover?" (3\u20135)
4) Ask use cases: "When should we consult it?"
5) Propose metadata and confirm:
   - Name: [suggested]
   - Description: [from user]
   - Topics: [list]
   - Use cases: [list]
   "Add it to your library now?"
6) Only after explicit "Yes" \u2192 call this tool

## Rules
- Do not add without user permission
- Do not guess metadata \u2014 ask concisely
- Confirm summary before calling the tool

## How to Get a NotebookLM Share Link

Visit https://notebooklm.google/ \u2192 Login (free: 100 notebooks, 50 sources each, 500k words, 50 daily queries)
1) Click "+ New" (top right) \u2192 Upload sources (docs, knowledge)
2) Click "Share" (top right) \u2192 Select "Anyone with the link"
3) Click "Copy link" (bottom left) \u2192 Give this link to Claude

(Upgraded: Google AI Pro/Ultra gives 5x higher limits)""",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The NotebookLM notebook URL"},
                "name": {"type": "string", "description": "Display name for the notebook (e.g., 'n8n Documentation')"},
                "description": {"type": "string", "description": "What knowledge/content is in this notebook"},
                "topics": {"type": "array", "items": {"type": "string"}, "description": "Topics covered in this notebook"},
                "content_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types of content (e.g., ['documentation', 'examples', 'best practices'])",
                },
                "use_cases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "When should Claude use this notebook (e.g., ['Implementing n8n workflows'])",
                },
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for organization"},
            },
            "required": ["url", "name", "description", "topics"],
        },
    ),
    Tool(
        name="list_notebooks",
        description=(
            "List all library notebooks with metadata (name, topics, use cases, URL). "
            "Use this to present options, then ask which notebook to use for the task."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_notebook",
        description="Get detailed information about a specific notebook by ID",
        inputSchema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "The notebook ID"}},
            "required": ["id"],
        },
    ),
    Tool(
        name="select_notebook",
        description="""Set a notebook as the active default (used when ask_question has no notebook_id).

## When To Use
- User switches context: "Let\u2019s work on React now"
- User asks explicitly to activate a notebook
- Obvious task change requires another notebook

## Auto-Switching
- Safe to auto-switch if the context is clear and you announce it:
  "Switching to React notebook for this task..."
- If ambiguous, ask: "Switch to [notebook] for this task?" """,
        inputSchema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "The notebook ID to activate"}},
            "required": ["id"],
        },
    ),
    Tool(
        name="update_notebook",
        description="""Update notebook metadata based on user intent.

## Pattern
1) Identify target notebook and fields (topics, description, use_cases, tags, url)
2) Propose the exact change back to the user
3) After explicit confirmation, call this tool""",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The notebook ID to update"},
                "name": {"type": "string", "description": "New display name"},
                "description": {"type": "string", "description": "New description"},
                "topics": {"type": "array", "items": {"type": "string"}, "description": "New topics list"},
                "content_types": {"type": "array", "items": {"type": "string"}, "description": "New content types"},
                "use_cases": {"type": "array", "items": {"type": "string"}, "description": "New use cases"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "New tags"},
                "url": {"type": "string", "description": "New notebook URL"},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="remove_notebook",
        description="""Dangerous \u2014 requires explicit user confirmation.

## Confirmation Workflow
1) User requests removal ("Remove the React notebook")
2) Look up full name to confirm
3) Ask: "Remove '[notebook_name]' from your library? (Does not delete the actual NotebookLM notebook)"
4) Only on explicit "Yes" \u2192 call remove_notebook

Never remove without permission or based on assumptions.""",
        inputSchema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "The notebook ID to remove"}},
            "required": ["id"],
        },
    ),
    Tool(
        name="search_notebooks",
        description=(
            "Search library by query (name, description, topics, tags). "
            "Use to propose relevant notebooks for the task and then ask which to use."
        ),
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    ),
    Tool(
        name="get_library_stats",
        description="Get statistics about your notebook library (total notebooks, usage, etc.)",
        inputSchema={"type": "object", "properties": {}},
    ),
]

_SESSION_MANAGEMENT_TOOLS = [
    Tool(
        name="list_sessions",
        description=(
            "List all active sessions with stats (age, message count, last activity). "
            "Use to continue the most relevant session instead of starting from scratch."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="close_session",
        description="Close a specific session by session ID. Ask before closing if the user might still need it.",
        inputSchema={
            "type": "object",
            "properties": {"session_id": {"type": "string", "description": "The session ID to close"}},
            "required": ["session_id"],
        },
    ),
    Tool(
        name="reset_session",
        description=(
            "Reset a session's chat history (keep same session ID). "
            "Use for a clean slate when the task changes; ask the user before resetting."
        ),
        inputSchema={
            "type": "object",
            "properties": {"session_id": {"type": "string", "description": "The session ID to reset"}},
            "required": ["session_id"],
        },
    ),
]

_SYSTEM_TOOLS = [
    Tool(
        name="get_health",
        description=(
            "Get server health status including authentication state, active sessions, and configuration. "
            "Use this to verify the server is ready before starting research workflows.\n\n"
            "If authenticated=false and having persistent issues:\n"
            "Consider running cleanup_data(preserve_library=true) + setup_auth for fresh start with clean browser session."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="setup_auth",
        description=(
            "Google authentication for NotebookLM access - opens a browser window for manual login to your Google account. "
            "Returns immediately after opening the browser. You have up to 10 minutes to complete the login. "
            "Use 'get_health' tool afterwards to verify authentication was saved successfully. "
            "Use this for first-time authentication or when auto-login credentials are not available. "
            "For switching accounts or rate-limit workarounds, use 're_auth' tool instead.\n\n"
            "TROUBLESHOOTING for persistent auth issues:\n"
            "If setup_auth fails or you encounter browser/session issues:\n"
            "1. Ask user to close ALL Chrome/Chromium instances\n"
            "2. Run cleanup_data(confirm=true, preserve_library=true) to clean old data\n"
            "3. Run setup_auth again for fresh start\n"
            "This helps resolve conflicts from old browser sessions and installation data."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "show_browser": {
                    "type": "boolean",
                    "description": "Show browser window (simple version). Default: true for setup. For advanced control, use browser_options instead.",
                },
                "browser_options": {
                    "type": "object",
                    "description": "Optional browser settings. Control visibility, timeouts, and stealth behavior.",
                    "properties": {
                        "show": {"type": "boolean", "description": "Show browser window (default: true for setup)"},
                        "headless": {"type": "boolean", "description": "Run browser in headless mode (default: false for setup)"},
                        "timeout_ms": {"type": "number", "description": "Browser operation timeout in milliseconds (default: 30000)"},
                    },
                },
            },
        },
    ),
    Tool(
        name="re_auth",
        description=(
            "Switch to a different Google account or re-authenticate. "
            "Use this when:\n"
            "- NotebookLM rate limit is reached (50 queries/day for free accounts)\n"
            "- You want to switch to a different Google account\n"
            "- Authentication is broken and needs a fresh start\n\n"
            "This will:\n"
            "1. Close all active browser sessions\n"
            "2. Delete all saved authentication data (cookies, Chrome profile)\n"
            "3. Open browser for fresh Google login\n\n"
            "After completion, use 'get_health' to verify authentication."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "show_browser": {
                    "type": "boolean",
                    "description": "Show browser window (simple version). Default: true for re-auth. For advanced control, use browser_options instead.",
                },
                "browser_options": {
                    "type": "object",
                    "description": "Optional browser settings. Control visibility, timeouts, and stealth behavior.",
                    "properties": {
                        "show": {"type": "boolean", "description": "Show browser window (default: true for re-auth)"},
                        "headless": {"type": "boolean", "description": "Run browser in headless mode (default: false for re-auth)"},
                        "timeout_ms": {"type": "number", "description": "Browser operation timeout in milliseconds (default: 30000)"},
                    },
                },
            },
        },
    ),
    Tool(
        name="cleanup_data",
        description=(
            "ULTRATHINK Deep Cleanup - Scans entire system for ALL NotebookLM MCP data files across 8 categories. "
            "Always runs in deep mode, shows categorized preview before deletion.\n\n"
            "LIBRARY PRESERVATION: Set preserve_library=true to keep your notebook library.json file while cleaning everything else.\n\n"
            "RECOMMENDED WORKFLOW for fresh start:\n"
            "1. Ask user to close ALL Chrome/Chromium instances\n"
            "2. Run cleanup_data(confirm=false, preserve_library=true) to preview\n"
            "3. Run cleanup_data(confirm=true, preserve_library=true) to execute\n"
            "4. Run setup_auth or re_auth for fresh browser session"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "Confirmation flag. Tool shows preview first, then user confirms deletion. "
                        "Set to true only after user has reviewed the preview and explicitly confirmed."
                    ),
                },
                "preserve_library": {
                    "type": "boolean",
                    "description": (
                        "Preserve library.json file during cleanup. Default: false. "
                        "Set to true to keep your notebook library while deleting everything else."
                    ),
                    "default": False,
                },
            },
            "required": ["confirm"],
        },
    ),
]


def build_tool_definitions(library: NotebookLibrary) -> list[Tool]:
    ask_question_tool = Tool(
        name="ask_question",
        description=build_ask_question_description(library),
        inputSchema=_ASK_QUESTION_INPUT_SCHEMA,
    )
    return [ask_question_tool] + _NOTEBOOK_MANAGEMENT_TOOLS + _SESSION_MANAGEMENT_TOOLS + _SYSTEM_TOOLS
