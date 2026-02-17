import re
import secrets
import time
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page

from ..auth.auth_manager import AuthManager
from ..config import CONFIG
from ..errors import RateLimitError
from ..types import ProgressCallback, SessionInfo
from ..utils.logger import log
from ..utils.page_utils import snapshot_all_responses, wait_for_latest_answer
from ..utils.stealth_utils import human_type, random_delay

if TYPE_CHECKING:
    from .shared_context_manager import SharedContextManager

_CLOSED_RE = re.compile(r"has been closed|Target .* closed|Browser has been closed|Context .* closed", re.IGNORECASE)


class BrowserSession:
    def __init__(
        self,
        session_id: str,
        shared_context_manager: "SharedContextManager",
        auth_manager: AuthManager,
        notebook_url: str,
    ) -> None:
        self.session_id = session_id
        self.notebook_url = notebook_url
        self.created_at = time.time()
        self.last_activity = time.time()
        self.message_count = 0

        self._shared_ctx = shared_context_manager
        self._auth = auth_manager
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._initialized = False

        log.info(f"BrowserSession {session_id} created")

    async def init(self) -> None:
        if self._initialized:
            log.warning(f"Session {self.session_id} already initialized")
            return

        log.info(f"Initializing session {self.session_id}...")
        try:
            self._context = await self._shared_ctx.get_or_create_context()

            try:
                self._page = await self._context.new_page()
            except Exception as e:
                if _CLOSED_RE.search(str(e)):
                    log.warning("Context was closed. Recreating and retrying...")
                    self._context = await self._shared_ctx.get_or_create_context()
                    self._page = await self._context.new_page()
                else:
                    raise

            log.success("  Created new page")

            log.info(f"  Navigating to: {self.notebook_url}")
            await self._page.goto(self.notebook_url, wait_until="domcontentloaded", timeout=CONFIG.browserTimeout)
            await random_delay(2000, 3000)

            is_auth = await self._auth.validate_cookies_expiry(self._context)
            if not is_auth:
                log.warning(f"  Session {self.session_id} needs authentication")
                if not await self._ensure_authenticated():
                    raise RuntimeError("Failed to authenticate session")
            else:
                log.success("  Session already authenticated")

            log.info("  Restoring sessionStorage...")
            session_data = await self._auth.load_session_storage()
            if session_data:
                await self._restore_session_storage(session_data)

            log.info("  Waiting for NotebookLM interface...")
            await self._wait_for_ready()

            self._initialized = True
            self.update_activity()
            log.success(f"Session {self.session_id} initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize session {self.session_id}: {e}")
            if self._page:
                try:
                    await self._page.close()
                except Exception:
                    pass
                self._page = None
            raise

    async def _wait_for_ready(self) -> None:
        if not self._page:
            raise RuntimeError("Page not initialized")
        try:
            await self._page.wait_for_selector("textarea.query-box-input", timeout=10000, state="visible")
            log.success("  Chat input ready!")
        except Exception:
            try:
                await self._page.wait_for_selector('textarea[aria-label="Feld für Anfragen"]', timeout=5000, state="visible")
                log.success("  Chat input ready (fallback)!")
            except Exception as e:
                log.error(f"  NotebookLM interface not ready: {e}")
                raise RuntimeError("Could not find NotebookLM chat input. Please ensure the notebook page has loaded correctly.")

    async def _ensure_authenticated(self) -> bool:
        if not self._page or not self._context:
            raise RuntimeError("Page not initialized")

        if await self._auth.validate_cookies_expiry(self._context):
            return True

        state_path = await self._auth.get_valid_state_path()
        if state_path:
            await self._auth.load_auth_state(self._context, state_path)
            await self._page.reload(wait_until="domcontentloaded")
            await random_delay(2000, 3000)
            if await self._auth.validate_cookies_expiry(self._context):
                log.success("  Auth state loaded successfully")
                return True

        if CONFIG.autoLoginEnabled:
            success = await self._auth.login_with_credentials(
                self._context, self._page, CONFIG.loginEmail, CONFIG.loginPassword
            )
            if success:
                await self._page.goto(self.notebook_url, wait_until="domcontentloaded")
                await random_delay(2000, 3000)
                return True
            return False
        else:
            log.error("  Auto-login disabled and no valid auth state - manual login required")
            return False

    async def _restore_session_storage(self, session_data: dict) -> None:
        if not self._page or not session_data:
            return
        try:
            target_origin = self._origin(self.notebook_url)
            current_origin = self._origin(self._page.url)
            if current_origin == target_origin:
                await self._page.evaluate("(d) => { for (const [k,v] of Object.entries(d)) sessionStorage.setItem(k,v); }", session_data)
                log.success(f"  SessionStorage restored: {len(session_data)} entries")
        except Exception as e:
            log.warning(f"  Failed to restore sessionStorage: {e}")

    def _origin(self, url: str) -> Optional[str]:
        try:
            p = urlparse(url)
            return f"{p.scheme}://{p.netloc}"
        except Exception:
            return None

    def _page_is_closed(self) -> bool:
        if not self._page:
            return True
        try:
            if hasattr(self._page, "is_closed") and self._page.is_closed():
                return True
            _ = self._page.url
            return False
        except Exception:
            return True

    async def ask(self, question: str, send_progress: Optional[ProgressCallback] = None) -> str:
        async def ask_once() -> str:
            if not self._initialized or self._page_is_closed():
                log.warning("  Session not initialized or page missing - re-initializing...")
                await self.init()

            page = self._page
            assert page is not None

            if send_progress:
                await send_progress("Verifying authentication...", 2, 5)

            if not await self._auth.validate_cookies_expiry(self._context):
                log.warning("  Session expired, re-authenticating...")
                if send_progress:
                    await send_progress("Re-authenticating session...", 2, 5)
                if not await self._ensure_authenticated():
                    raise RuntimeError("Failed to re-authenticate session")

            existing = await snapshot_all_responses(page)
            log.success(f"  Captured {len(existing)} existing responses")

            input_selector = await self._find_chat_input()
            if not input_selector:
                raise RuntimeError("Could not find visible chat input element.")

            if send_progress:
                await send_progress("Typing question with human-like behavior...", 2, 5)
            await human_type(page, input_selector, question, with_typos=True)
            await random_delay(500, 1000)

            if send_progress:
                await send_progress("Submitting question...", 3, 5)
            await page.keyboard.press("Enter")
            await random_delay(1000, 1500)

            if send_progress:
                await send_progress("Waiting for NotebookLM response (streaming detection active)...", 3, 5)

            answer = await wait_for_latest_answer(
                page,
                question=question,
                timeout_ms=120000,
                poll_interval_ms=1000,
                ignore_texts=existing,
            )

            if not answer:
                raise RuntimeError("Timeout waiting for response from NotebookLM")

            if await self._detect_rate_limit():
                raise RateLimitError("NotebookLM rate limit reached (50 queries/day for free accounts)")

            self.message_count += 1
            self.update_activity()
            log.success(f"Received answer ({len(answer)} chars, {self.message_count} total messages)")
            return answer

        try:
            return await ask_once()
        except Exception as e:
            msg = str(e)
            if _CLOSED_RE.search(msg):
                log.warning("  Detected closed page/context. Recovering session and retrying ask...")
                try:
                    self._initialized = False
                    if self._page:
                        try:
                            await self._page.close()
                        except Exception:
                            pass
                    self._page = None
                    await self.init()
                    return await ask_once()
                except Exception as e2:
                    log.error(f"Recovery failed: {e2}")
                    raise e2
            log.error(f"Failed to ask question: {msg}")
            raise

    async def _find_chat_input(self) -> Optional[str]:
        if not self._page:
            return None
        for sel in ["textarea.query-box-input", 'textarea[aria-label="Feld für Anfragen"]']:
            try:
                el = await self._page.query_selector(sel)
                if el and await el.is_visible():
                    log.success(f"  Found chat input: {sel}")
                    return sel
            except Exception:
                continue
        log.error("  Could not find visible chat input")
        return None

    async def _detect_rate_limit(self) -> bool:
        if not self._page:
            return False
        keywords = ["rate limit", "limit exceeded", "quota exhausted", "daily limit", "limit reached", "too many requests", "quota", "query limit"]
        error_selectors = [".error-message", ".error-container", "[role='alert']", ".rate-limit-message"]
        for sel in error_selectors:
            try:
                els = await self._page.query_selector_all(sel)
                for el in els:
                    try:
                        text = (await el.inner_text()).lower()
                        if any(k in text for k in keywords):
                            log.error(f"Rate limit detected: {text[:100]}")
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    async def reset(self) -> None:
        async def reset_once() -> None:
            if not self._initialized or self._page_is_closed():
                await self.init()
            assert self._page is not None
            log.info(f"Resetting chat history for session {self.session_id}...")
            await self._page.reload(wait_until="domcontentloaded")
            await random_delay(2000, 3000)
            await self._wait_for_ready()
            self.message_count = 0
            self.update_activity()
            log.success(f"Chat history reset for session {self.session_id}")

        try:
            await reset_once()
        except Exception as e:
            msg = str(e)
            if _CLOSED_RE.search(msg):
                log.warning("  Detected closed page/context during reset. Recovering...")
                self._initialized = False
                if self._page:
                    try:
                        await self._page.close()
                    except Exception:
                        pass
                self._page = None
                await self.init()
                await reset_once()
            else:
                log.error(f"Failed to reset: {msg}")
                raise

    async def close(self) -> None:
        log.info(f"Closing session {self.session_id}...")
        if self._page:
            try:
                await self._page.close()
                self._page = None
                log.success("  Page closed")
            except Exception as e:
                log.warning(f"  Error closing page: {e}")
        self._initialized = False
        log.success(f"Session {self.session_id} closed")

    def update_activity(self) -> None:
        self.last_activity = time.time()

    def is_expired(self, timeout_seconds: float) -> bool:
        return (time.time() - self.last_activity) > timeout_seconds

    def get_info(self) -> SessionInfo:
        now = time.time()
        return {
            "id": self.session_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "age_seconds": now - self.created_at,
            "inactive_seconds": now - self.last_activity,
            "message_count": self.message_count,
            "notebook_url": self.notebook_url,
        }

    def is_initialized(self) -> bool:
        return self._initialized and self._page is not None
