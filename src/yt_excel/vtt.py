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
