import asyncio
import secrets
from typing import Optional

from ..auth.auth_manager import AuthManager
from ..config import CONFIG
from ..types import SessionInfo
from ..utils.logger import log
from .browser_session import BrowserSession
from .shared_context_manager import SharedContextManager


class SessionManager:
    def __init__(self, auth_manager: AuthManager) -> None:
        self._auth = auth_manager
        self._shared_ctx = SharedContextManager(auth_manager)
        self._sessions: dict[str, BrowserSession] = {}
        self._max_sessions = CONFIG.maxSessions
        self._session_timeout = CONFIG.sessionTimeout
        self._cleanup_task: Optional[asyncio.Task] = None

        log.info("SessionManager initialized")
        log.info(f"  Max sessions: {self._max_sessions}")
        log.info(f"  Timeout: {self._session_timeout}s ({self._session_timeout // 60} minutes)")

        cleanup_interval = max(60, min(self._session_timeout // 2, 300))
        self._cleanup_interval = cleanup_interval
        self._start_cleanup_loop()

    def _start_cleanup_loop(self) -> None:
        async def loop():
            while True:
                await asyncio.sleep(self._cleanup_interval)
                try:
                    await self.cleanup_inactive_sessions()
                except Exception as e:
                    log.warning(f"Error during automatic session cleanup: {e}")

        try:
            loop_obj = asyncio.get_event_loop()
            if loop_obj.is_running():
                self._cleanup_task = asyncio.ensure_future(loop())
        except RuntimeError:
            pass

    def _generate_session_id(self) -> str:
        return secrets.token_hex(4)

    async def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        notebook_url: Optional[str] = None,
        override_headless: Optional[bool] = None,
    ) -> BrowserSession:
        target_url = (notebook_url or CONFIG.notebookUrl or "").strip()
        if not target_url:
            raise ValueError("Notebook URL is required to create a session")
        if not target_url.startswith("http"):
            raise ValueError("Notebook URL must be an absolute URL")

        if not session_id:
            session_id = self._generate_session_id()
            log.info(f"Auto-generated session ID: {session_id}")

        if override_headless is not None and self._shared_ctx.needs_headless_mode_change(override_headless):
            log.warning("Browser visibility changed - closing all sessions to recreate browser context...")
            await self.close_all_sessions()

        if session_id in self._sessions:
            session = self._sessions[session_id]
            if session.notebook_url != target_url:
                log.warning(f"Replacing session {session_id} with new notebook URL")
                await session.close()
                del self._sessions[session_id]
            else:
                session.update_activity()
                log.success(f"Reusing existing session {session_id}")
                return session

        if len(self._sessions) >= self._max_sessions:
            log.warning(f"Max sessions ({self._max_sessions}) reached, cleaning up...")
            if not await self._cleanup_oldest():
                raise RuntimeError(f"Max sessions ({self._max_sessions}) reached and no inactive sessions to clean up")

        log.info(f"Creating new session {session_id}...")
        try:
            await self._shared_ctx.get_or_create_context(override_headless)
            session = BrowserSession(session_id, self._shared_ctx, self._auth, target_url)
            await session.init()
            self._sessions[session_id] = session
            log.success(f"Session {session_id} created ({len(self._sessions)}/{self._max_sessions} active)")
            return session
        except Exception as e:
            log.error(f"Failed to create session: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            log.warning(f"Session {session_id} not found")
            return False
        session = self._sessions.pop(session_id)
        await session.close()
        log.success(f"Session {session_id} closed ({len(self._sessions)}/{self._max_sessions} active)")
        return True

    async def cleanup_inactive_sessions(self) -> int:
        inactive = [sid for sid, s in self._sessions.items() if s.is_expired(self._session_timeout)]
        if not inactive:
            return 0
        log.warning(f"Cleaning up {len(inactive)} inactive sessions...")
        for sid in inactive:
            try:
                session = self._sessions.pop(sid)
                await session.close()
            except Exception as e:
                log.warning(f"  Error cleaning up {sid}: {e}")
        log.success(f"Cleaned up {len(inactive)} sessions ({len(self._sessions)}/{self._max_sessions} active)")
        return len(inactive)

    async def _cleanup_oldest(self) -> bool:
        if not self._sessions:
            return False
        oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].created_at)
        session = self._sessions.pop(oldest_id)
        age = __import__("time").time() - session.created_at
        log.warning(f"Removing oldest session {oldest_id} (age: {age:.0f}s)")
        await session.close()
        return True

    async def close_sessions_for_notebook(self, notebook_url: str) -> int:
        matching = [sid for sid, s in self._sessions.items() if s.notebook_url == notebook_url]
        for sid in matching:
            try:
                session = self._sessions.pop(sid)
                await session.close()
            except Exception as e:
                log.warning(f"  Error closing session {sid}: {e}")
        if matching:
            log.success(f"Closed {len(matching)} sessions for notebook URL")
        return len(matching)

    async def close_all_sessions(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

        if not self._sessions:
            log.warning("Closing shared context (no active sessions)...")
            await self._shared_ctx.close_context()
            log.success("All sessions closed")
            return

        log.warning(f"Closing all {len(self._sessions)} sessions...")
        for sid in list(self._sessions.keys()):
            try:
                session = self._sessions.pop(sid)
                await session.close()
            except Exception as e:
                log.warning(f"  Error closing {sid}: {e}")

        await self._shared_ctx.close_context()
        log.success("All sessions closed")

    def get_all_sessions_info(self) -> list[SessionInfo]:
        return [s.get_info() for s in self._sessions.values()]

    def get_stats(self) -> dict:
        infos = self.get_all_sessions_info()
        total_messages = sum(i["message_count"] for i in infos)
        oldest = max((i["age_seconds"] for i in infos), default=0)
        return {
            "active_sessions": len(infos),
            "max_sessions": self._max_sessions,
            "session_timeout": self._session_timeout,
            "oldest_session_seconds": oldest,
            "total_messages": total_messages,
        }
