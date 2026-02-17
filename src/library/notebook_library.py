import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import CONFIG
from ..utils.logger import log
from .types import AddNotebookInput, Library, LibraryStats, NotebookEntry, UpdateNotebookInput


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotebookLibrary:
    def __init__(self) -> None:
        self._library_path = Path(CONFIG.dataDir) / "library.json"
        self._library: Library = self._load_library()
        log.info("NotebookLibrary initialized")
        log.info(f"  Library path: {self._library_path}")
        log.info(f"  Notebooks: {len(self._library['notebooks'])}")
        if self._library.get("active_notebook_id"):
            log.info(f"  Active: {self._library['active_notebook_id']}")

    def _load_library(self) -> Library:
        try:
            if self._library_path.exists():
                data = self._library_path.read_text(encoding="utf-8")
                lib: Library = json.loads(data)
                log.success(f"  Loaded library with {len(lib['notebooks'])} notebooks")
                return lib
        except Exception as e:
            log.warning(f"  Failed to load library: {e}")

        log.info("  Creating new library...")
        default = self._create_default_library()
        self._save_library(default)
        return default

    def _create_default_library(self) -> Library:
        has_config = bool(
            CONFIG.notebookUrl
            and CONFIG.notebookDescription
            and CONFIG.notebookDescription != "General knowledge base"
        )
        notebooks: list = []
        if has_config:
            entry_id = self._generate_id(CONFIG.notebookDescription, notebooks)
            notebooks.append({
                "id": entry_id,
                "url": CONFIG.notebookUrl,
                "name": CONFIG.notebookDescription[:50],
                "description": CONFIG.notebookDescription,
                "topics": CONFIG.notebookTopics,
                "content_types": CONFIG.notebookContentTypes,
                "use_cases": CONFIG.notebookUseCases,
                "added_at": _now_iso(),
                "last_used": _now_iso(),
                "use_count": 0,
                "tags": [],
            })
        return {
            "notebooks": notebooks,
            "active_notebook_id": notebooks[0]["id"] if notebooks else None,
            "last_modified": _now_iso(),
            "version": "1.0.0",
        }

    def _save_library(self, library: Library) -> None:
        try:
            library["last_modified"] = _now_iso()
            self._library_path.write_text(json.dumps(library, indent=2), encoding="utf-8")
            self._library = library
        except Exception as e:
            log.error(f"  Failed to save library: {e}")
            raise

    def _generate_id(self, name: str, existing_notebooks: Optional[list] = None) -> str:
        notebooks = existing_notebooks if existing_notebooks is not None else self._library["notebooks"]
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30]
        slug = base or "notebook"
        existing_ids = {n["id"] for n in notebooks}
        candidate = slug
        counter = 1
        while candidate in existing_ids:
            candidate = f"{slug}-{counter}"
            counter += 1
        return candidate

    def add_notebook(self, input_data: dict) -> NotebookEntry:
        name = input_data["name"]
        log.info(f"Adding notebook: {name}")
        entry_id = self._generate_id(name)
        entry: NotebookEntry = {
            "id": entry_id,
            "url": input_data["url"],
            "name": name,
            "description": input_data["description"],
            "topics": input_data["topics"],
            "content_types": input_data.get("content_types") or ["documentation", "examples"],
            "use_cases": input_data.get("use_cases") or [f"Learning about {name}", f"Implementing features with {name}"],
            "added_at": _now_iso(),
            "last_used": _now_iso(),
            "use_count": 0,
            "tags": input_data.get("tags") or [],
        }
        updated = dict(self._library)
        updated["notebooks"] = list(self._library["notebooks"]) + [entry]
        if len(updated["notebooks"]) == 1:
            updated["active_notebook_id"] = entry_id
        self._save_library(updated)
        log.success(f"Notebook added: {entry_id}")
        return entry

    def list_notebooks(self) -> list:
        return self._library["notebooks"]

    def get_notebook(self, notebook_id: str) -> Optional[NotebookEntry]:
        for n in self._library["notebooks"]:
            if n["id"] == notebook_id:
                return n
        return None

    def get_active_notebook(self) -> Optional[NotebookEntry]:
        active_id = self._library.get("active_notebook_id")
        if not active_id:
            return None
        return self.get_notebook(active_id)

    def select_notebook(self, notebook_id: str) -> NotebookEntry:
        notebook = self.get_notebook(notebook_id)
        if not notebook:
            raise ValueError(f"Notebook not found: {notebook_id}")
        updated = dict(self._library)
        updated["active_notebook_id"] = notebook_id
        updated_notebooks = []
        for n in self._library["notebooks"]:
            if n["id"] == notebook_id:
                updated_notebooks.append({**n, "last_used": _now_iso()})
            else:
                updated_notebooks.append(n)
        updated["notebooks"] = updated_notebooks
        self._save_library(updated)
        return self.get_notebook(notebook_id)

    def update_notebook(self, input_data: dict) -> NotebookEntry:
        notebook_id = input_data["id"]
        notebook = self.get_notebook(notebook_id)
        if not notebook:
            raise ValueError(f"Notebook not found: {notebook_id}")
        updated_entry = dict(notebook)
        for field in ("name", "description", "topics", "content_types", "use_cases", "tags", "url"):
            if field in input_data and input_data[field] is not None:
                updated_entry[field] = input_data[field]
        updated = dict(self._library)
        updated["notebooks"] = [
            updated_entry if n["id"] == notebook_id else n
            for n in self._library["notebooks"]
        ]
        self._save_library(updated)
        return updated_entry

    def remove_notebook(self, notebook_id: str) -> bool:
        if not self.get_notebook(notebook_id):
            return False
        updated = dict(self._library)
        updated["notebooks"] = [n for n in self._library["notebooks"] if n["id"] != notebook_id]
        if updated.get("active_notebook_id") == notebook_id:
            updated["active_notebook_id"] = updated["notebooks"][0]["id"] if updated["notebooks"] else None
        self._save_library(updated)
        return True

    def increment_use_count(self, notebook_id: str) -> Optional[NotebookEntry]:
        idx = next((i for i, n in enumerate(self._library["notebooks"]) if n["id"] == notebook_id), -1)
        if idx == -1:
            return None
        updated = dict(self._library)
        notebooks = list(self._library["notebooks"])
        notebooks[idx] = {**notebooks[idx], "use_count": notebooks[idx]["use_count"] + 1, "last_used": _now_iso()}
        updated["notebooks"] = notebooks
        self._save_library(updated)
        return notebooks[idx]

    def search_notebooks(self, query: str) -> list:
        q = query.lower()
        return [
            n for n in self._library["notebooks"]
            if q in n["name"].lower()
            or q in n["description"].lower()
            or any(q in t.lower() for t in n.get("topics", []))
            or any(q in t.lower() for t in n.get("tags", []))
        ]

    def get_stats(self) -> LibraryStats:
        notebooks = self._library["notebooks"]
        total_queries = sum(n.get("use_count", 0) for n in notebooks)
        most_used = max(notebooks, key=lambda n: n.get("use_count", 0), default=None)
        return {
            "total_notebooks": len(notebooks),
            "active_notebook": self._library.get("active_notebook_id"),
            "most_used_notebook": most_used["id"] if most_used else None,
            "total_queries": total_queries,
            "last_modified": self._library.get("last_modified", ""),
        }
