"""Unit + display tests for the folder icon editor UI layer.

Pure functions run without a display. GTK tests instantiate the editor and
require a display; they are skipped *individually* only when DISPLAY is absent,
never as a whole module.
"""
import io
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from PIL import Image

import folder_icon_editor as fie

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gtk, Gdk
    _GTK_AVAILABLE = True
except Exception:  # pragma: no cover - display-less environments
    _GTK_AVAILABLE = False


def _solid_png(directory, name, color, size=64):
    path = os.path.join(directory, name)
    Image.new("RGBA", (size, size), color).save(path, "PNG")
    return path


# ---------------------------------------------------------------------------
# Pure layer model (no display needed)
# ---------------------------------------------------------------------------

class TestSymbolLayerModel(unittest.TestCase):
    """The new ``symbol`` layer type round-trips through the schema."""

    def test_default_layer_symbol(self):
        layer = fie.default_layer(fie.LAYER_SYMBOL, symbol_id="folder",
                                  color="#ff0000")
        self.assertEqual(layer["type"], fie.LAYER_SYMBOL)
        self.assertEqual(layer["symbol_id"], "folder")
        self.assertEqual(layer["color"], "#ff0000")
        self.assertEqual(layer["scale"], 25)  # badge-sized
        self.assertEqual(set(layer), set(fie._LAYER_FIELDS))

    def test_normalize_layers_keeps_symbol_id(self):
        raw = [{"type": "symbol", "symbol_id": "emblem-ok",
                "color": "#00ff00", "scale": 40}]
        layers = fie.normalize_layers(raw)
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]["symbol_id"], "emblem-ok")
        self.assertEqual(layers[0]["color"], "#00ff00")
        self.assertEqual(layers[0]["scale"], 40)

    def test_derive_name_symbol(self):
        layer = fie.default_layer(fie.LAYER_SYMBOL, symbol_id="folder-symbolic")
        self.assertEqual(fie._derive_name(layer), "folder-symbolic")
        layer2 = fie.default_layer(fie.LAYER_SYMBOL)
        self.assertEqual(fie._derive_name(layer2), "")

    def test_symbol_id_is_a_content_field(self):
        self.assertIn("symbol_id", fie._CONTENT_FIELDS)


class TestSymbolRendering(unittest.TestCase):
    """Symbol layers are recolored by their color, alpha preserved."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = _solid_png(self.tmp.name, "glyph.png", (255, 255, 255, 255))

    def tearDown(self):
        self.tmp.cleanup()

    def _pixel(self, img):
        return img.convert("RGBA").getpixel((10, 10))

    def test_tint_symbol_to_color(self):
        img = Image.open(self.path).convert("RGBA")
        out = fie._tint_symbol_to_color(img, {"color": "#ff0000"})
        self.assertEqual(out.getpixel((10, 10))[:3], (255, 0, 0))
        self.assertEqual(out.getpixel((10, 10))[3], 255)

    def test_render_layer_symbol(self):
        layer = fie.default_layer(fie.LAYER_SYMBOL, path=self.path,
                                  color="#00aa00")
        img = fie.render_layer(layer)
        self.assertIsNotNone(img)
        self.assertEqual(img.getpixel((10, 10))[:3], (0, 170, 0))


# ---------------------------------------------------------------------------
# Accent lock: BOTH scopes (folder and global)
# ---------------------------------------------------------------------------

class TestAccentLockBothScopes(unittest.TestCase):
    def _editor(self, folder_accent=False, global_accent=False):
        editor = fie._Editor.__new__(fie._Editor)
        editor.global_host = None
        editor.scope = fie.SCOPE_FOLDER
        editor.scopes = {
            fie.SCOPE_FOLDER: {"hexes": ["#e62d42"],
                               "follow_accent": folder_accent},
            fie.SCOPE_GLOBAL: {"hexes": ["#111111"],
                               "follow_accent": global_accent},
        }
        editor.row_count = 1
        editor.hexes = ["#e62d42"]
        return editor

    def test_folder_scope_locks_to_accent(self):
        editor = self._editor(folder_accent=True)
        self.assertTrue(editor._accent_locked())
        self.assertEqual(editor.effective_hexes(), ["#3584e4"])

    def test_global_scope_locks_to_accent(self):
        editor = self._editor(global_accent=True)
        editor.scope = fie.SCOPE_GLOBAL
        self.assertTrue(editor._accent_locked())
        self.assertEqual(editor.effective_hexes(), ["#3584e4"])

    def test_unlocked_keeps_stored_hexes(self):
        editor = self._editor()
        self.assertFalse(editor._accent_locked())
        self.assertEqual(editor.effective_hexes(), ["#e62d42"])


# ---------------------------------------------------------------------------
# Providers: isolated with monkeypatch, never mutate real config
# ---------------------------------------------------------------------------

class TestProviders(unittest.TestCase):
    def test_providers_default_to_none_when_unwired(self):
        """Symbol providers default to None until a real module wires them.
        Project IO is a direct import (no provider shim); _HAS_PROJECT_MODULE
        reflects whether folder_icon_project could be imported."""
        for attr in ("_SYMBOL_LIST", "_SYMBOL_APPLY"):
            value = getattr(fie, attr)
            self.assertTrue(value is None or callable(value),
                            f"{attr} should be None or callable, got {value!r}")
        self.assertIsInstance(fie._HAS_PROJECT_MODULE, bool)

    def test_register_symbol_provider(self):
        fie.register_symbol_provider(lambda q: [], lambda sid: None)
        self.addCleanup(fie.register_symbol_provider, None, None)
        self.assertIsNotNone(fie._SYMBOL_LIST)
        self.assertIsNotNone(fie._SYMBOL_APPLY)


# ---------------------------------------------------------------------------
# Palette colors are distinct (the "quick cores todas iguais" bug)
# ---------------------------------------------------------------------------

class TestPaletteColors(unittest.TestCase):
    def test_ten_distinct_colours(self):
        hexes = [h for _, h in fie.PALETTE_COLORS]
        self.assertEqual(len(hexes), len(fie.PALETTE_COLORS))
        self.assertEqual(len(set(hexes)), len(hexes))
        self.assertTrue(all(fie._HEX_RE.match(h) for h in hexes))


# ---------------------------------------------------------------------------
# Persisted editor preferences (advanced mode + drop/clip defaults)
# ---------------------------------------------------------------------------

class TestPreferences(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conf = os.path.join(self.tmp.name, "editor.conf")
        self._orig = fie._advanced_mode_file
        fie._advanced_mode_file = lambda: self.conf

    def tearDown(self):
        fie._advanced_mode_file = self._orig
        self.tmp.cleanup()

    def test_defaults(self):
        self.assertEqual(
            fie.get_preference("default_drop_behavior", "add"), "add")
        self.assertEqual(fie.get_preference("default_clip", "none"), "none")
        self.assertFalse(fie.load_advanced_mode())

    def test_set_and_get_roundtrip(self):
        fie.set_preference("default_clip", "auto")
        fie.set_preference("default_drop_behavior", "replace")
        self.assertEqual(fie.get_preference("default_clip"), "auto")
        self.assertEqual(
            fie.get_preference("default_drop_behavior"), "replace")

    def test_legacy_advanced_file_is_upgraded_not_discarded(self):
        with open(self.conf, "w", encoding="utf-8") as f:
            f.write("1\n")
        self.assertTrue(fie.load_advanced_mode())
        # Writing a new preference upgrades the file but keeps advanced_mode.
        fie.set_preference("default_clip", "auto")
        self.assertTrue(fie.load_advanced_mode())
        self.assertEqual(fie.get_preference("default_clip"), "auto")

    def test_save_advanced_preserves_other_keys(self):
        fie.set_preference("default_clip", "auto")
        fie.save_advanced_mode(True)
        self.assertEqual(fie.get_preference("default_clip"), "auto")
        self.assertTrue(fie.load_advanced_mode())
        fie.save_advanced_mode(False)
        self.assertFalse(fie.load_advanced_mode())
        self.assertEqual(fie.get_preference("default_clip"), "auto")


# ---------------------------------------------------------------------------
# Documented keyboard shortcuts (README contract)
# ---------------------------------------------------------------------------

@unittest.skipIf(not _GTK_AVAILABLE, "GTK4 not importable")
class TestKeyboardShortcuts(unittest.TestCase):
    """The handler must match the shortcuts documented in the README.

    Ctrl+O opens a project, Ctrl+S saves the editable SVG project,
    Ctrl+Shift+S exports the rendered PNG, Ctrl+Shift+A toggles advanced
    mode, and Ctrl+A toggles advanced mode only outside a text input.
    """

    def _editor(self, focus_text=False):
        ed = fie._Editor.__new__(fie._Editor)
        self.calls = []
        ed._on_save_project = lambda *a: self.calls.append("save")
        ed._on_export_png = lambda *a: self.calls.append("export")
        ed._on_open_project = lambda *a: self.calls.append("open")
        ed.paste_image = lambda: self.calls.append("paste")
        ed._toggle_advanced_mode = lambda: self.calls.append("advanced")
        ed._focus_is_text_input = lambda: focus_text
        return ed

    def _press(self, ed, keyval, shift=False):
        state = Gdk.ModifierType.CONTROL_MASK
        if shift:
            state |= Gdk.ModifierType.SHIFT_MASK
        return ed._on_key_pressed(None, keyval, 0, state)

    def test_ctrl_s_saves_svg_project(self):
        ed = self._editor()
        self.assertTrue(self._press(ed, Gdk.KEY_s))
        self.assertEqual(self.calls, ["save"])

    def test_ctrl_shift_s_exports_png(self):
        ed = self._editor()
        self.assertTrue(self._press(ed, Gdk.KEY_S, shift=True))
        self.assertEqual(self.calls, ["export"])

    def test_ctrl_o_opens_project(self):
        ed = self._editor()
        self._press(ed, Gdk.KEY_o)
        self.assertEqual(self.calls, ["open"])

    def test_ctrl_shift_a_toggles_advanced(self):
        ed = self._editor(focus_text=True)
        self._press(ed, Gdk.KEY_A, shift=True)
        self.assertEqual(self.calls, ["advanced"])

    def test_ctrl_a_toggles_advanced_outside_text(self):
        ed = self._editor(focus_text=False)
        self._press(ed, Gdk.KEY_a)
        self.assertEqual(self.calls, ["advanced"])

    def test_ctrl_a_defers_to_text_input(self):
        ed = self._editor(focus_text=True)
        self.assertFalse(self._press(ed, Gdk.KEY_a))
        self.assertEqual(self.calls, [])

    def test_ctrl_v_pastes(self):
        ed = self._editor()
        self._press(ed, Gdk.KEY_v)
        self.assertEqual(self.calls, ["paste"])


# ---------------------------------------------------------------------------
# GTK / display tests
# ---------------------------------------------------------------------------

class _FakeJob:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _FakeHost:
    """Minimal GlobalIconHost stand-in for the regenerate entry point."""

    def __init__(self):
        self.progress_cb = None
        self.done_cb = None
        self.job = _FakeJob()

    def regenerate_folders(self, on_progress=None, on_done=None):
        self.progress_cb = on_progress
        self.done_cb = on_done
        return self.job


def _make_editor():
    layers = [
        fie.default_layer(fie.LAYER_IMAGE, text="x"),
        fie.default_layer(fie.LAYER_TEXT, text="Hi", color="#ff0000"),
    ]
    return fie._Editor(
        title="T", row_count=2, hexes=["#3584e4", "#e62d42"],
        layers=layers,
        base_builder=lambda spec, theme="": Image.new(
            "RGBA", (fie.CANVAS_SIZE, fie.CANVAS_SIZE),
            (128, 128, 128, 255)),
        on_apply=lambda *a, **k: True)


@unittest.skipIf(not _GTK_AVAILABLE, "GTK4 not importable")
class TestEditorGtk(unittest.TestCase):
    def setUp(self):
        if Gdk.Display.get_default() is None:
            self.skipTest("no display available")
        # Redirect every config write (advanced mode, image cache) to a temp
        # location so the user's real config is never touched. Must be set
        # before _Editor.__init__, which calls load_advanced_mode().
        self._tempdir = tempfile.TemporaryDirectory()
        cfg = os.path.join(self._tempdir.name, "config")
        cache = os.path.join(self._tempdir.name, "cache")
        home = os.path.join(self._tempdir.name, "home")
        for d in (cfg, cache, home):
            os.makedirs(d, exist_ok=True)
        self._env_patch = mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": cfg,
            "XDG_CACHE_HOME": cache,
            "HOME": home,
        })
        self._env_patch.start()
        # GLib.get_user_cache_dir() caches the first result and ignores later
        # XDG_CACHE_HOME changes; patch it so cache writes stay in the tempdir
        # regardless of which test initialized GLib first.
        self._cache_patch = mock.patch.object(
            fie.GLib, "get_user_cache_dir", lambda: cache)
        self._cache_patch.start()
        self._orig_advanced_file = fie._advanced_mode_file
        self._orig_advanced_cached = fie._ADVANCED_MODE_FILE
        fie._ADVANCED_MODE_FILE = None
        conf = os.path.join(cfg, "nautilus-extensions", "editor.conf")
        self._file_patch = mock.patch.object(
            fie, "_advanced_mode_file", lambda: str(conf))
        self._file_patch.start()
        self.editor = _make_editor()

    def tearDown(self):
        try:
            self.editor.dialog.destroy()
        except Exception:
            pass
        try:
            self._file_patch.stop()
        except Exception:
            pass
        fie._advanced_mode_file = self._orig_advanced_file
        fie._ADVANCED_MODE_FILE = self._orig_advanced_cached
        try:
            self._cache_patch.stop()
        except Exception:
            pass
        try:
            self._env_patch.stop()
        except Exception:
            pass
        try:
            self._tempdir.cleanup()
        except Exception:
            pass

    def test_editor_instantiates(self):
        self.assertIsNotNone(self.editor.dialog)
        self.assertEqual(len(self.editor.entries), 2)
        self.assertEqual(len(self.editor.pickers), 2)
        self.assertIsNotNone(self.editor.preview)
        self.assertIsNotNone(self.editor.listbox)
        self.assertIsNotNone(self.editor.advanced_switch)
        self.assertIsNotNone(self.editor.advanced_box)

    def test_advanced_mode_hides_shows_without_losing_state(self):
        layer = self.editor.current_layer()
        layer["hue"] = 90
        layer["offset_x"] = 12
        self.editor.advanced_switch.set_active(False)
        self.editor._apply_advanced_visibility()
        self.assertFalse(self.editor.advanced_box.get_visible())
        self.assertEqual(layer["hue"], 90)  # state preserved while hidden
        self.editor.advanced_switch.set_active(True)
        self.editor._apply_advanced_visibility()
        self.assertTrue(self.editor.advanced_box.get_visible())
        self.assertEqual(layer["hue"], 90)

    def test_responsive_layout_orientations(self):
        self.editor._apply_responsive_layout(520)
        self.assertEqual(self.editor.upper.get_orientation(),
                         Gtk.Orientation.VERTICAL)
        self.editor._apply_responsive_layout(840)
        self.assertEqual(self.editor.upper.get_orientation(),
                         Gtk.Orientation.HORIZONTAL)
        self.editor._apply_responsive_layout(1200)
        self.assertEqual(self.editor.upper.get_orientation(),
                         Gtk.Orientation.HORIZONTAL)

    def test_accent_lock_shows_accent_in_colour_rows(self):
        self.editor.scopes[fie.SCOPE_FOLDER]["follow_accent"] = True
        self.editor._sync_colour_rows()
        for entry in self.editor.entries:
            self.assertEqual(entry.get_text(), "#3584e4")

    def test_symbol_layer_is_addable(self):
        self.editor.layers.insert(0, fie.default_layer(fie.LAYER_SYMBOL,
                                                       symbol_id="folder"))
        self.editor.selected = 0
        self.editor._rebuild_rows()
        self.assertEqual(len(self.editor.layers), 3)
        self.assertEqual(self.editor.layers[0]["type"], fie.LAYER_SYMBOL)

    def test_default_clip_applies_to_added_images(self):
        self.editor.default_clip = "auto"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = _solid_png(tmp.name, "d.png", (0, 0, 0, 255))
        self.editor._add_image_paths([path])
        self.assertEqual(self.editor.layers[0]["type"], fie.LAYER_IMAGE)
        self.assertEqual(self.editor.layers[0]["mask_mode"], "auto")

    def test_default_clip_none_keeps_unmasked(self):
        self.editor.default_clip = "none"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = _solid_png(tmp.name, "e.png", (0, 0, 0, 255))
        self.editor._add_image_paths([path])
        self.assertEqual(self.editor.layers[0]["mask_mode"], "none")

    def test_default_drop_behavior_replace(self):
        # First layer is an image in _make_editor(); select it.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        new_path = _solid_png(tmp.name, "new.png", (10, 20, 30, 255))
        self.editor.selected = 0
        self.editor.default_drop_behavior = "replace"
        before = len(self.editor.layers)
        self.editor._on_images_dropped(None, [new_path], 0, 0)
        self.assertEqual(len(self.editor.layers), before)  # not appended
        self.assertEqual(self.editor.layers[0]["path"], new_path)
        self.assertEqual(self.editor.layers[0]["mask_mode"],
                         self.editor.default_clip)

    def test_default_drop_behavior_add(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        new_path = _solid_png(tmp.name, "add.png", (1, 2, 3, 255))
        self.editor.selected = 0
        self.editor.default_drop_behavior = "add"
        before = len(self.editor.layers)
        self.editor._on_images_dropped(None, [new_path], 0, 0)
        self.assertEqual(len(self.editor.layers), before + 1)

    def test_cleanup_keeps_referenced_and_young_files(self):
        base = os.path.join(fie.GLib.get_user_cache_dir(),
                            "folder-color", "pasted")
        os.makedirs(base, exist_ok=True)
        ref = os.path.join(base, "paste-ref.png")
        young = os.path.join(base, "paste-young.png")
        old = os.path.join(base, "paste-old.png")
        for path in (ref, young, old):
            with open(path, "wb") as f:
                f.write(b"x")
        ancient = time.time() - 2 * fie._Editor._CACHE_MIN_AGE
        os.utime(old, (ancient, ancient))
        # Reference one file from a layer so it must survive.
        self.editor.layers[0]["path"] = ref
        self.editor._cleanup_unused_cache()
        self.assertTrue(os.path.exists(ref))
        self.assertTrue(os.path.exists(young))
        self.assertFalse(os.path.exists(old))

    def test_regenerate_folders_calls_host_and_reports(self):
        host = _FakeHost()
        self.editor.global_host = host
        alerts = []
        self.editor._show_alert = lambda msg: alerts.append(msg)
        self.editor._on_regenerate_folders(None)
        self.assertIsNotNone(host.progress_cb)
        self.assertIsNotNone(host.done_cb)
        self.assertIs(host.job, self.editor.regen_job)
        host.progress_cb(1, 3, "/some/dir", "applied")
        host.done_cb(2, 1, 0, False)
        self.assertIsNone(self.editor.regen_job)
        self.assertTrue(any("Regeneration" in a for a in alerts))

    def test_regenerate_folders_without_host_is_noop(self):
        self.editor.global_host = None
        alerts = []
        self.editor._show_alert = lambda msg: alerts.append(msg)
        self.editor._on_regenerate_folders(None)
        self.assertEqual(alerts, [])
        self.assertIsNone(self.editor.regen_job)


if __name__ == "__main__":
    unittest.main()
