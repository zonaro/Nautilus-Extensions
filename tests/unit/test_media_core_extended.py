import unittest
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from media_core import detection, formats, registry, models
from media_core.backends import ffmpeg, pillow


class TestExtended(unittest.TestCase):
    def test_identification_categories(self):
        self.assertEqual(detection.detect_category('a.mp3').name, 'AUDIO')
        self.assertEqual(detection.detect_category('v.mp4').name, 'VIDEO')
        self.assertEqual(detection.detect_category('i.png').name, 'IMAGE')

    def test_normalization(self):
        self.assertEqual(formats.format_output_extension('JPEG'), 'jpg')
        self.assertEqual(formats.format_output_extension('ALAC'), 'm4a')

    def test_registry_selection(self):
        r = registry.ConversionRegistry()
        self.assertTrue(r.can_convert())
        be = r.get_backend('mp4', 'mp3')
        self.assertIsNotNone(be)

    def test_ffmpeg_commands(self):
        try:
            be = ffmpeg.FFmpegBackend()
        except Exception:
            self.skipTest('ffmpeg missing')
        item = models.MediaItem(path=Path('in.mp4'), category=models.MediaCategory.VIDEO, target_format='mp4')
        cmd = be.build_command(item, Path('out.mp4'))
        self.assertIsInstance(cmd, list)
        self.assertFalse(any(' ' in c for c in cmd[:2]))  # no shell concat
        self.assertEqual(cmd[-1], 'out.mp4')

    def test_output_path_safe(self):
        try:
            be = ffmpeg.FFmpegBackend()
        except Exception:
            self.skipTest('ffmpeg missing')
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            item = models.MediaItem(path=Path('test.mp4'), category=models.MediaCategory.VIDEO, target_format='mp4')
            out1 = be.build_output_path(item, Path(td))
            Path(out1).touch()
            out2 = be.build_output_path(item, Path(td))
            self.assertNotEqual(out1, out2)

    def test_incompatible_safe(self):
        r = registry.ConversionRegistry()
        self.assertIsInstance(r.can_convert('weird', 'strange'), bool)


if __name__ == '__main__':
    unittest.main()
