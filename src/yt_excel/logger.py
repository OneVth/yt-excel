"""File logging system for yt-excel pipeline.

Provides a file-based logging system independent of the rich CLI output.
All pipeline steps are logged to a timestamped file with DEBUG level by default,
regardless of the CLI output mode (normal/verbose/quiet).
"""

import logging
from datetime import datetime
from pathlib import Path


_FILE_HANDLER: logging.FileHandler | None = None


def setup_logging(
    enabled: bool = True,
    log_dir: str = "./logs",
    level: str = "DEBUG",
) -> Path | None:
    """Configure file-based logging for the yt-excel pipeline.

    Creates the log directory if it doesn't exist and sets up a FileHandler
    on the root 'yt_excel' logger with the specified level.

    Args:
        enabled: Whether file logging is active. If False, no handler is added.
        log_dir: Directory path for log files.
        level: Logging level for the file handler (e.g. "DEBUG", "INFO").

    Returns:
        Path to the created log file, or None if logging is disabled.
    """
    global _FILE_HANDLER

    # Clean up any previous handler from a prior setup call
    _teardown_logging()

    if not enabled:
        return None

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = log_path / f"yt-excel_{timestamp}.log"

    numeric_level = getattr(logging, level.upper(), logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)-5s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setLevel(numeric_level)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("yt_excel")
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(handler)

    _FILE_HANDLER = handler

    return log_file


def _teardown_logging() -> None:
    """Remove the file handler set up by setup_logging."""
    global _FILE_HANDLER

    if _FILE_HANDLER is not None:
        root_logger = logging.getLogger("yt_excel")
        root_logger.removeHandler(_FILE_HANDLER)
        _FILE_HANDLER.close()
        _FILE_HANDLER = None


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the yt_excel namespace.

    Args:
        name: Logger name (typically __name__ of the calling module).

    Returns:
        Logger instance under 'yt_excel' hierarchy.
    """
    if name.startswith("yt_excel"):
        return logging.getLogger(name)
    return logging.getLogger(f"yt_excel.{name}")
