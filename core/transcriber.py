import os
import time
from typing import Generator, Dict, Any, Optional, List
import ctranslate2

# PyAV compatibility shim for faster-whisper across all av versions
try:
    import av
    _orig_av_open = av.open
    def _safe_av_open(*args, **kwargs):
        try:
            return _orig_av_open(*args, **kwargs)
        except TypeError as e:
            if "metadata_errors" in str(e):
                kwargs.pop("metadata_errors", None)
                return _orig_av_open(*args, **kwargs)
            raise
    av.open = _safe_av_open
except Exception:
    pass

from faster_whisper import WhisperModel

# Supported model tiers
SUPPORTED_MODELS = {
    "tiny": {"name": "Tiny", "size": "~75MB", "vram": "~390MB", "speed": "Ultra Fast", "recommended": False},
    "base": {"name": "Base", "size": "~145MB", "vram": "~500MB", "speed": "Fast", "recommended": False},
    "small": {"name": "Small", "size": "~460MB", "vram": "~1.0GB", "speed": "Balanced", "recommended": True},
    "medium": {"name": "Medium", "size": "~1.5GB", "vram": "~2.6GB", "speed": "High Accuracy", "recommended": False},
    "large-v3": {"name": "Large-v3", "size": "~3.1GB", "vram": "~3.8GB", "speed": "Maximum Precision", "recommended": False},
}


class LocalWhisperTranscriber:
    """
    100% Offline Speech-to-Text inference engine powered by Faster-Whisper.
    Accelerated with CUDA (NVIDIA GPU) or multi-threaded CPU.
    """

    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = models_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "models")
        )
        os.makedirs(self.models_dir, exist_ok=True)
        self.current_model_size: Optional[str] = None
        self.model: Optional[WhisperModel] = None
        self.device, self.compute_type = self._detect_optimal_hardware()

    def _detect_optimal_hardware(self) -> tuple[str, str]:
        """Detects whether CUDA is available with valid runtime DLLs, else falls back to CPU."""
        try:
            import ctypes.util
            import site
            # Check for nvidia python packages and register DLL paths
            for sp in site.getsitepackages():
                for sub in [("nvidia", "cublas", "bin"), ("nvidia", "cudnn", "bin")]:
                    dll_path = os.path.join(sp, *sub)
                    if os.path.isdir(dll_path):
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(dll_path)
                            except Exception:
                                pass
                        if dll_path not in os.environ.get("PATH", ""):
                            os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")

            # Check if cublas is discoverable
            has_cublas = ctypes.util.find_library("cublas64_12") is not None or ctypes.util.find_library("cublas64_11") is not None
            if has_cublas and ctranslate2.get_cuda_device_count() > 0:
                return "cuda", "float16"
        except Exception:
            pass

        # Robust, high-speed multi-threaded CPU with int8 quantization
        return "cpu", "int8"

    def get_hardware_info(self) -> Dict[str, Any]:
        """Returns details about hardware acceleration status."""
        return {
            "device": self.device,
            "compute_type": self.compute_type,
            "is_gpu": self.device == "cuda",
            "cuda_available": ctranslate2.get_cuda_device_count() > 0,
        }

    def load_model(self, model_size: str = "small") -> WhisperModel:
        """Loads and caches the model in memory."""
        if model_size not in SUPPORTED_MODELS:
            model_size = "small"

        if self.model is not None and self.current_model_size == model_size:
            return self.model

        try:
            self.model = WhisperModel(
                model_size_or_path=model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.models_dir,
                local_files_only=False
            )
            self.current_model_size = model_size
            return self.model
        except Exception as e:
            # Fallback to CPU if CUDA encounters memory or library quirks
            if self.device == "cuda":
                print(f"[Transcriber] CUDA load failed ({e}), falling back to CPU...")
                self.device = "cpu"
                self.compute_type = "int8"
                self.model = WhisperModel(
                    model_size_or_path=model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=self.models_dir
                )
                self.current_model_size = model_size
                return self.model
            raise e

    def is_model_cached(self, model_size: str) -> bool:
        """Checks if model files are already cached locally with a valid model.bin file."""
        model_name = f"models--Systran--faster-whisper-{model_size}"
        model_path = os.path.join(self.models_dir, model_name)
        if not os.path.isdir(model_path):
            return False
        for root, dirs, files in os.walk(model_path):
            if "model.bin" in files:
                p = os.path.join(root, "model.bin")
                try:
                    if os.path.getsize(p) > 10 * 1024 * 1024:
                        return True
                except Exception:
                    pass
        return False

    def list_models(self) -> List[Dict[str, Any]]:
        """Returns list of models with local cache status and hardware compatibility."""
        results = []
        for key, info in SUPPORTED_MODELS.items():
            cached = self.is_model_cached(key)
            results.append({
                "id": key,
                "name": info["name"],
                "size": info["size"],
                "vram": info["vram"],
                "speed": info["speed"],
                "recommended": info["recommended"],
                "is_cached": cached,
                "is_active": (self.current_model_size == key)
            })
        return results

    def transcribe_stream(
        self,
        audio_path: str,
        model_size: str = "small",
        language: Optional[str] = None,
        vad_filter: bool = True,
        word_timestamps: bool = True,
        beam_size: int = 5
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming generator that transcribes audio completely offline and yields:
        - info: audio duration, detected language, confidence
        - segment: each sentence/segment as soon as it's processed
        - complete: aggregated final transcript and segments
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not self.is_model_cached(model_size):
            size_label = SUPPORTED_MODELS.get(model_size, {}).get("size", "")
            yield {
                "type": "status",
                "stage": "loading_model",
                "message": f"First-time setup: Downloading offline model weights for '{model_size}' ({size_label})... Please wait (cached permanently after this)."
            }
        else:
            yield {
                "type": "status",
                "stage": "loading_model",
                "message": f"Loading offline model ({model_size}) on {self.device.upper()} from local disk cache..."
            }

        model = self.load_model(model_size)

        yield {
            "type": "status",
            "stage": "transcribing",
            "message": f"Transcribing audio with {model_size} model on {self.device.upper()}..."
        }

        try:
            segments_generator, info = model.transcribe(
                audio_path,
                language=language if language and language != "auto" else None,
                beam_size=beam_size,
                vad_filter=vad_filter,
                vad_parameters=dict(min_silence_duration_ms=500),
                word_timestamps=word_timestamps
            )

            # Trigger initial generator evaluation to catch any runtime CUDA DLL errors early
            first_chunk = []
            segments_iter = iter(segments_generator)
            try:
                first_seg = next(segments_iter, None)
                if first_seg is not None:
                    first_chunk.append(first_seg)
            except RuntimeError as re:
                if self.device == "cuda" and ("cublas" in str(re).lower() or "cuda" in str(re).lower() or "dll" in str(re).lower()):
                    print(f"[Transcriber] CUDA runtime error encountered ({re}), falling back to CPU...")
                    self.device = "cpu"
                    self.compute_type = "int8"
                    model = WhisperModel(
                        model_size_or_path=model_size,
                        device="cpu",
                        compute_type="int8",
                        download_root=self.models_dir
                    )
                    self.current_model_size = model_size
                    self.model = model
                    segments_generator, info = model.transcribe(
                        audio_path,
                        language=language if language and language != "auto" else None,
                        beam_size=beam_size,
                        vad_filter=vad_filter,
                        vad_parameters=dict(min_silence_duration_ms=500),
                        word_timestamps=word_timestamps
                    )
                    segments_iter = iter(segments_generator)
                else:
                    raise re
        except RuntimeError as re:
            if self.device == "cuda":
                print(f"[Transcriber] CUDA runtime error encountered ({re}), falling back to CPU...")
                self.device = "cpu"
                self.compute_type = "int8"
                model = WhisperModel(
                    model_size_or_path=model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=self.models_dir
                )
                self.current_model_size = model_size
                self.model = model
                segments_generator, info = model.transcribe(
                    audio_path,
                    language=language if language and language != "auto" else None,
                    beam_size=beam_size,
                    vad_filter=vad_filter,
                    vad_parameters=dict(min_silence_duration_ms=500),
                    word_timestamps=word_timestamps
                )
                segments_iter = iter(segments_generator)
                first_chunk = []
            else:
                raise re

        yield {
            "type": "info",
            "language": info.language,
            "language_probability": round(info.language_probability, 3) if info.language_probability else 1.0,
            "duration": round(info.duration, 2) if info.duration else 0.0,
            "device": self.device,
            "model": model_size
        }

        collected_segments = []
        full_text_parts = []
        start_time = time.time()

        import itertools
        for segment in itertools.chain(first_chunk, segments_iter):
            seg_text = segment.text.strip()
            if not seg_text:
                continue

            words_data = []
            if segment.words:
                words_data = [
                    {
                        "word": w.word,
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "probability": round(w.probability, 2)
                    }
                    for w in segment.words
                ]

            segment_payload = {
                "id": segment.id,
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": seg_text,
                "words": words_data
            }

            collected_segments.append(segment_payload)
            full_text_parts.append(seg_text)

            yield {
                "type": "segment",
                "segment": segment_payload,
                "current_time": round(segment.end, 2),
                "total_duration": round(info.duration, 2) if info.duration else 0.0,
                "progress_percent": min(round((segment.end / (info.duration or 1.0)) * 100, 1), 99.0) if info.duration else None
            }

        elapsed = round(time.time() - start_time, 2)
        full_text = " ".join(full_text_parts)

        yield {
            "type": "complete",
            "full_text": full_text,
            "segments": collected_segments,
            "segments_count": len(collected_segments),
            "language": info.language,
            "duration": round(info.duration, 2) if info.duration else 0.0,
            "elapsed_seconds": elapsed,
            "speedup": round((info.duration / elapsed), 1) if (info.duration and elapsed > 0) else None,
            "device": self.device
        }
