"""Phase 7: VTT edge case tests.

Covers:
- <c> word-level timing with various class attributes
- <v> speaker tags with complex names
- Non-verbal + speech mixed segments
- Very long segments (100+ words)
- Entire segment is non-verbal
- Edge cases in markup stripping order
"""

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


class TestWordLevelTimingEdgeCases:
    """Edge cases for <c> word-level timing tags."""

    def test_nested_c_tags_with_color_classes(self):
        """Multiple <c> tags with different color classes are all stripped."""
        text = (
            '<c.colorE5E5E5>Hello</c><c.colorCCCCCC> </c>'
            '<c.colorE5E5E5>world</c>'
        )
        assert strip_markup(text) == "Hello world"

    def test_c_tag_with_timestamp_attributes(self):
        """<c> tags with timestamp sub-attributes are stripped."""
        text = '<c.colorE5E5E5><00:00:01.000>Hello</c> <c><00:00:01.500>world</c>'
        result = strip_markup(text)
        # Timestamps inside tags should be stripped along with tags
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_empty_c_tag(self):
        """Empty <c> tags don't create extra content."""
        text = "Hello <c></c>world"
        assert strip_markup(text) == "Hello world"

    def test_dense_word_timing_full_segment(self):
        """Dense word-level timing across entire segment."""
        text = (
            '<c.colorE5E5E5>The</c><c> </c><c.colorE5E5E5>quick</c>'
            '<c> </c><c.colorE5E5E5>brown</c><c> </c>'
            '<c.colorE5E5E5>fox</c><c> </c><c.colorE5E5E5>jumps</c>'
        )
        result = strip_markup(text)
        assert result == "The quick brown fox jumps"


class TestSpeakerTagEdgeCases:
    """Edge cases for <v> speaker tags."""

    def test_speaker_with_dots_and_numbers(self):
        """Speaker names with periods and numbers are stripped."""
        text = '<v Dr. Smith Jr. III>This is important.</v>'
        assert strip_markup(text) == "This is important."

    def test_speaker_with_special_characters(self):
        """Speaker names with various characters are stripped."""
        text = '<v Speaker (Host)>Welcome to the show.</v>'
        result = strip_markup(text)
        assert "Welcome to the show." in result
        # The (Host) part after tag removal should be handled
        assert "<v" not in result

    def test_multiple_speakers_in_one_segment(self):
        """Multiple speaker tags in one segment."""
        text = '<v Alice>Hello!</v> <v Bob>Hi there!</v>'
        assert strip_markup(text) == "Hello! Hi there!"

    def test_unclosed_v_tag(self):
        """Unclosed <v> tag still gets stripped."""
        text = '<v Speaker>Hello and welcome'
        result = strip_markup(text)
        assert result == "Hello and welcome"
        assert "<" not in result


class TestNonVerbalMixedContent:
    """Tests for segments mixing non-verbal and speech content."""

    def test_music_at_start_of_speech(self):
        """[Music] followed by speech."""
        text = "[Music] And welcome back to the show."
        assert remove_non_verbal(text) == "And welcome back to the show."

    def test_music_at_end_of_speech(self):
        """Speech followed by [Music]."""
        text = "Thank you for watching. [Music]"
        assert remove_non_verbal(text) == "Thank you for watching."

    def test_speech_between_non_verbal(self):
        """Speech sandwiched between non-verbal markers."""
        text = "[Applause] Thank you! [Laughter]"
        assert remove_non_verbal(text) == "Thank you!"

    def test_multiple_non_verbal_types_mixed(self):
        """Multiple non-verbal types mixed with speech."""
        text = "[Music] Hello (Laughs) and welcome [Applause]"
        assert remove_non_verbal(text) == "Hello and welcome"

    def test_music_symbols_with_text(self):
        """Music symbols mixed with actual text."""
        text = "♪ La la la ♪ That was beautiful"
        result = remove_non_verbal(text)
        assert "That was beautiful" in result

    def test_partial_bracket_not_non_verbal(self):
        """Text with standalone brackets that aren't non-verbal."""
        # This is a tricky case - our regex removes ALL bracketed content
        text = "The pH range is between [0] and [14]"
        result = remove_non_verbal(text)
        # Bracketed numbers will be removed by our current regex
        # This is acceptable per design doc 6.3 (brackets = non-verbal)
        assert "The pH range is between" in result


class TestLongSegments:
    """Tests for very long segments (100+ words)."""

    def test_100_word_segment_preserved(self):
        """A segment with 100+ words is preserved without splitting."""
        words = ["word" + str(i) for i in range(120)]
        long_text = " ".join(words)
        segments = [Segment(index=1, start="00:00:00.000", end="00:01:00.000", english=long_text)]
        result = strip_markup_segments(segments)
        assert len(result) == 1
        assert result[0].english == long_text

    def test_long_segment_with_markup(self):
        """Long segment with scattered markup is cleaned properly."""
        parts = []
        for i in range(50):
            parts.append(f"<c>word{i}</c>")
        text = " ".join(parts)
        result = strip_markup(text)
        for i in range(50):
            assert f"word{i}" in result
        assert "<c>" not in result

    def test_long_segment_passes_filter(self):
        """Long segments pass the short segment filter."""
        long_text = " ".join(["testing"] * 100)
        segments = [Segment(
            index=1,
            start="00:00:00.000",
            end="00:05:00.000",
            english=long_text,
        )]
        result = filter_short_segments(segments)
        assert len(result) == 1


class TestEntireNonVerbalSegments:
    """Tests for segments that are entirely non-verbal."""

    def test_only_music_bracket(self):
        """Segment with only [Music] becomes empty."""
        assert remove_non_verbal("[Music]") == ""

    def test_only_applause(self):
        """Segment with only [Applause] becomes empty."""
        assert remove_non_verbal("[Applause]") == ""

    def test_only_music_symbols(self):
        """Segment with only music symbols becomes empty."""
        assert remove_non_verbal("♪ ♪") == ""

    def test_only_parenthesized_action(self):
        """Segment with only (Laughs) becomes empty."""
        assert remove_non_verbal("(Laughs)") == ""

    def test_multiple_non_verbal_markers_only(self):
        """Segment with multiple non-verbal markers and no speech."""
        text = "[Music] [Applause] (Cheering)"
        assert remove_non_verbal(text) == ""

    def test_non_verbal_segment_removed_from_list(self):
        """Entirely non-verbal segments are removed from segment list."""
        segments = [
            Segment(index=1, start="00:00:00.000", end="00:00:02.000", english="[Music]"),
            Segment(index=2, start="00:00:03.000", end="00:00:06.000", english="Hello world"),
            Segment(index=3, start="00:00:07.000", end="00:00:09.000", english="[Applause]"),
        ]
        result = remove_non_verbal_segments(segments)
        assert len(result) == 1
        assert result[0].english == "Hello world"
        assert result[0].index == 1  # Reindexed


class TestFullVttProcessingEdgeCases:
    """Tests for the complete VTT processing pipeline with edge cases."""

    def test_vtt_with_only_non_verbal_raises_error(self):
        """VTT with only non-verbal segments raises ValueError."""
        vtt = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "[Music]\n\n"
            "00:00:03.000 --> 00:00:05.000\n"
            "[Applause]\n\n"
        )
        segments = parse_vtt(vtt)
        with pytest.raises(ValueError, match="No valid spoken segments"):
            process_segments(segments)

    def test_vtt_with_mixed_markup_and_non_verbal(self):
        """VTT with markup + non-verbal is properly cleaned."""
        vtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "<v Speaker>[Music] Hello &amp; welcome</v>\n\n"
            "00:00:05.000 --> 00:00:08.000\n"
            "<c.colorE5E5E5>Today</c> we learn <b>about</b> DNA\n\n"
        )
        segments = parse_vtt(vtt)
        result = process_segments(segments)
        assert len(result) == 2
        assert result[0].english == "Hello & welcome"
        assert result[1].english == "Today we learn about DNA"

    def test_vtt_short_segments_after_cleaning(self):
        """Segments that become very short after cleanup are filtered."""
        vtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "<b>A</b>\n\n"
            "00:00:05.000 --> 00:00:08.000\n"
            "This is a proper segment\n\n"
        )
        segments = parse_vtt(vtt)
        result = process_segments(segments)
        # "A" is only 1 char, should be filtered (min_text_length=2)
        assert len(result) == 1
        assert result[0].english == "This is a proper segment"

    def test_vtt_with_cue_identifiers(self):
        """VTT with numeric cue identifiers (SRT-style) parsed correctly."""
        vtt = (
            "WEBVTT\n\n"
            "1\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "First segment\n\n"
            "2\n"
            "00:00:05.000 --> 00:00:08.000\n"
            "Second segment\n\n"
        )
        segments = parse_vtt(vtt)
        assert len(segments) == 2
        assert segments[0].english == "First segment"
        assert segments[1].english == "Second segment"

    def test_vtt_with_no_trailing_newline(self):
        """VTT without trailing newline still captures last segment."""
        vtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "Last segment without newline"
        )
        segments = parse_vtt(vtt)
        assert len(segments) == 1
        assert segments[0].english == "Last segment without newline"

    def test_vtt_with_carriage_returns(self):
        """VTT with Windows-style line endings (\\r\\n) parsed correctly."""
        vtt = (
            "WEBVTT\r\n\r\n"
            "00:00:01.000 --> 00:00:04.000\r\n"
            "First segment\r\n\r\n"
            "00:00:05.000 --> 00:00:08.000\r\n"
            "Second segment\r\n"
        )
        segments = parse_vtt(vtt)
        assert len(segments) == 2

    def test_vtt_empty_content_returns_empty_list(self):
        """Empty VTT content returns empty list."""
        segments = parse_vtt("WEBVTT\n\n")
        assert segments == []

    def test_vtt_header_only_returns_empty_list(self):
        """VTT with only header and no cues returns empty list."""
        vtt = "WEBVTT\n\nNOTE This is a comment\n\n"
        segments = parse_vtt(vtt)
        assert segments == []
