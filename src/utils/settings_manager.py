import json
import os
from pathlib import Path
from typing import Any

from ..config import CONFIG
from .logger import log

PROFILES: dict[str, list[str]] = {
    "minimal": [
        "ask_question",
        "get_health",
        "list_notebooks",
        "select_notebook",
        "get_notebook",
    ],
    "standard": [
        "ask_question",
        "get_health",
        "list_notebooks",
        "select_notebook",
        "get_notebook",
        "setup_auth",
        "list_sessions",
        "add_notebook",
        "update_notebook",
        "search_notebooks",
    ],
    "full": ["*"],
}

_DEFAULT_SETTINGS = {
    "profile": "full",
    "disabledTools": [],
}


class SettingsManager:
    def __init__(self) -> None:
        self._settings_path = Path(CONFIG.configDir) / "settings.json"
        self._settings = self._load_settings()

    def _load_settings(self) -> dict:
        try:
            if self._settings_path.exists():
                data = self._settings_path.read_text(encoding="utf-8")
                return {**_DEFAULT_SETTINGS, **json.loads(data)}
        except Exception as e:
            log.warning(f"Failed to load settings: {e}. Using defaults.")
        return dict(_DEFAULT_SETTINGS)

    def get_effective_settings(self) -> dict:
        env_profile = os.environ.get("NOTEBOOKLM_PROFILE", "")
        env_disabled = os.environ.get("NOTEBOOKLM_DISABLED_TOOLS", "")

        profile = env_profile if env_profile in PROFILES else self._settings.get("profile", "full")
        disabled = list(self._settings.get("disabledTools", []))
        if env_disabled:
            for t in env_disabled.split(","):
                t = t.strip()
                if t and t not in disabled:
                    disabled.append(t)

        return {
            "profile": profile,
            "disabledTools": disabled,
            "customSettings": self._settings.get("customSettings"),
        }

    def filter_tools(self, all_tools: list) -> list:
        settings = self.get_effective_settings()
        profile = settings["profile"]
        disabled = settings["disabledTools"]
        allowed = PROFILES.get(profile, ["*"])

        result = []
        for tool in all_tools:
            name = tool.name if hasattr(tool, "name") else tool.get("name", "")
            if "*" not in allowed and name not in allowed:
                continue
            if name in disabled:
                continue
            result.append(tool)
        return result
