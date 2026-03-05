"""Tests for VTT parsing, markup stripping, and segment processing."""

from pathlib import Path

from yt_excel.vtt import Segment, parse_vtt

FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- parse_vtt tests ---


class TestParseVttBasic:
    """Test basic VTT parsing with timestamp extraction."""

    def test_basic_vtt_parses_all_segments(self) -> None:
        content = _read_fixture("basic.vtt")
        segments = parse_vtt(content)
        assert len(segments) == 5

    def test_basic_vtt_timestamps_preserved(self) -> None:
        content = _read_fixture("basic.vtt")
        segments = parse_vtt(content)
        assert segments[0].start == "00:00:01.000"
        assert segments[0].end == "00:00:04.500"
        assert segments[2].start == "00:00:09.000"
        assert segments[2].end == "00:00:12.800"

    def test_basic_vtt_text_extracted(self) -> None:
        content = _read_fixture("basic.vtt")
        segments = parse_vtt(content)
        assert segments[0].english == "Hello and welcome to this video."
        assert segments[1].english == "Today we're going to learn about DNA."
        assert segments[4].english == "Thank you for watching."

    def test_basic_vtt_indices_sequential(self) -> None:
        content = _read_fixture("basic.vtt")
        segments = parse_vtt(content)
        for i, seg in enumerate(segments, 1):
            assert seg.index == i

    def test_basic_vtt_korean_default_empty(self) -> None:
        content = _read_fixture("basic.vtt")
        segments = parse_vtt(content)
        for seg in segments:
            assert seg.korean == ""


class TestParseVttMultiline:
    """Test multi-line cue text joining."""

    def test_multiline_joined_with_space(self) -> None:
        content = _read_fixture("multiline.vtt")
        segments = parse_vtt(content)
        assert segments[0].english == "This is the first line and this is the second line."

    def test_three_lines_joined(self) -> None:
        content = _read_fixture("multiline.vtt")
        segments = parse_vtt(content)
        assert segments[1].english == "One line here then another and a third line."

    def test_single_line_unchanged(self) -> None:
        content = _read_fixture("multiline.vtt")
        segments = parse_vtt(content)
        assert segments[2].english == "Single line only."


class TestParseVttPositionCues:
    """Test that cue settings on timestamp line are ignored."""

    def test_position_cues_ignored_text_extracted(self) -> None:
        content = _read_fixture("position_cues.vtt")
        segments = parse_vtt(content)
        assert len(segments) == 3
        assert segments[0].english == "Hello and welcome to this video."
        assert segments[0].start == "00:00:01.000"
        assert segments[0].end == "00:00:04.500"


class TestParseVttEmpty:
    """Test edge cases with empty or minimal VTT."""

    def test_empty_vtt_returns_empty(self) -> None:
        segments = parse_vtt("WEBVTT\n\n")
        assert segments == []

    def test_header_only_returns_empty(self) -> None:
        segments = parse_vtt("WEBVTT")
        assert segments == []

    def test_no_text_cues_returns_empty(self) -> None:
        content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.500\n\n"
        segments = parse_vtt(content)
        assert segments == []


class TestParseVttRawTags:
    """Test that raw tags are preserved by parse_vtt (strip happens later)."""

    def test_c_tags_preserved_in_parse(self) -> None:
        content = _read_fixture("word_timing.vtt")
        segments = parse_vtt(content)
        assert "<c.colorE5E5E5>Hello</c>" in segments[0].english

    def test_v_tags_preserved_in_parse(self) -> None:
        content = _read_fixture("speaker_tags.vtt")
        segments = parse_vtt(content)
        assert "<v Speaker 1>" in segments[0].english
