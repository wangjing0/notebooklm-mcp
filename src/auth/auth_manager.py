import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page

from ..config import CONFIG, NOTEBOOKLM_AUTH_URL
from ..types import ProgressCallback
from ..utils.logger import log
from ..utils.stealth_utils import human_type, random_delay, random_mouse_movement, realistic_click

CRITICAL_COOKIE_NAMES = [
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "OSID", "__Secure-OSID", "__Secure-1PSID", "__Secure-3PSID",
]


class AuthManager:
    def __init__(self) -> None:
        self._state_path = Path(CONFIG.browserStateDir) / "state.json"
        self._session_path = Path(CONFIG.browserStateDir) / "session.json"

    async def save_browser_state(self, context: BrowserContext, page: Optional[Page] = None) -> bool:
        try:
            await context.storage_state(path=str(self._state_path))
            if page:
                try:
                    session_data: str = await page.evaluate("""() => {
                        const s = {};
                        for (let i = 0; i < sessionStorage.length; i++) {
                            const k = sessionStorage.key(i);
                            if (k) s[k] = sessionStorage.getItem(k) || '';
                        }
                        return JSON.stringify(s);
                    }""")
                    self._session_path.write_text(session_data, encoding="utf-8")
                    entries = len(json.loads(session_data))
                    log.success(f"Browser state saved (sessionStorage: {entries} entries)")
                except Exception as e:
                    log.warning(f"State saved, but sessionStorage failed: {e}")
            else:
                log.success("Browser state saved")
            return True
        except Exception as e:
            log.error(f"Failed to save browser state: {e}")
            return False

    def has_saved_state(self) -> bool:
        return self._state_path.exists()

    def get_state_path(self) -> Optional[str]:
        return str(self._state_path) if self._state_path.exists() else None

    async def get_valid_state_path(self) -> Optional[str]:
        if not self.has_saved_state():
            return None
        if await self.is_state_expired():
            log.warning("Saved state is expired (>24h old)")
            return None
        return str(self._state_path)

    async def load_session_storage(self) -> Optional[dict]:
        try:
            data = self._session_path.read_text(encoding="utf-8")
            session_data = json.loads(data)
            log.success(f"Loaded sessionStorage ({len(session_data)} entries)")
            return session_data
        except Exception as e:
            log.warning(f"Failed to load sessionStorage: {e}")
            return None

    async def validate_state(self, context: BrowserContext) -> bool:
        try:
            cookies = await context.cookies()
            if not cookies:
                log.warning("No cookies found in state")
                return False
            google_cookies = [c for c in cookies if "google.com" in c.get("domain", "")]
            if not google_cookies:
                log.warning("No Google cookies found")
                return False
            current_time = time.time()
            for cookie in google_cookies:
                expires = cookie.get("expires", -1)
                if expires is not None and expires != -1 and expires < current_time:
                    log.warning(f"Cookie '{cookie['name']}' has expired")
                    return False
            log.success("State validation passed")
            return True
        except Exception as e:
            log.warning(f"State validation failed: {e}")
            return False

    async def validate_cookies_expiry(self, context: BrowserContext) -> bool:
        try:
            cookies = await context.cookies()
            if not cookies:
                log.warning("No cookies found")
                return False
            critical = [c for c in cookies if c.get("name") in CRITICAL_COOKIE_NAMES]
            if not critical:
                log.warning("No critical auth cookies found")
                return False
            current_time = time.time()
            expired = []
            for c in critical:
                expires = c.get("expires", -1)
                if expires is not None and expires != -1 and expires < current_time:
                    expired.append(c["name"])
            if expired:
                log.warning(f"Expired cookies: {', '.join(expired)}")
                return False
            log.success(f"All {len(critical)} critical cookies are valid")
            return True
        except Exception as e:
            log.warning(f"Cookie validation failed: {e}")
            return False

    async def is_state_expired(self) -> bool:
        try:
            stat = self._state_path.stat()
            age = time.time() - stat.st_mtime
            if age > 24 * 3600:
                log.warning(f"Saved state is {age / 3600:.1f}h old (max: 24h)")
                return True
            return False
        except Exception:
            return True

    async def perform_login(self, page: Page, send_progress: Optional[ProgressCallback] = None) -> bool:
        try:
            log.info("Opening Google login page...")
            if send_progress:
                await send_progress("Navigating to Google login...", 3, 10)

            await page.goto(NOTEBOOKLM_AUTH_URL, timeout=60000)

            if send_progress:
                await send_progress("Waiting for manual login (up to 10 minutes)...", 4, 10)

            log.warning("Waiting for login (up to 10 minutes)...")
            check_interval = 1.0
            max_attempts = 600
            last_progress = 0

            for attempt in range(max_attempts):
                try:
                    current_url = page.url
                    elapsed = int(attempt * check_interval)
                    if send_progress and elapsed - last_progress >= 10:
                        last_progress = elapsed
                        step = min(8, 4 + elapsed // 60)
                        await send_progress(f"Waiting for login... ({elapsed}s elapsed)", step, 10)

                    if current_url.startswith("https://notebooklm.google.com/"):
                        if send_progress:
                            await send_progress("Login successful! NotebookLM detected!", 9, 10)
                        log.success("Login successful! NotebookLM URL detected.")
                        await asyncio.sleep(2)
                        return True

                    if "accounts.google.com" in current_url and attempt % 30 == 0 and attempt > 0:
                        log.warning(f"Still waiting... ({elapsed}s elapsed)")

                    await asyncio.sleep(check_interval)
                except Exception:
                    await asyncio.sleep(check_interval)
                    continue

            current_url = page.url
            if current_url.startswith("https://notebooklm.google.com/"):
                if send_progress:
                    await send_progress("Login successful (detected on timeout check)!", 9, 10)
                log.success("Login successful (detected on timeout check)")
                return True

            log.error("Login verification failed - timeout reached")
            return False
        except Exception as e:
            log.error(f"Login failed: {e}")
            return False

    async def login_with_credentials(
        self,
        context: BrowserContext,
        page: Page,
        email: str,
        password: str,
    ) -> bool:
        masked = self._mask_email(email)
        log.warning(f"Attempting automatic login for {masked}...")

        try:
            await page.goto(NOTEBOOKLM_AUTH_URL, wait_until="domcontentloaded", timeout=CONFIG.browserTimeout)
        except Exception:
            log.warning("Page load timeout (continuing anyway)")

        deadline = time.time() + CONFIG.autoLoginTimeoutMs / 1000

        if await self._wait_for_notebook(page, CONFIG.autoLoginTimeoutMs):
            log.success("Already authenticated")
            await self.save_browser_state(context, page)
            return True

        log.warning("Not authenticated yet, proceeding with login...")

        if await self._handle_account_chooser(page, email):
            log.success("Account selected from chooser")
            if await self._wait_for_notebook(page, CONFIG.autoLoginTimeoutMs):
                log.success("Automatic login successful")
                await self.save_browser_state(context, page)
                return True

        await self._fill_identifier(page, email)

        wait_attempts = 0
        while time.time() < deadline:
            if await self._fill_password(page, password):
                break
            wait_attempts += 1
            if wait_attempts % 20 == 0:
                secs = wait_attempts * 0.5
                rem = deadline - time.time()
                log.warning(f"Still waiting for password field... ({secs:.0f}s elapsed, {rem:.0f}s remaining)")
            if "challenge" in page.url:
                log.warning("Additional verification required (Google challenge page)")
                return False
            await asyncio.sleep(0.5)

        if await self._wait_for_redirect(page, deadline):
            log.success("Automatic login successful")
            await self.save_browser_state(context, page)
            return True

        log.error("Automatic login timed out")
        try:
            screenshot_path = Path(CONFIG.dataDir) / f"login_failed_{int(time.time())}.png"
            await page.screenshot(path=str(screenshot_path))
            log.info(f"Screenshot saved: {screenshot_path}")
        except Exception:
            pass
        return False

    async def _wait_for_redirect(self, page: Page, deadline: float) -> bool:
        while time.time() < deadline:
            try:
                if page.url.startswith("https://notebooklm.google.com/"):
                    log.success("NotebookLM URL detected!")
                    await asyncio.sleep(2)
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def _wait_for_notebook(self, page: Page, timeout_ms: int) -> bool:
        end = time.time() + timeout_ms / 1000
        while time.time() < end:
            try:
                if page.url.startswith("https://notebooklm.google.com/"):
                    return True
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    async def _handle_account_chooser(self, page: Page, email: str) -> bool:
        try:
            items = await page.query_selector_all("div[data-identifier], li[data-identifier]")
            if items:
                for item in items:
                    ident = (await item.get_attribute("data-identifier") or "").lower()
                    if ident == email.lower():
                        await item.click()
                        await random_delay(150, 320)
                        await asyncio.sleep(0.5)
                        return True
        except Exception:
            pass
        return False

    async def _fill_identifier(self, page: Page, email: str) -> bool:
        for selector in ["input#identifierId", "input[name='identifier']", "input[type='email']"]:
            try:
                field = await page.wait_for_selector(selector, state="attached", timeout=3000)
                if not field or not await field.is_visible():
                    continue
                box = await field.bounding_box()
                if box:
                    await random_mouse_movement(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await random_delay(200, 500)
                await realistic_click(page, selector, False)
                await human_type(page, selector, email, with_typos=False)
                await random_delay(400, 1200)

                for next_sel in ["button:has-text('Next')", "button:has-text('Weiter')", "#identifierNext"]:
                    try:
                        btn = page.locator(next_sel)
                        if await btn.count() > 0:
                            await realistic_click(page, next_sel, True)
                            break
                    except Exception:
                        continue
                else:
                    await field.press("Enter")

                await random_delay(800, 1500)
                return True
            except Exception:
                continue
        return False

    async def _fill_password(self, page: Page, password: str) -> bool:
        for selector in ["input[name='Passwd']", "input[type='password']"]:
            try:
                field = await page.query_selector(selector)
                if not field:
                    continue
                box = await field.bounding_box()
                if box:
                    await random_mouse_movement(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await random_delay(300, 700)
                await realistic_click(page, selector, False)
                await human_type(page, selector, password, with_typos=False)
                await random_delay(300, 1000)

                for next_sel in ["button:has-text('Next')", "button:has-text('Weiter')", "#passwordNext"]:
                    try:
                        btn = page.locator(next_sel)
                        if await btn.count() > 0:
                            await realistic_click(page, next_sel, True)
                            break
                    except Exception:
                        continue
                else:
                    await field.press("Enter")

                await random_delay(800, 1500)
                return True
            except Exception:
                continue
        return False

    async def perform_setup(self, send_progress: Optional[ProgressCallback] = None, override_headless: Optional[bool] = None) -> bool:
        from playwright.async_api import async_playwright

        show_browser = override_headless if override_headless is not None else True

        try:
            log.info("Preparing for new account authentication...")
            if send_progress:
                await send_progress("Clearing old authentication data...", 1, 10)
            await self.clear_all_auth_data()

            log.info("Launching persistent browser for interactive setup...")
            if send_progress:
                await send_progress("Launching persistent browser...", 2, 10)

            async with async_playwright() as pw:
                context = await pw.chromium.launch_persistent_context(
                    CONFIG.chromeProfileDir,
                    headless=not show_browser,
                    channel="chrome",
                    viewport={"width": CONFIG.viewport.width, "height": CONFIG.viewport.height},
                    locale="en-US",
                    timezone_id="Europe/Berlin",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
                pages = context.pages
                page = pages[0] if pages else await context.new_page()

                login_success = await self.perform_login(page, send_progress)

                if login_success:
                    if send_progress:
                        await send_progress("Saving authentication state...", 9, 10)
                    await self.save_browser_state(context, page)
                    log.success("Setup complete - authentication saved")

                await context.close()
                return login_success
        except Exception as e:
            log.error(f"Setup failed: {e}")
            return False

    async def clear_all_auth_data(self) -> None:
        log.warning("Clearing ALL authentication data...")
        deleted = 0
        state_dir = Path(CONFIG.browserStateDir)
        try:
            if state_dir.exists():
                for f in state_dir.iterdir():
                    if f.suffix == ".json":
                        f.unlink()
                        log.info(f"  Deleted: {f.name}")
                        deleted += 1
        except Exception as e:
            log.warning(f"Could not delete state files: {e}")

        chrome_dir = Path(CONFIG.chromeProfileDir)
        try:
            if chrome_dir.exists():
                shutil.rmtree(chrome_dir, ignore_errors=True)
                log.success(f"  Deleted Chrome profile: {chrome_dir}")
                deleted += 1
        except Exception as e:
            log.warning(f"Could not delete Chrome profile: {e}")

        if deleted == 0:
            log.info("  No old auth data found (already clean)")
        else:
            log.success(f"All auth data cleared ({deleted} items)")

    async def clear_state(self) -> bool:
        try:
            for p in (self._state_path, self._session_path):
                try:
                    p.unlink()
                except Exception:
                    pass
            log.success("Authentication state cleared")
            return True
        except Exception as e:
            log.error(f"Failed to clear state: {e}")
            return False

    async def hard_reset_state(self) -> bool:
        try:
            log.warning("Performing HARD RESET of all authentication state...")
            deleted = 0
            for p in (self._state_path, self._session_path):
                try:
                    p.unlink()
                    deleted += 1
                except Exception:
                    pass

            state_dir = Path(CONFIG.browserStateDir)
            if state_dir.exists():
                for f in state_dir.iterdir():
                    try:
                        f.unlink()
                        deleted += 1
                    except Exception:
                        pass

            if deleted == 0:
                log.info("No state to delete (already clean)")
            else:
                log.success(f"Hard reset complete: {deleted} items deleted")
            return True
        except Exception as e:
            log.error(f"Hard reset failed: {e}")
            return False

    async def load_auth_state(self, context: BrowserContext, state_path: str) -> bool:
        try:
            data = Path(state_path).read_text(encoding="utf-8")
            state = json.loads(data)
            if state.get("cookies"):
                await context.add_cookies(state["cookies"])
                log.success(f"Loaded {len(state['cookies'])} cookies")
                return True
            log.warning("No cookies found in state file")
            return False
        except Exception as e:
            log.error(f"Failed to load auth state: {e}")
            return False

    def _mask_email(self, email: str) -> str:
        if "@" not in email:
            return "***"
        name, domain = email.split("@", 1)
        if len(name) <= 2:
            return f"{'*' * len(name)}@{domain}"
        return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}@{domain}"
