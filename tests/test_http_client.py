"""Tests for the NotebookLM HTTP client internals (no network calls)."""

import json

import pytest

from src.http_client.client import (
    NotebookLMAPIClient,
    NotebookLMAuthError,
    Source,
    _encode_rpc,
    _extract_cookies,
    _extract_youtube_id,
    _is_allowed_auth_domain,
    _parse_chunked,
    _parse_source_from_response,
    _parse_sources_list,
)


class TestIsAllowedAuthDomain:
    def test_base_google_domain(self):
        assert _is_allowed_auth_domain(".google.com") is True

    def test_notebooklm_domain(self):
        assert _is_allowed_auth_domain("notebooklm.google.com") is True

    def test_googleusercontent_domain(self):
        assert _is_allowed_auth_domain(".googleusercontent.com") is True

    def test_regional_domain(self):
        assert _is_allowed_auth_domain(".google.co.uk") is True
        assert _is_allowed_auth_domain(".google.com.sg") is True

    def test_unrelated_domain(self):
        assert _is_allowed_auth_domain(".example.com") is False
        assert _is_allowed_auth_domain("github.com") is False


class TestExtractCookies:
    def test_extracts_sid_from_base_domain(self):
        state = {
            "cookies": [
                {"name": "SID", "value": "abc123", "domain": ".google.com"},
            ]
        }
        cookies = _extract_cookies(state)
        assert cookies["SID"] == "abc123"

    def test_base_domain_takes_priority(self):
        state = {
            "cookies": [
                {"name": "SID", "value": "regional", "domain": ".google.co.uk"},
                {"name": "SID", "value": "base", "domain": ".google.com"},
            ]
        }
        cookies = _extract_cookies(state)
        assert cookies["SID"] == "base"

    def test_skips_unallowed_domains(self):
        state = {
            "cookies": [
                {"name": "token", "value": "secret", "domain": "evil.com"},
                {"name": "SID", "value": "ok", "domain": ".google.com"},
            ]
        }
        cookies = _extract_cookies(state)
        assert "token" not in cookies
        assert cookies["SID"] == "ok"

    def test_empty_storage_returns_empty_dict(self):
        assert _extract_cookies({}) == {}
        assert _extract_cookies({"cookies": []}) == {}


class TestEncodeRpc:
    def test_produces_triple_nested_structure(self):
        encoded = _encode_rpc("testMethod", ["param1", "param2"])
        decoded = json.loads(encoded)
        assert isinstance(decoded, list)
        assert isinstance(decoded[0], list)
        assert isinstance(decoded[0][0], list)
        inner = decoded[0][0]
        assert inner[0] == "testMethod"

    def test_params_are_json_encoded(self):
        encoded = _encode_rpc("method", [[1, 2, 3]])
        decoded = json.loads(encoded)
        inner = decoded[0][0]
        params = json.loads(inner[1])
        assert params == [[1, 2, 3]]

    def test_fourth_element_is_generic(self):
        encoded = _encode_rpc("method", [])
        decoded = json.loads(encoded)
        inner = decoded[0][0]
        assert inner[3] == "generic"


class TestParseChunked:
    def test_strips_xssi_prefix(self):
        response = ")]}'\n100\n[\"data\"]\n"
        chunks = _parse_chunked(response)
        assert chunks == [["data"]]

    def test_handles_multiple_chunks(self):
        response = ")]}'\n5\n[1]\n5\n[2]\n"
        chunks = _parse_chunked(response)
        assert len(chunks) == 2

    def test_returns_empty_for_invalid_input(self):
        assert _parse_chunked("") == []
        assert _parse_chunked(")]}'\n") == []


class TestExtractYoutubeId:
    def test_watch_url(self):
        assert _extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert _extract_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert _extract_youtube_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_non_youtube_url(self):
        assert _extract_youtube_id("https://example.com/video") is None

    def test_plain_web_url(self):
        assert _extract_youtube_id("https://docs.python.org") is None


class TestNotebookInternalId:
    def test_extracts_id_from_url(self, tmp_path):
        client = NotebookLMAPIClient(tmp_path / "state.json")
        assert client._notebook_internal_id("https://notebooklm.google.com/notebook/abc123") == "abc123"

    def test_strips_trailing_slash(self, tmp_path):
        client = NotebookLMAPIClient(tmp_path / "state.json")
        assert client._notebook_internal_id("https://notebooklm.google.com/notebook/abc123/") == "abc123"

    def test_strips_query_string(self, tmp_path):
        client = NotebookLMAPIClient(tmp_path / "state.json")
        result = client._notebook_internal_id("https://notebooklm.google.com/notebook/abc123?authuser=0")
        assert result == "abc123"


class TestEnsureAuthFails:
    async def test_raises_auth_error_when_state_missing(self, tmp_path):
        client = NotebookLMAPIClient(tmp_path / "missing_state.json")
        with pytest.raises(NotebookLMAuthError, match="setup_auth"):
            await client._ensure_auth()

    async def test_raises_auth_error_when_sid_missing(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"cookies": []}))
        client = NotebookLMAPIClient(state_path)
        with pytest.raises(NotebookLMAuthError, match="setup_auth"):
            await client._ensure_auth()


class TestSourceDataclass:
    def test_kind_returns_type_name(self):
        s = Source(id="1", type_code=5)
        assert s.kind == "web_page"

    def test_kind_returns_unknown_for_none(self):
        s = Source(id="1", type_code=None)
        assert s.kind == "unknown"

    def test_is_ready_true_when_status_2(self):
        s = Source(id="1", status=2)
        assert s.is_ready is True

    def test_is_ready_false_when_status_1(self):
        s = Source(id="1", status=1)
        assert s.is_ready is False

    def test_to_dict_includes_all_fields(self):
        s = Source(id="x", title="Test", url="https://example.com", type_code=3, status=2)
        d = s.to_dict()
        assert d["id"] == "x"
        assert d["title"] == "Test"
        assert d["url"] == "https://example.com"
        assert d["kind"] == "pdf"
        assert d["status"] == 2
        assert d["is_ready"] is True
