import json
import os

from typing import Any

from fastmcp import FastMCP

from ..auth.auth_manager import AuthManager
from ..config import CONFIG, ServerConfig
from ..library.notebook_library import NotebookLibrary
from ..session.session_manager import SessionManager
from ..tools.handlers import ToolHandlers
from ..utils.logger import log
from .base_server import BaseMCPServer


class SingleTenantMCPServer(BaseMCPServer):
    def __init__(self, server_config: ServerConfig) -> None:
        super().__init__(server_config)
        self._auth = AuthManager()
        self._sessions = SessionManager(self._auth)
        self._library = NotebookLibrary()
        self._handlers = ToolHandlers(self._sessions, self._auth, self._library)
        self._mcp = self._build_mcp()

    def _build_mcp(self) -> FastMCP:
        mcp = FastMCP("notebooklm-mcp")
        handlers = self._handlers

        @mcp.tool()
        async def ask_question(
            question: str,
            session_id: str | None = None,
            notebook_id: str | None = None,
            notebook_url: str | None = None,
            show_browser: bool | None = None,
            browser_options: dict[str, Any] | None = None,
        ) -> str:
            """Conversational research partner using NotebookLM with Gemini AI."""
            result = await handlers.handle_ask_question({
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
            """List all active browser sessions."""
            return json.dumps(await handlers.handle_list_sessions(), indent=2)

        @mcp.tool()
        async def close_session(session_id: str) -> str:
            """Close a specific session by session ID."""
            return json.dumps(await handlers.handle_close_session({"session_id": session_id}), indent=2)

        @mcp.tool()
        async def reset_session(session_id: str) -> str:
            """Reset a session's chat history."""
            return json.dumps(await handlers.handle_reset_session({"session_id": session_id}), indent=2)

        @mcp.tool()
        async def get_health() -> str:
            """Get server health status."""
            return json.dumps(await handlers.handle_get_health(), indent=2)

        @mcp.tool()
        async def setup_auth(
            show_browser: bool | None = None,
            browser_options: dict[str, Any] | None = None,
        ) -> str:
            """Open a browser window for Google authentication."""
            return json.dumps(await handlers.handle_setup_auth({"show_browser": show_browser, "browser_options": browser_options}), indent=2)

        @mcp.tool()
        async def re_auth(
            show_browser: bool | None = None,
            browser_options: dict[str, Any] | None = None,
        ) -> str:
            """Switch Google accounts or re-authenticate."""
            return json.dumps(await handlers.handle_re_auth({"show_browser": show_browser, "browser_options": browser_options}), indent=2)

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
            """Add a NotebookLM notebook to your library."""
            return json.dumps(await handlers.handle_add_notebook({"url": url, "name": name, "description": description, "topics": topics, "content_types": content_types, "use_cases": use_cases, "tags": tags}), indent=2)

        @mcp.tool()
        async def list_notebooks() -> str:
            """List all library notebooks."""
            return json.dumps(await handlers.handle_list_notebooks(), indent=2)

        @mcp.tool()
        async def get_notebook(id: str) -> str:
            """Get detailed information about a specific notebook."""
            return json.dumps(await handlers.handle_get_notebook({"id": id}), indent=2)

        @mcp.tool()
        async def select_notebook(id: str) -> str:
            """Set a notebook as the active default."""
            return json.dumps(await handlers.handle_select_notebook({"id": id}), indent=2)

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
            """Update notebook metadata."""
            return json.dumps(await handlers.handle_update_notebook({"id": id, "name": name, "description": description, "topics": topics, "content_types": content_types, "use_cases": use_cases, "tags": tags, "url": url}), indent=2)

        @mcp.tool()
        async def remove_notebook(id: str) -> str:
            """Remove a notebook from the library."""
            return json.dumps(await handlers.handle_remove_notebook({"id": id}), indent=2)

        @mcp.tool()
        async def search_notebooks(query: str) -> str:
            """Search library notebooks."""
            return json.dumps(await handlers.handle_search_notebooks({"query": query}), indent=2)

        @mcp.tool()
        async def get_library_stats() -> str:
            """Get statistics about your notebook library."""
            return json.dumps(await handlers.handle_get_library_stats(), indent=2)

        @mcp.tool()
        async def cleanup_data(confirm: bool, preserve_library: bool = False) -> str:
            """Deep cleanup of all NotebookLM MCP data files."""
            return json.dumps(await handlers.handle_cleanup_data({"confirm": confirm, "preserve_library": preserve_library}), indent=2)

        return mcp

    def run(self) -> None:
        log.info("Starting NotebookLM MCP Server (single-tenant)...")
        log.info(f"  Config Dir: {CONFIG.configDir}")
        log.info(f"  Data Dir: {CONFIG.dataDir}")
        log.info(f"  Headless: {CONFIG.headless}")

        if self._server_config.multiTenant is False and os.getenv("MCP_TRANSPORT", "stdio") == "http":
            port = self._server_config.port
            log.info(f"  Transport: streamable-http on port {port}")
            self._mcp.run(transport="streamable-http", host=self._server_config.host, port=port)
        else:
            log.info("  Transport: stdio")
            self._mcp.run()
