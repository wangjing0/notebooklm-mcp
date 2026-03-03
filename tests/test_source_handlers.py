"""Tests for source management tool handlers."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.handlers import ToolHandlers


SAMPLE_NOTEBOOK_URL = "https://notebooklm.google.com/notebook/abc123"


@pytest.fixture
def handlers_with_notebook(tmp_library_with_notebook, mock_session_manager, mock_auth_manager, tmp_path):
    """ToolHandlers pre-populated with one notebook, using a tmp browserStateDir."""
    import src.config as cfg_module
    mock_config = MagicMock()
    mock_config.browserStateDir = str(tmp_path / "browser_state")
    mock_config.dataDir = str(tmp_path)
    mock_config.notebookUrl = ""
    Path(mock_config.browserStateDir).mkdir(parents=True, exist_ok=True)
    with patch.object(cfg_module, "CONFIG", mock_config):
        h = ToolHandlers(mock_session_manager, mock_auth_manager, tmp_library_with_notebook, config=mock_config)
    return h


@pytest.fixture
def mock_api_client():
    client = MagicMock()
    client.list_sources = AsyncMock(return_value=[])
    client.add_source_url = AsyncMock(return_value={"id": "src1", "title": "Example", "url": "https://example.com", "kind": "web_page", "status": 1, "is_ready": False})
    client.add_source_text = AsyncMock(return_value={"id": "src2", "title": "My Text", "url": None, "kind": "pasted_text", "status": 2, "is_ready": True})
    client.add_source_file = AsyncMock(return_value={"id": "src3", "title": "doc.pdf", "url": None, "kind": "unknown", "status": 1, "is_ready": False})
    client.delete_source = AsyncMock(return_value=True)
    return client


def _inject_api_client(handlers, mock_client):
    handlers._api_client = mock_client


class TestHandleListSources:
    async def test_returns_sources_list(self, handlers_with_notebook, mock_api_client):
        mock_api_client.list_sources = AsyncMock(return_value=[
            {"id": "s1", "title": "Source 1", "url": "https://a.com", "kind": "web_page", "status": 2, "is_ready": True},
        ])
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_list_sources({"notebook_id": nb_id})
        assert result["success"] is True
        assert len(result["data"]["sources"]) == 1

    async def test_returns_failure_for_unknown_notebook(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        result = await handlers_with_notebook.handle_list_sources({"notebook_id": "nonexistent"})
        assert result["success"] is False
        assert "error" in result

    async def test_propagates_api_error(self, handlers_with_notebook, mock_api_client):
        mock_api_client.list_sources = AsyncMock(side_effect=Exception("network error"))
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_list_sources({"notebook_id": nb_id})
        assert result["success"] is False
        assert "network error" in result["error"]


class TestHandleAddSourceUrl:
    async def test_adds_url_successfully(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_add_source_url({
            "notebook_id": nb_id,
            "url": "https://example.com",
        })
        assert result["success"] is True
        assert result["data"]["source"]["id"] == "src1"
        mock_api_client.add_source_url.assert_called_once()

    async def test_passes_url_to_client(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        await handlers_with_notebook.handle_add_source_url({
            "notebook_id": nb_id,
            "url": "https://youtube.com/watch?v=abc",
        })
        call_args = mock_api_client.add_source_url.call_args
        assert call_args[0][1] == "https://youtube.com/watch?v=abc"

    async def test_returns_failure_on_unknown_notebook(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        result = await handlers_with_notebook.handle_add_source_url({
            "notebook_id": "bad-id",
            "url": "https://example.com",
        })
        assert result["success"] is False


class TestHandleAddSourceText:
    async def test_adds_text_successfully(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_add_source_text({
            "notebook_id": nb_id,
            "title": "My Notes",
            "content": "Some content here",
        })
        assert result["success"] is True
        assert result["data"]["source"]["id"] == "src2"
        mock_api_client.add_source_text.assert_called_once()

    async def test_passes_title_and_content_to_client(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        await handlers_with_notebook.handle_add_source_text({
            "notebook_id": nb_id,
            "title": "Title A",
            "content": "Body A",
        })
        call_args = mock_api_client.add_source_text.call_args
        assert call_args[0][1] == "Title A"
        assert call_args[0][2] == "Body A"


class TestHandleAddSourceFile:
    async def test_returns_failure_when_file_not_found(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_add_source_file({
            "notebook_id": nb_id,
            "file_path": "/nonexistent/path/doc.pdf",
        })
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    async def test_adds_existing_file(self, handlers_with_notebook, mock_api_client, tmp_path):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_add_source_file({
            "notebook_id": nb_id,
            "file_path": str(test_file),
        })
        assert result["success"] is True
        assert result["data"]["source"]["id"] == "src3"


class TestHandleDeleteSource:
    async def test_deletes_source_successfully(self, handlers_with_notebook, mock_api_client):
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_delete_source({
            "notebook_id": nb_id,
            "source_id": "src1",
        })
        assert result["success"] is True
        assert result["data"]["deleted"] is True
        assert result["data"]["source_id"] == "src1"
        mock_api_client.delete_source.assert_called_once()

    async def test_propagates_delete_error(self, handlers_with_notebook, mock_api_client):
        mock_api_client.delete_source = AsyncMock(side_effect=Exception("source not found"))
        _inject_api_client(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_delete_source({
            "notebook_id": nb_id,
            "source_id": "missing-src",
        })
        assert result["success"] is False
        assert "source not found" in result["error"]
