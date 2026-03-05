"""YouTube URL parsing, metadata fetching, and caption downloading."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import yt_dlp

from yt_excel.retry import RetryExhaustedError, with_retry


# YouTube video ID is always 11 characters: alphanumeric, dash, underscore
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Accepted YouTube hostnames
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def extract_video_id(url: str) -> str:
    """Extract the 11-character video ID from a YouTube URL.

    Supports standard, shortened, and embed URL formats:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://www.youtube.com/v/VIDEO_ID

    Args:
        url: A YouTube video URL string.

    Returns:
        The 11-character video ID.

    Raises:
        ValueError: If the URL is not a valid YouTube URL or video ID
            cannot be extracted.
    """
    url = url.strip()
    if not url:
        raise ValueError("URL is empty.")

    parsed = urlparse(url)

    # Ensure scheme is present for proper parsing
    if not parsed.scheme:
        parsed = urlparse("https://" + url)

    hostname = (parsed.hostname or "").lower()
    if hostname not in _YOUTUBE_HOSTS:
        raise ValueError(
            f"Not a valid YouTube URL: {url}\n"
            "Expected a URL from youtube.com or youtu.be."
        )

    video_id: str | None = None

    # youtu.be/VIDEO_ID
    if hostname in ("youtu.be", "www.youtu.be"):
        path = parsed.path.lstrip("/")
        if path:
            video_id = path.split("/")[0]
    else:
        # /watch?v=VIDEO_ID
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            v_values = qs.get("v")
            if v_values:
                video_id = v_values[0]
        # /embed/VIDEO_ID or /v/VIDEO_ID
        elif parsed.path.startswith(("/embed/", "/v/")):
            parts = parsed.path.split("/")
            if len(parts) >= 3 and parts[2]:
                video_id = parts[2]

    if not video_id or not _VIDEO_ID_RE.match(video_id):
        raise ValueError(
            f"Could not extract a valid video ID from: {url}\n"
            "Expected a standard YouTube video URL."
        )

    return video_id


class CaptionNotFoundError(Exception):
    """No English captions (manual or auto) found for the video."""


class AutoCaptionOnlyError(Exception):
    """Only auto-generated English captions are available."""


@dataclass
class VideoMeta:
    """Video metadata fetched from YouTube."""

    video_id: str
    title: str
    channel: str
    duration: str  # "HH:MM:SS"


@dataclass
class CaptionInfo:
    """Information about available English captions."""

    lang_code: str        # e.g. "en", "en-US"
    caption_type: str     # "manual"
    available_codes: list[str]  # all matching en codes found in subtitles


# Retryable network errors from yt-dlp
_RETRYABLE_ERRORS = (
    yt_dlp.utils.DownloadError,
    yt_dlp.utils.ExtractorError,
    ConnectionError,
    TimeoutError,
    OSError,
)


def _format_duration(seconds: int | float) -> str:
    """Convert seconds to HH:MM:SS format."""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@with_retry(max_retries=3, retryable=_RETRYABLE_ERRORS)
def fetch_metadata(video_id: str) -> VideoMeta:
    """Fetch video metadata (title, channel, duration) via yt-dlp.

    Args:
        video_id: 11-character YouTube video ID.

    Returns:
        VideoMeta with title, channel name, and duration.

    Raises:
        RetryExhaustedError: If all retry attempts fail.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise yt_dlp.utils.DownloadError(f"Failed to fetch info for {video_id}")

    title = info.get("title", "Unknown")
    channel = info.get("channel", info.get("uploader", "Unknown"))
    duration_sec = info.get("duration", 0)

    return VideoMeta(
        video_id=video_id,
        title=title,
        channel=channel,
        duration=_format_duration(duration_sec),
    )


def _find_english_code(lang_dict: dict[str, list[dict]]) -> str | None:
    """Find the best English language code from a subtitle dictionary.

    Priority: 'en' exact match first, then first 'en-*' variant.

    Args:
        lang_dict: yt-dlp subtitle/automatic_captions dict mapping
            language codes to format lists.

    Returns:
        The best English language code, or None if not found.
    """
    if "en" in lang_dict:
        return "en"

    for code in sorted(lang_dict.keys()):
        if code.startswith("en-"):
            return code

    return None


@with_retry(max_retries=3, retryable=_RETRYABLE_ERRORS)
def list_captions(video_id: str) -> CaptionInfo:
    """List available English captions and determine their type.

    Checks manual subtitles first, then auto-generated.
    Only manual captions are accepted for processing.

    Args:
        video_id: 11-character YouTube video ID.

    Returns:
        CaptionInfo with the selected language code and type.

    Raises:
        CaptionNotFoundError: No English captions at all.
        AutoCaptionOnlyError: Only auto-generated English captions exist.
        RetryExhaustedError: Network failures exhausted all retries.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise yt_dlp.utils.DownloadError(f"Failed to fetch info for {video_id}")

    manual_subs: dict = info.get("subtitles") or {}
    auto_subs: dict = info.get("automatic_captions") or {}

    # Check manual subtitles first
    manual_en = _find_english_code(manual_subs)
    if manual_en is not None:
        all_en_codes = [c for c in manual_subs if c == "en" or c.startswith("en-")]
        return CaptionInfo(
            lang_code=manual_en,
            caption_type="manual",
            available_codes=all_en_codes,
        )

    # Check auto-generated captions
    auto_en = _find_english_code(auto_subs)
    if auto_en is not None:
        raise AutoCaptionOnlyError(
            "This video only has auto-generated English captions.\n"
            "Auto-generated captions are excluded by policy due to low accuracy.\n"
            "\n"
            "Possible actions:\n"
            "  1. Choose a different video with manual captions\n"
            "  2. Manually upload captions to the video and retry\n"
            "\n"
            "Aborting extraction."
        )

    # No English captions at all
    raise CaptionNotFoundError(
        "No English captions found for this video.\n"
        "Neither manual nor auto-generated English captions are available.\n"
        "\n"
        "Aborting extraction."
    )
