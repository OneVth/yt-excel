"""Translation engine using OpenAI API with sliding window batching."""

import json
import logging
import re
import time
from dataclasses import dataclass

from openai import OpenAI

from yt_excel.config import TranslationConfig
from yt_excel.vtt import Segment

logger = logging.getLogger(__name__)

# System prompt template for translation requests
_SYSTEM_PROMPT = (
    "You are a professional English-to-Korean subtitle translator.\n"
    "Translate the [TRANSLATE] segments from English to Korean.\n"
    "[CONTEXT] segments are provided for reference only — do NOT translate them.\n"
    "\n"
    "Rules:\n"
    "- Translate each segment independently (do not merge or split).\n"
    "- Maintain natural Korean while avoiding excessive paraphrasing.\n"
    "- Return a JSON object with a single key \"translations\" containing "
    "an array of exactly {count} Korean strings.\n"
    "- The array order must match the [TRANSLATE] segment order.\n"
    "- Do NOT include translations for [CONTEXT] segments."
)


def build_system_prompt(translate_count: int) -> str:
    """Build the system prompt with the expected translation count.

    Args:
        translate_count: Number of segments to translate in this batch.

    Returns:
        Formatted system prompt string.
    """
    return _SYSTEM_PROMPT.format(count=translate_count)


def build_user_message(
    translate_segments: list[Segment],
    context_before: list[Segment],
    context_after: list[Segment],
) -> str:
    """Build the user message with context and translation segments.

    Context segments are tagged with [CONTEXT] and translation targets
    with [TRANSLATE] so the LLM can distinguish them.

    Args:
        translate_segments: Segments to be translated.
        context_before: Preceding context segments (not translated).
        context_after: Following context segments (not translated).

    Returns:
        Formatted user message string.
    """
    lines: list[str] = []

    if context_before:
        for seg in context_before:
            lines.append(f"[CONTEXT] {seg.index}: {seg.english}")

    for seg in translate_segments:
        lines.append(f"[TRANSLATE] {seg.index}: {seg.english}")

    if context_after:
        for seg in context_after:
            lines.append(f"[CONTEXT] {seg.index}: {seg.english}")

    return "\n".join(lines)


@dataclass
class Batch:
    """A single translation batch with context windows.

    Attributes:
        translate_segments: Segments to translate in this batch.
        context_before: Preceding context segments (for reference only).
        context_after: Following context segments (for reference only).
    """

    translate_segments: list[Segment]
    context_before: list[Segment]
    context_after: list[Segment]


def build_batches(
    segments: list[Segment],
    batch_size: int = 10,
    context_before: int = 3,
    context_after: int = 3,
) -> list[Batch]:
    """Split segments into sliding window batches for translation.

    Each batch contains up to batch_size segments to translate, plus
    context_before preceding segments and context_after following segments
    for reference. Context windows are automatically adjusted at the
    start and end of the segment list.

    If total segments <= batch_size, a single batch with no context is created.

    Args:
        segments: All segments to translate.
        batch_size: Number of segments per translation batch.
        context_before: Number of preceding context segments.
        context_after: Number of following context segments.

    Returns:
        List of Batch objects ready for API calls.
    """
    if not segments:
        return []

    total = len(segments)

    # Single batch: no context needed
    if total <= batch_size:
        return [Batch(
            translate_segments=list(segments),
            context_before=[],
            context_after=[],
        )]

    batches: list[Batch] = []
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        translate = segments[start:end]

        ctx_before_start = max(0, start - context_before)
        ctx_before = segments[ctx_before_start:start]

        ctx_after_end = min(total, end + context_after)
        ctx_after = segments[end:ctx_after_end]

        batches.append(Batch(
            translate_segments=translate,
            context_before=ctx_before,
            context_after=ctx_after,
        ))

    return batches


def create_client(api_key: str) -> OpenAI:
    """Create an OpenAI client instance.

    Args:
        api_key: The OpenAI API key.

    Returns:
        Configured OpenAI client.
    """
    return OpenAI(api_key=api_key)
