"""Tests for the translation engine."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_excel.config import TranslationConfig
from yt_excel.translator import (
    Batch,
    TranslationResult,
    build_batches,
    build_system_prompt,
    build_user_message,
    call_translation_api,
    call_translation_api_async,
    parse_translation_response,
    translate_batch_with_retry,
    translate_batch_with_retry_async,
    translate_segments,
    translate_segments_async,
    validate_translations,
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


class TestValidateTranslations:
    """Tests for translation array length validation."""

    def test_exact_match(self) -> None:
        result = validate_translations(["a", "b", "c"], expected_count=3)
        assert result == ["a", "b", "c"]

    def test_excess_truncated_with_warning(self) -> None:
        result = validate_translations(["a", "b", "c", "d", "e"], expected_count=3)
        assert result == ["a", "b", "c"]

    def test_shortage_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="expected 3"):
            validate_translations(["a"], expected_count=3)

    def test_empty_list_when_expected_zero(self) -> None:
        result = validate_translations([], expected_count=0)
        assert result == []


class TestTranslateBatchWithRetry:
    """Tests for batch retry logic with mocked API."""

    def _mock_api_response(self, translations: list[str]) -> MagicMock:
        """Create a mock client that returns given translations."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"translations": translations}
        )
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    @patch("yt_excel.translator.time.sleep")
    def test_successful_translation(self, mock_sleep: MagicMock) -> None:
        mock_client = self._mock_api_response(["안녕"])
        batch = Batch(
            translate_segments=[_make_segment(1, "Hello")],
            context_before=[],
            context_after=[],
        )
        result = translate_batch_with_retry(
            mock_client, batch, "gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert result == ["안녕"]

    @patch("yt_excel.translator.time.sleep")
    def test_retry_on_shortage_then_success(self, mock_sleep: MagicMock) -> None:
        mock_client = MagicMock()
        # First call: too few translations; second call: correct
        responses = [
            self._make_response(["only_one"]),
            self._make_response(["번역1", "번역2"]),
        ]
        mock_client.chat.completions.create.side_effect = responses

        batch = Batch(
            translate_segments=[_make_segment(1, "Hello"), _make_segment(2, "World")],
            context_before=[],
            context_after=[],
        )
        result = translate_batch_with_retry(
            mock_client, batch, "gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert result == ["번역1", "번역2"]
        assert mock_client.chat.completions.create.call_count == 2

    @patch("yt_excel.translator.time.sleep")
    def test_three_failures_returns_empty_strings(self, mock_sleep: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("parse error")

        batch = Batch(
            translate_segments=[_make_segment(1, "Hello"), _make_segment(2, "World")],
            context_before=[],
            context_after=[],
        )
        result = translate_batch_with_retry(
            mock_client, batch, "gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert result == ["", ""]
        assert mock_client.chat.completions.create.call_count == 3

    @patch("yt_excel.translator.time.sleep")
    def test_rate_limit_429_retry(self, mock_sleep: MagicMock) -> None:
        from openai import RateLimitError

        mock_client = MagicMock()
        # Build a proper RateLimitError
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"retry-after": "2"}
        mock_resp.json.return_value = {"error": {"message": "rate limited"}}
        rate_err = RateLimitError(
            message="rate limited",
            response=mock_resp,
            body={"error": {"message": "rate limited"}},
        )
        good_response = self._make_response(["성공"])

        mock_client.chat.completions.create.side_effect = [rate_err, good_response]

        batch = Batch(
            translate_segments=[_make_segment(1, "Hello")],
            context_before=[],
            context_after=[],
        )
        result = translate_batch_with_retry(
            mock_client, batch, "gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert result == ["성공"]
        assert mock_client.chat.completions.create.call_count == 2

    @patch("yt_excel.translator.time.sleep")
    def test_excess_translations_truncated(self, mock_sleep: MagicMock) -> None:
        mock_client = self._mock_api_response(["a", "b", "c", "extra"])
        batch = Batch(
            translate_segments=[
                _make_segment(1, "Hello"),
                _make_segment(2, "World"),
                _make_segment(3, "Foo"),
            ],
            context_before=[],
            context_after=[],
        )
        result = translate_batch_with_retry(
            mock_client, batch, "gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert result == ["a", "b", "c"]

    def _make_response(self, translations: list[str]) -> MagicMock:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"translations": translations}
        )
        return mock_response


class TestTranslateSegments:
    """Tests for the full translation pipeline."""

    @patch("yt_excel.translator.time.sleep")
    def test_translates_all_segments(self, mock_sleep: MagicMock) -> None:
        segments = _make_segments(3)
        config = TranslationConfig(
            model="gpt-5-nano",
            batch_size=10,
            context_before=3,
            context_after=3,
            request_interval_ms=0,
            max_retries=3,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"translations": ["번역1", "번역2", "번역3"]}
        )
        mock_client.chat.completions.create.return_value = mock_response

        result = translate_segments(mock_client, segments, config)
        assert result.success_count == 3
        assert result.failed_count == 0
        assert len(result.segments) == 3
        assert result.segments[0].korean == "번역1"
        assert result.segments[2].korean == "번역3"

    @patch("yt_excel.translator.time.sleep")
    def test_failed_batch_leaves_korean_empty(self, mock_sleep: MagicMock) -> None:
        segments = _make_segments(3)
        config = TranslationConfig(
            model="gpt-5-nano",
            batch_size=10,
            context_before=3,
            context_after=3,
            request_interval_ms=0,
            max_retries=1,
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("always fails")

        result = translate_segments(mock_client, segments, config)
        assert result.success_count == 0
        assert result.failed_count == 3
        for seg in result.segments:
            assert seg.korean == ""


# --- Async Translation Tests ---


def _make_async_response(translations: list[str]) -> MagicMock:
    """Create a mock response object for async API calls."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(
        {"translations": translations}
    )
    return mock_response


def _make_async_client(translations: list[str]) -> MagicMock:
    """Create a mock AsyncOpenAI client returning given translations."""
    mock_client = MagicMock()
    mock_response = _make_async_response(translations)
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


class TestCallTranslationApiAsync:
    """Tests for async API calling function."""

    @pytest.mark.asyncio
    async def test_calls_async_openai_correctly(self) -> None:
        mock_client = _make_async_client(["안녕하세요"])
        batch = Batch(
            translate_segments=[_make_segment(1, "Hello")],
            context_before=[],
            context_after=[],
        )
        result = await call_translation_api_async(mock_client, batch, "gpt-5-nano")
        parsed = json.loads(result)
        assert parsed["translations"] == ["안녕하세요"]
        mock_client.chat.completions.create.assert_awaited_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-5-nano"
        assert call_kwargs["response_format"] == {"type": "json_object"}


class TestTranslateBatchWithRetryAsync:
    """Tests for async batch retry logic."""

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_successful_translation(self, mock_sleep: AsyncMock) -> None:
        mock_client = _make_async_client(["안녕"])
        batch = Batch(
            translate_segments=[_make_segment(1, "Hello")],
            context_before=[],
            context_after=[],
        )
        idx, result = await translate_batch_with_retry_async(
            mock_client, batch, batch_idx=0, total_batches=1,
            model="gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert idx == 0
        assert result == ["안녕"]

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_returns_batch_index_for_ordering(self, mock_sleep: AsyncMock) -> None:
        mock_client = _make_async_client(["결과"])
        batch = Batch(
            translate_segments=[_make_segment(1, "Test")],
            context_before=[],
            context_after=[],
        )
        idx, result = await translate_batch_with_retry_async(
            mock_client, batch, batch_idx=5, total_batches=10,
            model="gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert idx == 5
        assert result == ["결과"]

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_all_retries_exhausted_returns_empty(self, mock_sleep: AsyncMock) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=ValueError("parse error")
        )
        batch = Batch(
            translate_segments=[_make_segment(1, "Hello"), _make_segment(2, "World")],
            context_before=[],
            context_after=[],
        )
        idx, result = await translate_batch_with_retry_async(
            mock_client, batch, batch_idx=0, total_batches=1,
            model="gpt-5-nano", max_retries=3, request_interval_ms=0,
        )
        assert idx == 0
        assert result == ["", ""]
        assert mock_client.chat.completions.create.await_count == 3


class TestTranslateSegmentsAsync:
    """Tests for the full async translation pipeline."""

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_translates_all_segments(self, mock_sleep: AsyncMock) -> None:
        segments = _make_segments(3)
        config = TranslationConfig(
            model="gpt-5-nano",
            batch_size=10,
            context_before=3,
            context_after=3,
            request_interval_ms=0,
            max_retries=3,
            max_concurrent_batches=3,
        )
        mock_client = _make_async_client(["번역1", "번역2", "번역3"])
        result = await translate_segments_async(mock_client, segments, config)
        assert result.success_count == 3
        assert result.failed_count == 0
        assert len(result.segments) == 3
        assert result.segments[0].korean == "번역1"
        assert result.segments[2].korean == "번역3"

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_result_order_preserved_across_batches(
        self, mock_sleep: AsyncMock,
    ) -> None:
        """Ensure segments are ordered by index even with concurrent batches."""
        segments = _make_segments(15)
        config = TranslationConfig(
            model="gpt-5-nano",
            batch_size=5,
            context_before=2,
            context_after=2,
            request_interval_ms=0,
            max_retries=3,
            max_concurrent_batches=3,
        )
        # Each batch of 5 gets unique translations
        call_count = 0
        batch_translations = [
            ["번역1", "번역2", "번역3", "번역4", "번역5"],
            ["번역6", "번역7", "번역8", "번역9", "번역10"],
            ["번역11", "번역12", "번역13", "번역14", "번역15"],
        ]

        async def mock_create(**kwargs):
            nonlocal call_count
            user_msg = kwargs["messages"][1]["content"]
            # Determine which batch based on first segment index in message
            for i, trans in enumerate(batch_translations):
                expected_idx = i * 5 + 1
                if f"[TRANSLATE] {expected_idx}:" in user_msg:
                    return _make_async_response(trans).choices[0].message
            # Fallback
            idx = call_count
            call_count += 1
            resp = _make_async_response(batch_translations[idx % 3])
            return resp

        # Simpler approach: return different responses per call
        responses = [
            _make_async_response(t) for t in batch_translations
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=responses)

        result = await translate_segments_async(mock_client, segments, config)
        assert len(result.segments) == 15
        # Verify segments are in correct order
        for i, seg in enumerate(result.segments):
            assert seg.index == i + 1
            assert seg.korean == f"번역{i + 1}"

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_concurrency_limited_by_semaphore(
        self, mock_sleep: AsyncMock,
    ) -> None:
        """Verify that max_concurrent_batches limits concurrency."""
        segments = _make_segments(30)
        config = TranslationConfig(
            model="gpt-5-nano",
            batch_size=10,
            context_before=3,
            context_after=3,
            request_interval_ms=0,
            max_retries=3,
            max_concurrent_batches=2,
        )

        concurrent_count = 0
        max_concurrent = 0

        async def mock_create(**kwargs):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0)  # Yield to event loop
            concurrent_count -= 1
            return _make_async_response(
                ["ok"] * 10
            )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)

        result = await translate_segments_async(mock_client, segments, config)
        assert result.success_count == 30
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_failed_batch_does_not_affect_others(
        self, mock_sleep: AsyncMock,
    ) -> None:
        segments = _make_segments(20)
        config = TranslationConfig(
            model="gpt-5-nano",
            batch_size=10,
            context_before=3,
            context_after=3,
            request_interval_ms=0,
            max_retries=1,
            max_concurrent_batches=2,
        )
        # First call fails, second succeeds
        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("parse error")
            return _make_async_response(["성공"] * 10)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)

        result = await translate_segments_async(mock_client, segments, config)
        assert result.success_count == 10
        assert result.failed_count == 10

    @pytest.mark.asyncio
    @patch("yt_excel.translator.asyncio.sleep", new_callable=AsyncMock)
    async def test_on_batch_complete_callback(self, mock_sleep: AsyncMock) -> None:
        segments = _make_segments(15)
        config = TranslationConfig(
            model="gpt-5-nano",
            batch_size=5,
            context_before=2,
            context_after=2,
            request_interval_ms=0,
            max_retries=3,
            max_concurrent_batches=3,
        )
        mock_client = MagicMock()
        responses = [_make_async_response(["ok"] * 5) for _ in range(3)]
        mock_client.chat.completions.create = AsyncMock(side_effect=responses)

        callback_counts: list[int] = []
        result = await translate_segments_async(
            mock_client, segments, config,
            on_batch_complete=lambda count: callback_counts.append(count),
        )
        assert result.success_count == 15
        assert callback_counts == [5, 5, 5]
