"""Tests for VTT parsing, markup stripping, and segment processing."""

from pathlib import Path

import pytest

from yt_excel.vtt import (
    Segment,
    filter_short_segments,
    parse_vtt,
    process_segments,
    remove_non_verbal,
    remove_non_verbal_segments,
    strip_markup,
    strip_markup_segments,
)

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


# --- strip_markup tests ---


class TestStripMarkupCTags:
    """Test <c> word-level timing tag removal."""

    def test_c_tag_with_class_removed(self) -> None:
        assert strip_markup("<c.colorE5E5E5>Hello</c>") == "Hello"

    def test_c_tag_plain_removed(self) -> None:
        assert strip_markup("<c>word</c>") == "word"

    def test_multiple_c_tags(self) -> None:
        result = strip_markup("<c>Hello</c> and <c>world</c>")
        assert result == "Hello and world"

    def test_word_timing_fixture(self) -> None:
        content = _read_fixture("word_timing.vtt")
        segments = parse_vtt(content)
        cleaned = strip_markup(segments[0].english)
        assert cleaned == "Hello and welcome to this video."
        assert "<c" not in cleaned


class TestStripMarkupVTags:
    """Test <v> speaker tag removal."""

    def test_v_tag_removes_speaker_name(self) -> None:
        assert strip_markup("<v Speaker 1>Hello</v>") == "Hello"

    def test_v_tag_with_title(self) -> None:
        assert strip_markup("<v Dr. Smith>Good morning</v>") == "Good morning"

    def test_speaker_tags_fixture(self) -> None:
        content = _read_fixture("speaker_tags.vtt")
        segments = parse_vtt(content)
        cleaned = strip_markup(segments[1].english)
        assert cleaned == "Today we're going to learn about DNA."


class TestStripMarkupHTMLTags:
    """Test HTML inline tag removal."""

    def test_bold_tag_removed(self) -> None:
        assert strip_markup("<b>Bold text</b>") == "Bold text"

    def test_italic_tag_removed(self) -> None:
        assert strip_markup("<i>Italic text</i>") == "Italic text"

    def test_underline_tag_removed(self) -> None:
        assert strip_markup("<u>Underlined</u>") == "Underlined"

    def test_font_tag_with_attrs_removed(self) -> None:
        assert strip_markup('<font color="red">Colored</font>') == "Colored"

    def test_nested_tags(self) -> None:
        assert strip_markup("<b><i>Bold italic</i></b>") == "Bold italic"


class TestStripMarkupEntities:
    """Test HTML entity decoding."""

    def test_amp_decoded(self) -> None:
        assert strip_markup("Tom &amp; Jerry") == "Tom & Jerry"

    def test_lt_gt_decoded(self) -> None:
        assert strip_markup("&lt;hello&gt;") == "<hello>"

    def test_quot_decoded(self) -> None:
        assert strip_markup("&quot;hello&quot;") == '"hello"'

    def test_numeric_entity_decoded(self) -> None:
        assert strip_markup("it&#39;s") == "it's"

    def test_entities_fixture(self) -> None:
        content = _read_fixture("html_entities.vtt")
        segments = parse_vtt(content)
        cleaned = strip_markup(segments[0].english)
        assert cleaned == "This is an example of & usage."

    def test_entities_with_tags(self) -> None:
        content = _read_fixture("html_entities.vtt")
        segments = parse_vtt(content)
        cleaned = strip_markup(segments[3].english)
        assert cleaned == "Bold text and italic text here."


class TestStripMarkupWebVTTSpecific:
    """Test WebVTT-specific tag and directive removal."""

    def test_lang_tag_removed(self) -> None:
        assert strip_markup("<lang en>Hello</lang>") == "Hello"

    def test_ruby_rt_tags_removed(self) -> None:
        result = strip_markup("<ruby>DNA<rt>acid</rt></ruby>")
        assert result == "DNAacid"

    def test_cue_settings_in_text_removed(self) -> None:
        result = strip_markup("align:start Hello world")
        assert result == "Hello world"

    def test_position_in_text_removed(self) -> None:
        result = strip_markup("position:10% Some text size:80%")
        assert result == "Some text"


class TestStripMarkupWhitespace:
    """Test whitespace handling after stripping."""

    def test_consecutive_spaces_collapsed(self) -> None:
        assert strip_markup("Hello   world") == "Hello world"

    def test_leading_trailing_stripped(self) -> None:
        assert strip_markup("  Hello world  ") == "Hello world"

    def test_tag_removal_spaces_collapsed(self) -> None:
        result = strip_markup("<c>Hello</c>  <c>world</c>")
        assert result == "Hello world"


class TestStripMarkupSegments:
    """Test strip_markup_segments on segment lists."""

    def test_strips_all_segments(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:02.000", "<b>Hello</b>"),
            Segment(2, "00:00:03.000", "00:00:04.000", "<i>World</i>"),
        ]
        result = strip_markup_segments(segments)
        assert len(result) == 2
        assert result[0].english == "Hello"
        assert result[1].english == "World"

    def test_removes_empty_after_strip(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:02.000", "<b></b>"),
            Segment(2, "00:00:03.000", "00:00:04.000", "Hello"),
        ]
        result = strip_markup_segments(segments)
        assert len(result) == 1
        assert result[0].english == "Hello"
        assert result[0].index == 1  # reindexed

    def test_preserves_timestamps(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:04.500", "<c>Hello</c> &amp; world"),
        ]
        result = strip_markup_segments(segments)
        assert result[0].start == "00:00:01.000"
        assert result[0].end == "00:00:04.500"
        assert result[0].english == "Hello & world"


# --- remove_non_verbal tests ---


class TestRemoveNonVerbalBrackets:
    """Test [bracketed] non-verbal text removal."""

    def test_music_removed(self) -> None:
        assert remove_non_verbal("[Music]") == ""

    def test_applause_removed(self) -> None:
        assert remove_non_verbal("[Applause]") == ""

    def test_laughter_removed(self) -> None:
        assert remove_non_verbal("[Laughter]") == ""

    def test_music_playing_removed(self) -> None:
        assert remove_non_verbal("[Music playing]") == ""

    def test_mixed_with_speech(self) -> None:
        result = remove_non_verbal("Thank you! [Laughter] That was great.")
        assert result == "Thank you! That was great."

    def test_multiple_brackets(self) -> None:
        result = remove_non_verbal("[Music] Hello [Applause] world [Music]")
        assert result == "Hello world"


class TestRemoveNonVerbalParens:
    """Test (parenthesized) non-verbal text removal."""

    def test_laughs_removed(self) -> None:
        assert remove_non_verbal("(Laughs)") == ""

    def test_applause_paren_removed(self) -> None:
        assert remove_non_verbal("(Applause)") == ""

    def test_mixed_paren_with_speech(self) -> None:
        result = remove_non_verbal("Hello (Laughs) there")
        assert result == "Hello there"


class TestRemoveNonVerbalMusicSymbols:
    """Test music symbol removal."""

    def test_music_notes_removed(self) -> None:
        assert remove_non_verbal("\u266a \u266a") == ""

    def test_multiple_notes(self) -> None:
        assert remove_non_verbal("\u266a\u266b\u266c") == ""

    def test_notes_with_text(self) -> None:
        result = remove_non_verbal("\u266a Hello \u266a")
        assert result == "Hello"


class TestRemoveNonVerbalFixture:
    """Test non-verbal removal with fixture file."""

    def test_non_verbal_fixture_full_removal(self) -> None:
        content = _read_fixture("non_verbal.vtt")
        segments = parse_vtt(content)
        stripped = strip_markup_segments(segments)
        result = remove_non_verbal_segments(stripped)
        # [Music], [Applause], (Laughs), music notes, [Music playing] are full non-verbal
        # "Hello and welcome" and "And now let's get started" are speech
        # "Thank you! [Laughter] That was great." has mixed content
        texts = [s.english for s in result]
        assert "Hello and welcome to the show." in texts
        assert "Thank you! That was great." in texts
        assert "And now let's get started." in texts

    def test_non_verbal_fixture_no_music_segments(self) -> None:
        content = _read_fixture("non_verbal.vtt")
        segments = parse_vtt(content)
        stripped = strip_markup_segments(segments)
        result = remove_non_verbal_segments(stripped)
        for seg in result:
            assert "[Music]" not in seg.english
            assert "[Applause]" not in seg.english
            assert "(Laughs)" not in seg.english


class TestRemoveNonVerbalSegments:
    """Test remove_non_verbal_segments list processing."""

    def test_removes_full_non_verbal_segments(self) -> None:
        segments = [
            Segment(1, "00:00:00.500", "00:00:02.000", "[Music]"),
            Segment(2, "00:00:02.500", "00:00:05.000", "Hello world"),
        ]
        result = remove_non_verbal_segments(segments)
        assert len(result) == 1
        assert result[0].english == "Hello world"

    def test_reindexes_after_removal(self) -> None:
        segments = [
            Segment(1, "00:00:00.500", "00:00:02.000", "[Music]"),
            Segment(2, "00:00:02.500", "00:00:05.000", "Hello"),
            Segment(3, "00:00:05.500", "00:00:07.000", "[Applause]"),
            Segment(4, "00:00:07.500", "00:00:10.000", "World"),
        ]
        result = remove_non_verbal_segments(segments)
        assert len(result) == 2
        assert result[0].index == 1
        assert result[1].index == 2

    def test_keeps_mixed_content(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:04.000", "Thank you! [Laughter] Great."),
        ]
        result = remove_non_verbal_segments(segments)
        assert len(result) == 1
        assert result[0].english == "Thank you! Great."


# --- filter_short_segments tests ---


class TestFilterShortDuration:
    """Test filtering by minimum duration."""

    def test_removes_short_duration(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:01.300", "Hi"),  # 0.3s < 0.5s
            Segment(2, "00:00:02.000", "00:00:05.000", "Hello world"),  # 3.0s
        ]
        result = filter_short_segments(segments)
        assert len(result) == 1
        assert result[0].english == "Hello world"

    def test_boundary_exactly_05_kept(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:01.500", "OK"),  # exactly 0.5s
        ]
        result = filter_short_segments(segments)
        assert len(result) == 1

    def test_boundary_just_under_05_removed(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:01.499", "OK"),  # 0.499s
        ]
        result = filter_short_segments(segments)
        assert len(result) == 0

    def test_custom_min_duration(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:01.800", "Hello"),  # 0.8s
        ]
        result = filter_short_segments(segments, min_duration_sec=1.0)
        assert len(result) == 0


class TestFilterShortText:
    """Test filtering by minimum text length."""

    def test_single_char_removed(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:05.000", "A"),  # 1 char < 2
        ]
        result = filter_short_segments(segments)
        assert len(result) == 0

    def test_two_chars_kept(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:05.000", "OK"),  # 2 chars
        ]
        result = filter_short_segments(segments)
        assert len(result) == 1

    def test_empty_text_removed(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:05.000", ""),
        ]
        result = filter_short_segments(segments)
        assert len(result) == 0

    def test_custom_min_text_length(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:05.000", "Hi"),  # 2 chars
        ]
        result = filter_short_segments(segments, min_text_length=3)
        assert len(result) == 0


class TestFilterShortReindex:
    """Test reindexing after filtering."""

    def test_reindexes_correctly(self) -> None:
        segments = [
            Segment(1, "00:00:01.000", "00:00:01.200", "X"),      # filtered (both)
            Segment(2, "00:00:02.000", "00:00:05.000", "Hello"),   # kept
            Segment(3, "00:00:06.000", "00:00:06.100", "Y"),       # filtered (duration)
            Segment(4, "00:00:07.000", "00:00:10.000", "World"),   # kept
        ]
        result = filter_short_segments(segments)
        assert len(result) == 2
        assert result[0].index == 1
        assert result[0].english == "Hello"
        assert result[1].index == 2
        assert result[1].english == "World"


class TestFilterShortTimestampParsing:
    """Test timestamp parsing edge cases."""

    def test_hours_in_timestamp(self) -> None:
        segments = [
            Segment(1, "01:30:00.000", "01:30:03.000", "Long video segment"),
        ]
        result = filter_short_segments(segments)
        assert len(result) == 1

    def test_millisecond_precision(self) -> None:
        segments = [
            Segment(1, "00:00:01.001", "00:00:01.502", "Just enough"),  # 0.501s
        ]
        result = filter_short_segments(segments)
        assert len(result) == 1


# --- process_segments (full pipeline) tests ---


class TestProcessSegments:
    """Test the full segment processing pipeline."""

    def test_mixed_complex_fixture(self) -> None:
        content = _read_fixture("mixed_complex.vtt")
        segments = parse_vtt(content)
        result = process_segments(segments)
        # After processing:
        # - [Music] (0.3s, non-verbal) -> removed
        # - "Hello & welcome to this video." (3.5s) -> kept
        # - "Today we're going to learn" (3.2s) -> kept
        # - "A" (0.2s, short duration + short text) -> removed
        # - "DNA is the blueprint" (3.8s) -> kept
        # - empty (0.1s) -> removed
        # - "Thank you for watching!" (3.0s) -> kept
        assert len(result) >= 3
        texts = [s.english for s in result]
        assert any("Hello" in t and "welcome" in t for t in texts)
        assert any("Thank you" in t for t in texts)
        # No non-verbal or tags should remain
        for seg in result:
            assert "[Music]" not in seg.english
            assert "<" not in seg.english

    def test_all_filtered_raises_error(self) -> None:
        segments = [
            Segment(1, "00:00:00.000", "00:00:00.200", "[Music]"),
        ]
        with pytest.raises(ValueError, match="No valid spoken segments"):
            process_segments(segments)

    def test_preserves_timestamps_through_pipeline(self) -> None:
        content = _read_fixture("basic.vtt")
        segments = parse_vtt(content)
        result = process_segments(segments)
        assert result[0].start == "00:00:01.000"
        assert result[0].end == "00:00:04.500"

    def test_indices_sequential_after_pipeline(self) -> None:
        content = _read_fixture("basic.vtt")
        segments = parse_vtt(content)
        result = process_segments(segments)
        for i, seg in enumerate(result, 1):
            assert seg.index == i
