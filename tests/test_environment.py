"""Tests for API key validation (environment.py)."""

import os
from unittest.mock import patch

import pytest

from yt_excel.environment import validate_api_key


class TestValidateApiKey:
    """Tests for validate_api_key()."""

    def test_valid_key_returns_key(self):
        """Normal API key is returned as-is."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-123"}, clear=False):
            result = validate_api_key()
        assert result == "sk-test-key-123"

    def test_missing_key_exits(self):
        """Missing OPENAI_API_KEY raises SystemExit."""
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        with patch("yt_excel.environment.load_dotenv"):
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(SystemExit) as exc_info:
                    validate_api_key()
                assert "OPENAI_API_KEY is not set" in str(exc_info.value)

    def test_empty_key_exits(self):
        """Empty string API key raises SystemExit."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with pytest.raises(SystemExit) as exc_info:
                validate_api_key()
            assert "set but empty" in str(exc_info.value)

    def test_whitespace_only_key_exits(self):
        """Whitespace-only API key is treated as empty."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "   "}, clear=False):
            with pytest.raises(SystemExit) as exc_info:
                validate_api_key()
            assert "set but empty" in str(exc_info.value)

    def test_dotenv_loading_called(self):
        """load_dotenv is called with override=False."""
        with patch("yt_excel.environment.load_dotenv") as mock_dotenv:
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-abc"}, clear=False):
                validate_api_key()
            mock_dotenv.assert_called_once_with(override=False)

    def test_system_env_takes_precedence_over_dotenv(self):
        """System environment variable is not overridden by .env."""
        # load_dotenv(override=False) should not replace existing env vars
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-system"}, clear=False):
            result = validate_api_key()
        assert result == "sk-system"

    def test_error_message_does_not_contain_key_value(self):
        """Error messages must never leak the API key value."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with pytest.raises(SystemExit) as exc_info:
                validate_api_key()
            # Ensure no actual key-like string in the error
            assert "sk-" not in str(exc_info.value)
