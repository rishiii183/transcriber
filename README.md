# 🎙️ TranscribeAI - Universal Social & Offline Transcriber

A modern, high-performance media transcriber that extracts audio from **any social media link** (Twitter / X, LinkedIn, Instagram Reels, YouTube Shorts / Videos, TikTok, Reddit, etc.) or local audio/video files, and transcribes spoken dialogue into formatted text and subtitles **100% locally and completely offline**.

---

## ⚡ How It Works

1. **Paste Link or Drop File**: Input any public social media link or drag & drop a local media file (`.mp4`, `.mp3`, `.wav`, `.m4a`, `.mov`, `.webm`).
2. **Audio Extraction**: `yt-dlp` extracts the highest quality audio stream and converts it into 16kHz mono audio.
3. **100% Offline Speech Recognition**: **Faster-Whisper** (CTranslate2) runs the inference locally on your computer with zero external cloud APIs, zero per-minute fees, and 100% privacy.
4. **Interactive Player & Exports**: Listen to the audio with synchronized clickable timestamps (jump to any sentence in the audio), search within the transcript, copy text with one click, or export to `.TXT`, `.SRT`, `.VTT`, `.JSON`, or `.MD`.

---

## 🚀 Quick Start (Native Desktop App)

Simply double-click the **Transcribe** desktop app shortcut:
```text
Transcribe.lnk
```
*(Located right on your Desktop and inside this folder)*

- **Zero Terminal / CMD Windows**: Launches directly as a native standalone desktop application window.
- **No Batch Files**: Uses windowless Python execution (`pythonw.exe`) with PyWebView & Edge Chromium.
- **Standalone Lifecycle**: When you use the app, it runs as a dedicated application window. Closing the window cleanly exits the application.

---

### Command Line Mode (Optional for Developers)
For headless/scripted batch processing in PowerShell:
```bash
.venv\Scripts\python.exe transcribe_cli.py "https://youtu.be/..." --format all
```

---

## 🌐 Supported Platforms

| Platform | Supported Links | Notes |
| :--- | :--- | :--- |
| **YouTube** | Videos, Shorts, Premieres, Live replays | Instant extraction |
| **Instagram** | Reels, Posts, IGTV | Public reels work directly out-of-the-box |
| **Twitter / X** | Posts with video, voice notes, spaces | Full support |
| **LinkedIn** | Video posts, shared media | Public posts work directly |
| **TikTok** | Videos, sounds | Full support |
| **Reddit** | `reddit.com`, `v.redd.it` | Audio + video muxed automatically |
| **Local Files** | `.mp4`, `.mp3`, `.wav`, `.m4a`, `.mov`, `.mkv`, `.webm` | **100% Offline** (zero internet needed) |

---

## 🧠 Available Whisper Models

| Model | Size | Speed | Memory / VRAM | Recommended For |
| :--- | :--- | :--- | :--- | :--- |
| **Tiny** | ~75 MB | 25x Real-time | ~390 MB | Quick testing, low-resource hardware |
| **Base** | ~145 MB | 20x Real-time | ~500 MB | Fast general English transcription |
| **Small** | ~460 MB | 15x Real-time | ~1.0 GB | **Recommended default**: High accuracy + speed |
| **Medium** | ~1.5 GB | 8x Real-time | ~2.6 GB | Challenging accents & technical jargon |
| **Large-v3** | ~3.1 GB | 3x Real-time | ~3.8 GB | Maximum multilingual precision |

> **Note on First Run**: When a model size is selected for the first time, its weights are cached in `./data/models/`. From that moment onward, it works completely offline without ever downloading again.

---

## 📂 Project Architecture

```
all pf transcriber/
├── core/
│   ├── downloader.py       # yt-dlp universal media extractor & platform detector
│   ├── transcriber.py      # Faster-Whisper offline inference engine (CUDA/CPU fallback)
│   └── exporter.py         # Formatter for TXT, SRT, VTT, JSON, and Markdown
├── api/
│   └── server.py           # FastAPI backend with SSE streaming, range audio, and REST APIs
├── web/
│   ├── index.html          # Modern dark-mode interface
│   ├── styles.css          # Glassmorphism, animations, responsive design
│   └── app.js              # SSE progress listener & interactive transcript sync
├── tests/
│   ├── test_downloader.py  # Platform detection test suite
│   ├── test_transcriber.py # Hardware & model inference test suite
│   └── test_exporter.py    # Subtitle and format validation test suite
├── main.py             # Native desktop app runner (PyWebView)
├── Transcribe.lnk      # 1-Click Desktop App Shortcut (Zero CMD)
├── Transcribe.vbs      # Windowless VBS launcher
├── transcribe_cli.py   # Standalone CLI tool
├── requirements.txt    # Dependencies
└── README.md           # Documentation
```

---

## 🧪 Running Tests
To run all automated verification tests:
```bash
.venv\Scripts\python.exe -m unittest discover tests
```

