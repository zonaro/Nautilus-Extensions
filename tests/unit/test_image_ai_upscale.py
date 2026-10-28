"""Tests for image_ai_upscale — backend detection, argv, output naming and
models. Pure functions; no backend binary or GPU required."""
import os
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from image_ai_upscale import (
    detect_backend, backend_compatible, discover_models, default_model,
    planned_output, unique_output_path, build_argv, UpscaleJob, UpscaleModel,
    MODELS_DIR,
)


class TestBackendDetection(unittest.TestCase):
    def test_prefers_configured_path(self):
        with patch("image_ai_upscale.os.path.isfile", return_value=True), \
             patch("image_ai_upscale.os.access", return_value=True):
            self.assertEqual(detect_backend("/opt/upscayl-bin"), "/opt/upscayl-bin")

    def test_falls_back_to_path(self):
        def which(name):
            return "/usr/bin/upscayl-bin" if name == "upscayl-bin" else None
        with patch("image_ai_upscale.os.path.isfile", return_value=False), \
             patch("image_ai_upscale.shutil.which", side_effect=which):
            self.assertEqual(detect_backend(), "/usr/bin/upscayl-bin")

    def test_none_when_missing(self):
        with patch("image_ai_upscale.os.path.isfile", return_value=False), \
             patch("image_ai_upscale.shutil.which", return_value=None):
            self.assertIsNone(detect_backend())

    def test_compatible_false_for_missing(self):
        self.assertFalse(backend_compatible("/nonexistent/upscayl-bin"))


class TestModels(unittest.TestCase):
    def test_discover_empty_when_no_dir(self):
        self.assertEqual(discover_models("/nonexistent/dir"), [])

    def test_discover_skips_incomplete_pair(self):
        with patch("image_ai_upscale.os.path.isdir", return_value=True), \
             patch("image_ai_upscale.os.listdir", return_value=["a.param"]):
            self.assertEqual(discover_models("/tmp/x"), [])

    def test_default_model(self):
        m1 = UpscaleModel("real-esrgan-general-x4v3", "Real 4x", None, None, 4)
        m2 = UpscaleModel("upscayl-standard-4x", "Standard 4x", None, None, 4)
        self.assertIs(default_model([m1, m2]), m2)
        self.assertIsNone(default_model([]))


class TestOutputPaths(unittest.TestCase):
    def test_planned_output_same_folder(self):
        self.assertEqual(
            planned_output("/tmp/foto.jpg", 4),
            "/tmp/foto-upscaled-4x.jpg")

    def test_planned_output_custom_dir(self):
        self.assertEqual(
            planned_output("/tmp/foto.jpg", 4, output_dir="/out"),
            "/out/foto-upscaled-4x.jpg")

    def test_planned_output_force_ext(self):
        self.assertEqual(
            planned_output("/tmp/foto.jpg", 4, force_ext=".png"),
            "/tmp/foto-upscaled-4x.png")

    def test_unique_output_path_no_collision(self):
        with patch("image_ai_upscale.os.path.exists", return_value=False):
            self.assertEqual(
                unique_output_path("/tmp/foto-upscaled-4x.jpg"),
                "/tmp/foto-upscaled-4x.jpg")

    def test_unique_output_path_collision(self):
        def exists(path):
            return path.endswith("-2.jpg") or path.endswith("-4x.jpg")
        with patch("image_ai_upscale.os.path.exists", side_effect=exists):
            self.assertEqual(
                unique_output_path("/tmp/foto-upscaled-4x.jpg"),
                "/tmp/foto-upscaled-4x-3.jpg")


class TestArgv(unittest.TestCase):
    def test_build_argv_structure(self):
        model = UpscaleModel(
            "upscayl-standard-4x", "Standard 4x",
            "/m/x.param", "/m/x.bin", 4)
        job = UpscaleJob(
            input="/tmp/in.png", output="/tmp/out.png", models_dir="/models",
            model=model, scale=4, width=None, format="preserve", quality=85,
            gpu="auto", tile=None, tta=False, threads="1:1:1")
        argv = build_argv(job, "upscayl-bin")
        self.assertEqual(argv[0], "upscayl-bin")
        self.assertIn("-i", argv)
        self.assertIn("/tmp/in.png", argv)
        self.assertIn("-o", argv)
        self.assertIn("/tmp/out.png", argv)
        self.assertIn("-m", argv)
        self.assertIn("/models", argv)
        self.assertIn("-n", argv)
        self.assertIn("upscayl-standard-4x", argv)
        self.assertIn("-z", argv)
        self.assertIn("4", argv)  # native scale
        self.assertIn("-s", argv)
        self.assertIn("4", argv)  # output scale
        self.assertIn("-f", argv)
        self.assertIn("preserve", argv)
        self.assertIn("-g", argv)
        self.assertIn("auto", argv)
        self.assertIn("-j", argv)
        self.assertIn("1:1:1", argv)

    def test_build_argv_with_tta_and_tile(self):
        model = UpscaleModel("m", "M", None, None, 4)
        job = UpscaleJob(
            input="/tmp/in.png", output="/tmp/out.png", models_dir="/models",
            model=model, scale=2, width=1920, format="png", quality=90,
            gpu=1, tile=512, tta=True, threads="2:2:2")
        argv = build_argv(job, "upscayl-bin")
        self.assertIn("-w", argv)
        self.assertIn("1920", argv)
        self.assertIn("-x", argv)  # TTA flag
        self.assertIn("-t", argv)
        self.assertIn("512", argv)
        self.assertIn("-g", argv)
        self.assertIn("1", argv)


if __name__ == "__main__":
    unittest.main()
