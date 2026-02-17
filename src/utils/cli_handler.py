from ..config import CONFIG
from .logger import log


class CliHandler:
    def handle_command(self, args: list[str]) -> None:
        if not args:
            return

        cmd = args[0]
        if cmd == "config":
            self._show_config()
        else:
            log.warning(f"Unknown CLI command: {cmd}")

    def _show_config(self) -> None:
        print("NotebookLM MCP Server Configuration")
        print("=" * 40)
        print(f"  Data Dir:           {CONFIG.dataDir}")
        print(f"  Config Dir:         {CONFIG.configDir}")
        print(f"  Browser State Dir:  {CONFIG.browserStateDir}")
        print(f"  Chrome Profile Dir: {CONFIG.chromeProfileDir}")
        print(f"  Headless:           {CONFIG.headless}")
        print(f"  Max Sessions:       {CONFIG.maxSessions}")
        print(f"  Session Timeout:    {CONFIG.sessionTimeout}s")
        print(f"  Auto Login:         {CONFIG.autoLoginEnabled}")
        print(f"  Stealth:            {CONFIG.stealthEnabled}")
        print(f"  Notebook URL:       {CONFIG.notebookUrl or '(not set)'}")
