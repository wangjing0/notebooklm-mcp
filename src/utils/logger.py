import sys
from datetime import datetime


class Logger:
    _RESET = "\x1b[0m"
    _STYLES = {
        "info":    ("\u2139\ufe0f ", "\x1b[36m"),
        "success": ("\u2705", "\x1b[32m"),
        "warning": ("\u26a0\ufe0f ", "\x1b[33m"),
        "error":   ("\u274c", "\x1b[31m"),
        "debug":   ("\U0001f50d", "\x1b[35m"),
        "dim":     ("  ", "\x1b[2m"),
    }

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def log(self, message: str, level: str = "info") -> None:
        if not self.enabled:
            return
        prefix, color = self._STYLES.get(level, ("", ""))
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{color}{prefix}  [{timestamp}] {message}{self._RESET}", file=sys.stderr)

    def info(self, message: str) -> None:
        self.log(message, "info")

    def success(self, message: str) -> None:
        self.log(message, "success")

    def warning(self, message: str) -> None:
        self.log(message, "warning")

    def error(self, message: str) -> None:
        self.log(message, "error")

    def debug(self, message: str) -> None:
        self.log(message, "debug")

    def dim(self, message: str) -> None:
        self.log(message, "dim")

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


logger = Logger()


class _LogProxy:
    def info(self, msg: str) -> None: logger.info(msg)
    def success(self, msg: str) -> None: logger.success(msg)
    def warning(self, msg: str) -> None: logger.warning(msg)
    def error(self, msg: str) -> None: logger.error(msg)
    def debug(self, msg: str) -> None: logger.debug(msg)
    def dim(self, msg: str) -> None: logger.dim(msg)


log = _LogProxy()
