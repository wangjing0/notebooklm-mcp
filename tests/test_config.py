"""Tests for configuration utilities."""


from src.config import _parse_bool, _parse_int, _parse_list, build_config


class TestParseBool:
    def test_true_string_values(self):
        for val in ("true", "True", "TRUE", "1"):
            assert _parse_bool(val, False) is True

    def test_false_string_values(self):
        for val in ("false", "False", "FALSE", "0", "no"):
            assert _parse_bool(val, True) is False

    def test_none_returns_default_true(self):
        assert _parse_bool(None, True) is True

    def test_none_returns_default_false(self):
        assert _parse_bool(None, False) is False


class TestParseInt:
    def test_valid_integer(self):
        assert _parse_int("42", 0) == 42

    def test_negative_integer(self):
        assert _parse_int("-5", 0) == -5

    def test_invalid_string_returns_default(self):
        assert _parse_int("not-a-number", 99) == 99

    def test_empty_string_returns_default(self):
        assert _parse_int("", 10) == 10

    def test_none_returns_default(self):
        assert _parse_int(None, 5) == 5


class TestParseList:
    def test_comma_separated_values(self):
        result = _parse_list("a, b, c", [])
        assert result == ["a", "b", "c"]

    def test_strips_whitespace(self):
        result = _parse_list("  x  ,  y  ", [])
        assert result == ["x", "y"]

    def test_empty_string_returns_default(self):
        default = ["x", "y"]
        assert _parse_list("", default) == default

    def test_none_returns_default(self):
        default = ["a"]
        assert _parse_list(None, default) == default

    def test_single_value(self):
        assert _parse_list("solo", []) == ["solo"]

    def test_filters_empty_segments(self):
        result = _parse_list("a,,b", [])
        assert result == ["a", "b"]


class TestBuildConfig:
    def test_default_max_sessions(self, monkeypatch):
        monkeypatch.delenv("MAX_SESSIONS", raising=False)
        cfg = build_config()
        assert cfg.maxSessions == 10

    def test_default_session_timeout(self, monkeypatch):
        monkeypatch.delenv("SESSION_TIMEOUT", raising=False)
        cfg = build_config()
        assert cfg.sessionTimeout == 900

    def test_default_headless_true(self, monkeypatch):
        monkeypatch.delenv("HEADLESS", raising=False)
        cfg = build_config()
        assert cfg.headless is True

    def test_max_sessions_from_env(self, monkeypatch):
        monkeypatch.setenv("MAX_SESSIONS", "5")
        cfg = build_config()
        assert cfg.maxSessions == 5

    def test_headless_false_from_env(self, monkeypatch):
        monkeypatch.setenv("HEADLESS", "false")
        cfg = build_config()
        assert cfg.headless is False

    def test_notebook_url_from_env(self, monkeypatch):
        monkeypatch.setenv("NOTEBOOK_URL", "https://notebooklm.google.com/notebook/test")
        cfg = build_config()
        assert cfg.notebookUrl == "https://notebooklm.google.com/notebook/test"

    def test_notebook_topics_from_env(self, monkeypatch):
        monkeypatch.setenv("NOTEBOOK_TOPICS", "ai, ml, python")
        cfg = build_config()
        assert cfg.notebookTopics == ["ai", "ml", "python"]

    def test_invalid_profile_strategy_ignored(self, monkeypatch):
        monkeypatch.setenv("NOTEBOOK_PROFILE_STRATEGY", "invalid_value")
        cfg = build_config()
        assert cfg.profileStrategy == "auto"

    def test_valid_profile_strategies(self, monkeypatch):
        for strategy in ("auto", "single", "isolated"):
            monkeypatch.setenv("NOTEBOOK_PROFILE_STRATEGY", strategy)
            cfg = build_config()
            assert cfg.profileStrategy == strategy

    def test_data_dir_defaults_not_empty(self):
        cfg = build_config()
        assert cfg.dataDir
        assert cfg.configDir

    def test_browser_state_dir_derived_from_data_dir(self):
        cfg = build_config()
        assert cfg.browserStateDir
        assert "browser_state" in cfg.browserStateDir
