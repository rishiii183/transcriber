import os
import sys
import json
import uuid
import asyncio
import threading
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Query, Response
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.downloader import MediaDownloader, detect_platform
from core.transcriber import LocalWhisperTranscriber, SUPPORTED_MODELS
from core.instant_captions import fetch_instant_youtube_transcript
from core import exporter

app = FastAPI(title="Universal Social & Offline Transcriber", version="1.0.0")

# Enable CORS for local development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

downloader = MediaDownloader()
transcriber = LocalWhisperTranscriber()

# In-memory jobs registry
JOBS: Dict[str, Dict[str, Any]] = {}
JOB_QUEUES: Dict[str, asyncio.Queue] = {}


class TranscribeUrlRequest(BaseModel):
    url: str
    model: str = "small"
    language: Optional[str] = "auto"
    vad_filter: bool = True
    word_timestamps: bool = True


def _emit_job_event(job_id: str, event_data: Dict[str, Any]):
    """Sends event to the job's queue for real-time SSE streaming."""
    q = JOB_QUEUES.get(job_id)
    if q:
        try:
            loop = q._loop
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(q.put(event_data), loop)
        except Exception as e:
            print(f"Error emitting event for {job_id}: {e}")


def _worker_process_job(job_id: str, input_source: str, is_local_file: bool, options: Dict[str, Any]):
    """Background worker that handles downloading/extracting and offline transcription."""
    job = JOBS.get(job_id)
    if not job:
        return

    try:
        job["status"] = "processing"

        # Check for Instant YouTube Captions (0 MB media download)
        is_yt = detect_platform(input_source).get("id") == "youtube"
        if is_yt and not is_local_file:
            _emit_job_event(job_id, {
                "type": "stage",
                "stage": "instant_check",
                "message": "Checking for instant YouTube captions (0 MB download)..."
            })
            instant_res = fetch_instant_youtube_transcript(input_source, options.get("language"))
            if instant_res:
                _emit_job_event(job_id, {
                    "type": "status",
                    "stage": "instant",
                    "message": f"Instant captions found ({len(instant_res['segments'])} segments)! Zero media download."
                })
                # Stream segments smoothly to the UI
                for seg in instant_res["segments"]:
                    _emit_job_event(job_id, {
                        "type": "segment",
                        "segment": seg,
                        "progress_percent": 100
                    })

                job["status"] = "completed"
                job["result"] = {
                    "job_id": job_id,
                    "title": f"YouTube Transcript ({instant_res['video_id']})",
                    "platform": {"id": "youtube", "name": "YouTube (Instant Captions)", "color": "#ef4444"},
                    "duration": instant_res["duration"],
                    "full_text": instant_res["full_text"],
                    "segments": instant_res["segments"],
                    "language": instant_res["language"],
                    "model": "Instant Captions (0 MB)",
                    "speedup": "Instant",
                    "hardware": {"device": "Cloud Captions", "is_gpu": False}
                }
                _emit_job_event(job_id, {
                    "type": "finished",
                    "job_id": job_id,
                    "result": job["result"]
                })
                return

        # Step 1: Download or extract audio
        _emit_job_event(job_id, {
            "type": "stage",
            "stage": "download",
            "message": "Connecting to source and preparing audio..."
        })

        def download_progress(data):
            _emit_job_event(job_id, {"type": "download_progress", **data})

        media_info = downloader.extract_audio(
            url_or_path=input_source,
            job_id=job_id,
            progress_callback=download_progress
        )

        job["media_info"] = media_info
        job["audio_path"] = media_info["audio_path"]

        _emit_job_event(job_id, {
            "type": "media_ready",
            "title": media_info.get("title"),
            "platform": media_info.get("platform"),
            "uploader": media_info.get("uploader"),
            "duration": media_info.get("duration"),
            "thumbnail": media_info.get("thumbnail"),
            "audio_url": f"/api/audio/{job_id}"
        })

        # Step 2: Offline transcription via Faster-Whisper
        model_size = options.get("model", "small")
        language = options.get("language")
        vad_filter = options.get("vad_filter", True)
        word_timestamps = options.get("word_timestamps", True)

        segments = []
        full_text = ""

        stream_gen = transcriber.transcribe_stream(
            audio_path=media_info["audio_path"],
            model_size=model_size,
            language=language,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps
        )

        for event in stream_gen:
            event_type = event.get("type")
            if event_type == "segment":
                segments.append(event["segment"])
            elif event_type == "complete":
                full_text = event.get("full_text", "")

            _emit_job_event(job_id, event)

        # Step 3: Complete & save job result
        job["status"] = "completed"
        job["result"] = {
            "job_id": job_id,
            "title": media_info.get("title"),
            "platform": media_info.get("platform"),
            "duration": media_info.get("duration"),
            "full_text": full_text,
            "segments": segments,
            "language": options.get("language") or "auto",
            "model": model_size,
            "hardware": transcriber.get_hardware_info()
        }

        _emit_job_event(job_id, {
            "type": "finished",
            "job_id": job_id,
            "result": job["result"]
        })

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        print(f"[Worker Error] {exc}")
        _emit_job_event(job_id, {
            "type": "error",
            "message": str(exc)
        })
    finally:
        _emit_job_event(job_id, {"type": "close"})


@app.get("/api/detect")
def detect_url(url: str = Query(...)):
    """Auto-detects platform metadata from input URL for instant UI preview."""
    info = detect_platform(url)
    return info


@app.get("/api/models")
def get_models():
    """Lists available offline models, local cache status, and GPU info."""
    return {
        "hardware": transcriber.get_hardware_info(),
        "models": transcriber.list_models()
    }


@app.post("/api/models/preload")
def preload_model(model: str = Query(..., description="Model size to cache offline"), background_tasks: BackgroundTasks = None):
    """Pre-downloads model weights so system is 100% prepared for full offline use."""
    if model not in SUPPORTED_MODELS:
        raise HTTPException(status_code=400, detail="Invalid model identifier")

    def _preload():
        try:
            transcriber.load_model(model)
        except Exception as e:
            print(f"Failed to preload model {model}: {e}")

    background_tasks.add_task(_preload)
    return {"status": "preloading_started", "model": model}


@app.post("/api/transcribe")
async def transcribe_url(request: TranscribeUrlRequest):
    """Starts transcription from a social media or direct web URL."""
    job_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    JOB_QUEUES[job_id] = asyncio.Queue()

    JOBS[job_id] = {
        "id": job_id,
        "input_source": request.url,
        "is_local": False,
        "status": "queued",
        "created_at": asyncio.get_event_loop().time(),
        "options": request.model_dump()
    }

    thread = threading.Thread(
        target=_worker_process_job,
        args=(job_id, request.url, False, request.model_dump()),
        daemon=True
    )
    thread.start()

    return {"job_id": job_id, "status": "queued"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    model: str = Form("small"),
    language: str = Form("auto"),
    vad_filter: bool = Form(True),
    word_timestamps: bool = Form(True)
):
    """Handles direct audio or video file uploads for 100% offline usage."""
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(downloader.cache_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    dest_path = os.path.join(job_dir, file.filename)
    with open(dest_path, "wb") as f:
        content = await file.read()
        f.write(content)

    JOB_QUEUES[job_id] = asyncio.Queue()
    options = {
        "model": model,
        "language": language,
        "vad_filter": vad_filter,
        "word_timestamps": word_timestamps
    }

    JOBS[job_id] = {
        "id": job_id,
        "input_source": dest_path,
        "is_local": True,
        "status": "queued",
        "options": options
    }

    thread = threading.Thread(
        target=_worker_process_job,
        args=(job_id, dest_path, True, options),
        daemon=True
    )
    thread.start()

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/stream/{job_id}")
async def stream_job(job_id: str):
    """Server-Sent Events (SSE) streaming real-time progress and transcribed chunks."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    q = JOB_QUEUES.get(job_id)
    if not q:
        raise HTTPException(status_code=404, detail="Queue not available")

    async def event_generator():
        try:
            while True:
                event = await q.get()
                if event.get("type") == "close":
                    break
                data_str = json.dumps(event)
                yield f"data: {data_str}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/audio/{job_id}")
def get_audio(job_id: str):
    """Serves extracted audio stream with range support for the HTML5 audio player."""
    job = JOBS.get(job_id)
    if not job or "audio_path" not in job:
        raise HTTPException(status_code=404, detail="Audio file not ready or not found")

    audio_path = job["audio_path"]
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file missing on disk")

    ext = os.path.splitext(audio_path)[1].lower()
    media_type = "audio/wav" if ext == ".wav" else "audio/mpeg" if ext == ".mp3" else "application/octet-stream"

    return FileResponse(audio_path, media_type=media_type)


@app.get("/api/export/{job_id}")
def export_transcript(job_id: str, format: str = Query("txt")):
    """Generates and downloads the transcript in TXT, SRT, VTT, JSON, or Markdown."""
    job = JOBS.get(job_id)
    if not job or "result" not in job:
        raise HTTPException(status_code=404, detail="Transcript result not found")

    result = job["result"]
    title = (result.get("title") or "transcript").replace(" ", "_")
    # Sanitize title for filename
    clean_title = "".join(c for c in title if c.isalnum() or c in ("-", "_")).rstrip() or "transcript"
    fmt = format.lower().strip()

    if fmt == "txt":
        content = exporter.to_txt(result.get("segments", []), result.get("full_text", ""))
        media_type = "text/plain; charset=utf-8"
        filename = f"{clean_title}.txt"
    elif fmt == "srt":
        content = exporter.to_srt(result.get("segments", []))
        media_type = "application/x-subrip; charset=utf-8"
        filename = f"{clean_title}.srt"
    elif fmt == "vtt":
        content = exporter.to_vtt(result.get("segments", []))
        media_type = "text/vtt; charset=utf-8"
        filename = f"{clean_title}.vtt"
    elif fmt == "json":
        content = exporter.to_json(result)
        media_type = "application/json; charset=utf-8"
        filename = f"{clean_title}.json"
    elif fmt in ("md", "markdown"):
        content = exporter.to_markdown(result)
        media_type = "text/markdown; charset=utf-8"
        filename = f"{clean_title}.md"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'. Use txt, srt, vtt, json, or md.")

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# Serve frontend static files
web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.isdir(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=False)

