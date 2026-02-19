"""Tests for SettingsManager profile and tool filtering."""


import pytest

from src.utils.settings_manager import PROFILES, SettingsManager


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    """SettingsManager backed by an isolated tmp directory."""
    import src.config
    monkeypatch.setattr(src.config.CONFIG, "configDir", str(tmp_path))
    monkeypatch.delenv("NOTEBOOKLM_PROFILE", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_DISABLED_TOOLS", raising=False)
    return SettingsManager()


@pytest.fixture
def mock_tools():
    """Minimal tool objects with a name attribute."""
    class _Tool:
        def __init__(self, name):
            self.name = name

    return [_Tool(n) for n in ["ask_question", "get_health", "list_notebooks", "setup_auth", "add_notebook"]]


class TestDefaultSettings:
    def test_default_profile_is_full(self, tmp_settings):
        settings = tmp_settings.get_effective_settings()
        assert settings["profile"] == "full"

    def test_default_no_disabled_tools(self, tmp_settings):
        settings = tmp_settings.get_effective_settings()
        assert settings["disabledTools"] == []


class TestProfileFiltering:
    def test_full_profile_includes_all_tools(self, tmp_settings, mock_tools):
        result = tmp_settings.filter_tools(mock_tools)
        assert len(result) == len(mock_tools)

    def test_minimal_profile_filters_tools(self, tmp_settings, mock_tools, monkeypatch):
        monkeypatch.setenv("NOTEBOOKLM_PROFILE", "minimal")
        result = tmp_settings.filter_tools(mock_tools)
        names = {t.name for t in result}
        assert "ask_question" in names
        assert "get_health" in names
        assert "setup_auth" not in names
        assert "add_notebook" not in names

    def test_standard_profile_includes_core_tools(self, tmp_settings, mock_tools, monkeypatch):
        monkeypatch.setenv("NOTEBOOKLM_PROFILE", "standard")
        result = tmp_settings.filter_tools(mock_tools)
        names = {t.name for t in result}
        assert "ask_question" in names
        assert "add_notebook" in names

    def test_unknown_profile_falls_back_to_full(self, tmp_settings, mock_tools, monkeypatch):
        monkeypatch.setenv("NOTEBOOKLM_PROFILE", "nonexistent_profile")
        result = tmp_settings.filter_tools(mock_tools)
        assert len(result) == len(mock_tools)


class TestDisabledTools:
    def test_disabled_tool_excluded_from_full_profile(self, tmp_settings, mock_tools, monkeypatch):
        monkeypatch.setenv("NOTEBOOKLM_DISABLED_TOOLS", "setup_auth")
        result = tmp_settings.filter_tools(mock_tools)
        names = {t.name for t in result}
        assert "setup_auth" not in names

    def test_multiple_disabled_tools(self, tmp_settings, mock_tools, monkeypatch):
        monkeypatch.setenv("NOTEBOOKLM_DISABLED_TOOLS", "setup_auth, add_notebook")
        result = tmp_settings.filter_tools(mock_tools)
        names = {t.name for t in result}
        assert "setup_auth" not in names
        assert "add_notebook" not in names


class TestProfiles:
    def test_minimal_profile_defined(self):
        assert "minimal" in PROFILES

    def test_standard_profile_defined(self):
        assert "standard" in PROFILES

    def test_full_profile_is_wildcard(self):
        assert "*" in PROFILES["full"]

    def test_minimal_subset_of_standard(self):
        minimal = set(PROFILES["minimal"])
        standard = set(PROFILES["standard"])
        assert minimal.issubset(standard)

    def test_minimal_contains_ask_question(self):
        assert "ask_question" in PROFILES["minimal"]
