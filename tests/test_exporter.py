import unittest
import json
from core import exporter


class TestExporter(unittest.TestCase):
    def setUp(self):
        self.segments = [
            {"id": 0, "start": 0.0, "end": 2.5, "text": "Hello and welcome to this test."},
            {"id": 1, "start": 2.8, "end": 6.12, "text": "This audio is transcribed completely offline."}
        ]
        self.data = {
            "title": "Sample Reel",
            "platform": {"name": "Instagram Reel"},
            "duration": 6.12,
            "language": "en",
            "full_text": "Hello and welcome to this test. This audio is transcribed completely offline.",
            "segments": self.segments
        }

    def test_timestamp_formatting(self):
        # 65.5 seconds = 00:01:05,500 (SRT) / 00:01:05.500 (VTT)
        self.assertEqual(exporter.format_timestamp(65.5, srt_format=True), "00:01:05,500")
        self.assertEqual(exporter.format_timestamp(65.5, srt_format=False), "00:01:05.500")

    def test_friendly_time(self):
        self.assertEqual(exporter.format_friendly_time(45.0), "00:45")
        self.assertEqual(exporter.format_friendly_time(3670.0), "01:01:10")

    def test_to_txt(self):
        txt = exporter.to_txt(self.segments, full_text=self.data["full_text"])
        self.assertIn("Hello and welcome", txt)
        self.assertIn("completely offline", txt)

    def test_to_srt(self):
        srt = exporter.to_srt(self.segments)
        self.assertIn("1\n00:00:00,000 --> 00:00:02,500", srt)
        self.assertIn("Hello and welcome to this test.", srt)
        self.assertIn("2\n00:00:02,800 --> 00:00:06,120", srt)

    def test_to_vtt(self):
        vtt = exporter.to_vtt(self.segments)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> 00:00:02.500", vtt)

    def test_to_json(self):
        json_str = exporter.to_json(self.data)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["title"], "Sample Reel")
        self.assertEqual(len(parsed["segments"]), 2)

    def test_to_markdown(self):
        md = exporter.to_markdown(self.data)
        self.assertIn("# Transcript: Sample Reel", md)
        self.assertIn("- **Source**: Instagram Reel", md)
        self.assertIn("`00:00 - 00:02`", md)


if __name__ == "__main__":
    unittest.main()

