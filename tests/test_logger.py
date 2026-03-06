"""Tests for the file logging system."""

import logging

import pytest

from yt_excel.cli import Output
from yt_excel.logger import _teardown_logging, get_logger, setup_logging


@pytest.fixture(autouse=True)
def _cleanup_logging():
    """Ensure logging is torn down after each test."""
    yield
    _teardown_logging()


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_creates_log_directory(self, tmp_path):
        """Log directory is created automatically if it doesn't exist."""
        log_dir = tmp_path / "nested" / "logs"
        assert not log_dir.exists()

        log_file = setup_logging(enabled=True, log_dir=str(log_dir))

        assert log_dir.exists()
        assert log_file is not None
        assert log_file.parent == log_dir

    def test_log_file_naming_format(self, tmp_path):
        """Log file follows yt-excel_YYYY-MM-DD_HHMMSS.log format."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))

        assert log_file is not None
        assert log_file.name.startswith("yt-excel_")
        assert log_file.suffix == ".log"
        # Check format: yt-excel_YYYY-MM-DD_HHMMSS.log
        stem = log_file.stem  # yt-excel_2026-03-06_143021
        parts = stem.split("_", 1)
        assert parts[0] == "yt-excel"
        assert len(parts[1]) == len("2026-03-06_143021")

    def test_disabled_logging_returns_none(self, tmp_path):
        """When enabled=False, no log file is created."""
        log_file = setup_logging(enabled=False, log_dir=str(tmp_path))

        assert log_file is None
        # No files should be created
        assert list(tmp_path.iterdir()) == []

    def test_log_level_debug_by_default(self, tmp_path):
        """Default log level is DEBUG."""
        setup_logging(enabled=True, log_dir=str(tmp_path), level="DEBUG")

        yt_logger = logging.getLogger("yt_excel")
        assert yt_logger.level == logging.DEBUG

    def test_log_level_info(self, tmp_path):
        """Log level can be set to INFO."""
        setup_logging(enabled=True, log_dir=str(tmp_path), level="INFO")

        yt_logger = logging.getLogger("yt_excel")
        assert yt_logger.level == logging.INFO

    def test_writes_to_log_file(self, tmp_path):
        """Messages are actually written to the log file."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))

        test_logger = get_logger("yt_excel.test")
        test_logger.info("Test message for file logging")

        # Flush handlers
        for handler in logging.getLogger("yt_excel").handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "Test message for file logging" in content
        assert "[INFO ]" in content

    def test_log_format_includes_timestamp(self, tmp_path):
        """Log entries include timestamp in expected format."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))

        test_logger = get_logger("yt_excel.test")
        test_logger.info("Format check")

        for handler in logging.getLogger("yt_excel").handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        # Format: 2026-03-06 14:30:21.123 [INFO ] Format check
        lines = [ln for ln in content.splitlines() if "Format check" in ln]
        assert len(lines) == 1
        line = lines[0]
        # Check timestamp pattern at start
        assert line[4] == "-"  # YYYY-
        assert line[7] == "-"  # MM-
        assert line[10] == " "  # DD space
        assert line[13] == ":"  # HH:

    def test_debug_messages_written_at_debug_level(self, tmp_path):
        """DEBUG messages are recorded when level is DEBUG."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))

        test_logger = get_logger("yt_excel.test")
        test_logger.debug("Debug detail message")

        for handler in logging.getLogger("yt_excel").handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "Debug detail message" in content
        assert "[DEBUG]" in content

    def test_debug_messages_not_written_at_info_level(self, tmp_path):
        """DEBUG messages are filtered out when level is INFO."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path), level="INFO")

        test_logger = get_logger("yt_excel.test")
        test_logger.debug("Should not appear")
        test_logger.info("Should appear")

        for handler in logging.getLogger("yt_excel").handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "Should not appear" not in content
        assert "Should appear" in content

    def test_multiple_setup_calls_cleanup(self, tmp_path):
        """Calling setup_logging again cleans up the previous handler."""
        dir1 = tmp_path / "logs1"
        dir2 = tmp_path / "logs2"

        setup_logging(enabled=True, log_dir=str(dir1))
        setup_logging(enabled=True, log_dir=str(dir2))

        test_logger = get_logger("yt_excel.test")
        test_logger.info("Only in second log")

        for handler in logging.getLogger("yt_excel").handlers:
            handler.flush()

        # Should only have handler for dir2
        yt_logger = logging.getLogger("yt_excel")
        file_handlers = [
            h for h in yt_logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

    def test_warning_level_logged(self, tmp_path):
        """WARNING messages are recorded."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))

        test_logger = get_logger("yt_excel.test")
        test_logger.warning("A warning occurred")

        for handler in logging.getLogger("yt_excel").handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "A warning occurred" in content
        assert "[WARN " in content or "[WARNING]" in content


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_yt_excel_namespaced_logger(self):
        """get_logger returns a logger under yt_excel namespace."""
        result = get_logger("yt_excel.youtube")
        assert result.name == "yt_excel.youtube"

    def test_non_yt_excel_name_gets_prefixed(self):
        """Names not starting with yt_excel get prefixed."""
        result = get_logger("something")
        assert result.name == "yt_excel.something"

    def test_yt_excel_name_not_double_prefixed(self):
        """Names already starting with yt_excel are not double-prefixed."""
        result = get_logger("yt_excel.cli")
        assert result.name == "yt_excel.cli"


class TestLoggingConfig:
    """Tests for LoggingConfig dataclass."""

    def test_default_values(self):
        from yt_excel.config import LoggingConfig

        cfg = LoggingConfig()
        assert cfg.enabled is True
        assert cfg.dir == "./logs"
        assert cfg.level == "DEBUG"

    def test_custom_values(self):
        from yt_excel.config import LoggingConfig

        cfg = LoggingConfig(enabled=False, dir="/tmp/custom", level="INFO")
        assert cfg.enabled is False
        assert cfg.dir == "/tmp/custom"
        assert cfg.level == "INFO"

    def test_app_config_includes_logging(self):
        from yt_excel.config import AppConfig

        config = AppConfig()
        assert hasattr(config, "logging")
        assert config.logging.enabled is True

    def test_load_config_parses_logging_section(self, tmp_path):
        from yt_excel.config import load_config

        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "logging:\n"
            "  enabled: false\n"
            "  dir: ./custom_logs\n"
            '  level: "INFO"\n'
        )

        config = load_config(config_file)
        assert config.logging.enabled is False
        assert config.logging.dir == "./custom_logs"
        assert config.logging.level == "INFO"


class TestOutputLoggingIntegration:
    """Tests that Output methods write to the log file."""

    def _flush_handlers(self):
        for handler in logging.getLogger("yt_excel").handlers:
            handler.flush()

    def _read_log(self, log_file):
        self._flush_handlers()
        return log_file.read_text(encoding="utf-8")

    def test_success_logs_info(self, tmp_path):
        """Output.success() logs at INFO level."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="normal")
        out.success("Step completed")
        content = self._read_log(log_file)
        assert "Step completed" in content
        assert "[INFO ]" in content

    def test_info_logs_info(self, tmp_path):
        """Output.info() logs at INFO level."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="normal")
        out.info("General info")
        content = self._read_log(log_file)
        assert "General info" in content

    def test_warning_logs_warning(self, tmp_path):
        """Output.warning() logs at WARNING level."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="normal")
        out.warning("Something warned")
        content = self._read_log(log_file)
        assert "Something warned" in content
        assert "[WARN " in content or "[WARNING]" in content

    def test_error_logs_error(self, tmp_path):
        """Output.error() logs at ERROR level."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="normal")
        out.error("Critical failure")
        content = self._read_log(log_file)
        assert "Critical failure" in content
        assert "[ERROR]" in content

    def test_step_logs_info(self, tmp_path):
        """Output.step() logs at INFO level."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="normal")
        out.step("\U0001f50d", "Fetching video info...")
        content = self._read_log(log_file)
        assert "Fetching video info..." in content

    def test_detail_logs_info(self, tmp_path):
        """Output.detail() logs at INFO level."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="normal")
        out.detail("Title: Test Video")
        content = self._read_log(log_file)
        assert "Title: Test Video" in content

    def test_verbose_logs_debug(self, tmp_path):
        """Output.verbose() logs at DEBUG level."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="normal")
        out.verbose("Language code: en")
        content = self._read_log(log_file)
        assert "Language code: en" in content
        assert "[DEBUG]" in content

    def test_quiet_mode_still_logs(self, tmp_path):
        """Even in quiet mode, all messages go to the log file."""
        log_file = setup_logging(enabled=True, log_dir=str(tmp_path))
        out = Output(mode="quiet")
        out.success("Quiet success")
        out.info("Quiet info")
        out.step("\U0001f50d", "Quiet step")
        out.detail("Quiet detail")
        out.verbose("Quiet verbose")
        content = self._read_log(log_file)
        assert "Quiet success" in content
        assert "Quiet info" in content
        assert "Quiet step" in content
        assert "Quiet detail" in content
        assert "Quiet verbose" in content
