"""CLI entrypoint and pipeline orchestration."""

import argparse
import sys

from yt_excel import __version__
from yt_excel.config import load_config
from yt_excel.environment import validate_api_key
from yt_excel.youtube import extract_video_id


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

    # API key validation (skip in dry-run mode)
    if not args.dry_run:
        validate_api_key()

    # URL parsing
    try:
        video_id = extract_video_id(args.url)
    except ValueError as e:
        print(f"\u274c ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 1: output parsed info for verification
    if config.ui.default_mode != "quiet":
        print(f"\U0001f50d Video ID: {video_id}")
        print(f"   Master: {config.file.master_path}")
        print(f"   Model: {config.translation.model}")
        print(f"   Mode: {config.ui.default_mode}")
        if args.dry_run:
            print("   Dry run: enabled (API key validation skipped)")
