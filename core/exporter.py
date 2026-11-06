import json
from typing import List, Dict, Any, Optional


def format_timestamp(seconds: float, srt_format: bool = True) -> str:
    """Converts seconds (e.g. 75.32) into HH:MM:SS,mmm (SRT) or HH:MM:SS.mmm (VTT)."""
    if seconds is None or seconds < 0:
        seconds = 0.0

    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))

    if millis >= 1000:
        millis = 999

    delimiter = "," if srt_format else "."
    return f"{hrs:02d}:{mins:02d}:{secs:02d}{delimiter}{millis:03d}"


def format_friendly_time(seconds: float) -> str:
    """Formats seconds into human friendly MM:SS or HH:MM:SS."""
    if seconds is None:
        return "00:00"
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def to_txt(segments: List[Dict[str, Any]], full_text: Optional[str] = None, include_timestamps: bool = False) -> str:
    """Exports transcript as plain text, optionally with timestamps."""
    if not include_timestamps:
        if full_text:
            return full_text.strip()
        return " ".join(s.get("text", "").strip() for s in segments if s.get("text")).strip()

    lines = []
    for s in segments:
        text = s.get("text", "").strip()
        if not text:
            continue
        start_str = format_friendly_time(s.get("start", 0))
        lines.append(f"[{start_str}] {text}")
    return "\n".join(lines)


def to_srt(segments: List[Dict[str, Any]]) -> str:
    """Exports segments to standard SubRip (.srt) subtitle format."""
    entries = []
    idx = 1
    for s in segments:
        text = s.get("text", "").strip()
        if not text:
            continue
        start_ts = format_timestamp(s.get("start", 0.0), srt_format=True)
        end_ts = format_timestamp(s.get("end", 0.0), srt_format=True)
        entries.append(f"{idx}\n{start_ts} --> {end_ts}\n{text}\n")
        idx += 1
    return "\n".join(entries)


def to_vtt(segments: List[Dict[str, Any]]) -> str:
    """Exports segments to WebVTT (.vtt) caption format."""
    lines = ["WEBVTT\n"]
    for s in segments:
        text = s.get("text", "").strip()
        if not text:
            continue
        start_ts = format_timestamp(s.get("start", 0.0), srt_format=False)
        end_ts = format_timestamp(s.get("end", 0.0), srt_format=False)
        lines.append(f"{start_ts} --> {end_ts}\n{text}\n")
    return "\n".join(lines)


def to_json(data: Dict[str, Any]) -> str:
    """Exports complete metadata and segment breakdown as formatted JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def to_markdown(data: Dict[str, Any]) -> str:
    """Exports structured transcript with metadata header in Markdown."""
    title = data.get("title", "Audio Transcription")
    platform = data.get("platform", {}).get("name", "Media")
    duration = format_friendly_time(data.get("duration", 0))
    language = (data.get("language") or "auto").upper()
    full_text = data.get("full_text", "")
    segments = data.get("segments", [])

    lines = [
        f"# Transcript: {title}",
        "",
        f"- **Source**: {platform}",
        f"- **Duration**: {duration}",
        f"- **Language**: {language}",
        f"- **Engine**: Local Whisper (100% Offline)",
        "",
        "## Summary Transcript",
        "",
        full_text,
        "",
        "## Timestamped Breakdown",
        ""
    ]

    for s in segments:
        text = s.get("text", "").strip()
        if not text:
            continue
        t_start = format_friendly_time(s.get("start", 0))
        t_end = format_friendly_time(s.get("end", 0))
        lines.append(f"- **`{t_start} - {t_end}`**: {text}")

    return "\n".join(lines)

