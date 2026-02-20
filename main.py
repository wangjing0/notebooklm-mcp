#!/usr/bin/env python3
import asyncio
import json
import sys

from typing import Any

from fastmcp import FastMCP

from src.auth.auth_manager import AuthManager
from src.config import CONFIG
from src.library.notebook_library import NotebookLibrary
from src.session.session_manager import SessionManager
from src.tools import ToolHandlers
from src.utils.cli_handler import CliHandler
from src.utils.logger import log


mcp = FastMCP("notebooklm-mcp")

_auth = AuthManager()
_sessions = SessionManager(_auth)
_library = NotebookLibrary()
_handlers = ToolHandlers(_sessions, _auth, _library)


@mcp.tool()
async def ask_question(
    question: str,
    session_id: str | None = None,
    notebook_id: str | None = None,
    notebook_url: str | None = None,
    show_browser: bool | None = None,
    browser_options: dict[str, Any] | None = None,
) -> str:
    """Conversational research partner using NotebookLM with Gemini AI.

    Asks questions to your NotebookLM notebook and returns source-grounded answers.
    Sessions maintain context for follow-up questions — always prefer continuing
    an existing session for the same task.

    For authentication issues, use setup_auth and verify with get_health.
    """
    result = await _handlers.handle_ask_question({
        "question": question,
        "session_id": session_id,
        "notebook_id": notebook_id,
        "notebook_url": notebook_url,
        "show_browser": show_browser,
        "browser_options": browser_options,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_sessions() -> str:
    """List all active browser sessions with stats (age, message count, last activity)."""
    result = await _handlers.handle_list_sessions()
    return json.dumps(result, indent=2)


@mcp.tool()
async def close_session(session_id: str) -> str:
    """Close a specific session by session ID."""
    result = await _handlers.handle_close_session({"session_id": session_id})
    return json.dumps(result, indent=2)


@mcp.tool()
async def reset_session(session_id: str) -> str:
    """Reset a session's chat history while keeping the same session ID."""
    result = await _handlers.handle_reset_session({"session_id": session_id})
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_health() -> str:
    """Get server health status including authentication state and active sessions."""
    result = await _handlers.handle_get_health()
    return json.dumps(result, indent=2)


@mcp.tool()
async def setup_auth(
    show_browser: bool | None = None,
    browser_options: dict[str, Any] | None = None,
) -> str:
    """Open a browser window for Google authentication to access NotebookLM."""
    result = await _handlers.handle_setup_auth(
        {"show_browser": show_browser, "browser_options": browser_options}
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def re_auth(
    show_browser: bool | None = None,
    browser_options: dict[str, Any] | None = None,
) -> str:
    """Switch Google accounts or re-authenticate with a fresh browser session."""
    result = await _handlers.handle_re_auth(
        {"show_browser": show_browser, "browser_options": browser_options}
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def add_notebook(
    url: str,
    name: str,
    description: str,
    topics: list[str],
    content_types: list[str] | None = None,
    use_cases: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Add a NotebookLM notebook to your library. Requires explicit user permission."""
    result = await _handlers.handle_add_notebook({
        "url": url,
        "name": name,
        "description": description,
        "topics": topics,
        "content_types": content_types,
        "use_cases": use_cases,
        "tags": tags,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_notebooks() -> str:
    """List all library notebooks with metadata (name, topics, use cases, URL)."""
    result = await _handlers.handle_list_notebooks()
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_notebook(id: str) -> str:
    """Get detailed information about a specific notebook by ID."""
    result = await _handlers.handle_get_notebook({"id": id})
    return json.dumps(result, indent=2)


@mcp.tool()
async def select_notebook(id: str) -> str:
    """Set a notebook as the active default for ask_question."""
    result = await _handlers.handle_select_notebook({"id": id})
    return json.dumps(result, indent=2)


@mcp.tool()
async def update_notebook(
    id: str,
    name: str | None = None,
    description: str | None = None,
    topics: list[str] | None = None,
    content_types: list[str] | None = None,
    use_cases: list[str] | None = None,
    tags: list[str] | None = None,
    url: str | None = None,
) -> str:
    """Update notebook metadata. Requires user confirmation before calling."""
    result = await _handlers.handle_update_notebook({
        "id": id,
        "name": name,
        "description": description,
        "topics": topics,
        "content_types": content_types,
        "use_cases": use_cases,
        "tags": tags,
        "url": url,
    })
    return json.dumps(result, indent=2)


@mcp.tool()
async def remove_notebook(id: str) -> str:
    """Remove a notebook from the library. Requires explicit user confirmation."""
    result = await _handlers.handle_remove_notebook({"id": id})
    return json.dumps(result, indent=2)


@mcp.tool()
async def search_notebooks(query: str) -> str:
    """Search library notebooks by name, description, topics, or tags."""
    result = await _handlers.handle_search_notebooks({"query": query})
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_library_stats() -> str:
    """Get statistics about your notebook library (total notebooks, usage, etc.)."""
    result = await _handlers.handle_get_library_stats()
    return json.dumps(result, indent=2)


@mcp.tool()
async def cleanup_data(
    confirm: bool,
    preserve_library: bool = False,
) -> str:
    """Deep cleanup of all NotebookLM MCP data files. Shows preview before deletion."""
    result = await _handlers.handle_cleanup_data(
        {"confirm": confirm, "preserve_library": preserve_library}
    )
    return json.dumps(result, indent=2)


def main() -> None:
    """Run the MCP server (stdio by default, streamable-http when MCP_TRANSPORT=http)."""
    import os
    log.info("Starting NotebookLM MCP Server (FastMCP)...")
    log.info(f"  Config Dir: {CONFIG.configDir}")
    log.info(f"  Data Dir: {CONFIG.dataDir}")
    log.info(f"  Headless: {CONFIG.headless}")
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.getenv("PORT", "8000"))
        log.info(f"  Transport: streamable-http on port {port}")
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        log.info("  Transport: stdio")
        mcp.run()


def main_sync() -> None:
    args = sys.argv[1:]
    if args and args[0] == "config":
        cli = CliHandler()
        asyncio.run(cli.handle_command(args))
        return
    if args and args[0].startswith("--"):
        from src.mcp_server.cli import main as cli_main
        cli_main(args)
        return
    main()


if __name__ == "__main__":
    main_sync()
