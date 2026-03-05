"""VTT parsing, markup stripping, and segment processing."""

import html
import re
from dataclasses import dataclass


@dataclass
class Segment:
    """A single subtitle segment with timestamp and text.

    Attributes:
        index: Segment sequence number (1-based).
        start: Start timestamp in original VTT format (HH:MM:SS.mmm).
        end: End timestamp in original VTT format (HH:MM:SS.mmm).
        english: English text content.
        korean: Korean translation (empty until translated).
    """

    index: int
    start: str
    end: str
    english: str
    korean: str = ""


# Regex for VTT timestamp line: "HH:MM:SS.mmm --> HH:MM:SS.mmm [cue settings]"
_TIMESTAMP_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})"
)


def parse_vtt(content: str) -> list[Segment]:
    """Parse VTT content into a list of Segment objects.

    Extracts timestamp pairs and associated text from raw VTT content.
    Multi-line text within a single cue is joined with a single space.
    Cue settings (align, position, etc.) on the timestamp line are ignored.

    The timestamp strings are preserved exactly as they appear in the VTT file.

    Args:
        content: Raw VTT file content as a string.

    Returns:
        List of Segment objects with index, start, end, and english fields.

    Raises:
        ValueError: If VTT content contains no valid cue segments.
    """
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    segments: list[Segment] = []
    current_start: str | None = None
    current_end: str | None = None
    current_text_lines: list[str] = []
    index = 1

    for line in lines:
        line_stripped = line.strip()

        # Check for timestamp line
        match = _TIMESTAMP_RE.match(line_stripped)
        if match:
            # Save previous segment if exists
            if current_start is not None and current_text_lines:
                text = " ".join(current_text_lines)
                segments.append(Segment(
                    index=index,
                    start=current_start,
                    end=current_end,  # type: ignore[arg-type]
                    english=text,
                ))
                index += 1

            current_start = match.group(1)
            current_end = match.group(2)
            current_text_lines = []
            continue

        # Skip WEBVTT header, NOTE blocks, cue identifiers (numeric-only lines)
        if current_start is None:
            continue

        # Empty line = end of cue block
        if not line_stripped:
            if current_text_lines:
                text = " ".join(current_text_lines)
                segments.append(Segment(
                    index=index,
                    start=current_start,
                    end=current_end,  # type: ignore[arg-type]
                    english=text,
                ))
                index += 1
                current_start = None
                current_end = None
                current_text_lines = []
            continue

        # Skip numeric cue identifiers (lines that are just numbers before timestamps)
        if line_stripped.isdigit():
            continue

        # Collect text lines
        current_text_lines.append(line_stripped)

    # Handle last segment (no trailing empty line)
    if current_start is not None and current_text_lines:
        text = " ".join(current_text_lines)
        segments.append(Segment(
            index=index,
            start=current_start,
            end=current_end,  # type: ignore[arg-type]
            english=text,
        ))

    return segments


# --- Markup Stripping ---

# Matches any HTML/WebVTT tag (opening, closing, self-closing)
_TAG_RE = re.compile(r"<[^>]+>")

# VTT cue setting keywords that appear on text lines (not timestamp lines)
_CUE_SETTING_RE = re.compile(
    r"(?:align|position|size|line|vertical|region):[^\s]+"
)


def strip_markup(text: str) -> str:
    """Remove HTML/WebVTT markup and decode HTML entities.

    Processing order (per design doc 6.2):
    1. Remove VTT cue setting directives (align:start, position:10%, etc.)
    2. Remove all HTML/WebVTT tags (<c>, <v>, <b>, <i>, <font>, etc.)
    3. Decode HTML entities (&amp; -> &, &#39; -> ', etc.)
    4. Collapse consecutive whitespace to single space
    5. Trim leading/trailing whitespace

    Tags are removed but their inner text is preserved:
    - <c.colorE5E5E5>word</c> -> word
    - <v Speaker>Hello</v> -> Hello
    - <b>Bold</b> -> Bold

    Args:
        text: VTT cue text potentially containing markup.

    Returns:
        Clean text with all markup removed and entities decoded.
    """
    # 1. Remove VTT cue settings
    result = _CUE_SETTING_RE.sub("", text)

    # 2. Remove all HTML/WebVTT tags
    result = _TAG_RE.sub("", result)

    # 3. Decode HTML entities
    result = html.unescape(result)

    # 4. Collapse consecutive whitespace
    result = re.sub(r"\s+", " ", result)

    # 5. Trim
    return result.strip()


def strip_markup_segments(segments: list[Segment]) -> list[Segment]:
    """Apply markup stripping to all segments, removing empty ones.

    Args:
        segments: List of Segment objects with raw VTT text.

    Returns:
        New list with markup stripped. Segments that become empty after
        stripping are excluded.
    """
    result: list[Segment] = []
    index = 1
    for seg in segments:
        cleaned = strip_markup(seg.english)
        if cleaned:
            result.append(Segment(
                index=index,
                start=seg.start,
                end=seg.end,
                english=cleaned,
            ))
            index += 1
    return result


# --- Non-verbal Text Filter ---

# Bracketed non-verbal: [Music], [Applause], [Laughter], [Music playing], etc.
_BRACKET_NONVERBAL_RE = re.compile(r"\[[^\]]*\]")

# Parenthesized non-verbal: (Laughs), (Applause), (Music), etc.
_PAREN_NONVERBAL_RE = re.compile(r"\([^)]*\)")

# Musical notes: various unicode music symbols
_MUSIC_SYMBOL_RE = re.compile(r"[♪♫♬♩]+[\s♪♫♬♩]*")


def remove_non_verbal(text: str) -> str:
    """Remove non-verbal text markers from subtitle text.

    Removes:
    - Bracketed descriptions: [Music], [Applause], [Laughter], etc.
    - Parenthesized descriptions: (Laughs), (Music), etc.
    - Musical note symbols: various combinations

    If the entire text is non-verbal, returns empty string.
    If mixed with speech, only the non-verbal portions are removed.

    Args:
        text: Subtitle text (should already be markup-stripped).

    Returns:
        Text with non-verbal markers removed, whitespace collapsed.
    """
    result = _BRACKET_NONVERBAL_RE.sub("", text)
    result = _PAREN_NONVERBAL_RE.sub("", result)
    result = _MUSIC_SYMBOL_RE.sub("", result)
    result = re.sub(r"\s+", " ", result)
    return result.strip()


def remove_non_verbal_segments(segments: list[Segment]) -> list[Segment]:
    """Apply non-verbal removal to all segments, dropping empty results.

    Args:
        segments: List of Segment objects (should already be markup-stripped).

    Returns:
        New list with non-verbal text removed. Segments that become empty
        after removal are excluded and remaining segments are reindexed.
    """
    result: list[Segment] = []
    index = 1
    for seg in segments:
        cleaned = remove_non_verbal(seg.english)
        if cleaned:
            result.append(Segment(
                index=index,
                start=seg.start,
                end=seg.end,
                english=cleaned,
            ))
            index += 1
    return result
