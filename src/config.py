import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from platformdirs import user_data_dir

load_dotenv()

NOTEBOOKLM_AUTH_URL = (
    "https://accounts.google.com/v3/signin/identifier"
    "?continue=https%3A%2F%2Fnotebooklm.google.com%2F"
    "&flowName=GlifWebSignIn&flowEntry=ServiceLogin"
)

_DATA_DIR = user_data_dir("notebooklm-mcp")


@dataclass
class Viewport:
    width: int = 1024
    height: int = 768


@dataclass
class Config:
    notebookUrl: str = ""
    headless: bool = True
    browserTimeout: int = 30000
    viewport: Viewport = field(default_factory=Viewport)
    maxSessions: int = 10
    sessionTimeout: int = 900
    autoLoginEnabled: bool = False
    loginEmail: str = ""
    loginPassword: str = ""
    autoLoginTimeoutMs: int = 120000
    stealthEnabled: bool = True
    stealthRandomDelays: bool = True
    stealthHumanTyping: bool = True
    stealthMouseMovements: bool = True
    typingWpmMin: int = 160
    typingWpmMax: int = 240
    minDelayMs: int = 100
    maxDelayMs: int = 400
    configDir: str = field(default="")
    dataDir: str = field(default="")
    browserStateDir: str = field(default="")
    chromeProfileDir: str = field(default="")
    chromeInstancesDir: str = field(default="")
    notebookDescription: str = "General knowledge base"
    notebookTopics: list = field(default_factory=lambda: ["General topics"])
    notebookContentTypes: list = field(default_factory=lambda: ["documentation", "examples"])
    notebookUseCases: list = field(default_factory=lambda: ["General research"])
    profileStrategy: str = "auto"
    cloneProfileOnIsolated: bool = False
    cleanupInstancesOnStartup: bool = True
    cleanupInstancesOnShutdown: bool = True
    instanceProfileTtlHours: int = 72
    instanceProfileMaxCount: int = 20

    def __post_init__(self):
        if not self.dataDir:
            self.dataDir = _DATA_DIR
        if not self.configDir:
            self.configDir = _DATA_DIR
        if not self.browserStateDir:
            self.browserStateDir = str(Path(self.dataDir) / "browser_state")
        if not self.chromeProfileDir:
            self.chromeProfileDir = str(Path(self.dataDir) / "chrome_profile")
        if not self.chromeInstancesDir:
            self.chromeInstancesDir = str(Path(self.dataDir) / "chrome_profile_instances")


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in ("true", "1")


def _parse_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_list(value: Optional[str], default: list) -> list:
    if not value:
        return default
    return [s.strip() for s in value.split(",") if s.strip()]


def build_config() -> Config:
    cfg = Config()
    cfg.notebookUrl = os.environ.get("NOTEBOOK_URL", cfg.notebookUrl)
    cfg.headless = _parse_bool(os.environ.get("HEADLESS"), cfg.headless)
    cfg.browserTimeout = _parse_int(os.environ.get("BROWSER_TIMEOUT"), cfg.browserTimeout)
    cfg.maxSessions = _parse_int(os.environ.get("MAX_SESSIONS"), cfg.maxSessions)
    cfg.sessionTimeout = _parse_int(os.environ.get("SESSION_TIMEOUT"), cfg.sessionTimeout)
    cfg.autoLoginEnabled = _parse_bool(os.environ.get("AUTO_LOGIN_ENABLED"), cfg.autoLoginEnabled)
    cfg.loginEmail = os.environ.get("LOGIN_EMAIL", cfg.loginEmail)
    cfg.loginPassword = os.environ.get("LOGIN_PASSWORD", cfg.loginPassword)
    cfg.autoLoginTimeoutMs = _parse_int(os.environ.get("AUTO_LOGIN_TIMEOUT_MS"), cfg.autoLoginTimeoutMs)
    cfg.stealthEnabled = _parse_bool(os.environ.get("STEALTH_ENABLED"), cfg.stealthEnabled)
    cfg.stealthRandomDelays = _parse_bool(os.environ.get("STEALTH_RANDOM_DELAYS"), cfg.stealthRandomDelays)
    cfg.stealthHumanTyping = _parse_bool(os.environ.get("STEALTH_HUMAN_TYPING"), cfg.stealthHumanTyping)
    cfg.stealthMouseMovements = _parse_bool(os.environ.get("STEALTH_MOUSE_MOVEMENTS"), cfg.stealthMouseMovements)
    cfg.typingWpmMin = _parse_int(os.environ.get("TYPING_WPM_MIN"), cfg.typingWpmMin)
    cfg.typingWpmMax = _parse_int(os.environ.get("TYPING_WPM_MAX"), cfg.typingWpmMax)
    cfg.minDelayMs = _parse_int(os.environ.get("MIN_DELAY_MS"), cfg.minDelayMs)
    cfg.maxDelayMs = _parse_int(os.environ.get("MAX_DELAY_MS"), cfg.maxDelayMs)
    cfg.notebookDescription = os.environ.get("NOTEBOOK_DESCRIPTION", cfg.notebookDescription)
    cfg.notebookTopics = _parse_list(os.environ.get("NOTEBOOK_TOPICS"), cfg.notebookTopics)
    cfg.notebookContentTypes = _parse_list(os.environ.get("NOTEBOOK_CONTENT_TYPES"), cfg.notebookContentTypes)
    cfg.notebookUseCases = _parse_list(os.environ.get("NOTEBOOK_USE_CASES"), cfg.notebookUseCases)
    strategy = os.environ.get("NOTEBOOK_PROFILE_STRATEGY")
    if strategy in ("auto", "single", "isolated"):
        cfg.profileStrategy = strategy
    cfg.cloneProfileOnIsolated = _parse_bool(os.environ.get("NOTEBOOK_CLONE_PROFILE"), cfg.cloneProfileOnIsolated)
    cfg.cleanupInstancesOnStartup = _parse_bool(os.environ.get("NOTEBOOK_CLEANUP_ON_STARTUP"), cfg.cleanupInstancesOnStartup)
    cfg.cleanupInstancesOnShutdown = _parse_bool(os.environ.get("NOTEBOOK_CLEANUP_ON_SHUTDOWN"), cfg.cleanupInstancesOnShutdown)
    cfg.instanceProfileTtlHours = _parse_int(os.environ.get("NOTEBOOK_INSTANCE_TTL_HOURS"), cfg.instanceProfileTtlHours)
    cfg.instanceProfileMaxCount = _parse_int(os.environ.get("NOTEBOOK_INSTANCE_MAX_COUNT"), cfg.instanceProfileMaxCount)
    return cfg


def ensure_directories(cfg: "Config") -> None:
    for d in [cfg.dataDir, cfg.browserStateDir, cfg.chromeProfileDir, cfg.chromeInstancesDir]:
        Path(d).mkdir(parents=True, exist_ok=True)


def apply_browser_options(cfg: "Config", options: Optional[dict] = None, show_browser: Optional[bool] = None) -> "Config":
    import copy
    c = copy.copy(cfg)
    c.viewport = copy.copy(cfg.viewport)
    c.notebookTopics = list(cfg.notebookTopics)
    c.notebookContentTypes = list(cfg.notebookContentTypes)
    c.notebookUseCases = list(cfg.notebookUseCases)

    if show_browser is not None:
        c.headless = not show_browser

    if options:
        if options.get("show") is not None:
            c.headless = not options["show"]
        if options.get("headless") is not None:
            c.headless = options["headless"]
        if options.get("timeout_ms") is not None:
            c.browserTimeout = options["timeout_ms"]
        stealth = options.get("stealth") or {}
        if stealth.get("enabled") is not None:
            c.stealthEnabled = stealth["enabled"]
        if stealth.get("random_delays") is not None:
            c.stealthRandomDelays = stealth["random_delays"]
        if stealth.get("human_typing") is not None:
            c.stealthHumanTyping = stealth["human_typing"]
        if stealth.get("mouse_movements") is not None:
            c.stealthMouseMovements = stealth["mouse_movements"]
        if stealth.get("typing_wpm_min") is not None:
            c.typingWpmMin = stealth["typing_wpm_min"]
        if stealth.get("typing_wpm_max") is not None:
            c.typingWpmMax = stealth["typing_wpm_max"]
        if stealth.get("delay_min_ms") is not None:
            c.minDelayMs = stealth["delay_min_ms"]
        if stealth.get("delay_max_ms") is not None:
            c.maxDelayMs = stealth["delay_max_ms"]
        vp = options.get("viewport") or {}
        if vp.get("width") is not None:
            c.viewport.width = vp["width"]
        if vp.get("height") is not None:
            c.viewport.height = vp["height"]

    return c


CONFIG = build_config()
ensure_directories(CONFIG)
