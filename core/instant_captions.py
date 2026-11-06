import re
from typing import Optional, Dict, Any, List


def extract_youtube_id(url: str) -> Optional[str]:
    """Extracts 11-character YouTube video ID from various URL formats."""
    if not url or not isinstance(url, str):
        return None
    patterns = [
        r'(?:v=|\/shorts\/|\/embed\/|youtu\.be\/|\/v\/)([a-zA-Z0-9_-]{11})',
        r'^[a-zA-Z0-9_-]{11}$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return None


def fetch_instant_youtube_transcript(url: str, preferred_lang: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches official or auto-generated YouTube captions in 1-2 seconds with ZERO media download.
    Returns structured transcript dict or None if not available.
    """
    vid = extract_youtube_id(url)
    if not vid:
        return None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript_list = api.list(vid)

        target_transcript = None

        # 1. Try matching preferred language if specified
        if preferred_lang and preferred_lang != "auto":
            for t in transcript_list:
                if t.language_code.lower().startswith(preferred_lang.lower()):
                    target_transcript = t
                    break

        # 2. Try English
        if not target_transcript:
            for t in transcript_list:
                if t.language_code.lower().startswith("en"):
                    target_transcript = t
                    break

        # 3. Fallback to first available language
        if not target_transcript:
            for t in transcript_list:
                target_transcript = t
                break

        if not target_transcript:
            return None

        data = target_transcript.fetch()
        segments = []
        full_text_parts = []

        for i, item in enumerate(data):
            text = item.text.strip().replace("\n", " ")
            if not text:
                continue
            start = round(float(item.start), 2)
            end = round(start + float(item.duration), 2)
            segments.append({
                "id": i,
                "start": start,
                "end": end,
                "text": text,
                "words": []
            })
            full_text_parts.append(text)

        total_duration = segments[-1]["end"] if segments else 0.0

        return {
            "type": "instant_youtube",
            "video_id": vid,
            "language": target_transcript.language_code,
            "segments": segments,
            "full_text": " ".join(full_text_parts),
            "duration": total_duration,
            "instant": True
        }
    except Exception as e:
        # Transcript unavailable or disabled on YouTube
        return None

