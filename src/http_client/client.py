"""HTTP client for NotebookLM API — ported from notebooklm-py reverse engineering.

Authenticates via Playwright storage_state.json (same file saved by setup_auth),
then makes direct HTTP calls to the NotebookLM batchexecute RPC endpoint.
"""

import asyncio
import contextlib
import json
import re

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


_BASE_URL = "https://notebooklm.google.com/_/LabsTailwindUi/data/batchexecute"
_UPLOAD_URL = "https://notebooklm.google.com/upload/_/?authuser=0"
_HOMEPAGE_URL = "https://notebooklm.google.com/"

_ALLOWED_AUTH_DOMAINS = {
    ".google.com",
    "notebooklm.google.com",
    ".googleusercontent.com",
}

_SOURCE_TYPE_CODE_MAP: dict[int, str] = {
    1: "google_docs",
    2: "google_slides",
    3: "pdf",
    4: "pasted_text",
    5: "web_page",
    8: "markdown",
    9: "youtube",
    10: "media",
    11: "docx",
    13: "image",
    14: "google_spreadsheet",
    16: "csv",
}

_YOUTUBE_PATTERNS = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

# RPC method IDs
_RPC_GET_NOTEBOOK = "rLM1Ne"
_RPC_ADD_SOURCE = "izAoDd"
_RPC_ADD_SOURCE_FILE = "o4cbdc"
_RPC_DELETE_SOURCE = "tGMBJ"
_RPC_START_RESEARCH_FAST = "Ljjv0c"
_RPC_START_RESEARCH_DEEP = "QA9ei"
_RPC_POLL_RESEARCH = "e3bVqc"
_RPC_IMPORT_RESEARCH = "LBwxtb"


class NotebookLMAuthError(Exception):
    pass


class NotebookLMRPCError(Exception):
    pass


@dataclass
class Source:
    id: str
    title: str | None = None
    url: str | None = None
    type_code: int | None = None
    status: int = 2

    @property
    def kind(self) -> str:
        if self.type_code is None:
            return "unknown"
        return _SOURCE_TYPE_CODE_MAP.get(self.type_code, f"type_{self.type_code}")

    @property
    def is_ready(self) -> bool:
        return self.status == 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "kind": self.kind,
            "status": self.status,
            "is_ready": self.is_ready,
        }


def _is_allowed_auth_domain(domain: str) -> bool:
    if domain in _ALLOWED_AUTH_DOMAINS:
        return True
    # Regional Google domains: .google.co.uk, .google.com.sg, etc.
    return domain.startswith(".google.")


def _extract_cookies(storage_state: dict) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for cookie in storage_state.get("cookies", []):
        domain = cookie.get("domain", "")
        name = cookie.get("name")
        if not _is_allowed_auth_domain(domain) or not name:
            continue
        is_base = domain == ".google.com"
        if name not in cookies or is_base:
            cookies[name] = cookie.get("value", "")
    return cookies


def _encode_rpc(method_id: str, params: list) -> str:
    params_json = json.dumps(params, separators=(",", ":"))
    rpc_request = [[[method_id, params_json, None, "generic"]]]
    return json.dumps(rpc_request, separators=(",", ":"))


def _parse_chunked(text: str) -> list[Any]:
    # Strip anti-XSSI prefix: )]}'\n
    if text.startswith(")]}'"):
        text = text[5:]
    text = text.lstrip("\n")
    chunks = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        # Skip byte-count lines (numeric-only)
        line = lines[i]
        i += 1
        if not line.strip():
            continue
        try:
            int(line.strip())
            # Next line should be JSON payload
            if i < len(lines):
                payload = lines[i]
                i += 1
                with contextlib.suppress(json.JSONDecodeError):
                    chunks.append(json.loads(payload))
        except ValueError:
            # Not a byte-count line — try parsing as JSON directly
            with contextlib.suppress(json.JSONDecodeError):
                chunks.append(json.loads(line))
    return chunks


def _extract_first_rpc_result(chunks: list[Any]) -> Any:
    """Extract the first RPC result data from parsed chunks."""
    for chunk in chunks:
        if isinstance(chunk, list) and chunk:
            inner = chunk[0]
            if isinstance(inner, list) and len(inner) >= 3:
                # Format: [method_id, json_payload, ..., status]
                payload_str = inner[2]
                if isinstance(payload_str, str):
                    try:
                        return json.loads(payload_str)
                    except json.JSONDecodeError:
                        pass
    return None


def _extract_youtube_id(url: str) -> str | None:
    m = _YOUTUBE_PATTERNS.search(url)
    return m.group(1) if m else None


def _parse_source_from_response(data: Any) -> Source | None:
    """Parse a Source from an add_source RPC response."""
    try:
        # Expected: [[[[id], title, metadata]]]
        inner = data
        for _ in range(3):
            if isinstance(inner, list) and inner:
                inner = inner[0]
            else:
                break
        if not isinstance(inner, list) or not inner:
            return None
        # inner[0] is id or [id], inner[1] is title
        raw_id = inner[0]
        source_id = raw_id[0] if isinstance(raw_id, list) else raw_id
        title = inner[1] if len(inner) > 1 else None
        if isinstance(title, list):
            title = title[0] if title else None
        # Try to extract type code from metadata
        type_code = None
        if len(inner) > 2 and isinstance(inner[2], list):
            meta = inner[2]
            if meta and isinstance(meta[0], int):
                type_code = meta[0]
        return Source(id=str(source_id), title=title, type_code=type_code, status=1)
    except (IndexError, TypeError):
        return None


def _parse_sources_list(data: Any) -> list[Source]:
    """Parse sources list from get_notebook RPC response."""
    sources = []
    try:
        # Sources at data[0][1]
        raw_list = data[0][1]
        if not isinstance(raw_list, list):
            return sources
        for item in raw_list:
            try:
                # item structure: [id, title, metadata_list, ...]
                if not isinstance(item, list) or not item:
                    continue
                source_id = item[0]
                if isinstance(source_id, list):
                    source_id = source_id[0]
                title = item[1] if len(item) > 1 else None
                if isinstance(title, list):
                    title = title[0] if title else None
                # type code and status
                type_code = None
                status = 2
                url = None
                if len(item) > 2 and isinstance(item[2], list):
                    meta = item[2]
                    if meta and isinstance(meta[0], int):
                        type_code = meta[0]
                    # Try to extract status (often at deeper nesting)
                    for sub in meta:
                        if isinstance(sub, int) and sub in (0, 1, 2, 3):
                            status = sub
                            break
                    # Try to extract URL
                    for sub in meta:
                        if isinstance(sub, list):
                            for subsub in sub:
                                if isinstance(subsub, str) and subsub.startswith("http"):
                                    url = subsub
                                    break
                sources.append(Source(
                    id=str(source_id),
                    title=title,
                    url=url,
                    type_code=type_code,
                    status=status,
                ))
            except (IndexError, TypeError):
                continue
    except (IndexError, TypeError):
        pass
    return sources


class NotebookLMAPIClient:
    """Direct HTTP client for NotebookLM, authenticated via Playwright storage_state.json."""

    def __init__(self, browser_state_path: Path) -> None:
        self._state_path = browser_state_path
        self._cookies: dict[str, str] = {}
        self._csrf_token: str = ""
        self._session_id: str = ""
        self._authenticated = False

    def _notebook_internal_id(self, notebook_url: str) -> str:
        """Extract the internal NotebookLM ID from a URL."""
        return notebook_url.split("/notebook/")[-1].strip("/").split("?")[0]

    async def _ensure_auth(self) -> None:
        if self._authenticated:
            return
        if not self._state_path.exists():
            raise NotebookLMAuthError(
                "Not authenticated. Run setup_auth first to create browser state."
            )
        state = json.loads(self._state_path.read_text())
        self._cookies = _extract_cookies(state)
        if not self._cookies.get("SID"):
            raise NotebookLMAuthError(
                "Invalid authentication state. Run setup_auth to re-authenticate."
            )
        cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _HOMEPAGE_URL,
                headers={"Cookie": cookie_header},
                follow_redirects=True,
                timeout=30.0,
            )
            resp.raise_for_status()
            csrf_match = re.search(r'"SNlM0e"\s*:\s*"([^"]+)"', resp.text)
            sid_match = re.search(r'"FdrFJe"\s*:\s*"([^"]+)"', resp.text)
            if not csrf_match or not sid_match:
                raise NotebookLMAuthError(
                    "Could not extract auth tokens. Session may have expired. Run setup_auth."
                )
            self._csrf_token = csrf_match.group(1)
            self._session_id = sid_match.group(1)
        self._authenticated = True

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    async def _rpc(self, method_id: str, params: list, notebook_id: str) -> Any:
        await self._ensure_auth()
        f_req = _encode_rpc(method_id, params)
        body = f"f.req={quote(f_req, safe='')}&at={quote(self._csrf_token, safe='')}&"
        url = (
            f"{_BASE_URL}"
            f"?rpcids={method_id}"
            f"&source-path=/notebook/{notebook_id}"
            "&hl=en&rt=c"
            f"&f.sid={self._session_id}"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "Cookie": self._cookie_header(),
                },
                content=body,
                timeout=60.0,
            )
            if resp.status_code in (401, 403):
                self._authenticated = False
                raise NotebookLMAuthError("Authentication failed. Run setup_auth to re-authenticate.")
            resp.raise_for_status()
        chunks = _parse_chunked(resp.text)
        return _extract_first_rpc_result(chunks)

    async def list_sources(self, notebook_url: str) -> list[dict[str, Any]]:
        nb_id = self._notebook_internal_id(notebook_url)
        data = await self._rpc(_RPC_GET_NOTEBOOK, [nb_id, None, [2], None, 0], nb_id)
        if data is None:
            return []
        sources = _parse_sources_list(data)
        return [s.to_dict() for s in sources]

    async def add_source_url(self, notebook_url: str, url: str) -> dict[str, Any]:
        nb_id = self._notebook_internal_id(notebook_url)
        yt_id = _extract_youtube_id(url)
        if yt_id:
            params: list[Any] = [
                [[None, None, None, None, None, None, None, [url], None, None, 1]],
                nb_id,
                [2],
                [1, None, None, None, None, None, None, None, None, None, [1]],
            ]
        else:
            params = [
                [[None, None, [url], None, None, None, None, None]],
                nb_id,
                [2],
                None,
                None,
            ]
        data = await self._rpc(_RPC_ADD_SOURCE, params, nb_id)
        source = _parse_source_from_response(data)
        if source is None:
            raise NotebookLMRPCError(f"Failed to parse source response for URL: {url}")
        source.url = url
        return source.to_dict()

    async def add_source_text(self, notebook_url: str, title: str, content: str) -> dict[str, Any]:
        nb_id = self._notebook_internal_id(notebook_url)
        params: list[Any] = [
            [[None, [title, content], None, None, None, None, None, None]],
            nb_id,
            [2],
            None,
            None,
        ]
        data = await self._rpc(_RPC_ADD_SOURCE, params, nb_id)
        source = _parse_source_from_response(data)
        if source is None:
            raise NotebookLMRPCError("Failed to parse source response for text source")
        source.title = title
        return source.to_dict()

    async def add_source_file(self, notebook_url: str, file_path: Path) -> dict[str, Any]:
        nb_id = self._notebook_internal_id(notebook_url)
        filename = file_path.name
        # Step 1: Register file to get source_id
        params: list[Any] = [
            [[filename]],
            nb_id,
            [2],
            [1, None, None, None, None, None, None, None, None, None, [1]],
        ]
        data = await self._rpc(_RPC_ADD_SOURCE_FILE, params, nb_id)
        # Recursively unwrap nested lists to extract source_id
        source_id = data
        while isinstance(source_id, list):
            source_id = source_id[0]
        source_id = str(source_id)

        # Step 2: Start resumable upload session
        await self._ensure_auth()
        file_bytes = file_path.read_bytes()
        file_size = len(file_bytes)
        upload_init_body = json.dumps({
            "PROJECT_ID": nb_id,
            "SOURCE_NAME": filename,
            "SOURCE_ID": source_id,
        })
        async with httpx.AsyncClient() as client:
            init_resp = await client.post(
                _UPLOAD_URL,
                headers={
                    "x-goog-upload-protocol": "resumable",
                    "x-goog-upload-command": "start",
                    "x-goog-upload-header-content-length": str(file_size),
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "Cookie": self._cookie_header(),
                },
                content=upload_init_body,
                timeout=30.0,
            )
            init_resp.raise_for_status()
            upload_url = init_resp.headers.get("x-goog-upload-url", "")
            if not upload_url:
                raise NotebookLMRPCError("No upload URL returned from server")

            # Step 3: Upload file content
            upload_resp = await client.post(
                upload_url,
                headers={
                    "x-goog-upload-protocol": "resumable",
                    "x-goog-upload-command": "upload, finalize",
                    "x-goog-upload-offset": "0",
                    "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                    "Cookie": self._cookie_header(),
                },
                content=file_bytes,
                timeout=120.0,
            )
            upload_resp.raise_for_status()

        return Source(
            id=source_id,
            title=filename,
            type_code=None,
            status=1,
        ).to_dict()

    async def delete_source(self, notebook_url: str, source_id: str) -> bool:
        nb_id = self._notebook_internal_id(notebook_url)
        params: list[Any] = [
            [[source_id]],
            nb_id,
            [2],
            None,
        ]
        await self._rpc(_RPC_DELETE_SOURCE, params, nb_id)
        return True

    async def start_research(
        self,
        notebook_url: str,
        query: str,
        source: str = "web",
        mode: str = "fast",
    ) -> dict[str, Any]:
        nb_id = self._notebook_internal_id(notebook_url)
        source_type = 1 if source == "web" else 2
        if mode == "deep":
            params: list[Any] = [None, [1], [query, source_type], 5, nb_id]
            data = await self._rpc(_RPC_START_RESEARCH_DEEP, params, nb_id)
        else:
            params = [[query, source_type], None, 1, nb_id]
            data = await self._rpc(_RPC_START_RESEARCH_FAST, params, nb_id)
        # Response: [task_id, report_id] or nested equivalent
        task_id = None
        if isinstance(data, list) and data:
            task_id = data[0]
            if isinstance(task_id, list):
                task_id = task_id[0]
        return {"task_id": str(task_id) if task_id else "", "query": query, "source": source, "mode": mode}

    async def get_research_status(self, notebook_url: str) -> dict[str, Any]:
        nb_id = self._notebook_internal_id(notebook_url)
        params: list[Any] = [None, None, nb_id]
        data = await self._rpc(_RPC_POLL_RESEARCH, params, nb_id)
        if not isinstance(data, list) or not data:
            return {"tasks": []}
        tasks = []
        for item in data:
            try:
                if not isinstance(item, list) or len(item) < 2:
                    continue
                task_id = item[0]
                task_info = item[1]
                if not isinstance(task_info, list):
                    continue
                query = task_info[1] if len(task_info) > 1 else ""
                status_code = task_info[4] if len(task_info) > 4 else 1
                status = "completed" if status_code == 2 else "in_progress"
                sources = []
                summary = ""
                if len(task_info) > 3 and isinstance(task_info[3], list):
                    result_data = task_info[3]
                    if result_data and isinstance(result_data[0], list):
                        for src in result_data[0]:
                            if isinstance(src, list) and len(src) >= 3:
                                src_url = src[2] if isinstance(src[2], str) else ""
                                src_title = src[0] if isinstance(src[0], str) else ""
                                sources.append({"url": src_url, "title": src_title})
                    if len(result_data) > 1 and isinstance(result_data[1], str):
                        summary = result_data[1]
                tasks.append({
                    "task_id": str(task_id),
                    "query": query,
                    "status": status,
                    "sources": sources,
                    "summary": summary,
                })
            except (IndexError, TypeError):
                continue
        return {"tasks": tasks}

    async def import_research_sources(
        self,
        notebook_url: str,
        task_id: str,
        sources: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        nb_id = self._notebook_internal_id(notebook_url)
        encoded_sources = [
            [None, None, [s.get("url", ""), s.get("title", "")], None, None, None, None, None, None, None, 2]
            for s in sources
        ]
        params: list[Any] = [None, [1], task_id, nb_id, encoded_sources]
        data = await self._rpc(_RPC_IMPORT_RESEARCH, params, nb_id)
        # Parse imported sources from response
        imported = []
        try:
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, list) and item:
                        src_id = item[0]
                        if isinstance(src_id, list):
                            src_id = src_id[0]
                        title = item[1] if len(item) > 1 else ""
                        if isinstance(title, list):
                            title = title[0] if title else ""
                        imported.append({"id": str(src_id), "title": title})
        except (IndexError, TypeError):
            pass
        return imported

    async def wait_until_source_ready(
        self,
        notebook_url: str,
        source_id: str,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Poll list_sources until the given source reaches READY status."""
        interval = 1.0
        elapsed = 0.0
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            sources = await self.list_sources(notebook_url)
            for s in sources:
                if s["id"] == source_id and s["status"] in (2, 3):  # READY or ERROR
                    return s
            interval = min(interval * 1.5, 10.0)
        raise TimeoutError(f"Source {source_id} did not become ready within {timeout}s")
