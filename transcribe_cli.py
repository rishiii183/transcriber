#!/usr/bin/env python3
"""
Command Line Interface for the Universal Social Media & Offline Transcriber.
Usage:
    python transcribe_cli.py "https://www.youtube.com/watch?v=..." --model small --format txt,srt
    python transcribe_cli.py "C:\\path\\to\\video.mp4" --output ./transcript.txt
"""

import os
import sys
import io

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
from core.downloader import MediaDownloader, detect_platform
from core.transcriber import LocalWhisperTranscriber
from core.instant_captions import fetch_instant_youtube_transcript
from core import exporter


def main():
    parser = argparse.ArgumentParser(
        description="Universal Social Media & 100% Offline Transcriber"
    )
    parser.add_argument("source", help="URL (YouTube, X, Instagram, LinkedIn, etc.) or local media file path")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"], help="Whisper model size (default: small)")
    parser.add_argument("--language", default=None, help="Language code (e.g. en, es, fr, hi) or omit for auto-detect")
    parser.add_argument("--format", default="txt", help="Comma-separated export formats: txt, srt, vtt, json, md, or all")
    parser.add_argument("--output-dir", default="./output", help="Directory where exported transcripts will be saved")
    parser.add_argument("--no-vad", action="store_true", help="Disable Voice Activity Detection filter")

    args = parser.parse_args()

    print("=" * 60)
    print(" 🎙️  Universal Social & Offline Transcriber (CLI)")
    print("=" * 60)

    platform_info = detect_platform(args.source)
    print(f"[1/3] Source detected: {platform_info['name']}")

    downloader = MediaDownloader()
    transcriber = LocalWhisperTranscriber()
    hw_info = transcriber.get_hardware_info()
    print(f"      Engine Hardware: {'NVIDIA GPU (CUDA)' if hw_info['is_gpu'] else 'CPU Multi-threaded'}")

    # Instant check for YouTube links
    if platform_info["id"] == "youtube":
        print("[2/3] Checking for instant YouTube captions (0 MB download)...")
        instant_res = fetch_instant_youtube_transcript(args.source, args.language)
        if instant_res:
            print(f"      ⚡ Found instant YouTube captions ({len(instant_res['segments'])} segments) in {instant_res['language'].upper()}!")
            print("      Streaming recognition output:\n")
            for seg in instant_res["segments"][:15]:
                ts = exporter.format_friendly_time(seg["start"])
                print(f"      [{ts}] {seg['text']}")
            if len(instant_res["segments"]) > 15:
                print(f"      ... and {len(instant_res['segments']) - 15} more segments.")

            print(f"\n      Instant extraction completed! (0 MB media downloaded).")

            # Save exports
            os.makedirs(args.output_dir, exist_ok=True)
            clean_title = f"youtube_{instant_res['video_id']}"
            result_data = {
                "title": f"YouTube Transcript ({instant_res['video_id']})",
                "platform": platform_info,
                "duration": instant_res["duration"],
                "full_text": instant_res["full_text"],
                "segments": instant_res["segments"],
                "language": instant_res["language"],
                "model": "Instant YouTube Captions"
            }
            formats = [f.strip().lower() for f in args.format.split(",")]
            if "all" in formats:
                formats = ["txt", "srt", "vtt", "json", "md"]

            print("\nSaved Transcripts:")
            for fmt in formats:
                out_path = os.path.join(args.output_dir, f"{clean_title}.{fmt}")
                if fmt == "txt":
                    content = exporter.to_txt(instant_res["segments"], instant_res["full_text"])
                elif fmt == "srt":
                    content = exporter.to_srt(instant_res["segments"])
                elif fmt == "vtt":
                    content = exporter.to_vtt(instant_res["segments"])
                elif fmt == "json":
                    content = exporter.to_json(result_data)
                elif fmt in ("md", "markdown"):
                    content = exporter.to_markdown(result_data)
                else:
                    continue

                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  ✓ {out_path}")

            print("\nDone! 🎉")
            return

    # Extract / Download audio
    print(f"[2/3] Extracting audio stream from {platform_info['name']}...")
    try:
        media_info = downloader.extract_audio(args.source)
        audio_path = media_info["audio_path"]
        title = media_info.get("title") or "media_transcript"
        print(f"      Audio ready: {os.path.basename(audio_path)}")
        if media_info.get("duration"):
            print(f"      Duration: {exporter.format_friendly_time(media_info['duration'])}")
    except Exception as e:
        print(f"\n❌ Error downloading/extracting media: {e}", file=sys.stderr)
        sys.exit(1)

    # Transcribe
    print(f"[3/3] Transcribing with local '{args.model}' model (100% Offline)...")
    try:
        segments = []
        full_text = ""
        stream = transcriber.transcribe_stream(
            audio_path=audio_path,
            model_size=args.model,
            language=args.language,
            vad_filter=not args.no_vad
        )

        for event in stream:
            ev_type = event.get("type")
            if ev_type == "info":
                lang = event.get("language", "unknown").upper()
                print(f"      Detected Language: {lang} (Confidence: {event.get('language_probability', 1.0) * 100:.1f}%)")
                print("      Streaming recognition output:\n")
            elif ev_type == "segment":
                seg = event["segment"]
                segments.append(seg)
                ts = exporter.format_friendly_time(seg["start"])
                print(f"      [{ts}] {seg['text']}")
            elif ev_type == "complete":
                full_text = event.get("full_text", "")
                elapsed = event.get("elapsed_seconds", 0)
                speedup = event.get("speedup")
                speed_str = f"{speedup}x" if speedup else "Instant"
                print(f"\n      Transcription completed in {elapsed}s ({speed_str} real-time speed).")

    except Exception as e:
        print(f"\n❌ Error during offline transcription: {e}", file=sys.stderr)
        sys.exit(1)

    # Export
    os.makedirs(args.output_dir, exist_ok=True)
    clean_title = "".join(c for c in title if c.isalnum() or c in ("-", "_")).rstrip() or "transcript"
    result_data = {
        "title": title,
        "platform": platform_info,
        "duration": media_info.get("duration"),
        "full_text": full_text,
        "segments": segments,
        "language": args.language or "auto",
        "model": args.model
    }

    formats = [f.strip().lower() for f in args.format.split(",")]
    if "all" in formats:
        formats = ["txt", "srt", "vtt", "json", "md"]

    print("\nSaved Transcripts:")
    for fmt in formats:
        out_path = os.path.join(args.output_dir, f"{clean_title}.{fmt}")
        if fmt == "txt":
            content = exporter.to_txt(segments, full_text)
        elif fmt == "srt":
            content = exporter.to_srt(segments)
        elif fmt == "vtt":
            content = exporter.to_vtt(segments)
        elif fmt == "json":
            content = exporter.to_json(result_data)
        elif fmt in ("md", "markdown"):
            content = exporter.to_markdown(result_data)
        else:
            continue

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✓ {out_path}")

    print("\nDone! 🎉")


if __name__ == "__main__":
    main()
