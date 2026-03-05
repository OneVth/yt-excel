"""Phase 7: Pipeline error handling tests.

Covers:
- AuthenticationError (invalid API key) during translation
- Unhandled translation exceptions are caught gracefully
- Network failure during metadata fetch
- Network failure during caption download
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yt_excel.cli import Output, _run_pipeline, build_parser
from yt_excel.config import AppConfig
from yt_excel.youtube import CaptionInfo, VideoMeta


SAMPLE_VTT = """\
WEBVTT

00:00:01.000 --> 00:00:04.500
Hello and welcome to this video.

00:00:05.000 --> 00:00:08.200
Today we are going to learn about DNA.
"""


def _make_args(url: str, tmp_path: Path):
    """Create mock CLI args."""
    parser = build_parser()
    return parser.parse_args([url, "--master", str(tmp_path / "Master.xlsx")])


def _make_config(tmp_path: Path) -> AppConfig:
    """Create test config."""
    config = AppConfig()
    config.file.master_path = str(tmp_path / "Master.xlsx")
    config.translation.max_retries = 1
    config.translation.request_interval_ms = 0
    return config


class TestAuthenticationErrorPipeline:
    """Tests for invalid API key during translation step."""

    @patch("yt_excel.cli.download_captions")
    @patch("yt_excel.cli.list_captions")
    @patch("yt_excel.cli.fetch_metadata")
    @patch("yt_excel.cli.validate_api_key")
    @patch("yt_excel.translator.time.sleep")
    def test_auth_error_exits_gracefully(
        self,
        mock_sleep,
        mock_api_key,
        mock_fetch_meta,
        mock_list_captions,
        mock_download,
        tmp_path,
    ):
        """AuthenticationError during translation exits with error message."""
        from openai import AuthenticationError

        mock_api_key.return_value = "sk-invalid-key"
        mock_fetch_meta.return_value = VideoMeta(
            video_id="dQw4w9WgXcQ",
            title="Auth Test",
            channel="TestChannel",
            duration="00:02:00",
        )
        mock_list_captions.return_value = CaptionInfo(
            lang_code="en", caption_type="manual", available_codes=["en"]
        )
        mock_download.return_value = SAMPLE_VTT

        args = _make_args("https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path)
        config = _make_config(tmp_path)
        out = Output("quiet")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_client.chat.completions.create.side_effect = AuthenticationError(
            message="Incorrect API key provided",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )

        with patch("yt_excel.cli.create_client", return_value=mock_client):
            with patch("yt_excel.cli.detect_font", return_value="Malgun Gothic"):
                with pytest.raises(SystemExit) as exc_info:
                    _run_pipeline(args, config, out, 0.0)
                assert exc_info.value.code == 1


class TestNetworkFailurePipeline:
    """Tests for network failures at different pipeline stages."""

    @patch("yt_excel.cli.fetch_metadata")
    @patch("yt_excel.cli.validate_api_key")
    def test_metadata_fetch_failure_exits(
        self, mock_api_key, mock_fetch_meta, tmp_path
    ):
        """Network failure during metadata fetch exits with error."""
        mock_api_key.return_value = "sk-test"
        mock_fetch_meta.side_effect = Exception("Network timeout")

        args = _make_args("https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path)
        config = _make_config(tmp_path)
        out = Output("quiet")

        with pytest.raises(SystemExit) as exc_info:
            _run_pipeline(args, config, out, 0.0)
        assert exc_info.value.code == 1

    @patch("yt_excel.cli.download_captions")
    @patch("yt_excel.cli.list_captions")
    @patch("yt_excel.cli.fetch_metadata")
    @patch("yt_excel.cli.validate_api_key")
    def test_caption_download_failure_exits(
        self, mock_api_key, mock_fetch_meta, mock_list_captions, mock_download, tmp_path
    ):
        """Network failure during caption download exits with error."""
        mock_api_key.return_value = "sk-test"
        mock_fetch_meta.return_value = VideoMeta(
            video_id="dQw4w9WgXcQ",
            title="Download Fail",
            channel="TestChannel",
            duration="00:02:00",
        )
        mock_list_captions.return_value = CaptionInfo(
            lang_code="en", caption_type="manual", available_codes=["en"]
        )
        mock_download.side_effect = Exception("Download failed after 3 retries")

        args = _make_args("https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path)
        config = _make_config(tmp_path)
        out = Output("quiet")

        with pytest.raises(SystemExit) as exc_info:
            _run_pipeline(args, config, out, 0.0)
        assert exc_info.value.code == 1
