import contextlib
import os
import shutil
import time

from pathlib import Path

from playwright.async_api import BrowserContext, async_playwright

from ..auth.auth_manager import AuthManager
from ..config import CONFIG, Config
from ..utils.logger import log


class SharedContextManager:
    def __init__(self, auth_manager: AuthManager, config: Config | None = None) -> None:
        self._auth = auth_manager
        self._config = config or CONFIG
        self._context: BrowserContext | None = None
        self._context_created_at: float | None = None
        self._current_profile_dir: str | None = None
        self._is_isolated: bool = False
        self._current_headless: bool | None = None
        self._pw = None

        log.info("SharedContextManager initialized (PERSISTENT MODE)")
        log.info(f"  Chrome Profile: {self._config.chromeProfileDir}")

    async def get_or_create_context(self, override_headless: bool | None = None) -> BrowserContext:
        if self.needs_headless_mode_change(override_headless):
            log.warning("Headless mode change detected - recreating browser context...")
            await self.close_context()

        if await self._needs_recreation():
            await self._recreate_context(override_headless)
        else:
            log.success("Reusing existing persistent context")

        assert self._context is not None
        return self._context

    async def _needs_recreation(self) -> bool:
        if not self._context:
            return True
        try:
            await self._context.cookies()
            return False
        except Exception:
            log.warning("Context appears closed - will recreate")
            self._context = None
            self._context_created_at = None
            self._current_headless = None
            return True

    async def _recreate_context(self, override_headless: bool | None = None) -> None:
        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                log.warning(f"Error closing old context: {e}")

        state_path = await self._auth.get_valid_state_path()
        if state_path:
            log.success(f"  Found auth state: {state_path}")
        else:
            log.warning("  No saved auth - fresh persistent profile")

        should_be_headless = (not override_headless) if override_headless is not None else self._config.headless

        launch_opts = {
            "headless": should_be_headless,
            "channel": "chrome",
            "viewport": {"width": self._config.viewport.width, "height": self._config.viewport.height},
            "locale": "en-US",
            "timezone_id": "Europe/Berlin",
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }

        base_profile = self._config.chromeProfileDir
        strategy = self._config.profileStrategy

        if self._pw is None:
            self._pw = await async_playwright().start()
        pw = self._pw

        async def try_launch(user_data_dir: str) -> BrowserContext:
            log.info("  Launching persistent Chrome context...")
            log.dim(f"  Profile location: {user_data_dir}")
            return await pw.chromium.launch_persistent_context(user_data_dir, **launch_opts)

        try:
            if strategy == "isolated":
                isolated_dir = self._prepare_isolated_dir(base_profile)
                self._context = await try_launch(isolated_dir)
                self._current_profile_dir = isolated_dir
                self._is_isolated = True
            else:
                self._context = await try_launch(base_profile)
                self._current_profile_dir = base_profile
                self._is_isolated = False
        except Exception as e:
            msg = str(e)
            is_singleton = any(k in msg.lower() for k in ("processsingleton", "singletonlock", "profile is already in use"))
            if strategy == "single" or not is_singleton:
                raise
            log.warning("Base Chrome profile in use. Falling back to isolated profile...")
            isolated_dir = self._prepare_isolated_dir(base_profile)
            self._context = await try_launch(isolated_dir)
            self._current_profile_dir = isolated_dir
            self._is_isolated = True

        if state_path:
            await self._auth.load_auth_state(self._context, state_path)

        self._context_created_at = time.time()
        self._current_headless = should_be_headless

        def on_close() -> None:
            log.warning("Persistent context was closed externally")
            self._context = None
            self._context_created_at = None
            self._current_headless = None

        with contextlib.suppress(Exception):
            self._context.on("close", lambda _ctx: on_close())

        if state_path:
            try:
                if await self._auth.validate_cookies_expiry(self._context):
                    log.success("  Authentication state loaded successfully")
                else:
                    log.warning("  Cookies expired - will need re-login")
            except Exception as e:
                log.warning(f"  Could not validate auth state: {e}")

        log.success("Persistent context ready!")

    def _prepare_isolated_dir(self, base_profile: str) -> str:
        stamp = f"{os.getpid()}-{int(time.time() * 1000)}"
        isolated_dir = str(Path(self._config.chromeInstancesDir) / f"instance-{stamp}")
        Path(isolated_dir).mkdir(parents=True, exist_ok=True)
        if self._config.cloneProfileOnIsolated and Path(base_profile).exists():
            try:
                shutil.copytree(base_profile, isolated_dir, dirs_exist_ok=True)
                log.success("  Clone complete")
            except Exception as e:
                log.warning(f"  Could not clone profile: {e}")
        return isolated_dir

    async def close_context(self) -> None:
        if self._context:
            log.warning("Closing persistent context...")
            try:
                await self._context.close()
                self._context = None
                self._context_created_at = None
                self._current_headless = None
                log.success(f"Persistent context closed. Profile saved: {self._current_profile_dir}")
            except Exception as e:
                log.error(f"Error closing context: {e}")
        if self._pw:
            try:
                await self._pw.stop()
                self._pw = None
            except Exception:
                pass

    def needs_headless_mode_change(self, override_headless: bool | None = None) -> bool:
        if self._current_headless is None:
            return False
        target = (not override_headless) if override_headless is not None else self._config.headless
        return self._current_headless != target

    def get_current_headless_mode(self) -> bool | None:
        return self._current_headless

    def get_context_info(self) -> dict:
        if not self._context:
            return {"exists": False, "user_data_dir": self._config.chromeProfileDir, "persistent": True}
        age = (time.time() - self._context_created_at) if self._context_created_at else None
        return {
            "exists": True,
            "age_seconds": age,
            "age_hours": age / 3600 if age else None,
            "user_data_dir": self._config.chromeProfileDir,
            "persistent": True,
        }
