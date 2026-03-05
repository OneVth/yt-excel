"""Excel reader/writer for Master.xlsx — initialization, integrity, and data operations."""

from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet


# --- Sheet Names ---
METADATA_SHEET = "_metadata"
STUDY_LOG_SHEET = "_study_log"

# --- _metadata Column Headers (13 fields) ---
METADATA_HEADERS = [
    "video_id",
    "video_title",
    "video_url",
    "channel_name",
    "video_duration",
    "sheet_name",
    "processed_at",
    "total_segments",
    "filtered_segments",
    "translation_success",
    "translation_failed",
    "model_used",
    "tool_version",
]

# --- _study_log Column Headers (8 fields) ---
STUDY_LOG_HEADERS = [
    "No",
    "Study Date",
    "Video Title",
    "Duration",
    "Segments",
    "Status",
    "Review Count",
    "Notes",
]

# --- Data Sheet Column Headers ---
DATA_HEADERS = ["Index", "Start", "End", "English", "Korean"]


@dataclass
class InitResult:
    """Result of Master.xlsx initialization.

    Attributes:
        created: True if the file was newly created.
        metadata_recovered: True if _metadata was missing and recreated.
        study_log_recovered: True if _study_log was missing and recreated.
    """

    created: bool = False
    metadata_recovered: bool = False
    study_log_recovered: bool = False


def _write_header_row(ws: Worksheet, headers: list[str]) -> None:
    """Write header row to a worksheet."""
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col_idx, value=header)


def initialize_workbook(master_path: str | Path) -> InitResult:
    """Initialize Master.xlsx, creating it if missing or recovering missing sheets.

    If the file does not exist, creates a new workbook with _metadata and
    _study_log sheets (headers only). If the file exists, verifies that both
    required sheets are present and recreates any missing ones.

    Existing data sheets and their contents are never modified.

    Args:
        master_path: Path to the Master.xlsx file.

    Returns:
        InitResult describing what actions were taken.
    """
    path = Path(master_path)
    result = InitResult()

    if not path.exists():
        # Create new workbook
        wb = Workbook()

        # Remove default "Sheet" created by openpyxl
        default_sheet = wb.active
        if default_sheet is not None:
            wb.remove(default_sheet)

        # Create _metadata sheet with headers
        ws_meta = wb.create_sheet(METADATA_SHEET)
        _write_header_row(ws_meta, METADATA_HEADERS)

        # Create _study_log sheet with headers
        ws_log = wb.create_sheet(STUDY_LOG_SHEET)
        _write_header_row(ws_log, STUDY_LOG_HEADERS)

        wb.save(str(path))
        result.created = True
        return result

    # File exists — verify integrity
    wb = openpyxl.load_workbook(str(path))
    modified = False

    if METADATA_SHEET not in wb.sheetnames:
        ws_meta = wb.create_sheet(METADATA_SHEET)
        _write_header_row(ws_meta, METADATA_HEADERS)
        result.metadata_recovered = True
        modified = True

    if STUDY_LOG_SHEET not in wb.sheetnames:
        ws_log = wb.create_sheet(STUDY_LOG_SHEET)
        _write_header_row(ws_log, STUDY_LOG_HEADERS)
        result.study_log_recovered = True
        modified = True

    if modified:
        wb.save(str(path))

    return result
