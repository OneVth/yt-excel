"""CLI entrypoint and pipeline orchestration."""

import argparse
import sys

from rich.console import Console

from yt_excel import __version__
from yt_excel.config import load_config


# --- Output Utility ---

_console = Console(stderr=True)


class Output:
    """Rich-based CLI output utility with log level filtering.

    Manages output verbosity based on mode (normal/verbose/quiet)
    and provides consistent emoji-prefixed messages per design doc 13.3.
    """

    def __init__(self, mode: str = "normal") -> None:
        self.mode = mode

    def success(self, message: str, indent: int = 0) -> None:
        """Print a success message (green checkmark)."""
        if self.mode == "quiet":
            return
        prefix = "   " * indent
        _console.print(f"{prefix}[green]\u2705 {message}[/green]")

    def info(self, message: str, indent: int = 0) -> None:
        """Print an info message (blue info icon)."""
        if self.mode == "quiet":
            return
        prefix = "   " * indent
        _console.print(f"{prefix}[blue]\u2139 {message}[/blue]")

    def warning(self, message: str, indent: int = 0) -> None:
        """Print a warning message (yellow warning icon)."""
        prefix = "   " * indent
        _console.print(f"{prefix}[yellow]\u26a0 {message}[/yellow]")

    def error(self, message: str, indent: int = 0) -> None:
        """Print an error message (red cross)."""
        prefix = "   " * indent
        _console.print(f"{prefix}[red]\u274c {message}[/red]")

    def step(self, emoji: str, message: str) -> None:
        """Print a pipeline step header (e.g. emoji + description)."""
        if self.mode == "quiet":
            return
        _console.print(f"\n{emoji} {message}")

    def detail(self, message: str, indent: int = 1) -> None:
        """Print an indented detail line (shown in normal and verbose modes)."""
        if self.mode == "quiet":
            return
        prefix = "   " * indent
        _console.print(f"{prefix}{message}")

    def verbose(self, message: str, indent: int = 1) -> None:
        """Print a verbose-only detail line."""
        if self.mode != "verbose":
            return
        prefix = "   " * indent
        _console.print(f"{prefix}[dim]{message}[/dim]")

    def blank(self) -> None:
        """Print a blank line."""
        if self.mode == "quiet":
            return
        _console.print()


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the yt-excel CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="yt-excel",
        description="YouTube English subtitles -> Korean translation -> Master Excel",
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="YouTube video URL",
    )
    parser.add_argument(
        "--master", "-m",
        metavar="<path>",
        help="Master.xlsx path (default: from config.yaml)",
    )
    parser.add_argument(
        "--model",
        metavar="<name>",
        help="Translation model (default: from config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose log output",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output (errors and final result only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze captions without translating or saving",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"yt-excel {__version__}",
    )
    return parser


def main() -> None:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    # URL is required (except --help/--version handled by argparse)
    if not args.url:
        parser.print_help()
        sys.exit(1)

    # Load config and apply CLI overrides
    config = load_config()

    if args.master:
        config.file.master_path = args.master
    if args.model:
        config.translation.model = args.model
    if args.verbose:
        config.ui.default_mode = "verbose"
    if args.quiet:
        config.ui.default_mode = "quiet"

    out = Output(config.ui.default_mode)

    # API key validation (skip in dry-run mode)
    if not args.dry_run:
        from yt_excel.environment import validate_api_key

        try:
            validate_api_key()
        except SystemExit as e:
            out.error(str(e))
            sys.exit(1)
        out.step("\U0001f511", "API key verified")

    # URL parsing
    from yt_excel.youtube import extract_video_id

    try:
        video_id = extract_video_id(args.url)
    except ValueError as e:
        out.error(f"ERROR: {e}")
        sys.exit(1)

    out.verbose(f"Video ID: {video_id}")
