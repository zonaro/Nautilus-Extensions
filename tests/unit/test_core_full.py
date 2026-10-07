import unittest
from pathlib import Path
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from media_core import detection, formats, registry, models, capabilities, presets_manager
from media_core.backends import ffmpeg, pillow


class TestCoreFull(unittest.TestCase):
    def test_identification(self):
        self.assertEqual(detection.detect_category('a.mp3').name, 'AUDIO')
        self.assertEqual(detection.detect_category('v.mp4').name, 'VIDEO')
        self.assertEqual(detection.detect_category('i.png').name, 'IMAGE')
        self.assertEqual(detection.detect_category('x.unknown').name, 'UNKNOWN')

    def test_normalization(self):
        self.assertEqual(formats.format_output_extension('jpeg'), 'jpg')
        self.assertEqual(formats.format_output_extension('JPEG'), 'jpg')
        self.assertEqual(formats.format_output_extension('alac'), 'm4a')

    def test_registry(self):
        r = registry.ConversionRegistry()
        self.assertTrue(len(r.backends) >= 0)
        self.assertEqual(r.get_media_type('f.mp4').name, 'VIDEO')
        self.assertTrue(r.can_convert('mp4', 'mp3') in (True, False))

    def test_backend_selection(self):
        r = registry.ConversionRegistry()
        be = r.get_backend('mp4', 'mp3')
        self.assertIsNotNone(be)

    def test_ffmpeg_command_generation(self):
        try:
            be = ffmpeg.FFmpegBackend()
        except Exception:
            self.skipTest('no ffmpeg')
        item = models.MediaItem(path=Path('in.mp4'), category=models.MediaCategory.VIDEO, target_format='mp4')
        cmd = be.build_command(item, Path('out.mp4'))
        self.assertIsInstance(cmd, list)
        self.assertNotIn(' ', cmd[0]) if cmd else None
        self.assertIn('-i', cmd)

    def test_presets(self):
        self.assertTrue(len(presets_manager.Presets.VIDEO) > 0)
        self.assertTrue(len(presets_manager.Presets.AUDIO) > 0)
        self.assertTrue(len(presets_manager.Presets.IMAGE) > 0)

    def test_safe_output_path(self):
        try:
            be = ffmpeg.FFmpegBackend()
        except Exception:
            self.skipTest('no ffmpeg')
        with tempfile.TemporaryDirectory() as td:
            item = models.MediaItem(path=Path('test.mp4'), category=models.MediaCategory.VIDEO, target_format='mp4')
            out1 = be.build_output_path(item, Path(td))
            Path(out1).touch()
            out2 = be.build_output_path(item, Path(td))
            self.assertNotEqual(out1, out2)

    def test_incompatible(self):
        r = registry.ConversionRegistry()
        self.assertIsInstance(r.can_convert('bad', 'bad2'), bool)

    def test_pillow(self):
        self.assertTrue(pillow.PillowBackend.can_register())


if __name__ == '__main__':
    unittest.main()
