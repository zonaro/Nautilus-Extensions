"""Audio tag core: read/write round-trip incl. covers."""
import unittest
import tempfile
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from media_core import audio_tags as AT

GEN = [("mp3", "libmp3lame"), ("m4a", "aac"), ("ogg", "libvorbis"),
       ("opus", "libopus"), ("flac", "flac"), ("wav", "pcm_s16le"),
       ("aiff", "pcm_s16be")]


def _gen(d):
    out = {}
    for ext, acodec in GEN:
        p = os.path.join(d, f"t.{ext}")
        rc = os.system(
            f"ffmpeg -hide_banner -loglevel error -y -f lavfi "
            f"-i sine=frequency=440:duration=1 -c:a {acodec} {p}"
            f" >/dev/null 2>&1")
        if rc == 0 and os.path.exists(p):
            out[ext] = p
    return out


class TestAudioTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AT.mutagen_available():
            raise unittest.SkipTest("mutagen not installed")
        if shutil.which("ffmpeg") is None:
            raise unittest.SkipTest("ffmpeg not found")
        cls._tmp = tempfile.mkdtemp()
        cls.files = _gen(cls._tmp)
        if not cls.files:
            raise unittest.SkipTest("could not generate fixtures")

    def test_can_edit(self):
        self.assertTrue(AT.can_edit("x.mp3"))
        self.assertTrue(AT.can_edit("x.wav"))
        self.assertTrue(AT.can_edit("x.aiff"))
        self.assertFalse(AT.can_edit("x.txt"))

    def test_riff_saved_as_v23(self):
        from mutagen.id3 import ID3
        from mutagen.wave import WAVE
        from mutagen.aiff import AIFF
        kinds = {"wav": WAVE, "aiff": AIFF}
        for ext, kind in kinds.items():
            with self.subTest(fmt=ext):
                p = self.files.get(ext)
                if p is None:
                    self.skipTest(f"no {ext} fixture")
                AT.write_tags(p, {"title": "V"}, ("keep",))
                self.assertEqual(kind(p).tags.version, (2, 3, 0))

    def test_roundtrip_all_formats(self):
        from PIL import Image
        cov = os.path.join(self._tmp, "c.png")
        Image.new("RGB", (32, 32), (0, 255, 0)).save(cov)
        data = open(cov, "rb").read()
        for ext, p in self.files.items():
            with self.subTest(fmt=ext):
                AT.write_tags(p, {"title": "T", "artist": "A",
                                  "track": "2", "tracktotal": "9"},
                              ("set", "image/png", data))
                t = AT.read_tags(p)
                self.assertEqual(t["title"], "T")
                self.assertEqual(t["track"], "2")
                self.assertEqual(t["tracktotal"], "9")
                c = AT.read_cover(p)
                self.assertIsNotNone(c)
                self.assertEqual(c[0], "image/png")
                self.assertTrue(len(c[1]) > 0)

    def test_clear_and_remove(self):
        p = next(iter(self.files.values()))
        AT.write_tags(p, {"title": "X"}, ("remove",))
        AT.write_tags(p, {"title": ""}, ("remove",))
        self.assertEqual(AT.read_tags(p)["title"], "")
        self.assertIsNone(AT.read_cover(p))

    def test_unsupported_raises(self):
        with self.assertRaises(ValueError):
            AT.write_tags("/tmp/x.txt", {"title": "X"})


if __name__ == "__main__":
    unittest.main()
