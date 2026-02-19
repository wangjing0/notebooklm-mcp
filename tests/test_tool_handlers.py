"""Tests for ToolHandlers library operations (no browser required)."""

import pytest

from src.library.notebook_library import NotebookLibrary
from src.tools.handlers import ToolHandlers


@pytest.fixture
def handlers(tmp_library, mock_session_manager, mock_auth_manager):
    """ToolHandlers wired to an in-memory library with mocked browser dependencies."""
    return ToolHandlers(mock_session_manager, mock_auth_manager, tmp_library)


@pytest.fixture
def handlers_with_notebook(tmp_library_with_notebook, mock_session_manager, mock_auth_manager):
    """ToolHandlers pre-populated with one notebook."""
    return ToolHandlers(mock_session_manager, mock_auth_manager, tmp_library_with_notebook)


class TestHandleListNotebooks:
    async def test_returns_success(self, handlers):
        result = await handlers.handle_list_notebooks()
        assert result["success"] is True

    async def test_returns_empty_list_initially(self, handlers):
        result = await handlers.handle_list_notebooks()
        assert result["data"]["notebooks"] == []

    async def test_returns_all_notebooks(self, handlers_with_notebook):
        result = await handlers_with_notebook.handle_list_notebooks()
        assert len(result["data"]["notebooks"]) == 1


class TestHandleGetNotebook:
    async def test_returns_notebook_by_id(self, handlers_with_notebook):
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_get_notebook({"id": nb_id})
        assert result["success"] is True
        assert result["data"]["notebook"]["id"] == nb_id

    async def test_returns_failure_for_nonexistent(self, handlers):
        result = await handlers.handle_get_notebook({"id": "nonexistent"})
        assert result["success"] is False
        assert "error" in result


class TestHandleAddNotebook:
    async def test_add_notebook_success(self, handlers):
        result = await handlers.handle_add_notebook({
            "url": "https://notebooklm.google.com/notebook/new",
            "name": "New Notebook",
            "description": "A fresh notebook",
            "topics": ["new", "topic"],
        })
        assert result["success"] is True
        assert result["data"]["notebook"]["name"] == "New Notebook"

    async def test_add_notebook_appears_in_list(self, handlers):
        await handlers.handle_add_notebook({
            "url": "https://notebooklm.google.com/notebook/added",
            "name": "Added",
            "description": "desc",
            "topics": [],
        })
        list_result = await handlers.handle_list_notebooks()
        assert len(list_result["data"]["notebooks"]) == 1


class TestHandleSelectNotebook:
    async def test_select_existing_notebook(self, handlers_with_notebook):
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_select_notebook({"id": nb_id})
        assert result["success"] is True

    async def test_select_nonexistent_returns_failure(self, handlers):
        result = await handlers.handle_select_notebook({"id": "nonexistent"})
        assert result["success"] is False


class TestHandleUpdateNotebook:
    async def test_update_name(self, handlers_with_notebook):
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        result = await handlers_with_notebook.handle_update_notebook({"id": nb_id, "name": "Updated"})
        assert result["success"] is True
        assert result["data"]["notebook"]["name"] == "Updated"

    async def test_update_nonexistent_returns_failure(self, handlers):
        result = await handlers.handle_update_notebook({"id": "nonexistent", "name": "x"})
        assert result["success"] is False


class TestHandleRemoveNotebook:
    async def test_remove_existing(self, handlers_with_notebook):
        nb = handlers_with_notebook._library.list_notebooks()[0]
        result = await handlers_with_notebook.handle_remove_notebook({"id": nb["id"]})
        assert result["success"] is True
        assert result["data"]["removed"] is True

    async def test_remove_nonexistent_returns_failure(self, handlers):
        result = await handlers.handle_remove_notebook({"id": "nonexistent"})
        assert result["success"] is False

    async def test_remove_closes_sessions(self, handlers_with_notebook, mock_session_manager):
        nb_id = handlers_with_notebook._library.list_notebooks()[0]["id"]
        await handlers_with_notebook.handle_remove_notebook({"id": nb_id})
        mock_session_manager.close_sessions_for_notebook.assert_called_once()


class TestHandleSearchNotebooks:
    async def test_search_returns_matches(self, handlers_with_notebook):
        result = await handlers_with_notebook.handle_search_notebooks({"query": "Test"})
        assert result["success"] is True
        assert len(result["data"]["notebooks"]) == 1

    async def test_search_no_match(self, handlers_with_notebook):
        result = await handlers_with_notebook.handle_search_notebooks({"query": "zxyzxyzxyz"})
        assert result["success"] is True
        assert result["data"]["notebooks"] == []


class TestHandleGetLibraryStats:
    async def test_stats_empty_library(self, handlers):
        result = await handlers.handle_get_library_stats()
        assert result["success"] is True
        assert result["data"]["total_notebooks"] == 0

    async def test_stats_with_notebook(self, handlers_with_notebook):
        result = await handlers_with_notebook.handle_get_library_stats()
        assert result["success"] is True
        assert result["data"]["total_notebooks"] == 1
