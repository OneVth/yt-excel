"""Tests for Excel reader/writer (Master.xlsx operations)."""

import openpyxl
import pytest

from yt_excel.excel import (
    DATA_HEADERS,
    METADATA_HEADERS,
    METADATA_SHEET,
    STUDY_LOG_HEADERS,
    STUDY_LOG_SHEET,
    InitResult,
    initialize_workbook,
)


class TestInitializeWorkbook:
    """Tests for initialize_workbook — creation and integrity checks."""

    def test_creates_new_file_when_not_exists(self, tmp_path):
        """New file is created with _metadata and _study_log sheets."""
        path = tmp_path / "Master.xlsx"
        result = initialize_workbook(path)

        assert result.created is True
        assert result.metadata_recovered is False
        assert result.study_log_recovered is False
        assert path.exists()

        wb = openpyxl.load_workbook(str(path))
        assert METADATA_SHEET in wb.sheetnames
        assert STUDY_LOG_SHEET in wb.sheetnames
        # Should not have the default "Sheet"
        assert "Sheet" not in wb.sheetnames

    def test_new_file_has_metadata_headers(self, tmp_path):
        """Newly created _metadata sheet has all 13 column headers."""
        path = tmp_path / "Master.xlsx"
        initialize_workbook(path)

        wb = openpyxl.load_workbook(str(path))
        ws = wb[METADATA_SHEET]
        headers = [ws.cell(row=1, column=i).value for i in range(1, 14)]
        assert headers == METADATA_HEADERS

    def test_new_file_has_study_log_headers(self, tmp_path):
        """Newly created _study_log sheet has all 8 column headers."""
        path = tmp_path / "Master.xlsx"
        initialize_workbook(path)

        wb = openpyxl.load_workbook(str(path))
        ws = wb[STUDY_LOG_SHEET]
        headers = [ws.cell(row=1, column=i).value for i in range(1, 9)]
        assert headers == STUDY_LOG_HEADERS

    def test_existing_file_both_sheets_intact(self, tmp_path):
        """Existing file with both sheets passes integrity check unchanged."""
        path = tmp_path / "Master.xlsx"
        # Pre-create a valid file
        initialize_workbook(path)

        # Run again — should detect both sheets and do nothing
        result = initialize_workbook(path)
        assert result.created is False
        assert result.metadata_recovered is False
        assert result.study_log_recovered is False

    def test_recovers_missing_study_log(self, tmp_path):
        """Missing _study_log is recreated while preserving _metadata."""
        path = tmp_path / "Master.xlsx"
        # Create file, then remove _study_log
        wb = openpyxl.Workbook()
        default = wb.active
        if default is not None:
            wb.remove(default)
        ws_meta = wb.create_sheet(METADATA_SHEET)
        ws_meta.cell(row=1, column=1, value="video_id")
        ws_meta.cell(row=2, column=1, value="test123abcd")
        wb.save(str(path))

        result = initialize_workbook(path)
        assert result.created is False
        assert result.metadata_recovered is False
        assert result.study_log_recovered is True

        wb = openpyxl.load_workbook(str(path))
        assert STUDY_LOG_SHEET in wb.sheetnames
        # Existing _metadata data should be preserved
        ws = wb[METADATA_SHEET]
        assert ws.cell(row=2, column=1).value == "test123abcd"

    def test_recovers_missing_metadata(self, tmp_path):
        """Missing _metadata is recreated while preserving other sheets."""
        path = tmp_path / "Master.xlsx"
        wb = openpyxl.Workbook()
        default = wb.active
        if default is not None:
            wb.remove(default)
        ws_log = wb.create_sheet(STUDY_LOG_SHEET)
        ws_log.cell(row=1, column=1, value="No")
        ws_log.cell(row=2, column=1, value=1)
        # Also add a data sheet
        ws_data = wb.create_sheet("How DNA Works")
        ws_data.cell(row=1, column=1, value="Index")
        ws_data.cell(row=2, column=1, value=1)
        wb.save(str(path))

        result = initialize_workbook(path)
        assert result.metadata_recovered is True
        assert result.study_log_recovered is False

        wb = openpyxl.load_workbook(str(path))
        assert METADATA_SHEET in wb.sheetnames
        # Existing _study_log and data sheet preserved
        assert wb[STUDY_LOG_SHEET].cell(row=2, column=1).value == 1
        assert wb["How DNA Works"].cell(row=2, column=1).value == 1

    def test_recovers_both_missing_sheets(self, tmp_path):
        """Both _metadata and _study_log recreated when both missing."""
        path = tmp_path / "Master.xlsx"
        wb = openpyxl.Workbook()
        # Just has a data sheet
        ws = wb.active
        ws.title = "Some Data Sheet"
        ws.cell(row=1, column=1, value="Index")
        wb.save(str(path))

        result = initialize_workbook(path)
        assert result.metadata_recovered is True
        assert result.study_log_recovered is True

        wb = openpyxl.load_workbook(str(path))
        assert METADATA_SHEET in wb.sheetnames
        assert STUDY_LOG_SHEET in wb.sheetnames
        # Original data sheet still there
        assert "Some Data Sheet" in wb.sheetnames
