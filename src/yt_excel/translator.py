"""Translation engine using OpenAI API with sliding window batching."""

import json
import logging
import re
import time

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


def create_client(api_key: str) -> OpenAI:
    """Create an OpenAI client instance.

    Args:
        api_key: The OpenAI API key.

    Returns:
        Configured OpenAI client.
    """
    return OpenAI(api_key=api_key)
