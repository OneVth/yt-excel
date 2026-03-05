"""Tests for the translation engine."""

import json
from unittest.mock import MagicMock, patch

import pytest

from yt_excel.translator import (
    Batch,
    build_batches,
    build_system_prompt,
    build_user_message,
    call_translation_api,
    parse_translation_response,
)
from yt_excel.vtt import Segment


def _make_segment(index: int, english: str) -> Segment:
    """Helper to create a Segment with dummy timestamps."""
    return Segment(
        index=index,
        start="00:00:01.000",
        end="00:00:02.000",
        english=english,
    )


class TestBuildSystemPrompt:
    """Tests for system prompt generation."""

    def test_includes_translate_count(self) -> None:
        prompt = build_system_prompt(10)
        assert "exactly 10 Korean strings" in prompt

    def test_mentions_context_and_translate_tags(self) -> None:
        prompt = build_system_prompt(5)
        assert "[TRANSLATE]" in prompt
        assert "[CONTEXT]" in prompt

    def test_instructs_json_response(self) -> None:
        prompt = build_system_prompt(10)
        assert "JSON" in prompt
        assert "translations" in prompt

    def test_instructs_not_to_translate_context(self) -> None:
        prompt = build_system_prompt(10)
        assert "do NOT translate" in prompt.lower() or "do NOT translate them" in prompt


class TestBuildUserMessage:
    """Tests for user message construction."""

    def test_translate_segments_tagged(self) -> None:
        segments = [_make_segment(1, "Hello"), _make_segment(2, "World")]
        msg = build_user_message(segments, [], [])
        assert "[TRANSLATE] 1: Hello" in msg
        assert "[TRANSLATE] 2: World" in msg

    def test_context_before_tagged(self) -> None:
        ctx_before = [_make_segment(1, "Before")]
        translate = [_make_segment(2, "Target")]
        msg = build_user_message(translate, ctx_before, [])
        assert "[CONTEXT] 1: Before" in msg
        assert "[TRANSLATE] 2: Target" in msg

    def test_context_after_tagged(self) -> None:
        translate = [_make_segment(1, "Target")]
        ctx_after = [_make_segment(2, "After")]
        msg = build_user_message(translate, [], ctx_after)
        assert "[TRANSLATE] 1: Target" in msg
        assert "[CONTEXT] 2: After" in msg

    def test_context_before_appears_before_translate(self) -> None:
        ctx_before = [_make_segment(1, "Before")]
        translate = [_make_segment(2, "Target")]
        ctx_after = [_make_segment(3, "After")]
        msg = build_user_message(translate, ctx_before, ctx_after)
        lines = msg.split("\n")
        assert lines[0].startswith("[CONTEXT]")
        assert lines[1].startswith("[TRANSLATE]")
        assert lines[2].startswith("[CONTEXT]")

    def test_no_context_segments(self) -> None:
        translate = [_make_segment(1, "Only this")]
        msg = build_user_message(translate, [], [])
        assert "[CONTEXT]" not in msg
        assert "[TRANSLATE] 1: Only this" in msg

    def test_full_context_window(self) -> None:
        ctx_before = [_make_segment(i, f"Before {i}") for i in range(1, 4)]
        translate = [_make_segment(i, f"Translate {i}") for i in range(4, 14)]
        ctx_after = [_make_segment(i, f"After {i}") for i in range(14, 17)]
        msg = build_user_message(translate, ctx_before, ctx_after)

        lines = msg.split("\n")
        # 3 context before + 10 translate + 3 context after = 16 lines
        assert len(lines) == 16
        # First 3 are context
        for line in lines[:3]:
            assert line.startswith("[CONTEXT]")
        # Middle 10 are translate
        for line in lines[3:13]:
            assert line.startswith("[TRANSLATE]")
        # Last 3 are context
        for line in lines[13:]:
            assert line.startswith("[CONTEXT]")


def _make_segments(count: int) -> list[Segment]:
    """Helper to create a list of numbered segments."""
    return [_make_segment(i, f"Segment {i}") for i in range(1, count + 1)]


class TestBuildBatches:
    """Tests for sliding window batch construction."""

    def test_empty_segments(self) -> None:
        assert build_batches([]) == []

    def test_single_batch_no_context_when_lte_batch_size(self) -> None:
        segments = _make_segments(10)
        batches = build_batches(segments, batch_size=10)
        assert len(batches) == 1
        assert len(batches[0].translate_segments) == 10
        assert batches[0].context_before == []
        assert batches[0].context_after == []

    def test_single_batch_fewer_than_batch_size(self) -> None:
        segments = _make_segments(5)
        batches = build_batches(segments, batch_size=10)
        assert len(batches) == 1
        assert len(batches[0].translate_segments) == 5
        assert batches[0].context_before == []
        assert batches[0].context_after == []

    def test_two_batches_normal(self) -> None:
        segments = _make_segments(15)
        batches = build_batches(segments, batch_size=10, context_before=3, context_after=3)
        assert len(batches) == 2

        # First batch: segments 1-10
        b1 = batches[0]
        assert len(b1.translate_segments) == 10
        assert b1.context_before == []  # No context before first batch
        assert len(b1.context_after) == 3
        assert b1.context_after[0].index == 11

        # Second batch: segments 11-15
        b2 = batches[1]
        assert len(b2.translate_segments) == 5
        assert len(b2.context_before) == 3
        assert b2.context_before[0].index == 8
        assert b2.context_after == []  # No context after last batch

    def test_context_before_clamped_at_start(self) -> None:
        segments = _make_segments(20)
        batches = build_batches(segments, batch_size=10, context_before=3, context_after=3)
        # First batch has no context_before
        assert batches[0].context_before == []

    def test_context_after_clamped_at_end(self) -> None:
        segments = _make_segments(20)
        batches = build_batches(segments, batch_size=10, context_before=3, context_after=3)
        # Last batch has no context_after
        assert batches[-1].context_after == []

    def test_three_batches_context_windows(self) -> None:
        segments = _make_segments(25)
        batches = build_batches(segments, batch_size=10, context_before=3, context_after=3)
        assert len(batches) == 3

        # Middle batch should have full context windows
        b2 = batches[1]
        assert len(b2.context_before) == 3
        assert len(b2.context_after) == 3

    def test_all_segments_covered_exactly_once(self) -> None:
        segments = _make_segments(25)
        batches = build_batches(segments, batch_size=10, context_before=3, context_after=3)
        translated_indices = []
        for batch in batches:
            translated_indices.extend(seg.index for seg in batch.translate_segments)
        assert translated_indices == list(range(1, 26))

    def test_single_segment(self) -> None:
        segments = _make_segments(1)
        batches = build_batches(segments, batch_size=10)
        assert len(batches) == 1
        assert len(batches[0].translate_segments) == 1

    def test_exactly_batch_size_plus_one(self) -> None:
        segments = _make_segments(11)
        batches = build_batches(segments, batch_size=10, context_before=3, context_after=3)
        assert len(batches) == 2
        assert len(batches[0].translate_segments) == 10
        assert len(batches[1].translate_segments) == 1
        # Second batch should have 3 context_before (segments 8,9,10)
        assert len(batches[1].context_before) == 3


class TestParseTranslationResponse:
    """Tests for JSON response parsing."""

    def test_valid_json_with_translations_key(self) -> None:
        raw = json.dumps({"translations": ["번역1", "번역2", "번역3"]})
        result = parse_translation_response(raw, expected_count=3)
        assert result == ["번역1", "번역2", "번역3"]

    def test_valid_json_array_directly(self) -> None:
        raw = json.dumps(["번역1", "번역2"])
        result = parse_translation_response(raw, expected_count=2)
        assert result == ["번역1", "번역2"]

    def test_markdown_code_block_wrapper(self) -> None:
        inner = json.dumps({"translations": ["안녕", "세계"]})
        raw = f"```json\n{inner}\n```"
        result = parse_translation_response(raw, expected_count=2)
        assert result == ["안녕", "세계"]

    def test_markdown_code_block_no_language(self) -> None:
        inner = json.dumps({"translations": ["안녕"]})
        raw = f"```\n{inner}\n```"
        result = parse_translation_response(raw, expected_count=1)
        assert result == ["안녕"]

    def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_translation_response("not json at all", expected_count=1)

    def test_invalid_json_in_markdown_block(self) -> None:
        raw = "```json\n{broken json\n```"
        with pytest.raises(ValueError, match="Failed to parse JSON"):
            parse_translation_response(raw, expected_count=1)

    def test_unexpected_structure_raises_value_error(self) -> None:
        raw = json.dumps({"wrong_key": "value"})
        with pytest.raises(ValueError, match="Unexpected response structure"):
            parse_translation_response(raw, expected_count=1)

    def test_translations_not_a_list_raises_value_error(self) -> None:
        raw = json.dumps({"translations": "not a list"})
        with pytest.raises(ValueError, match="must be a list"):
            parse_translation_response(raw, expected_count=1)

    def test_non_string_items_converted_to_string(self) -> None:
        raw = json.dumps({"translations": [123, True]})
        result = parse_translation_response(raw, expected_count=2)
        assert result == ["123", "True"]

    def test_whitespace_around_json(self) -> None:
        raw = "  \n" + json.dumps({"translations": ["테스트"]}) + "\n  "
        result = parse_translation_response(raw, expected_count=1)
        assert result == ["테스트"]


class TestCallTranslationApi:
    """Tests for the API calling function (mocked)."""

    def test_calls_openai_with_correct_params(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"translations": ["안녕하세요"]}
        )
        mock_client.chat.completions.create.return_value = mock_response

        batch = Batch(
            translate_segments=[_make_segment(1, "Hello")],
            context_before=[],
            context_after=[],
        )
        result = call_translation_api(mock_client, batch, model="gpt-5-nano")

        assert result == json.dumps({"translations": ["안녕하세요"]})

        # Verify API was called with json_object response format
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-5-nano"
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"

    def test_returns_empty_string_when_content_is_none(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create.return_value = mock_response

        batch = Batch(
            translate_segments=[_make_segment(1, "Hello")],
            context_before=[],
            context_after=[],
        )
        result = call_translation_api(mock_client, batch, model="gpt-5-nano")
        assert result == ""
