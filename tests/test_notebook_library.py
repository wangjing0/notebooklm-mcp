"""Tests for NotebookLibrary CRUD operations."""

import pytest

from src.library.notebook_library import NotebookLibrary


class TestEmptyLibrary:
    def test_list_returns_empty(self, tmp_library):
        assert tmp_library.list_notebooks() == []

    def test_no_active_notebook(self, tmp_library):
        assert tmp_library.get_active_notebook() is None

    def test_get_nonexistent_returns_none(self, tmp_library):
        assert tmp_library.get_notebook("nonexistent") is None

    def test_stats_on_empty_library(self, tmp_library):
        stats = tmp_library.get_stats()
        assert stats["total_notebooks"] == 0
        assert stats["total_queries"] == 0
        assert stats["active_notebook"] is None
        assert stats["most_used_notebook"] is None

    def test_search_returns_empty(self, tmp_library):
        assert tmp_library.search_notebooks("anything") == []


class TestAddNotebook:
    def test_add_returns_entry_with_id(self, tmp_library, sample_notebook_data):
        nb = tmp_library.add_notebook(sample_notebook_data)
        assert nb["id"]
        assert nb["name"] == sample_notebook_data["name"]
        assert nb["url"] == sample_notebook_data["url"]
        assert nb["description"] == sample_notebook_data["description"]
        assert nb["topics"] == sample_notebook_data["topics"]

    def test_add_sets_use_count_to_zero(self, tmp_library, sample_notebook_data):
        nb = tmp_library.add_notebook(sample_notebook_data)
        assert nb["use_count"] == 0

    def test_first_notebook_becomes_active(self, tmp_library, sample_notebook_data):
        tmp_library.add_notebook(sample_notebook_data)
        active = tmp_library.get_active_notebook()
        assert active is not None
        assert active["name"] == sample_notebook_data["name"]

    def test_second_notebook_does_not_override_active(self, tmp_library, sample_notebook_data):
        first = tmp_library.add_notebook(sample_notebook_data)
        tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/second",
            "name": "Second Notebook",
            "description": "Another notebook",
            "topics": ["other"],
        })
        active = tmp_library.get_active_notebook()
        assert active["id"] == first["id"]

    def test_duplicate_names_get_unique_ids(self, tmp_library):
        nb1 = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/1",
            "name": "Same Name",
            "description": "First",
            "topics": [],
        })
        nb2 = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/2",
            "name": "Same Name",
            "description": "Second",
            "topics": [],
        })
        assert nb1["id"] != nb2["id"]

    def test_add_persists_across_instances(self, tmp_library, sample_notebook_data, monkeypatch):
        import src.config
        tmp_library.add_notebook(sample_notebook_data)
        library2 = NotebookLibrary()
        assert len(library2.list_notebooks()) == 1
        assert library2.list_notebooks()[0]["name"] == sample_notebook_data["name"]

    def test_default_content_types_applied(self, tmp_library):
        nb = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/x",
            "name": "Minimal",
            "description": "d",
            "topics": [],
        })
        assert nb["content_types"]

    def test_default_use_cases_applied(self, tmp_library):
        nb = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/x",
            "name": "Minimal",
            "description": "d",
            "topics": [],
        })
        assert nb["use_cases"]


class TestGetNotebook:
    def test_get_by_id(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        result = tmp_library_with_notebook.get_notebook(nb_id)
        assert result is not None
        assert result["name"] == "Test Notebook"

    def test_get_nonexistent_returns_none(self, tmp_library_with_notebook):
        assert tmp_library_with_notebook.get_notebook("does-not-exist") is None


class TestSelectNotebook:
    def test_select_changes_active(self, tmp_library):
        tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/first",
            "name": "First",
            "description": "d",
            "topics": [],
        })
        nb2 = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/second",
            "name": "Second",
            "description": "d",
            "topics": [],
        })
        tmp_library.select_notebook(nb2["id"])
        assert tmp_library.get_active_notebook()["id"] == nb2["id"]

    def test_select_nonexistent_raises(self, tmp_library):
        with pytest.raises(ValueError, match="Notebook not found"):
            tmp_library.select_notebook("nonexistent")

    def test_select_updates_last_used(self, tmp_library_with_notebook):
        nb = tmp_library_with_notebook.list_notebooks()[0]
        old_last_used = nb["last_used"]
        import time
        time.sleep(0.01)
        tmp_library_with_notebook.select_notebook(nb["id"])
        updated = tmp_library_with_notebook.get_notebook(nb["id"])
        assert updated["last_used"] >= old_last_used


class TestUpdateNotebook:
    def test_update_name(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        updated = tmp_library_with_notebook.update_notebook({"id": nb_id, "name": "New Name"})
        assert updated["name"] == "New Name"

    def test_update_description(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        updated = tmp_library_with_notebook.update_notebook({"id": nb_id, "description": "New desc"})
        assert updated["description"] == "New desc"

    def test_update_topics(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        updated = tmp_library_with_notebook.update_notebook({"id": nb_id, "topics": ["new-topic"]})
        assert updated["topics"] == ["new-topic"]

    def test_update_url(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        new_url = "https://notebooklm.google.com/notebook/updated"
        updated = tmp_library_with_notebook.update_notebook({"id": nb_id, "url": new_url})
        assert updated["url"] == new_url

    def test_update_nonexistent_raises(self, tmp_library):
        with pytest.raises(ValueError, match="Notebook not found"):
            tmp_library.update_notebook({"id": "nonexistent", "name": "x"})

    def test_update_persists(self, tmp_library_with_notebook, monkeypatch):
        import src.config
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        tmp_library_with_notebook.update_notebook({"id": nb_id, "name": "Persisted Name"})
        library2 = NotebookLibrary()
        assert library2.get_notebook(nb_id)["name"] == "Persisted Name"


class TestRemoveNotebook:
    def test_remove_existing(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        result = tmp_library_with_notebook.remove_notebook(nb_id)
        assert result is True
        assert tmp_library_with_notebook.list_notebooks() == []

    def test_remove_nonexistent_returns_false(self, tmp_library):
        assert tmp_library.remove_notebook("nonexistent") is False

    def test_remove_active_clears_active(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        tmp_library_with_notebook.remove_notebook(nb_id)
        assert tmp_library_with_notebook.get_active_notebook() is None

    def test_remove_active_promotes_next(self, tmp_library):
        tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/1",
            "name": "First",
            "description": "d",
            "topics": [],
        })
        nb2 = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/2",
            "name": "Second",
            "description": "d",
            "topics": [],
        })
        first_id = tmp_library.list_notebooks()[0]["id"]
        tmp_library.remove_notebook(first_id)
        active = tmp_library.get_active_notebook()
        assert active is not None
        assert active["id"] == nb2["id"]


class TestSearchNotebooks:
    def test_search_by_name(self, tmp_library_with_notebook):
        results = tmp_library_with_notebook.search_notebooks("Test")
        assert len(results) == 1

    def test_search_by_topic(self, tmp_library_with_notebook):
        results = tmp_library_with_notebook.search_notebooks("pytest")
        assert len(results) == 1

    def test_search_by_description(self, tmp_library_with_notebook):
        results = tmp_library_with_notebook.search_notebooks("testing purposes")
        assert len(results) == 1

    def test_search_case_insensitive(self, tmp_library_with_notebook):
        results = tmp_library_with_notebook.search_notebooks("TEST NOTEBOOK")
        assert len(results) == 1

    def test_search_no_match(self, tmp_library_with_notebook):
        results = tmp_library_with_notebook.search_notebooks("zxyzxyzxyzxyz")
        assert results == []

    def test_search_returns_multiple_matches(self, tmp_library):
        for i in range(3):
            tmp_library.add_notebook({
                "url": f"https://notebooklm.google.com/notebook/{i}",
                "name": f"Python Notebook {i}",
                "description": "Python-related content",
                "topics": ["python"],
            })
        results = tmp_library.search_notebooks("python")
        assert len(results) == 3


class TestIncrementUseCount:
    def test_increment_once(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        result = tmp_library_with_notebook.increment_use_count(nb_id)
        assert result is not None
        assert result["use_count"] == 1

    def test_increment_multiple_times(self, tmp_library_with_notebook):
        nb_id = tmp_library_with_notebook.list_notebooks()[0]["id"]
        for _ in range(5):
            tmp_library_with_notebook.increment_use_count(nb_id)
        nb = tmp_library_with_notebook.get_notebook(nb_id)
        assert nb["use_count"] == 5

    def test_increment_nonexistent_returns_none(self, tmp_library):
        assert tmp_library.increment_use_count("nonexistent") is None


class TestLibraryStats:
    def test_stats_with_one_notebook(self, tmp_library_with_notebook):
        stats = tmp_library_with_notebook.get_stats()
        assert stats["total_notebooks"] == 1
        assert stats["total_queries"] == 0
        assert stats["active_notebook"] is not None

    def test_most_used_notebook(self, tmp_library):
        tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/1",
            "name": "Rarely Used",
            "description": "d",
            "topics": [],
        })
        nb2 = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/2",
            "name": "Often Used",
            "description": "d",
            "topics": [],
        })
        tmp_library.increment_use_count(nb2["id"])
        tmp_library.increment_use_count(nb2["id"])
        stats = tmp_library.get_stats()
        assert stats["most_used_notebook"] == nb2["id"]
        assert stats["total_queries"] == 2

    def test_total_queries_sums_all(self, tmp_library):
        nb1 = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/1",
            "name": "First",
            "description": "d",
            "topics": [],
        })
        nb2 = tmp_library.add_notebook({
            "url": "https://notebooklm.google.com/notebook/2",
            "name": "Second",
            "description": "d",
            "topics": [],
        })
        tmp_library.increment_use_count(nb1["id"])
        tmp_library.increment_use_count(nb2["id"])
        tmp_library.increment_use_count(nb2["id"])
        stats = tmp_library.get_stats()
        assert stats["total_queries"] == 3
