import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Optional

from platformdirs import user_data_dir

from .logger import log


class CleanupManager:
    def __init__(self) -> None:
        self._home = Path.home()
        self._data_dir = Path(user_data_dir("notebooklm-mcp"))

    def _path_exists(self, p: Path) -> bool:
        return p.exists()

    def _dir_size(self, p: Path) -> int:
        if not p.exists():
            return 0
        if p.is_file():
            return p.stat().st_size
        total = 0
        try:
            for item in p.rglob("*"):
                try:
                    if item.is_file():
                        total += item.stat().st_size
                except Exception:
                    pass
        except Exception:
            pass
        return total

    def format_bytes(self, n: int) -> str:
        if n == 0:
            return "0 Bytes"
        for unit in ("Bytes", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.2f} {unit}"
            n /= 1024
        return f"{n:.2f} TB"

    def get_cleanup_paths(self, mode: str, preserve_library: bool = False) -> dict:
        categories = []
        all_paths: set[str] = set()
        total_bytes = 0

        current_subdirs = [
            self._data_dir / "browser_state",
            self._data_dir / "chrome_profile",
            self._data_dir / "chrome_profile_instances",
        ]

        if mode in ("all", "deep"):
            current: list[Path] = []
            if preserve_library:
                for sd in current_subdirs:
                    if sd.exists() and str(sd) not in all_paths:
                        current.append(sd)
                        all_paths.add(str(sd))
            else:
                if self._data_dir.exists() and str(self._data_dir) not in all_paths:
                    current.append(self._data_dir)
                    all_paths.add(str(self._data_dir))

            if current:
                cat_bytes = sum(self._dir_size(p) for p in current)
                total_bytes += cat_bytes
                desc = (
                    "Active installation data (library.json preserved)"
                    if preserve_library
                    else "Active installation data and browser profiles"
                )
                categories.append({
                    "name": "Current Installation (notebooklm-mcp)",
                    "description": desc,
                    "paths": [str(p) for p in current],
                    "totalBytes": cat_bytes,
                    "optional": False,
                })

        return {
            "categories": categories,
            "totalPaths": list(all_paths),
            "totalSizeBytes": total_bytes,
        }

    def perform_cleanup(self, mode: str, preserve_library: bool = False) -> dict:
        log.info(f"Starting cleanup in '{mode}' mode...")
        preview = self.get_cleanup_paths(mode, preserve_library)
        deleted: list[str] = []
        failed: list[str] = []
        category_summary: dict = {}

        for cat in preview["categories"]:
            count = 0
            cat_bytes = 0
            for p_str in cat["paths"]:
                p = Path(p_str)
                try:
                    if p.exists():
                        size = self._dir_size(p)
                        shutil.rmtree(p, ignore_errors=True)
                        deleted.append(p_str)
                        count += 1
                        cat_bytes += size
                        log.success(f"  Deleted: {p_str}")
                except Exception as e:
                    log.error(f"  Failed to delete {p_str}: {e}")
                    failed.append(p_str)
            category_summary[cat["name"]] = {"count": count, "bytes": cat_bytes}

        return {
            "success": len(failed) == 0,
            "deletedPaths": deleted,
            "failedPaths": failed,
            "totalSizeBytes": preview["totalSizeBytes"],
            "categorySummary": category_summary,
        }

    def get_platform_info(self) -> dict:
        sys_platform = sys.platform
        if sys_platform == "darwin":
            name = "macOS"
        elif sys_platform.startswith("linux"):
            name = "Linux"
        elif sys_platform == "win32":
            name = "Windows"
        else:
            name = sys_platform
        return {"platform": name}
