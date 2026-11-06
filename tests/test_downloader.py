import unittest
import os
from core.downloader import detect_platform, MediaDownloader


class TestDownloader(unittest.TestCase):
    def test_platform_detection(self):
        yt_test = detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(yt_test["id"], "youtube")
        self.assertEqual(yt_test["name"], "YouTube")

        yt_short = detect_platform("https://www.youtube.com/shorts/abc123xyz")
        self.assertEqual(yt_short["id"], "youtube")
        self.assertEqual(yt_short["name"], "YouTube Shorts")

        twitter_test = detect_platform("https://x.com/openai/status/123456789")
        self.assertEqual(twitter_test["id"], "twitter")
        self.assertEqual(twitter_test["name"], "X / Twitter")

        ig_test = detect_platform("https://www.instagram.com/reel/C8qabcdefgh/")
        self.assertEqual(ig_test["id"], "instagram")
        self.assertEqual(ig_test["name"], "Instagram Reel")

        li_test = detect_platform("https://www.linkedin.com/posts/anthropic_ai_video_1234")
        self.assertEqual(li_test["id"], "linkedin")
        self.assertEqual(li_test["name"], "LinkedIn")

        tt_test = detect_platform("https://www.tiktok.com/@user/video/7123456789")
        self.assertEqual(tt_test["id"], "tiktok")

    def test_local_file_detection(self):
        # Create a temp file to test local detection
        test_file = "temp_test_audio.wav"
        with open(test_file, "w") as f:
            f.write("test")
        try:
            detected = detect_platform(os.path.abspath(test_file))
            self.assertEqual(detected["id"], "local")
            self.assertEqual(detected["name"], "Local File")
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


if __name__ == "__main__":
    unittest.main()

