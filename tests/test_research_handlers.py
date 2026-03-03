"""Tests for research tool handlers."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.tools.handlers import ToolHandlers


@pytest.fixture
def handlers_with_notebook(tmp_library_with_notebook, mock_session_manager, mock_auth_manager, tmp_path):
    mock_config = MagicMock()
    mock_config.browserStateDir = str(tmp_path / "browser_state")
    mock_config.dataDir = str(tmp_path)
    mock_config.notebookUrl = ""
    Path(mock_config.browserStateDir).mkdir(parents=True, exist_ok=True)
    h = ToolHandlers(mock_session_manager, mock_auth_manager, tmp_library_with_notebook, config=mock_config)
    return h


@pytest.fixture
def mock_api_client():
    client = MagicMock()
    client.start_research = AsyncMock(return_value={
        "task_id": "task-abc",
        "query": "machine learning",
        "source": "web",
        "mode": "fast",
    })
    client.get_research_status = AsyncMock(return_value={
        "tasks": [
            {
                "task_id": "task-abc",
                "query": "machine learning",
                "status": "completed",
                "sources": [{"url": "https://ml.example.com", "title": "ML Overview"}],
                "summary": "A brief overview of ML concepts.",
            }
        ]
    })
    client.import_research_sources = AsyncMock(return_value=[
        {"id": "imported-1", "title": "ML Overview"},
    ])
    return client


def _inject(handlers, mock_client):
    handlers._api_client = mock_client


class TestHandleStartResearch:
    async def test_returns_task_id(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_start_research({
            "notebook_id": nb_id,
            "query": "machine learning",
        })
        assert result["success"] is True
        assert result["data"]["task_id"] == "task-abc"

    async def test_passes_source_and_mode(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        await handlers_with_notebook.handle_start_research({
            "notebook_id": nb_id,
            "query": "deep learning",
            "source": "drive",
            "mode": "deep",
        })
        call_args = mock_api_client.start_research.call_args
        assert call_args[0][2] == "drive"
        assert call_args[0][3] == "deep"

    async def test_defaults_to_web_fast(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        await handlers_with_notebook.handle_start_research({
            "notebook_id": nb_id,
            "query": "test query",
        })
        call_args = mock_api_client.start_research.call_args
        assert call_args[0][2] == "web"
        assert call_args[0][3] == "fast"

    async def test_returns_failure_for_unknown_notebook(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        result = await handlers_with_notebook.handle_start_research({
            "notebook_id": "nonexistent",
            "query": "test",
        })
        assert result["success"] is False

    async def test_propagates_api_error(self, handlers_with_notebook, mock_api_client):
        mock_api_client.start_research = AsyncMock(side_effect=Exception("auth error"))
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_start_research({
            "notebook_id": nb_id,
            "query": "test",
        })
        assert result["success"] is False
        assert "auth error" in result["error"]


class TestHandleGetResearchStatus:
    async def test_returns_tasks(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_get_research_status({"notebook_id": nb_id})
        assert result["success"] is True
        assert len(result["data"]["tasks"]) == 1
        assert result["data"]["tasks"][0]["task_id"] == "task-abc"

    async def test_returns_sources_in_task(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_get_research_status({"notebook_id": nb_id})
        task = result["data"]["tasks"][0]
        assert len(task["sources"]) == 1
        assert task["sources"][0]["url"] == "https://ml.example.com"

    async def test_returns_failure_for_unknown_notebook(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        result = await handlers_with_notebook.handle_get_research_status({"notebook_id": "bad"})
        assert result["success"] is False


class TestHandleImportResearchSources:
    async def test_imports_sources_successfully(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_import_research_sources({
            "notebook_id": nb_id,
            "task_id": "task-abc",
            "sources": [{"url": "https://ml.example.com", "title": "ML Overview"}],
        })
        assert result["success"] is True
        assert len(result["data"]["imported"]) == 1
        assert result["data"]["imported"][0]["id"] == "imported-1"

    async def test_passes_task_id_to_client(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        await handlers_with_notebook.handle_import_research_sources({
            "notebook_id": nb_id,
            "task_id": "task-xyz",
            "sources": [],
        })
        call_args = mock_api_client.import_research_sources.call_args
        assert call_args[0][1] == "task-xyz"

    async def test_returns_failure_for_unknown_notebook(self, handlers_with_notebook, mock_api_client):
        _inject(handlers_with_notebook, mock_api_client)
        result = await handlers_with_notebook.handle_import_research_sources({
            "notebook_id": "nonexistent",
            "task_id": "task-abc",
            "sources": [],
        })
        assert result["success"] is False

    async def test_propagates_import_error(self, handlers_with_notebook, mock_api_client):
        mock_api_client.import_research_sources = AsyncMock(side_effect=Exception("import failed"))
        _inject(handlers_with_notebook, mock_api_client)
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_import_research_sources({
            "notebook_id": nb_id,
            "task_id": "task-abc",
            "sources": [],
        })
        assert result["success"] is False
        assert "import failed" in result["error"]
