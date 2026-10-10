"""Advanced overrides: opts patching, capability lists, Pillow resize."""
import unittest
from pathlib import Path
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from media_core.models import MediaCategory, MediaItem
from media_core.backends.ffmpeg import FFmpegBackend
from media_core import capabilities as caps


def _cmd(fmt, category=MediaCategory.VIDEO, opts=None):
    be = FFmpegBackend()
    item = MediaItem(path=Path("in.mp4"), category=category,
                     target_format=fmt)
    return be.build_command(item, Path("out"), opts=opts)


class TestOptsPatching(unittest.TestCase):
    def test_video_overrides(self):
        cmd = _cmd("mp4", opts={"vcodec": "libx265", "crf": "26",
                                "speed": "fast", "resolution": "720p",
                                "fps": "30", "acodec": "aac",
                                "abitrate": "160k"})
        self.assertIn("libx265", cmd)
        self.assertIn("26", cmd[cmd.index("-crf") + 1])
        self.assertEqual(cmd[cmd.index("-preset") + 1], "fast")
        self.assertIn("scale=-2:720", cmd[cmd.index("-vf") + 1])
        self.assertEqual(cmd[cmd.index("-r") + 1], "30")
        self.assertEqual(cmd[cmd.index("-b:a") + 1], "160k")

    def test_gif_ignores_opts(self):
        cmd = _cmd("gif", opts={"vcodec": "libx265", "crf": "26",
                                "resolution": "720p"})
        self.assertNotIn("libx265", cmd)
        self.assertNotIn("-crf", cmd)

    def test_lossless_skips_abitrate_but_applies_ar_ac(self):
        cmd = _cmd("flac", category=MediaCategory.AUDIO,
                   opts={"abitrate": "320k", "sample_rate": 48000,
                         "channels": 2})
        self.assertNotIn("-b:a", cmd)
        self.assertEqual(cmd[cmd.index("-ar") + 1], "48000")
        self.assertEqual(cmd[cmd.index("-ac") + 1], "2")

    def test_speed_replaces_existing_preset(self):
        cmd = _cmd("mp4", opts={"vcodec": "mpeg4", "speed": "fast"})
        self.assertIn("mpeg4", cmd)
        self.assertEqual(cmd[cmd.index("-preset") + 1], "fast")

    def test_speed_not_appended_for_other_codecs(self):
        cmd = _cmd("wmv", opts={"speed": "fast"})
        self.assertNotIn("-preset", cmd)

    def test_progress_flag_kept(self):
        cmd = _cmd("mp4", opts={"crf": "20"})
        self.assertIn("-progress", cmd)
        self.assertIn("pipe:1", cmd)


class TestCapabilityLists(unittest.TestCase):
    def test_video_codecs(self):
        vcs = caps.available_video_codecs()
        self.assertIn("libx264", [e for e, _ in vcs])

    def test_audio_codecs(self):
        acs = caps.available_audio_codecs()
        self.assertIn("aac", [e for e, _ in acs])

    def test_hw_list(self):
        hws = caps.available_hw()
        self.assertEqual(hws[:2], ["Auto", "CPU"])


class TestPillowResize(unittest.TestCase):
    def test_max_side(self):
        from PIL import Image
        from media_core.backends.pillow import PillowBackend
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "big.png"
            Image.new("RGB", (800, 600), (0, 128, 255)).save(src)
            be = PillowBackend()
            out = be.convert_image(src, Path(d), "jpg", quality=85,
                                   max_side=200)
            with Image.open(out) as im:
                self.assertTrue(max(im.size) <= 200)


if __name__ == "__main__":
    unittest.main()
