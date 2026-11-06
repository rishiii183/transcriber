import os
import re
import shutil
import uuid
from typing import Optional, Callable, Dict, Any
from urllib.parse import urlparse
import yt_dlp

# Ensure static_ffmpeg is loaded if available
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

# Ensure .venv/Scripts is in PATH if ffmpeg is there
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "Scripts"))
if os.path.isdir(scripts_dir) and scripts_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = scripts_dir + os.pathsep + os.environ.get("PATH", "")


def is_local_path(path_str: str) -> bool:
    """Checks if a string represents a local file path."""
    if not path_str or not isinstance(path_str, str):
        return False
    clean = path_str.strip()
    if re.match(r'^[a-zA-Z]:[\\/]', clean):
        return True
    if clean.startswith((".\\", "./", "..\\", "../", "file://")):
        return True
    ext = os.path.splitext(clean)[1].lower()
    if ext in [".mp4", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm", ".mov", ".mkv"]:
        return True
    return False


def detect_platform(url: str) -> Dict[str, str]:
    """Detects platform from URL and returns platform id, name, and badge styling."""
    if not url or not isinstance(url, str):
        return {"id": "unknown", "name": "Unknown", "icon": "globe", "color": "#64748b"}

    clean_url = url.strip().lower()

    if os.path.exists(url) or is_local_path(url):
        return {"id": "local", "name": "Local File", "icon": "file-audio", "color": "#10b981"}

    if any(k in clean_url for k in ["youtube.com", "youtu.be"]):
        is_short = "/shorts/" in clean_url
        return {
            "id": "youtube",
            "name": "YouTube Shorts" if is_short else "YouTube",
            "icon": "youtube",
            "color": "#ef4444"
        }
    if any(k in clean_url for k in ["twitter.com", "x.com"]):
        return {"id": "twitter", "name": "X / Twitter", "icon": "twitter", "color": "#0ea5e9"}
    if "instagram.com" in clean_url:
        is_reel = "/reel/" in clean_url or "/reels/" in clean_url
        return {
            "id": "instagram",
            "name": "Instagram Reel" if is_reel else "Instagram",
            "icon": "instagram",
            "color": "#ec4899"
        }
    if "linkedin.com" in clean_url:
        return {"id": "linkedin", "name": "LinkedIn", "icon": "linkedin", "color": "#0a66c2"}
    if "tiktok.com" in clean_url:
        return {"id": "tiktok", "name": "TikTok", "icon": "video", "color": "#06b6d4"}
    if "facebook.com" in clean_url or "fb.watch" in clean_url:
        return {"id": "facebook", "name": "Facebook", "icon": "facebook", "color": "#1877f2"}
    if "reddit.com" in clean_url or "v.redd.it" in clean_url:
        return {"id": "reddit", "name": "Reddit", "icon": "message-square", "color": "#ff4500"}

    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "") if parsed.netloc else "Web Audio"
    return {"id": "web", "name": domain.capitalize(), "icon": "globe", "color": "#8b5cf6"}


class MediaDownloader:
    """Universal downloader and audio extractor powered by yt-dlp."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "cache")
        )
        os.makedirs(self.cache_dir, exist_ok=True)

    def extract_audio(
        self,
        url_or_path: str,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cookie_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extracts audio from a social media link or local file.
        Returns dict with audio_path, title, duration, platform info, and metadata.
        """
        job_id = job_id or str(uuid.uuid4())
        job_dir = os.path.join(self.cache_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)

        platform_info = detect_platform(url_or_path)

        # Case 1: Local file input or path
        if os.path.exists(url_or_path):
            return self._process_local_file(url_or_path, job_id, job_dir, platform_info, progress_callback)
        elif is_local_path(url_or_path):
            raise FileNotFoundError(f"Local media file not found: '{url_or_path}'. Please check that the file path is correct.")

        # Check for placeholder URLs
        if "..." in url_or_path:
            raise ValueError(f"Please replace the placeholder URL '{url_or_path}' with a real YouTube, X/Twitter, Instagram, or LinkedIn link.")

        # Case 2: Social media / web link
        return self._download_and_extract(url_or_path, job_id, job_dir, platform_info, progress_callback, cookie_file)

    def _process_local_file(
        self,
        local_path: str,
        job_id: str,
        job_dir: str,
        platform_info: Dict[str, str],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        filename = os.path.basename(local_path)
        base_name, ext = os.path.splitext(filename)
        out_wav = os.path.join(job_dir, "audio.wav")

        if progress_callback:
            progress_callback({
                "status": "extracting",
                "stage": "extract_audio",
                "percent": 30,
                "message": "Extracting audio from local file..."
            })

        # Copy or convert to audio.wav via ffmpeg if available or PyAV
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            import subprocess
            cmd = [
                ffmpeg_bin, "-y", "-i", local_path,
                "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                out_wav
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            target_path = out_wav
        else:
            # Fallback: copy file directly, faster-whisper/PyAV will decode it natively
            target_path = os.path.join(job_dir, filename)
            shutil.copy2(local_path, target_path)

        if progress_callback:
            progress_callback({
                "status": "ready",
                "stage": "ready_to_transcribe",
                "percent": 100,
                "message": "Audio extracted successfully."
            })

        return {
            "job_id": job_id,
            "title": base_name,
            "duration": None,
            "audio_path": target_path,
            "platform": platform_info,
            "is_local": True,
            "source_url": local_path
        }

    def _download_and_extract(
        self,
        url: str,
        job_id: str,
        job_dir: str,
        platform_info: Dict[str, str],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cookie_file: Optional[str] = None
    ) -> Dict[str, Any]:
        output_template = os.path.join(job_dir, "%(id)s.%(ext)s")

        def _yt_dlp_hook(d):
            if not progress_callback:
                return
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                percent = round((downloaded / total * 100), 1) if total > 0 else 0
                speed = d.get("speed")
                speed_str = f"{round(speed / 1024 / 1024, 1)} MB/s" if speed else ""
                eta = d.get("eta")
                eta_str = f"{eta}s" if eta else ""
                progress_callback({
                    "status": "downloading",
                    "stage": "download_media",
                    "percent": min(percent, 95),
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "speed": speed_str,
                    "eta": eta_str,
                    "message": f"Downloading {platform_info['name']} media... {percent}%"
                })
            elif status == "finished":
                progress_callback({
                    "status": "extracting",
                    "stage": "extract_audio",
                    "percent": 98,
                    "message": "Extracting high-fidelity audio stream..."
                })

        ydl_opts = {
            "format": "ba[abr<=96]/worstaudio/ba/b",
            "outtmpl": output_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "96",
            }],
            "postprocessor_args": [
                "-ar", "16000",
                "-ac", "1"
            ],
            "progress_hooks": [_yt_dlp_hook],
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "nocheckcertificate": True,
            "retries": 3,
            "socket_timeout": 30,
        }

        if cookie_file and os.path.exists(cookie_file):
            ydl_opts["cookiefile"] = cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if progress_callback:
                progress_callback({
                    "status": "connecting",
                    "stage": "init",
                    "percent": 5,
                    "message": f"Connecting to {platform_info['name']}..."
                })

            info = ydl.extract_info(url, download=True)

        # Locate extracted audio file
        wav_files = [
            os.path.join(job_dir, f) for f in os.listdir(job_dir)
            if f.lower().endswith((".wav", ".mp3", ".m4a", ".opus", ".aac"))
        ]

        if not wav_files:
            raise FileNotFoundError(f"Failed to extract audio for {url}. No audio file found in {job_dir}")

        audio_path = wav_files[0]
        title = info.get("title") or f"{platform_info['name']} Media"
        duration = info.get("duration")
        thumbnail = info.get("thumbnail")
        uploader = info.get("uploader") or info.get("channel") or info.get("artist")

        if progress_callback:
            progress_callback({
                "status": "ready",
                "stage": "ready_to_transcribe",
                "percent": 100,
                "message": "Media download & extraction complete."
            })

        return {
            "job_id": job_id,
            "title": title,
            "duration": duration,
            "uploader": uploader,
            "thumbnail": thumbnail,
            "audio_path": audio_path,
            "platform": platform_info,
            "is_local": False,
            "source_url": url
        }

