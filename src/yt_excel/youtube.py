"""YouTube URL parsing and video_id extraction."""

import re
from urllib.parse import parse_qs, urlparse


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
