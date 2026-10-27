"""Unit tests for the folder icon editor layer model (no display needed)."""
import io
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from PIL import Image

import folder_icon_editor as fie


def _solid_png(directory, name, color, size=64):
    path = os.path.join(directory, name)
    Image.new("RGBA", (size, size), color).save(path, "PNG")
    return path


class TestNormalizeLayers(unittest.TestCase):
    """normalize_layers() accepts every stored shape."""

    def test_none_and_empty(self):
        self.assertEqual(fie.normalize_layers(None), [])
        self.assertEqual(fie.normalize_layers([]), [])
        self.assertEqual(fie.normalize_layers({}), [])

    def test_list_of_layers(self):
        layers = fie.normalize_layers([
            {"type": "image", "path": "/tmp/a.png"},
            {"type": "text", "text": "hi"},
        ])
        self.assertEqual(len(layers), 2)
        self.assertEqual(layers[0]["type"], "image")
        self.assertEqual(layers[1]["type"], "text")
        for layer in layers:
            self.assertEqual(set(layer), set(fie._LAYER_FIELDS))

    def test_wrapped_layers(self):
        raw = {"spec": "#ff0000", "layers": [{"type": "text", "text": "x"}]}
        layers = fie.normalize_layers(raw)
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]["type"], "text")

    def test_legacy_state(self):
        legacy = {"overlay_path": "/tmp/old.png", "opacity": 80, "scale": 120,
                  "offset_x": 5, "offset_y": -7, "rotation": 30,
                  "spec": "#ff0000"}
        layers = fie.normalize_layers(legacy)
        self.assertEqual(len(layers), 1)
        layer = layers[0]
        self.assertEqual(layer["type"], "image")
        self.assertEqual(layer["path"], "/tmp/old.png")
        self.assertEqual(layer["opacity"], 80)
        self.assertEqual(layer["scale"], 120)
        self.assertEqual(layer["offset_x"], 5)
        self.assertEqual(layer["offset_y"], -7)
        self.assertEqual(layer["rotation"], 30)

    def test_legacy_state_without_overlay(self):
        # The caller relies on this: no overlay -> no layers at all.
        self.assertEqual(fie.normalize_layers({"overlay_path": ""}), [])
        self.assertEqual(fie.normalize_layers({"spec": "#ff0000"}), [])

    def test_nan_and_infinity(self):
        layers = fie.normalize_layers([{
            "type": "image", "path": "/tmp/a.png",
            "opacity": float("nan"), "scale": float("inf"),
            "hue": float("-inf"), "saturation": float("nan"),
            "rotation": float("nan"), "offset_x": float("inf"),
        }])
        self.assertEqual(len(layers), 1)
        layer = layers[0]
        self.assertEqual(layer["opacity"], fie._DEFAULTS["opacity"])
        self.assertEqual(layer["scale"], fie._DEFAULTS["scale"])
        self.assertEqual(layer["hue"], fie._DEFAULTS["hue"])
        self.assertEqual(layer["saturation"], fie._DEFAULTS["saturation"])
        self.assertEqual(layer["rotation"], fie._DEFAULTS["rotation"])
        self.assertEqual(layer["offset_x"], fie._DEFAULTS["offset_x"])
        for value in (layer["opacity"], layer["scale"], layer["hue"]):
            self.assertTrue(math.isfinite(value))

    def test_unknown_keys_dropped_and_values_clamped(self):
        layer = fie.normalize_layers([{
            "type": "text", "text": "hi", "opacity": 999, "scale": 1,
            "hue": -900, "saturation": 400, "rotation": 900,
            "offset_x": 99999, "font_size": 3, "bold": "yes", "junk": 1,
        }])[0]
        self.assertNotIn("junk", layer)
        self.assertEqual(layer["opacity"], 100)
        self.assertEqual(layer["scale"], 10)
        self.assertEqual(layer["hue"], -180)
        self.assertEqual(layer["saturation"], 100)
        self.assertEqual(layer["rotation"], 180)
        self.assertEqual(layer["offset_x"], 256)
        self.assertEqual(layer["font_size"], 8)
        self.assertIs(layer["bold"], True)

    def test_missing_keys_get_defaults(self):
        layer = fie.normalize_layers([{"type": "emblem"}])[0]
        self.assertEqual(set(layer), set(fie._LAYER_FIELDS))
        self.assertEqual(layer["emblem_uri"], "")
        self.assertEqual(layer["opacity"], 100)
        self.assertEqual(layer["color"], "#ffffff")


class TestClampInt(unittest.TestCase):
    """_clamp_int() keeps every value inside its range."""

    def test_bounds(self):
        self.assertEqual(fie._clamp_int(50, "opacity"), 50)
        self.assertEqual(fie._clamp_int(-10, "opacity"), 0)
        self.assertEqual(fie._clamp_int(1000, "opacity"), 100)
        self.assertEqual(fie._clamp_int(0, "scale"), 10)
        self.assertEqual(fie._clamp_int(1000, "scale"), 400)
        self.assertEqual(fie._clamp_int(-1000, "rotation"), -180)
        self.assertEqual(fie._clamp_int(-1000, "offset_x"), -256)
        self.assertEqual(fie._clamp_int(1000, "offset_x"), 256)
        self.assertEqual(fie._clamp_int(-1000, "saturation"), -100)
        self.assertEqual(fie._clamp_int(1000, "saturation"), 100)

    def test_invalid_values_use_the_default(self):
        self.assertEqual(fie._clamp_int("nope", "opacity"),
                         fie._DEFAULTS["opacity"])
        self.assertEqual(fie._clamp_int(None, "scale"), fie._DEFAULTS["scale"])
        self.assertEqual(fie._clamp_int(float("nan"), "hue"),
                         fie._DEFAULTS["hue"])
        self.assertEqual(fie._clamp_int(float("inf"), "hue"),
                         fie._DEFAULTS["hue"])
        self.assertEqual(fie._clamp_int(True, "opacity"),
                         fie._DEFAULTS["opacity"])


class TestComposeOrder(unittest.TestCase):
    """compose_layers() paints the stack in reverse (top-first list)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.red = _solid_png(self.tmp.name, "red.png", (255, 0, 0, 255), 256)
        self.green = _solid_png(self.tmp.name, "green.png", (0, 255, 0, 255), 256)
        self.base = Image.new("RGBA", (256, 256), (0, 0, 255, 255))

    def tearDown(self):
        self.tmp.cleanup()

    def _pixel(self, data):
        return Image.open(io.BytesIO(data)).convert("RGBA").getpixel((128, 128))

    def test_index_zero_is_painted_last(self):
        red = fie.default_layer(fie.LAYER_IMAGE, path=self.red)
        green = fie.default_layer(fie.LAYER_IMAGE, path=self.green)
        data = fie.compose_layers(self.base, [red, green])
        self.assertIsNotNone(data)
        self.assertEqual(data[:4], b"\x89PNG")
        self.assertEqual(self._pixel(data)[:3], (255, 0, 0))

    def test_swapping_the_stack_swaps_the_visible_layer(self):
        red = fie.default_layer(fie.LAYER_IMAGE, path=self.red)
        green = fie.default_layer(fie.LAYER_IMAGE, path=self.green)
        data = fie.compose_layers(self.base, [green, red])
        self.assertEqual(self._pixel(data)[:3], (0, 255, 0))

    def test_none_base_returns_none(self):
        layer = fie.default_layer(fie.LAYER_IMAGE, path=self.red)
        self.assertIsNone(fie.compose_layers(None, [layer]))

    def test_empty_stack_keeps_the_base(self):
        data = fie.compose_layers(self.base, [])
        self.assertIsNotNone(data)
        self.assertEqual(self._pixel(data)[:3], (0, 0, 255))


class TestAlphaPreservation(unittest.TestCase):
    """Hue/saturation must not touch the alpha band."""

    def setUp(self):
        self.img = Image.new("RGBA", (16, 16), (255, 0, 0, 128))

    def test_hue_keeps_alpha(self):
        shifted = fie._shift_hue(self.img, 120)
        self.assertEqual(shifted.getpixel((5, 5))[3], 128)
        self.assertNotEqual(shifted.getpixel((5, 5))[:3], (255, 0, 0))

    def test_saturation_keeps_alpha(self):
        shifted = fie._shift_saturation(self.img, -100)
        self.assertEqual(shifted.getpixel((5, 5))[3], 128)
        red, green, blue = shifted.getpixel((5, 5))[:3]
        self.assertEqual(red, green)
        self.assertEqual(green, blue)

    def test_opacity_scales_the_alpha(self):
        layer = fie.default_layer(fie.LAYER_IMAGE)
        layer["opacity"] = 50
        faded = fie._apply_transforms(self.img, layer)
        self.assertEqual(faded.getpixel((5, 5))[3], 64)

    def test_render_cache_does_not_leak_between_layers(self):
        # The cached image must not be mutated by the transforms.
        layer = fie.default_layer(fie.LAYER_IMAGE)
        layer["opacity"] = 50
        first = fie._apply_transforms(self.img, layer)
        second = fie._apply_transforms(self.img, layer)
        self.assertEqual(first.getpixel((5, 5))[3], second.getpixel((5, 5))[3])
        self.assertEqual(self.img.getpixel((5, 5))[3], 128)


class TestDropAnchor(unittest.TestCase):
    """The drop anchor arithmetic (pure helper)."""

    def test_same_row_is_rejected(self):
        self.assertIsNone(fie._drop_anchor(2, 2, 0, 40))

    def test_above_the_middle_inserts_before(self):
        # source 0 dropped on row 2, above its middle -> stays before row 2
        self.assertEqual(fie._drop_anchor(0, 2, 5, 40), 1)

    def test_below_the_middle_inserts_after(self):
        # source 0 dropped on row 2, below its middle -> after row 2
        self.assertEqual(fie._drop_anchor(0, 2, 35, 40), 2)

    def test_source_below_the_target(self):
        # [A, B, C, D]: D (3) dropped on B (1) above the middle -> [A, D, B, C]
        self.assertEqual(fie._drop_anchor(3, 1, 0, 40), 1)
        # D (3) dropped on B (1) below the middle -> [A, B, D, C]
        self.assertEqual(fie._drop_anchor(3, 1, 39, 40), 2)

    def test_source_above_the_target(self):
        # [A, B, C, D]: A (0) dropped on C (2) above the middle -> [B, A, C, D]
        self.assertEqual(fie._drop_anchor(0, 2, 5, 40), 1)
        # A (0) dropped on C (2) below the middle -> [B, C, A, D]
        self.assertEqual(fie._drop_anchor(0, 2, 35, 40), 2)

    def test_payload_parsing(self):
        self.assertEqual(fie._payload_index("3"), 3)
        self.assertEqual(fie._payload_index(b"4"), 4)
        with self.assertRaises(ValueError):
            fie._payload_index("not-a-number")
        with self.assertRaises(ValueError):
            fie._payload_index(None)


class TestClampDialogSize(unittest.TestCase):
    """_clamp_dialog_size() limits the dialog to the screen, with a floor."""

    def test_large_screen_keeps_base_size(self):
        self.assertEqual(
            fie._clamp_dialog_size(1920, 1080), (820, 700))

    def test_narrow_screen_limits_width(self):
        # 700 - 48 margin -> 652 wide, height untouched.
        width, height = fie._clamp_dialog_size(700, 1080)
        self.assertEqual(width, 652)
        self.assertEqual(height, 700)

    def test_short_screen_limits_height(self):
        # 600 - 140 margin -> 460 high (== floor), width untouched.
        width, height = fie._clamp_dialog_size(1920, 600)
        self.assertEqual(width, 820)
        self.assertEqual(height, 460)

    def test_never_below_minimums(self):
        # A tiny screen still yields the usable minimum, not a collapsed box.
        self.assertEqual(
            fie._clamp_dialog_size(200, 150), (520, 460))

    def test_invalid_available_falls_back_to_minimums(self):
        for avail in ((0, 0), (-10, -20), (None, None)):
            self.assertEqual(
                fie._clamp_dialog_size(*avail), (520, 460))


if __name__ == "__main__":
    unittest.main()
