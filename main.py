#!/usr/bin/env python3
import asyncio
import json
import sys
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.auth.auth_manager import AuthManager
from src.config import CONFIG
from src.library.notebook_library import NotebookLibrary
from src.session.session_manager import SessionManager
from src.tools import ToolHandlers, build_tool_definitions
from src.utils.cli_handler import CliHandler
from src.utils.logger import log
from src.utils.settings_manager import SettingsManager


class NotebookLMMCPServer:
    def __init__(self) -> None:
        self._server: Server = Server("notebooklm-mcp")
        self._auth = AuthManager()
        self._sessions = SessionManager(self._auth)
        self._library = NotebookLibrary()
        self._settings = SettingsManager()
        self._handlers = ToolHandlers(self._sessions, self._auth, self._library)

        all_tools = build_tool_definitions(self._library)
        self._tools: list[Tool] = self._settings.filter_tools(all_tools)

        self._setup_handlers()
        effective = self._settings.get_effective_settings()
        log.info("NotebookLM MCP Server initialized")
        log.info("  Version: 1.1.0")
        log.info(f"  Python: {sys.version.split()[0]}")
        log.info(f"  Platform: {sys.platform}")
        log.info(f"  Profile: {effective['profile']} ({len(self._tools)} tools active)")

    def _setup_handlers(self) -> None:
        server = self._server

        @server.list_tools()
        async def list_tools() -> list[Tool]:
            log.info("[MCP] list_tools request received")
            return self._tools

        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            log.info(f"[MCP] Tool call: {name}")
            progress_token = (arguments or {}).get("_meta", {}).get("progressToken")

            async def send_progress(message: str, progress: Optional[int] = None, total: Optional[int] = None) -> None:
                if progress_token is not None:
                    params: dict[str, Any] = {"progressToken": progress_token, "message": message}
                    if progress is not None:
                        params["progress"] = progress
                    if total is not None:
                        params["total"] = total
                    await server.request_context.session.send_progress_notification(**params)
                    log.dim(f"  Progress: {message}")

            try:
                result = await self._dispatch(name, arguments or {}, send_progress)
            except Exception as e:
                log.error(f"[MCP] Tool execution error: {e}")
                result = {"success": False, "error": str(e)}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _dispatch(self, name: str, args: dict, send_progress: Any) -> dict:
        match name:
            case "ask_question":
                return await self._handlers.handle_ask_question(args, send_progress)
            case "list_sessions":
                return await self._handlers.handle_list_sessions()
            case "close_session":
                return await self._handlers.handle_close_session(args)
            case "reset_session":
                return await self._handlers.handle_reset_session(args)
            case "get_health":
                return await self._handlers.handle_get_health()
            case "setup_auth":
                return await self._handlers.handle_setup_auth(args, send_progress)
            case "re_auth":
                return await self._handlers.handle_re_auth(args, send_progress)
            case "add_notebook":
                return await self._handlers.handle_add_notebook(args)
            case "list_notebooks":
                return await self._handlers.handle_list_notebooks()
            case "get_notebook":
                return await self._handlers.handle_get_notebook(args)
            case "select_notebook":
                return await self._handlers.handle_select_notebook(args)
            case "update_notebook":
                return await self._handlers.handle_update_notebook(args)
            case "remove_notebook":
                return await self._handlers.handle_remove_notebook(args)
            case "search_notebooks":
                return await self._handlers.handle_search_notebooks(args)
            case "get_library_stats":
                return await self._handlers.handle_get_library_stats()
            case "cleanup_data":
                return await self._handlers.handle_cleanup_data(args)
            case _:
                log.error(f"[MCP] Unknown tool: {name}")
                return {"success": False, "error": f"Unknown tool: {name}"}

    async def run(self) -> None:
        log.info("Starting NotebookLM MCP Server...")
        log.info("")
        log.info("Configuration:")
        log.info(f"  Config Dir: {CONFIG.configDir}")
        log.info(f"  Data Dir: {CONFIG.dataDir}")
        log.info(f"  Headless: {CONFIG.headless}")
        log.info(f"  Max Sessions: {CONFIG.maxSessions}")
        log.info(f"  Session Timeout: {CONFIG.sessionTimeout}s")
        log.info(f"  Stealth: {CONFIG.stealthEnabled}")
        log.info("")

        async with stdio_server() as streams:
            read_stream, write_stream = streams
            log.success("MCP Server connected via stdio")
            log.success("Ready to receive requests from Claude Code!")
            log.info("")
            log.info("Available tools:")
            for tool in self._tools:
                desc = (tool.description or "No description").split("\n")[0]
                log.info(f"  - {tool.name}: {desc[:80]}...")
            log.info("")
            await self._server.run(
                read_stream,
                write_stream,
                self._server.create_initialization_options(),
            )


async def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "config":
        cli = CliHandler()
        await cli.handle_command(args)
        return

    sys.stderr.write("╔══════════════════════════════════════════════════════════╗\n")
    sys.stderr.write("║                                                          ║\n")
    sys.stderr.write("║           NotebookLM MCP Server v1.1.0                   ║\n")
    sys.stderr.write("║                                                          ║\n")
    sys.stderr.write("║   Chat with Gemini 2.5 through NotebookLM via MCP        ║\n")
    sys.stderr.write("║                                                          ║\n")
    sys.stderr.write("╚══════════════════════════════════════════════════════════╝\n")
    sys.stderr.write("\n")

    import signal

    server: Optional["NotebookLMMCPServer"] = None

    def _make_shutdown_handler(sig_name: str):
        def _handler():
            log.info(f"\nReceived {sig_name}, shutting down gracefully...")
            if server is not None:
                loop = asyncio.get_event_loop()
                loop.create_task(_graceful_exit(server))
        return _handler

    async def _graceful_exit(srv: "NotebookLMMCPServer") -> None:
        try:
            await srv._handlers.cleanup()
        except Exception:
            pass
        log.success("Shutdown complete")
        sys.exit(0)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _make_shutdown_handler(sig.name))
        except NotImplementedError:
            pass

    try:
        server = NotebookLMMCPServer()
        await server.run()
    except Exception as e:
        log.error(f"Fatal error starting server: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
