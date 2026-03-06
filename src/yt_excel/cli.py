"""CLI entrypoint and pipeline orchestration."""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone

import openpyxl
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from yt_excel import __version__
from yt_excel.config import AppConfig, load_config
from yt_excel.logger import setup_logging
from yt_excel.environment import validate_api_key
from yt_excel.excel import (
    DuplicateVideoError,
    FileLockError,
    MetadataRow,
    apply_all_styles,
    check_duplicate,
    check_file_lock,
    detect_font,
    generate_unique_sheet_name,
    initialize_workbook,
    write_data_sheet,
    write_metadata_row,
    write_study_log_row,
)
from yt_excel.translator import (
    TranslationResult,
    build_batches,
    create_async_client,
    create_client,
    translate_batch_with_retry,
    translate_segments,
    translate_segments_async,
)
from yt_excel.vtt import (
    Segment,
    filter_short_segments,
    parse_vtt,
    remove_non_verbal_segments,
    strip_markup_segments,
)
from yt_excel.youtube import (
    AutoCaptionOnlyError,
    CaptionNotFoundError,
    VideoMeta,
    download_captions,
    extract_video_id,
    fetch_metadata,
    list_captions,
)


# --- Output Utility ---

_console = Console(stderr=True)
_logger = logging.getLogger("yt_excel.cli")


class Output:
    """Rich-based CLI output utility with log level filtering.

    Manages output verbosity based on mode (normal/verbose/quiet)
    and provides consistent emoji-prefixed messages per design doc 13.3.
    All messages are simultaneously logged to file via the logging module.
    """

    def __init__(self, mode: str = "normal") -> None:
        self.mode = mode

    def success(self, message: str, indent: int = 0) -> None:
        """Print a success message (green checkmark)."""
        _logger.info(message)
        if self.mode == "quiet":
            return
        prefix = "   " * indent
        _console.print(f"{prefix}[green]\u2705 {message}[/green]")

    def info(self, message: str, indent: int = 0) -> None:
        """Print an info message (blue info icon)."""
        _logger.info(message)
        if self.mode == "quiet":
            return
        prefix = "   " * indent
        _console.print(f"{prefix}[blue]\u2139 {message}[/blue]")

    def warning(self, message: str, indent: int = 0) -> None:
        """Print a warning message (yellow warning icon)."""
        _logger.warning(message)
        prefix = "   " * indent
        _console.print(f"{prefix}[yellow]\u26a0 {message}[/yellow]")

    def error(self, message: str, indent: int = 0) -> None:
        """Print an error message (red cross)."""
        _logger.error(message)
        prefix = "   " * indent
        _console.print(f"{prefix}[red]\u274c {message}[/red]")

    def step(self, emoji: str, message: str) -> None:
        """Print a pipeline step header (e.g. emoji + description)."""
        _logger.info(message)
        if self.mode == "quiet":
            return
        _console.print(f"\n{emoji} {message}")

    def detail(self, message: str, indent: int = 1) -> None:
        """Print an indented detail line (shown in normal and verbose modes)."""
        _logger.info(message)
        if self.mode == "quiet":
            return
        prefix = "   " * indent
        _console.print(f"{prefix}{message}")

    def verbose(self, message: str, indent: int = 1) -> None:
        """Print a verbose-only detail line."""
        _logger.debug(message)
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

    # Set up file logging
    log_file = setup_logging(
        enabled=config.logging.enabled,
        log_dir=config.logging.dir,
        level=config.logging.level,
    )

    out = Output(config.ui.default_mode)
    pipeline_start = time.monotonic()

    _logger.info("Pipeline started: %s", args.url)
    if log_file:
        _logger.info("Log file: %s", log_file)

    _run_pipeline(args, config, out, pipeline_start)


def _run_pipeline(
    args: argparse.Namespace,
    config: AppConfig,
    out: Output,
    pipeline_start: float,
) -> None:
    """Execute the full pipeline from URL parsing to Excel writing.

    Args:
        args: Parsed CLI arguments.
        config: Application configuration.
        out: Output utility instance.
        pipeline_start: Monotonic time at pipeline start.
    """
    # --- Step 1: API key validation (skip in dry-run) ---
    if not args.dry_run:
        try:
            api_key = validate_api_key()
        except SystemExit as e:
            out.error(str(e))
            sys.exit(1)
        out.step("\U0001f511", "API key verified")
    else:
        api_key = ""

    # --- Step 2: URL parsing ---
    try:
        video_id = extract_video_id(args.url)
    except ValueError as e:
        out.error(f"ERROR: {e}")
        sys.exit(1)

    # --- Step 3: Fetch video metadata ---
    out.step("\U0001f50d", "Fetching video info...")
    try:
        meta = fetch_metadata(video_id)
    except Exception as e:
        out.error(f"Failed to fetch video info: {e}")
        sys.exit(1)

    out.detail(f"Title: {meta.title}")
    out.detail(f"Channel: {meta.channel}")
    out.detail(f"Duration: {meta.duration}")

    # --- Step 4: Check captions ---
    out.step("\U0001f4dd", "Checking captions...")
    try:
        caption_info = list_captions(video_id)
    except CaptionNotFoundError as e:
        out.error(str(e))
        sys.exit(1)
    except AutoCaptionOnlyError as e:
        out.warning(str(e))
        sys.exit(1)
    except Exception as e:
        out.error(f"Failed to check captions: {e}")
        sys.exit(1)

    out.success("Manual English captions found", indent=1)
    out.verbose(f"Language code: {caption_info.lang_code}", indent=1)

    # --- Step 5: Master.xlsx initialization + lock check + duplicate check ---
    out.step("\U0001f4cb", "Checking Master.xlsx...")
    master_path = config.file.master_path

    try:
        init_result = initialize_workbook(master_path)
    except Exception as e:
        out.error(f"Failed to initialize Master.xlsx: {e}")
        sys.exit(1)

    if init_result.created:
        out.warning(
            "File not found \u2014 created new Master.xlsx with _metadata and _study_log sheets",
            indent=1,
        )
    else:
        if init_result.metadata_recovered:
            out.warning("_metadata sheet missing \u2014 recreated with headers", indent=1)
            out.warning(
                "WARNING: Previously processed video records are lost. "
                "Existing data sheets are preserved but will not appear in metadata.",
                indent=1,
            )
        if init_result.study_log_recovered:
            out.warning("_study_log sheet missing \u2014 recreated with headers", indent=1)

    try:
        check_file_lock(master_path)
    except FileLockError as e:
        out.error(str(e))
        sys.exit(1)

    out.step("\U0001f50e", "Checking duplicates...")
    try:
        check_duplicate(master_path, video_id)
    except DuplicateVideoError as e:
        out.info(str(e))
        sys.exit(0)

    out.success("New video \u2014 not processed before", indent=1)

    if init_result.created:
        out.success("New file created", indent=1)
    else:
        out.success("File found \u2014 structure verified \u2014 writable", indent=1)

    # --- Step 6: Download captions ---
    out.step("\u2b07\ufe0f ", "Downloading captions...")
    try:
        vtt_content = download_captions(video_id, caption_info.lang_code)
    except Exception as e:
        out.error(f"Failed to download captions: {e}")
        sys.exit(1)

    raw_segments = parse_vtt(vtt_content)
    out.success(f"Downloaded ({len(raw_segments)} cue segments)", indent=1)

    # --- Step 7: Process segments ---
    out.step("\U0001f9f9", "Processing segments...")

    markup_stripped = strip_markup_segments(raw_segments)
    markup_removed_count = len(raw_segments) - len(markup_stripped)
    out.detail(f"Markup stripped: {markup_removed_count} tags removed")

    nonverbal_cleaned = remove_non_verbal_segments(markup_stripped)
    nonverbal_removed_count = len(markup_stripped) - len(nonverbal_cleaned)
    out.detail(f"Non-verbal removed: {nonverbal_removed_count} segments")

    final_segments = filter_short_segments(
        nonverbal_cleaned,
        min_duration_sec=config.filter.min_duration_sec,
        min_text_length=config.filter.min_text_length,
    )
    short_removed_count = len(nonverbal_cleaned) - len(final_segments)
    out.detail(f"Short segments removed: {short_removed_count} segments")

    if not final_segments:
        out.error("No valid spoken segments remain after filtering.")
        sys.exit(1)

    out.success(f"{len(final_segments)} valid segments remaining", indent=1)

    filtered_count = len(raw_segments) - len(final_segments)

    # --- Step 8: Dry-run exits here (translation + Excel skipped) ---
    if args.dry_run:
        cost = _estimate_cost(len(final_segments), config.translation.model)
        num_batches = (
            (len(final_segments) + config.translation.batch_size - 1)
            // config.translation.batch_size
        )
        out.step("\U0001f4ca", "Dry Run Analysis")
        out.detail(f"Video: {meta.title} ({meta.duration})")
        out.detail(
            f"Segments: {len(final_segments)} / {len(raw_segments)} original "
            f"({filtered_count} filtered)"
        )
        out.detail(f"Batches: {num_batches} (batch_size={config.translation.batch_size})")
        out.detail(f"Model: {config.translation.model}")
        out.detail(f"Estimated cost: ~${cost:.4f}")
        out.blank()
        out.info("Dry run complete \u2014 no translation or Excel write performed.")
        return

    # --- Step 9: Translation ---
    async_mode = config.translation.async_enabled
    mode_label = "async" if async_mode else "sync"
    out.step("\U0001f310", f"Translating ({config.translation.model}, {mode_label})...")

    try:
        if async_mode:
            async_client = create_async_client(api_key)
            translation_result = _translate_async_with_progress(
                async_client, final_segments, config, out,
            )
        else:
            client = create_client(api_key)
            translation_result = _translate_with_progress(
                client, final_segments, config, out,
            )
    except Exception as e:
        out.error(f"Translation failed: {e}")
        sys.exit(1)

    out.blank()
    out.success(
        f"Translation complete ({translation_result.success_count} success, "
        f"{translation_result.failed_count} failed)",
        indent=1,
    )

    # --- Step 10: Write to Excel ---
    out.step("\U0001f4be", "Writing to Master.xlsx...")

    font_name = detect_font(config.style.font)
    wb = openpyxl.load_workbook(str(master_path))

    sheet_name = generate_unique_sheet_name(meta.title, wb.sheetnames)
    out.detail(f"Sheet: {sheet_name}")
    if config.style.font == "auto":
        out.detail(f"Font: {font_name} (auto-detected)")
    else:
        out.detail(f"Font: {font_name}")

    # Write data sheet
    write_data_sheet(wb, sheet_name, translation_result.segments)
    out.success("Data sheet saved", indent=1)

    # Write metadata
    processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata_row = MetadataRow(
        video_id=video_id,
        video_title=meta.title,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        channel_name=meta.channel,
        video_duration=meta.duration,
        sheet_name=sheet_name,
        processed_at=processed_at,
        total_segments=len(final_segments),
        filtered_segments=filtered_count,
        translation_success=translation_result.success_count,
        translation_failed=translation_result.failed_count,
        model_used=config.translation.model,
        tool_version=__version__,
    )
    write_metadata_row(wb, metadata_row)
    out.success("Metadata updated", indent=1)

    # Write study log
    try:
        write_study_log_row(
            wb,
            video_title=meta.title,
            video_duration=meta.duration,
            total_segments=len(final_segments),
        )
        out.success("Study log updated", indent=1)
    except Exception as e:
        out.warning(f"Study log update failed: {e} (non-critical)")

    # Apply styles
    apply_all_styles(wb, font_name, data_sheet_name=sheet_name)

    # Save workbook with retry (design doc 12.1: 2 retries, fixed 1s)
    _save_workbook_with_retry(wb, master_path, out)

    # --- Summary ---
    elapsed = time.monotonic() - pipeline_start
    cost = _estimate_cost(len(final_segments), config.translation.model)
    out.step("\U0001f4ca", "Summary")
    out.detail(f"Segments: {len(final_segments)} / {len(raw_segments)} original")
    out.detail(
        f"Translation: {translation_result.success_count} \u2705  "
        f"{translation_result.failed_count} \u274c"
    )
    out.detail(f"Cost: ~${cost:.4f}")
    out.detail(f"Time: {elapsed:.1f}s")
    _logger.info("Pipeline completed in %.1fs", elapsed)


def _translate_with_progress(
    client: "OpenAI",  # type: ignore[name-defined]
    segments: list[Segment],
    config: AppConfig,
    out: Output,
) -> TranslationResult:
    """Run translation with a rich progress bar (segment-level tracking).

    In quiet mode, falls back to the standard translate_segments (no progress bar).

    Args:
        client: OpenAI client instance.
        segments: Segments to translate.
        config: Application configuration.
        out: Output utility.

    Returns:
        TranslationResult with translated segments.
    """
    if out.mode == "quiet":
        return translate_segments(client, segments, config.translation)

    batches = build_batches(
        segments,
        batch_size=config.translation.batch_size,
        context_before=config.translation.context_before,
        context_after=config.translation.context_after,
    )

    translated_segments: list[Segment] = []
    success_count = 0
    failed_count = 0

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        console=_console,
    ) as progress:
        task = progress.add_task("Translating", total=len(segments))

        for batch in batches:
            translations = translate_batch_with_retry(
                client=client,
                batch=batch,
                model=config.translation.model,
                max_retries=config.translation.max_retries,
                request_interval_ms=config.translation.request_interval_ms,
            )

            for seg, korean in zip(batch.translate_segments, translations):
                translated_segments.append(Segment(
                    index=seg.index,
                    start=seg.start,
                    end=seg.end,
                    english=seg.english,
                    korean=korean,
                ))
                if korean:
                    success_count += 1
                else:
                    failed_count += 1

            progress.update(task, advance=len(batch.translate_segments))

    return TranslationResult(
        segments=translated_segments,
        success_count=success_count,
        failed_count=failed_count,
    )


def _translate_async_with_progress(
    client: "AsyncOpenAI",  # type: ignore[name-defined]
    segments: list[Segment],
    config: AppConfig,
    out: Output,
) -> TranslationResult:
    """Run async translation with a rich progress bar.

    In quiet mode, falls back to async without progress bar.

    Args:
        client: AsyncOpenAI client instance.
        segments: Segments to translate.
        config: Application configuration.
        out: Output utility.

    Returns:
        TranslationResult with translated segments.
    """
    if out.mode == "quiet":
        return asyncio.run(
            translate_segments_async(client, segments, config.translation)
        )

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        console=_console,
    )

    with progress:
        task = progress.add_task("Translating", total=len(segments))

        def on_batch_complete(count: int) -> None:
            progress.update(task, advance=count)

        result = asyncio.run(
            translate_segments_async(
                client, segments, config.translation,
                on_batch_complete=on_batch_complete,
            )
        )

    return result


def _estimate_cost(segment_count: int, model: str) -> float:
    """Estimate translation cost based on segment count and model.

    Uses approximate token counts from design doc 7.3.

    Args:
        segment_count: Number of segments translated.
        model: Model name.

    Returns:
        Estimated cost in USD.
    """
    avg_input_tokens_per_seg = 33  # ~20 English tokens + overhead
    avg_output_tokens_per_seg = 20

    total_input = segment_count * avg_input_tokens_per_seg
    total_output = segment_count * avg_output_tokens_per_seg

    pricing = {
        "gpt-5-nano": {"input": 0.05, "output": 0.40},
        "gpt-5-mini": {"input": 0.25, "output": 2.00},
    }
    rates = pricing.get(model, pricing["gpt-5-nano"])

    return (total_input * rates["input"] + total_output * rates["output"]) / 1_000_000


def _save_workbook_with_retry(
    wb: openpyxl.Workbook,
    master_path: str,
    out: Output,
    max_retries: int = 2,
) -> None:
    """Save workbook with retry on permission errors.

    Args:
        wb: The workbook to save.
        master_path: File path.
        out: Output utility.
        max_retries: Max retry attempts.
    """
    for attempt in range(1, max_retries + 1):
        try:
            wb.save(str(master_path))
            return
        except PermissionError:
            if attempt == max_retries:
                out.error(
                    "Failed to save Master.xlsx after retries. "
                    "Please close the file in Excel and retry."
                )
                sys.exit(1)
            out.warning(f"Save failed (attempt {attempt}/{max_retries}), retrying in 1s...")
            time.sleep(1.0)
