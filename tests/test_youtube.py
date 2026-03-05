"""Tests for YouTube URL parsing, metadata fetching, and caption logic."""

from unittest.mock import MagicMock, patch

import pytest

from yt_excel.youtube import (
    AutoCaptionOnlyError,
    CaptionNotFoundError,
    _classify_captions,
    _find_english_code,
    _format_duration,
    extract_video_id,
    fetch_metadata,
    download_captions,
)


# ---------------------------------------------------------------------------
# extract_video_id
# ---------------------------------------------------------------------------

class TestExtractVideoId:
    """Tests for URL parsing and video_id extraction."""

    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ])
    def test_standard_watch_urls(self, url: str, expected: str):
        assert extract_video_id(url) == expected

    def test_shortened_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_v_url(self):
        assert extract_video_id("https://www.youtube.com/v/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmE&t=42"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_url_without_scheme(self):
        assert extract_video_id("youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_with_whitespace(self):
        assert extract_video_id("  https://youtu.be/dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="URL is empty"):
            extract_video_id("")

    def test_whitespace_only_url_raises(self):
        with pytest.raises(ValueError, match="URL is empty"):
            extract_video_id("   ")

    def test_non_youtube_url_raises(self):
        with pytest.raises(ValueError, match="Not a valid YouTube URL"):
            extract_video_id("https://vimeo.com/12345")

    def test_youtube_url_without_video_id_raises(self):
        with pytest.raises(ValueError, match="Could not extract"):
            extract_video_id("https://www.youtube.com/watch")

    def test_invalid_video_id_length_raises(self):
        with pytest.raises(ValueError, match="Could not extract"):
            extract_video_id("https://www.youtube.com/watch?v=short")

    def test_video_id_with_dash_and_underscore(self):
        assert extract_video_id("https://youtu.be/Ab_-Cd12_eF") == "Ab_-Cd12_eF"

    def test_random_url_raises(self):
        with pytest.raises(ValueError):
            extract_video_id("not-a-url-at-all")


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    """Tests for duration formatting helper."""

    def test_zero_seconds(self):
        assert _format_duration(0) == "00:00:00"

    def test_minutes_and_seconds(self):
        assert _format_duration(292) == "00:04:52"

    def test_hours(self):
        assert _format_duration(3661) == "01:01:01"

    def test_float_seconds_truncated(self):
        assert _format_duration(292.7) == "00:04:52"


# ---------------------------------------------------------------------------
# _find_english_code
# ---------------------------------------------------------------------------

class TestFindEnglishCode:
    """Tests for English language code matching."""

    def test_exact_en(self):
        assert _find_english_code({"en": [], "fr": []}) == "en"

    def test_en_us_fallback(self):
        assert _find_english_code({"en-US": [], "fr": []}) == "en-US"

    def test_en_exact_preferred_over_variant(self):
        assert _find_english_code({"en-US": [], "en": [], "en-GB": []}) == "en"

    def test_first_variant_alphabetically(self):
        result = _find_english_code({"en-GB": [], "en-US": []})
        assert result == "en-GB"

    def test_no_english_returns_none(self):
        assert _find_english_code({"fr": [], "de": []}) is None

    def test_empty_dict_returns_none(self):
        assert _find_english_code({}) is None


# ---------------------------------------------------------------------------
# _classify_captions
# ---------------------------------------------------------------------------

class TestClassifyCaptions:
    """Tests for caption type classification."""

    def test_manual_en_found(self):
        result = _classify_captions(
            manual_subs={"en": [{"ext": "vtt"}]},
            auto_subs={"en": [{"ext": "vtt"}]},
        )
        assert result.caption_type == "manual"
        assert result.lang_code == "en"

    def test_manual_en_us_found(self):
        result = _classify_captions(
            manual_subs={"en-US": [{"ext": "vtt"}]},
            auto_subs={},
        )
        assert result.lang_code == "en-US"
        assert result.caption_type == "manual"

    def test_manual_multiple_en_codes(self):
        result = _classify_captions(
            manual_subs={"en": [], "en-GB": [], "fr": []},
            auto_subs={},
        )
        assert result.lang_code == "en"
        assert sorted(result.available_codes) == ["en", "en-GB"]

    def test_manual_and_auto_coexist_selects_manual(self):
        """Design doc 5.4: manual+auto coexistence selects manual only."""
        result = _classify_captions(
            manual_subs={"en": [{"ext": "vtt"}]},
            auto_subs={"en": [{"ext": "vtt"}]},
        )
        assert result.caption_type == "manual"

    def test_auto_only_raises(self):
        with pytest.raises(AutoCaptionOnlyError, match="auto-generated"):
            _classify_captions(
                manual_subs={"fr": []},
                auto_subs={"en": [{"ext": "vtt"}]},
            )

    def test_no_captions_raises(self):
        with pytest.raises(CaptionNotFoundError, match="No English captions"):
            _classify_captions(manual_subs={}, auto_subs={})

    def test_non_english_manual_with_auto_en_raises(self):
        """Manual exists but not English; auto English exists -> auto-only error."""
        with pytest.raises(AutoCaptionOnlyError):
            _classify_captions(
                manual_subs={"ko": [], "ja": []},
                auto_subs={"en-US": []},
            )

    def test_non_english_only_raises_not_found(self):
        with pytest.raises(CaptionNotFoundError):
            _classify_captions(
                manual_subs={"ko": []},
                auto_subs={"fr": []},
            )


# ---------------------------------------------------------------------------
# fetch_metadata (mocked yt-dlp)
# ---------------------------------------------------------------------------

class TestFetchMetadata:
    """Tests for video metadata fetching with mocked yt-dlp."""

    def _mock_extract_info(self, info_dict: dict):
        """Create a mock YoutubeDL context manager returning info_dict."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info_dict
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        return mock_ydl

    @patch("yt_excel.youtube.yt_dlp.YoutubeDL")
    def test_fetch_metadata_success(self, mock_ydl_cls):
        info = {
            "title": "How DNA Works",
            "channel": "TED-Ed",
            "duration": 292,
        }
        mock_ydl_cls.return_value = self._mock_extract_info(info)

        meta = fetch_metadata("dQw4w9WgXcQ")
        assert meta.video_id == "dQw4w9WgXcQ"
        assert meta.title == "How DNA Works"
        assert meta.channel == "TED-Ed"
        assert meta.duration == "00:04:52"

    @patch("yt_excel.youtube.yt_dlp.YoutubeDL")
    def test_fetch_metadata_uses_uploader_fallback(self, mock_ydl_cls):
        info = {
            "title": "Test",
            "uploader": "FallbackChannel",
            "duration": 60,
        }
        mock_ydl_cls.return_value = self._mock_extract_info(info)

        meta = fetch_metadata("dQw4w9WgXcQ")
        assert meta.channel == "FallbackChannel"

    @patch("yt_excel.youtube.yt_dlp.YoutubeDL")
    def test_fetch_metadata_missing_fields_uses_defaults(self, mock_ydl_cls):
        info = {}
        mock_ydl_cls.return_value = self._mock_extract_info(info)

        meta = fetch_metadata("dQw4w9WgXcQ")
        assert meta.title == "Unknown"
        assert meta.channel == "Unknown"
        assert meta.duration == "00:00:00"


# ---------------------------------------------------------------------------
# download_captions (mocked yt-dlp)
# ---------------------------------------------------------------------------

class TestDownloadCaptions:
    """Tests for VTT caption downloading with mocked yt-dlp."""

    @patch("yt_excel.youtube.yt_dlp.YoutubeDL")
    def test_download_via_url(self, mock_ydl_cls):
        """When yt-dlp provides a subtitle URL, download via urlopen."""
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello"

        mock_response = MagicMock()
        mock_response.read.return_value = vtt_content.encode("utf-8")

        mock_ydl_extract = MagicMock()
        mock_ydl_extract.extract_info.return_value = {
            "requested_subtitles": {
                "en": {"url": "https://example.com/sub.vtt", "ext": "vtt"}
            }
        }
        mock_ydl_extract.__enter__ = MagicMock(return_value=mock_ydl_extract)
        mock_ydl_extract.__exit__ = MagicMock(return_value=False)

        mock_ydl_download = MagicMock()
        mock_ydl_download.urlopen.return_value = mock_response
        mock_ydl_download.__enter__ = MagicMock(return_value=mock_ydl_download)
        mock_ydl_download.__exit__ = MagicMock(return_value=False)

        # First call = extract_info, second call = urlopen
        mock_ydl_cls.side_effect = [mock_ydl_extract, mock_ydl_download]

        result = download_captions("dQw4w9WgXcQ", "en")
        assert result == vtt_content

    @patch("yt_excel.youtube.yt_dlp.YoutubeDL")
    def test_download_via_inline_data(self, mock_ydl_cls):
        """When yt-dlp provides inline subtitle data."""
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nInline"

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "requested_subtitles": {
                "en": {"data": vtt_content, "ext": "vtt"}
            }
        }
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_cls.return_value = mock_ydl

        result = download_captions("dQw4w9WgXcQ", "en")
        assert result == vtt_content

    @patch("yt_excel.youtube.yt_dlp.YoutubeDL")
    def test_download_missing_track_raises(self, mock_ydl_cls):
        """Requested language code not in subtitles raises CaptionNotFoundError."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "requested_subtitles": {}
        }
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_cls.return_value = mock_ydl

        with pytest.raises(CaptionNotFoundError, match="not found"):
            download_captions("dQw4w9WgXcQ", "en")

    @patch("yt_excel.youtube.yt_dlp.YoutubeDL")
    def test_download_no_url_no_data_raises(self, mock_ydl_cls):
        """Track exists but has neither url nor data."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "requested_subtitles": {
                "en": {"ext": "vtt"}
            }
        }
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl_cls.return_value = mock_ydl

        with pytest.raises(CaptionNotFoundError, match="No downloadable content"):
            download_captions("dQw4w9WgXcQ", "en")
