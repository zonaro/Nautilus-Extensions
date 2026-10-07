import unittest
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from media_core import detection, formats, registry, models, capabilities
from media_core.backends import ffmpeg, pillow


class TestDetection(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(detection.detect_category(Path('test.mp3')).name, 'AUDIO')
        self.assertEqual(detection.detect_category(Path('test.mp4')).name, 'VIDEO')
        self.assertEqual(detection.detect_category(Path('test.jpg')).name, 'IMAGE')
        self.assertEqual(detection.detect_category(Path('test.unknown')).name, 'UNKNOWN')


class TestFormats(unittest.TestCase):
    def test_extensions(self):
        self.assertEqual(formats.format_output_extension('jpeg'), 'jpg')
        self.assertEqual(formats.format_output_extension('mp4'), 'mp4')


class TestRegistry(unittest.TestCase):
    def test_basic(self):
        r = registry.ConversionRegistry()
        self.assertIsNotNone(r.backends)
        self.assertEqual(r.get_media_type('f.mp4').name, 'VIDEO')


class TestBackends(unittest.TestCase):
    def test_ffmpeg_build(self):
        try:
            be = ffmpeg.FFmpegBackend()
        except Exception:
            self.skipTest("ffmpeg not found")
        item = models.MediaItem(path=Path('in.mp4'), category=models.MediaCategory.VIDEO, target_format='mp4')
        cmd = be.build_command(item, Path('out.mp4'))
        self.assertIsInstance(cmd, list)
        self.assertIn('-i', cmd)

    def test_pillow_available(self):
        self.assertTrue(pillow.PillowBackend.can_register())


if __name__ == '__main__':
    unittest.main()
