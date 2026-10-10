"""Progress feedback must reach the UI: ffmpeg needs -progress pipe:1."""
import unittest
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from media_core.models import MediaCategory, MediaItem
from media_core.backends.ffmpeg import FFmpegBackend


class TestProgressFeedback(unittest.TestCase):
    def test_build_command_reports_progress(self):
        try:
            be = FFmpegBackend()
        except Exception:
            self.skipTest("ffmpeg not found")
        item = MediaItem(path=Path("in.mp4"),
                         category=MediaCategory.VIDEO, target_format="mp4")
        cmd = be.build_command(item, Path("out.mp4"))
        self.assertIn("-progress", cmd)
        self.assertIn("pipe:1", cmd)

    def test_parse_progress_ratio(self):
        try:
            be = FFmpegBackend()
        except Exception:
            self.skipTest("ffmpeg not found")
        self.assertAlmostEqual(
            be._parse_progress_ratio("out_time_ms=3000000", 6.0), 0.5)
        self.assertAlmostEqual(
            be._parse_progress_ratio("out_time=00:00:03.00", 6.0), 0.5)
        self.assertIsNone(be._parse_progress_ratio("frame=10", 6.0))
        self.assertIsNone(be._parse_progress_ratio("out_time_ms=1", None))


if __name__ == "__main__":
    unittest.main()
