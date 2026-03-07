"""Tests for duration threshold check in cli.py."""

import argparse
from unittest.mock import patch

import pytest

from yt_excel.cli import (
    Output,
    _check_duration_threshold,
    _format_duration_human,
    _parse_duration_to_seconds,
)
from yt_excel.config import AppConfig
from yt_excel.youtube import VideoMeta


def _make_meta(duration: str = "00:05:00") -> VideoMeta:
    """Create a VideoMeta with the given duration."""
    return VideoMeta(
        video_id="dQw4w9WgXcQ",
        title="Test Video",
        channel="Test Channel",
        duration=duration,
    )


def _make_config(max_duration_minutes: int = 15) -> AppConfig:
    """Create an AppConfig with the given max_duration_minutes."""
    config = AppConfig()
    config.filter.max_duration_minutes = max_duration_minutes
    return config


class TestParseDurationToSeconds:
    """Tests for _parse_duration_to_seconds helper."""

    def test_hhmmss_format(self):
        assert _parse_duration_to_seconds("01:30:00") == 5400

    def test_short_video(self):
        assert _parse_duration_to_seconds("00:05:19") == 319

    def test_zero_duration(self):
        assert _parse_duration_to_seconds("00:00:00") == 0

    def test_mmss_format(self):
        assert _parse_duration_to_seconds("05:30") == 330


class TestFormatDurationHuman:
    """Tests for _format_duration_human helper."""

    def test_with_hours(self):
        assert _format_duration_human(5400) == "1h 30m 00s"

    def test_without_hours(self):
        assert _format_duration_human(319) == "5m 19s"

    def test_zero(self):
        assert _format_duration_human(0) == "0m 00s"


class TestCheckDurationThreshold:
    """Tests for _check_duration_threshold."""

    def test_within_threshold_passes_silently(self):
        """Duration within threshold should pass without prompting."""
        meta = _make_meta("00:05:00")  # 5 min
        config = _make_config(15)
        out = Output("normal")

        # Should not raise
        _check_duration_threshold(meta, config, out)

    def test_exactly_at_threshold_passes(self):
        """Duration exactly at threshold should pass."""
        meta = _make_meta("00:15:00")  # 15 min
        config = _make_config(15)
        out = Output("normal")

        _check_duration_threshold(meta, config, out)

    def test_exceeds_threshold_user_confirms_y(self):
        """Duration exceeds threshold, user inputs 'y' -> proceed."""
        meta = _make_meta("01:30:00")  # 90 min
        config = _make_config(15)
        out = Output("normal")

        with patch("builtins.input", return_value="y"):
            _check_duration_threshold(meta, config, out)

    def test_exceeds_threshold_user_declines_n(self):
        """Duration exceeds threshold, user inputs 'N' -> exit."""
        meta = _make_meta("01:30:00")
        config = _make_config(15)
        out = Output("normal")

        with patch("builtins.input", return_value="N"):
            with pytest.raises(SystemExit):
                _check_duration_threshold(meta, config, out)

    def test_exceeds_threshold_empty_input_declines(self):
        """Duration exceeds threshold, empty input (default N) -> exit."""
        meta = _make_meta("01:30:00")
        config = _make_config(15)
        out = Output("normal")

        with patch("builtins.input", return_value=""):
            with pytest.raises(SystemExit):
                _check_duration_threshold(meta, config, out)

    def test_yes_flag_skips_prompt(self):
        """--yes flag should skip prompt and proceed."""
        meta = _make_meta("01:30:00")
        config = _make_config(15)
        out = Output("normal")

        # Should not raise, should not call input()
        with patch("builtins.input") as mock_input:
            _check_duration_threshold(meta, config, out, yes_flag=True)
            mock_input.assert_not_called()

    def test_quiet_mode_auto_aborts(self):
        """Quiet mode should auto-abort without prompting."""
        meta = _make_meta("01:30:00")
        config = _make_config(15)
        out = Output("quiet")

        with patch("builtins.input") as mock_input:
            with pytest.raises(SystemExit):
                _check_duration_threshold(meta, config, out)
            mock_input.assert_not_called()

    def test_dry_run_skips_prompt(self):
        """--dry-run should skip prompt (no API cost)."""
        meta = _make_meta("01:30:00")
        config = _make_config(15)
        out = Output("normal")

        with patch("builtins.input") as mock_input:
            _check_duration_threshold(meta, config, out, dry_run=True)
            mock_input.assert_not_called()

    def test_max_duration_zero_disables_check(self):
        """max_duration_minutes=0 should disable the check entirely."""
        meta = _make_meta("10:00:00")  # 10 hours
        config = _make_config(0)
        out = Output("normal")

        with patch("builtins.input") as mock_input:
            _check_duration_threshold(meta, config, out)
            mock_input.assert_not_called()

    def test_eof_on_input_declines(self):
        """EOFError on input should be treated as decline."""
        meta = _make_meta("01:30:00")
        config = _make_config(15)
        out = Output("normal")

        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(SystemExit):
                _check_duration_threshold(meta, config, out)


class TestBuildParserYesFlag:
    """Tests for --yes/-y CLI option in build_parser."""

    def test_yes_flag_long(self):
        from yt_excel.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["https://youtube.com/watch?v=test", "--yes"])
        assert args.yes is True

    def test_yes_flag_short(self):
        from yt_excel.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["https://youtube.com/watch?v=test", "-y"])
        assert args.yes is True

    def test_no_yes_flag_default_false(self):
        from yt_excel.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["https://youtube.com/watch?v=test"])
        assert args.yes is False
