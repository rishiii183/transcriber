import unittest
import os
import wave
import struct
import math
from core.transcriber import LocalWhisperTranscriber


class TestTranscriber(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transcriber = LocalWhisperTranscriber()
        # Generate a small 1-second 16kHz mono WAV file for testing
        cls.test_wav = os.path.abspath("test_sample.wav")
        sample_rate = 16000
        duration = 1.0  # seconds
        frequency = 440.0  # Hz

        with wave.open(cls.test_wav, "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            num_samples = int(sample_rate * duration)
            for i in range(num_samples):
                val = int(32767.0 * 0.1 * math.sin(2.0 * math.pi * frequency * i / sample_rate))
                wav_file.writeframes(struct.pack("<h", val))

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_wav):
            try:
                os.remove(cls.test_wav)
            except Exception:
                pass

    def test_hardware_detection(self):
        hw = self.transcriber.get_hardware_info()
        self.assertIn("device", hw)
        self.assertIn(hw["device"], ["cuda", "cpu"])

    def test_model_listing(self):
        models = self.transcriber.list_models()
        self.assertGreaterEqual(len(models), 4)
        ids = [m["id"] for m in models]
        self.assertIn("tiny", ids)
        self.assertIn("small", ids)

    def test_transcribe_stream_execution(self):
        # Test stream generator execution with tiny model
        events = list(self.transcriber.transcribe_stream(
            audio_path=self.test_wav,
            model_size="tiny",
            vad_filter=False
        ))
        event_types = [e.get("type") for e in events]
        self.assertIn("status", event_types)
        self.assertIn("info", event_types)
        self.assertIn("complete", event_types)


if __name__ == "__main__":
    unittest.main()

