"""Tests for custom error types."""

import pytest

from src.errors import AuthenticationError, RateLimitError


class TestRateLimitError:
    def test_is_exception(self):
        with pytest.raises(RateLimitError):
            raise RateLimitError("Rate limit exceeded")

    def test_message_preserved(self):
        msg = "Daily query limit reached"
        with pytest.raises(RateLimitError, match=msg):
            raise RateLimitError(msg)

    def test_inherits_from_exception(self):
        assert issubclass(RateLimitError, Exception)


class TestAuthenticationError:
    def test_is_exception(self):
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("Auth failed")

    def test_message_preserved(self):
        msg = "Google session expired"
        with pytest.raises(AuthenticationError, match=msg):
            raise AuthenticationError(msg)

    def test_inherits_from_exception(self):
        assert issubclass(AuthenticationError, Exception)


class TestErrorDistinction:
    def test_errors_are_distinct_types(self):
        assert RateLimitError is not AuthenticationError

    def test_rate_limit_not_auth_error(self):
        assert not issubclass(RateLimitError, AuthenticationError)

    def test_auth_error_not_rate_limit(self):
        assert not issubclass(AuthenticationError, RateLimitError)

    def test_catch_specific_type(self):
        caught_rate_limit = False
        try:
            raise RateLimitError("limit")
        except AuthenticationError:
            pass
        except RateLimitError:
            caught_rate_limit = True
        assert caught_rate_limit
