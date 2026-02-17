import time
from typing import Any, Optional

from ..auth.auth_manager import AuthManager
from ..config import CONFIG, apply_browser_options
from ..errors import RateLimitError
from ..library.notebook_library import NotebookLibrary
from ..session.session_manager import SessionManager
from ..utils.cleanup_manager import CleanupManager
from ..utils.logger import log
from ..types import ProgressCallback

FOLLOW_UP_REMINDER = (
    "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know? You can always ask another question "
    "using the same session ID! Think about it carefully: before you reply to the user, review "
    "their original request and this answer. If anything is still unclear or missing, ask me "
    "another question first."
)


class ToolHandlers:
    def __init__(
        self,
        session_manager: SessionManager,
        auth_manager: AuthManager,
        library: NotebookLibrary,
    ) -> None:
        self._sessions = session_manager
        self._auth = auth_manager
        self._library = library

    async def handle_ask_question(
        self,
        args: dict,
        send_progress: Optional[ProgressCallback] = None,
    ) -> dict:
        question: str = args["question"]
        session_id: Optional[str] = args.get("session_id")
        notebook_id: Optional[str] = args.get("notebook_id")
        notebook_url: Optional[str] = args.get("notebook_url")
        show_browser: Optional[bool] = args.get("show_browser")
        browser_options: Optional[dict] = args.get("browser_options")

        log.info("[TOOL] ask_question called")
        log.info(f'  Question: "{question[:100]}"...')
        if session_id:
            log.info(f"  Session ID: {session_id}")
        if notebook_id:
            log.info(f"  Notebook ID: {notebook_id}")
        if notebook_url:
            log.info(f"  Notebook URL: {notebook_url}")

        try:
            resolved_url = notebook_url
            if not resolved_url and notebook_id:
                notebook = self._library.increment_use_count(notebook_id)
                if not notebook:
                    raise ValueError(f"Notebook not found in library: {notebook_id}")
                resolved_url = notebook["url"]
                log.info(f"  Resolved notebook: {notebook['name']}")
            elif not resolved_url:
                active = self._library.get_active_notebook()
                if active:
                    notebook = self._library.increment_use_count(active["id"])
                    if not notebook:
                        raise ValueError(f"Active notebook not found: {active['id']}")
                    resolved_url = notebook["url"]
                    log.info(f"  Using active notebook: {notebook['name']}")

            if send_progress:
                await send_progress("Getting or creating browser session...", 1, 5)

            original_headless = CONFIG.headless
            original_timeout = CONFIG.browserTimeout
            _cfg = apply_browser_options(CONFIG, browser_options, show_browser)
            CONFIG.headless = _cfg.headless
            CONFIG.browserTimeout = _cfg.browserTimeout

            override_headless: Optional[bool] = None
            if show_browser is not None:
                override_headless = show_browser
            elif browser_options and browser_options.get("show") is not None:
                override_headless = browser_options["show"]
            elif browser_options and browser_options.get("headless") is not None:
                override_headless = not browser_options["headless"]

            try:
                session = await self._sessions.get_or_create_session(
                    session_id, resolved_url, override_headless
                )

                if send_progress:
                    await send_progress("Asking question to NotebookLM...", 2, 5)

                raw_answer = await session.ask(question, send_progress)
                answer = raw_answer.rstrip() + FOLLOW_UP_REMINDER

                info = session.get_info()
                result = {
                    "status": "success",
                    "question": question,
                    "answer": answer,
                    "session_id": session.session_id,
                    "notebook_url": session.notebook_url,
                    "session_info": {
                        "age_seconds": info["age_seconds"],
                        "message_count": info["message_count"],
                        "last_activity": info["last_activity"],
                    },
                }

                if send_progress:
                    await send_progress("Question answered successfully!", 5, 5)

                log.success("[TOOL] ask_question completed successfully")
                return {"success": True, "data": result}
            finally:
                CONFIG.headless = original_headless
                CONFIG.browserTimeout = original_timeout

        except Exception as e:
            msg = str(e)
            if isinstance(e, RateLimitError) or "rate limit" in msg.lower():
                log.error("[TOOL] Rate limit detected")
                return {
                    "success": False,
                    "error": (
                        "NotebookLM rate limit reached (50 queries/day for free accounts).\n\n"
                        "You can:\n"
                        "1. Use the 're_auth' tool to login with a different Google account\n"
                        "2. Wait until tomorrow for the quota to reset\n"
                        "3. Upgrade to Google AI Pro/Ultra for 5x higher limits\n\n"
                        f"Original error: {msg}"
                    ),
                }
            log.error(f"[TOOL] ask_question failed: {msg}")
            return {"success": False, "error": msg}

    async def handle_list_sessions(self) -> dict:
        log.info("[TOOL] list_sessions called")
        try:
            stats = self._sessions.get_stats()
            sessions = self._sessions.get_all_sessions_info()
            result = {
                "active_sessions": stats["active_sessions"],
                "max_sessions": stats["max_sessions"],
                "session_timeout": stats["session_timeout"],
                "oldest_session_seconds": stats["oldest_session_seconds"],
                "total_messages": stats["total_messages"],
                "sessions": [
                    {
                        "id": s["id"],
                        "created_at": s["created_at"],
                        "last_activity": s["last_activity"],
                        "age_seconds": s["age_seconds"],
                        "inactive_seconds": s["inactive_seconds"],
                        "message_count": s["message_count"],
                        "notebook_url": s["notebook_url"],
                    }
                    for s in sessions
                ],
            }
            log.success(f"[TOOL] list_sessions completed ({result['active_sessions']} sessions)")
            return {"success": True, "data": result}
        except Exception as e:
            log.error(f"[TOOL] list_sessions failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_close_session(self, args: dict) -> dict:
        session_id: str = args["session_id"]
        log.info(f"[TOOL] close_session called: {session_id}")
        try:
            closed = await self._sessions.close_session(session_id)
            if closed:
                log.success("[TOOL] close_session completed")
                return {"success": True, "data": {"status": "success", "message": f"Session {session_id} closed successfully", "session_id": session_id}}
            else:
                log.warning(f"[TOOL] Session {session_id} not found")
                return {"success": False, "error": f"Session {session_id} not found"}
        except Exception as e:
            log.error(f"[TOOL] close_session failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_reset_session(self, args: dict) -> dict:
        session_id: str = args["session_id"]
        log.info(f"[TOOL] reset_session called: {session_id}")
        try:
            session = self._sessions.get_session(session_id)
            if not session:
                log.warning(f"[TOOL] Session {session_id} not found")
                return {"success": False, "error": f"Session {session_id} not found"}
            await session.reset()
            log.success("[TOOL] reset_session completed")
            return {"success": True, "data": {"status": "success", "message": f"Session {session_id} reset successfully", "session_id": session_id}}
        except Exception as e:
            log.error(f"[TOOL] reset_session failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_get_health(self) -> dict:
        log.info("[TOOL] get_health called")
        try:
            state_path = await self._auth.get_valid_state_path()
            authenticated = state_path is not None
            stats = self._sessions.get_stats()
            result: dict[str, Any] = {
                "status": "ok",
                "authenticated": authenticated,
                "notebook_url": CONFIG.notebookUrl or "not configured",
                "active_sessions": stats["active_sessions"],
                "max_sessions": stats["max_sessions"],
                "session_timeout": stats["session_timeout"],
                "total_messages": stats["total_messages"],
                "headless": CONFIG.headless,
                "auto_login_enabled": CONFIG.autoLoginEnabled,
                "stealth_enabled": CONFIG.stealthEnabled,
            }
            if not authenticated:
                result["troubleshooting_tip"] = (
                    "For fresh start with clean browser session: Close all Chrome instances "
                    "→ cleanup_data(confirm=true, preserve_library=true) → setup_auth"
                )
            log.success("[TOOL] get_health completed")
            return {"success": True, "data": result}
        except Exception as e:
            log.error(f"[TOOL] get_health failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_setup_auth(
        self,
        args: dict,
        send_progress: Optional[ProgressCallback] = None,
    ) -> dict:
        show_browser: Optional[bool] = args.get("show_browser")
        browser_options: Optional[dict] = args.get("browser_options")

        if send_progress:
            await send_progress("Initializing authentication setup...", 0, 10)

        log.info("[TOOL] setup_auth called")
        start = time.time()

        original_headless = CONFIG.headless
        original_timeout = CONFIG.browserTimeout
        _cfg = apply_browser_options(CONFIG, browser_options, show_browser)
        CONFIG.headless = _cfg.headless
        CONFIG.browserTimeout = _cfg.browserTimeout

        try:
            if send_progress:
                await send_progress("Preparing authentication browser...", 1, 10)
            if send_progress:
                await send_progress("Opening browser window...", 2, 10)

            success = await self._auth.perform_setup(send_progress)
            duration = time.time() - start

            if success:
                if send_progress:
                    await send_progress("Authentication saved successfully!", 10, 10)
                log.success(f"[TOOL] setup_auth completed ({duration:.1f}s)")
                return {
                    "success": True,
                    "data": {
                        "status": "authenticated",
                        "message": "Successfully authenticated and saved browser state",
                        "authenticated": True,
                        "duration_seconds": duration,
                    },
                }
            else:
                log.error(f"[TOOL] setup_auth failed ({duration:.1f}s)")
                return {"success": False, "error": "Authentication failed or was cancelled"}
        except Exception as e:
            duration = time.time() - start
            log.error(f"[TOOL] setup_auth failed: {e} ({duration:.1f}s)")
            return {"success": False, "error": str(e)}
        finally:
            CONFIG.headless = original_headless
            CONFIG.browserTimeout = original_timeout

    async def handle_re_auth(
        self,
        args: dict,
        send_progress: Optional[ProgressCallback] = None,
    ) -> dict:
        show_browser: Optional[bool] = args.get("show_browser")
        browser_options: Optional[dict] = args.get("browser_options")

        if send_progress:
            await send_progress("Preparing re-authentication...", 0, 12)

        log.info("[TOOL] re_auth called")
        start = time.time()

        original_headless = CONFIG.headless
        original_timeout = CONFIG.browserTimeout
        _cfg = apply_browser_options(CONFIG, browser_options, show_browser)
        CONFIG.headless = _cfg.headless
        CONFIG.browserTimeout = _cfg.browserTimeout

        try:
            if send_progress:
                await send_progress("Closing all active sessions...", 1, 12)
            await self._sessions.close_all_sessions()

            if send_progress:
                await send_progress("Clearing authentication data...", 2, 12)
            await self._auth.clear_all_auth_data()

            if send_progress:
                await send_progress("Starting fresh authentication...", 3, 12)
            success = await self._auth.perform_setup(send_progress)
            duration = time.time() - start

            if success:
                if send_progress:
                    await send_progress("Re-authentication complete!", 12, 12)
                log.success(f"[TOOL] re_auth completed ({duration:.1f}s)")
                return {
                    "success": True,
                    "data": {
                        "status": "authenticated",
                        "message": "Successfully re-authenticated with new account. All previous sessions have been closed.",
                        "authenticated": True,
                        "duration_seconds": duration,
                    },
                }
            else:
                log.error(f"[TOOL] re_auth failed ({duration:.1f}s)")
                return {"success": False, "error": "Re-authentication failed or was cancelled"}
        except Exception as e:
            duration = time.time() - start
            log.error(f"[TOOL] re_auth failed: {e} ({duration:.1f}s)")
            return {"success": False, "error": str(e)}
        finally:
            CONFIG.headless = original_headless
            CONFIG.browserTimeout = original_timeout

    async def handle_add_notebook(self, args: dict) -> dict:
        log.info(f"[TOOL] add_notebook called: {args.get('name')}")
        try:
            notebook = self._library.add_notebook(args)
            log.success(f"[TOOL] add_notebook completed: {notebook['id']}")
            return {"success": True, "data": {"notebook": notebook}}
        except Exception as e:
            log.error(f"[TOOL] add_notebook failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_list_notebooks(self) -> dict:
        log.info("[TOOL] list_notebooks called")
        try:
            notebooks = self._library.list_notebooks()
            log.success(f"[TOOL] list_notebooks completed ({len(notebooks)} notebooks)")
            return {"success": True, "data": {"notebooks": notebooks}}
        except Exception as e:
            log.error(f"[TOOL] list_notebooks failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_get_notebook(self, args: dict) -> dict:
        nb_id: str = args["id"]
        log.info(f"[TOOL] get_notebook called: {nb_id}")
        try:
            notebook = self._library.get_notebook(nb_id)
            if not notebook:
                log.warning(f"[TOOL] Notebook not found: {nb_id}")
                return {"success": False, "error": f"Notebook not found: {nb_id}"}
            log.success(f"[TOOL] get_notebook completed: {notebook['name']}")
            return {"success": True, "data": {"notebook": notebook}}
        except Exception as e:
            log.error(f"[TOOL] get_notebook failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_select_notebook(self, args: dict) -> dict:
        nb_id: str = args["id"]
        log.info(f"[TOOL] select_notebook called: {nb_id}")
        try:
            notebook = self._library.select_notebook(nb_id)
            log.success(f"[TOOL] select_notebook completed: {notebook['name']}")
            return {"success": True, "data": {"notebook": notebook}}
        except Exception as e:
            log.error(f"[TOOL] select_notebook failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_update_notebook(self, args: dict) -> dict:
        log.info(f"[TOOL] update_notebook called: {args.get('id')}")
        try:
            notebook = self._library.update_notebook(args)
            log.success(f"[TOOL] update_notebook completed: {notebook['name']}")
            return {"success": True, "data": {"notebook": notebook}}
        except Exception as e:
            log.error(f"[TOOL] update_notebook failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_remove_notebook(self, args: dict) -> dict:
        nb_id: str = args["id"]
        log.info(f"[TOOL] remove_notebook called: {nb_id}")
        try:
            notebook = self._library.get_notebook(nb_id)
            if not notebook:
                log.warning(f"[TOOL] Notebook not found: {nb_id}")
                return {"success": False, "error": f"Notebook not found: {nb_id}"}
            removed = self._library.remove_notebook(nb_id)
            if removed:
                closed = await self._sessions.close_sessions_for_notebook(notebook["url"])
                log.success("[TOOL] remove_notebook completed")
                return {"success": True, "data": {"removed": True, "closed_sessions": closed}}
            return {"success": False, "error": f"Notebook not found: {nb_id}"}
        except Exception as e:
            log.error(f"[TOOL] remove_notebook failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_search_notebooks(self, args: dict) -> dict:
        query: str = args["query"]
        log.info(f'[TOOL] search_notebooks called: "{query}"')
        try:
            notebooks = self._library.search_notebooks(query)
            log.success(f"[TOOL] search_notebooks completed ({len(notebooks)} results)")
            return {"success": True, "data": {"notebooks": notebooks}}
        except Exception as e:
            log.error(f"[TOOL] search_notebooks failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_get_library_stats(self) -> dict:
        log.info("[TOOL] get_library_stats called")
        try:
            stats = self._library.get_stats()
            log.success("[TOOL] get_library_stats completed")
            return {"success": True, "data": stats}
        except Exception as e:
            log.error(f"[TOOL] get_library_stats failed: {e}")
            return {"success": False, "error": str(e)}

    async def handle_cleanup_data(self, args: dict) -> dict:
        confirm: bool = args["confirm"]
        preserve_library: bool = args.get("preserve_library", False)
        log.info(f"[TOOL] cleanup_data called (confirm={confirm}, preserve_library={preserve_library})")

        manager = CleanupManager()
        try:
            mode = "deep"
            if not confirm:
                preview = await manager.get_cleanup_paths(mode, preserve_library)
                log.info(f"  Found {len(preview['total_paths'])} items ({manager.format_bytes(preview['total_size_bytes'])})")
                return {
                    "success": True,
                    "data": {
                        "status": "preview",
                        "mode": mode,
                        "preview": {
                            "categories": preview["categories"],
                            "totalPaths": len(preview["total_paths"]),
                            "totalSizeBytes": preview["total_size_bytes"],
                        },
                    },
                }
            else:
                result = await manager.perform_cleanup(mode, preserve_library)
                if result["success"]:
                    log.success(f"[TOOL] cleanup_data completed - deleted {len(result['deleted_paths'])} items")
                else:
                    log.warning(f"[TOOL] cleanup_data completed with {len(result['failed_paths'])} errors")
                return {
                    "success": result["success"],
                    "data": {
                        "status": "completed" if result["success"] else "partial",
                        "mode": mode,
                        "result": {
                            "deletedPaths": result["deleted_paths"],
                            "failedPaths": result["failed_paths"],
                            "totalSizeBytes": result["total_size_bytes"],
                            "categorySummary": result["category_summary"],
                        },
                    },
                }
        except Exception as e:
            log.error(f"[TOOL] cleanup_data failed: {e}")
            return {"success": False, "error": str(e)}

    async def cleanup(self) -> None:
        log.info("Cleaning up tool handlers...")
        await self._sessions.close_all_sessions()
        log.success("Tool handlers cleanup complete")
