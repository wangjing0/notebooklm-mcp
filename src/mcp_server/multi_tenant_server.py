import asyncio
import re

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import Any

from ..config import ServerConfig
from ..library.notebook_library import NotebookLibrary
from ..tenant_manager import TenantManager
from ..tools.definitions import build_tool_definitions
from ..tools.handlers import ToolHandlers
from ..utils.logger import log
from .base_server import BaseMCPServer


_USER_ID_RE = re.compile(r"^[ -~]{1,128}$")

_TOOL_DISPATCH: dict[str, str] = {
    "ask_question": "handle_ask_question",
    "list_sessions": "handle_list_sessions",
    "close_session": "handle_close_session",
    "reset_session": "handle_reset_session",
    "get_health": "handle_get_health",
    "setup_auth": "handle_setup_auth",
    "re_auth": "handle_re_auth",
    "add_notebook": "handle_add_notebook",
    "list_notebooks": "handle_list_notebooks",
    "get_notebook": "handle_get_notebook",
    "select_notebook": "handle_select_notebook",
    "update_notebook": "handle_update_notebook",
    "remove_notebook": "handle_remove_notebook",
    "search_notebooks": "handle_search_notebooks",
    "get_library_stats": "handle_get_library_stats",
    "cleanup_data": "handle_cleanup_data",
}

_NO_ARGS_TOOLS = {"list_sessions", "get_health", "list_notebooks", "get_library_stats"}

_SERVER_VERSION = "1.0.0"
_EVICTION_INTERVAL_SECONDS = 300


async def _eviction_loop(tenant_manager: TenantManager) -> None:
    while True:
        await asyncio.sleep(_EVICTION_INTERVAL_SECONDS)
        try:
            evicted = await tenant_manager.evict_idle_tenants()
            if evicted:
                log.info(f"[eviction] Removed {evicted} idle tenant(s)")
        except Exception as e:
            log.warning(f"[eviction] Error during idle eviction: {e}")


def _build_app(tenant_manager: TenantManager) -> Any:
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, Response
    except ImportError as e:
        raise ImportError("fastapi is required for multi-tenant HTTP mode. Run: uv add fastapi uvicorn") from e

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        task = asyncio.create_task(_eviction_loop(tenant_manager))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await tenant_manager.shutdown()

    app = FastAPI(
        title="notebooklm-mcp",
        description="Multi-tenant NotebookLM MCP server",
        lifespan=lifespan,
    )

    _default_library = NotebookLibrary()

    def _jsonrpc_error(req_id: object, code: int, message: str) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

    def _jsonrpc_ok(req_id: object, result: object) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})

    @app.get("/health")
    async def health() -> dict:  # type: ignore[type-arg]
        return {
            "status": "healthy",
            "service": "notebooklm-mcp",
            "active_tenants": tenant_manager.active_tenant_count,
        }

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> Any:
        try:
            body = await request.json()
        except Exception:
            return _jsonrpc_error(None, -32700, "Parse error: invalid JSON")

        req_id = body.get("id")
        if body.get("jsonrpc") != "2.0":
            return _jsonrpc_error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

        method = body.get("method", "")
        params = body.get("params") or {}

        if method.startswith("notifications/"):
            return Response(status_code=204)

        if method == "initialize":
            return _jsonrpc_ok(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "logging": {}},
                "serverInfo": {"name": "notebooklm-mcp", "version": _SERVER_VERSION},
            })

        if method == "tools/list":
            user_id = request.headers.get("X-User-ID", "").strip()
            if user_id and _USER_ID_RE.match(user_id):
                try:
                    tenant = await tenant_manager.get_tenant(user_id)
                    tool_defs = build_tool_definitions(tenant.library)
                except Exception as e:
                    log.warning(f"[MCP] tools/list failed for {user_id}, using defaults: {e}")
                    tool_defs = build_tool_definitions(_default_library)
            else:
                tool_defs = build_tool_definitions(_default_library)
            return _jsonrpc_ok(req_id, {
                "tools": [
                    {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                    for t in tool_defs
                ]
            })

        if method == "tools/call":
            user_id = request.headers.get("X-User-ID", "").strip()
            if not user_id or not _USER_ID_RE.match(user_id):
                return _jsonrpc_error(req_id, -32600, "Missing or invalid X-User-ID header (1-128 printable ASCII chars)")

            tool_name = params.get("name", "")
            arguments = params.get("arguments") or {}

            handler_name = _TOOL_DISPATCH.get(tool_name)
            if not handler_name:
                return _jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}")

            try:
                tenant = await tenant_manager.get_tenant(user_id)
                handlers = ToolHandlers(tenant.sessions, tenant.auth, tenant.library, tenant.config)
                handler = getattr(handlers, handler_name)

                if tool_name in _NO_ARGS_TOOLS:
                    tool_result = await handler()
                else:
                    tool_result = await handler(arguments)

                return _jsonrpc_ok(req_id, tool_result)
            except Exception as e:
                log.error(f"[MCP] tool {tool_name} for {user_id} failed: {e}")
                return _jsonrpc_error(req_id, -32603, f"Internal error: {e}")

        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    return app


class MultiTenantMCPServer(BaseMCPServer):
    def __init__(self, server_config: ServerConfig) -> None:
        super().__init__(server_config)
        self._tenant_manager = TenantManager(server_config)

    def run(self) -> None:
        try:
            import uvicorn
        except ImportError as e:
            raise ImportError("uvicorn is required for HTTP mode. Run: uv add uvicorn") from e

        app = _build_app(self._tenant_manager)
        host = self._server_config.host
        port = self._server_config.port
        log.info(f"Starting multi-tenant HTTP server on {host}:{port}")
        uvicorn.run(app, host=host, port=port)
