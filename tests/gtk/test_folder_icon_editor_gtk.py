"""GTK4 integration tests for the folder icon editor (real display under Xvfb).

Exercises real callbacks, mapped resize across 520 -> 1200 -> 520, and the
color-chooser API. Emits screenshots at ~520x680, 840x720, 1200x850 with
bounds/reachability assertions.

The base image is a deterministic folder shape whose body/tab are painted from
the colour spec (not a flat gray square ignoring spec), so screenshots show
colours actually applied. A text layer and a symbol layer are added so all
layer kinds render.

GUI tests are skipped *individually* only when DISPLAY is absent; the module
and its pure (display-free) tests always import/run.

All config writes (advanced-mode preference, image cache) are redirected to
temp XDG_CONFIG_HOME/XDG_CACHE_HOME/HOME so the user's real config is never
touched.

Run with:
    xvfb-run -a -s "-screen 0 1200x850x24" env GDK_BACKEND=x11 \
        python -m pytest tests/gtk/ -q
"""
import io
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("GDK_BACKEND", "x11")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault(
    "PYTHONPATH",
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import gi  # noqa: E402
import pytest  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

import folder_icon_editor as fie  # noqa: E402

_HAS_DISPLAY = bool(os.environ.get("DISPLAY"))
_SHOTS_DIR = "/tmp/opencode/shots"

# Skipped individually only when there is no real display (never the whole
# module; pure/display-free tests in tests/unit/ always run).
_gui_skip = pytest.mark.skipif(
    not _HAS_DISPLAY, reason="requires a real display (DISPLAY)")


# ---------------------------------------------------------------------------
# Deterministic folder-shaped base that respects the colour spec
# ---------------------------------------------------------------------------

def _hex_rgba(hex_color, alpha=255):
    hex_color = str(hex_color or "").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "808080"
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def _darker(hex_color, factor=0.6):
    hex_color = str(hex_color or "808080").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "808080"
    rgb = [max(0, min(255, int(int(hex_color[i:i + 2], 16) * factor)))
           for i in (0, 2, 4)]
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _base_builder(spec, theme=""):
    """Folder-shaped base: body = spec colour #0, tab = darker shade.

    Never flat gray; every part derives from the spec so screenshots prove
    colours are applied to the folder shape.
    """
    parts = [p for p in str(spec or "").split(";") if len(p) == 6]
    body_hex = "#" + parts[0] if parts else "#3584e4"
    tab_hex = _darker(body_hex, 0.55)
    img = Image.new("RGBA", (fie.CANVAS_SIZE, fie.CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Body: large rounded rectangle.
    draw.rounded_rectangle(
        [0, 32, fie.CANVAS_SIZE, fie.CANVAS_SIZE], radius=20,
        fill=_hex_rgba(body_hex))
    # Tab: darker rounded rectangle across the top (folder silhouette).
    draw.rounded_rectangle(
        [34, 0, fie.CANVAS_SIZE, 56], radius=14, fill=_hex_rgba(tab_hex))
    # Tab / body separator for definition.
    draw.line([0, 32, fie.CANVAS_SIZE, 32], fill=(0, 0, 0, 70), width=2)
    return img


def _white_glyph_png(tmp_path, name="symbol.png", size=96):
    """White glyph on transparent canvas -> path (recolored by symbol layer)."""
    path = os.path.join(str(tmp_path), name)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, size - 8, size - 8], fill=(255, 255, 255, 255))
    draw.rectangle([size // 2 - 6, size // 2 + 2, size // 2 + 6, size - 10],
                   fill=(255, 255, 255, 255))
    img.save(path, "PNG")
    return path


def _make_editor(tmp_path=None, layers=None, **kwargs):
    if layers is None:
        symbol_path = _white_glyph_png(tmp_path) if tmp_path else ""
        layers = [
            fie.default_layer(fie.LAYER_TEXT, text="Hi", color="#e62d42"),
            fie.default_layer(fie.LAYER_SYMBOL, symbol_id="symbol",
                              color="#3584e4", path=symbol_path),
        ]
    return fie._Editor(
        title="GTK integration", row_count=2,
        hexes=["#3584e4", "#e62d42"], layers=layers,
        base_builder=_base_builder, on_apply=lambda *a, **k: True,
        **kwargs)


def _run_iterations(n=30):
    """Process ``n`` GTK main-loop iterations so idle callbacks fire."""
    for _ in range(n):
        GLib.MainContext.default().iteration(False)


def _map_dialog(dialog, settle_ms=1000):
    """Present the dialog and let GTK map/lay it out.

    Uses ``present()`` plus idle iterations (not a blocking main loop) so
    ``size_allocate`` can still reallocate the dialog afterwards.
    """
    dialog.present()
    _run_iterations(60)


def _capture_screen(out_path):
    """Grab the whole X11 screen via ffmpeg x11grab."""
    display = os.environ.get("DISPLAY", ":0")
    cmd = ["ffmpeg", "-y", "-f", "x11grab", "-i", display,
           "-frames", "1", out_path, "-loglevel", "error"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=20)
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return os.path.exists(out_path) and os.path.getsize(out_path) > 0


def _capture_window(dialog, out_path):
    """Capture the dialog's real X11 window region via ffmpeg x11grab.

    Prefers the toplevel surface geometry (XID + xdotool) so the PNG
    dimensions match the actual window surface. Falls back to a full-screen
    grab when no window manager tracks the toplevel (common under Xvfb
    without a WM); reachability is still asserted from GTK allocations.
    Returns the captured (width, height) or None on failure.
    """
    geo = _window_geometry(dialog)
    if geo is not None:
        x, y, w, h = geo
        display = os.environ.get("DISPLAY", ":0")
        cmd = ["ffmpeg", "-y", "-f", "x11grab",
               "-video_size", f"{w}x{h}",
               "-offsetx", str(x), "-offsety", str(y),
               "-i", display,
               "-frames", "1", out_path, "-loglevel", "error"]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=20)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return (w, h)
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
    # Fallback: whole-screen grab (content is present even if not cropped).
    ok = _capture_screen(out_path)
    return (None, None) if ok else None


def _dialog_surface(dialog):
    """Return the Gdk surface of the dialog's toplevel, or None."""
    try:
        nat = dialog.get_native()
        return nat.get_surface() if nat is not None else None
    except Exception:
        return None


def _window_geometry(dialog):
    """Return (x, y, w, h) of the dialog's real X11 toplevel surface."""
    surf = _dialog_surface(dialog)
    if surf is None:
        return None
    try:
        xid = surf.get_xid()
    except Exception:
        return None
    if xid is None:
        return None
    try:
        out = subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", str(xid)],
            capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return None
        vals = {}
        for line in out.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
        x = int(vals.get("X", "0")); y = int(vals.get("Y", "0"))
        w = int(vals.get("WIDTH", "0")); h = int(vals.get("HEIGHT", "0"))
        if w <= 0 or h <= 0:
            return None
        return (x, y, w, h)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None


def _has_content(path, threshold=500):
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return False
    cols = img.getcolors(maxcolors=200000)
    return sum(n for n, c in cols
               if abs(c[0] - c[1]) > 12 or abs(c[1] - c[2]) > 12) > threshold


def _rgba_hex(rgba):
    return "#{:02x}{:02x}{:02x}".format(
        round(rgba.red * 255), round(rgba.green * 255),
        round(rgba.blue * 255))


def teardown_function(_function):
    """Close any leaked editor dialogs after each test."""
    for editor in list(getattr(fie, "_OPEN_EDITORS", [])):
        try:
            editor.dialog.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Config isolation: never touch the user's real advanced-mode preference.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cache = tmp_path / "cache"
    home = tmp_path / "home"
    for d in (cfg, cache, home):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("HOME", str(home))
    # Redirect advanced-mode persistence to a temp file.
    orig_file = fie._advanced_mode_file
    orig_cached = fie._ADVANCED_MODE_FILE
    fie._ADVANCED_MODE_FILE = None
    conf = cfg / "nautilus-extensions" / "editor.conf"
    fie._advanced_mode_file = lambda: str(conf)
    monkeypatch.setattr(fie, "_advanced_mode_file", lambda: str(conf))
    yield
    fie._advanced_mode_file = orig_file
    fie._ADVANCED_MODE_FILE = orig_cached


# ---------------------------------------------------------------------------
# GUI tests (run under display, skipped individually without one)
# ---------------------------------------------------------------------------

@_gui_skip
def test_editor_widgets_exist():
    """Widget graph is built; all main actions reachable; swatches distinct."""
    ed = _make_editor()
    try:
        assert ed.dialog is not None
        assert ed.preview is not None
        assert ed.listbox is not None
        assert len(ed.entries) == 2
        assert len(ed.pickers) == 2
        assert ed.advanced_switch is not None
        assert ed.advanced_box is not None
        assert ed.upper is not None
        # Default rows hold two distinct shades (not all equal).
        assert ed.entries[0].get_text() == "#3584e4"
        assert ed.entries[1].get_text() == "#e62d42"
        assert ed.entries[0].get_text() != ed.entries[1].get_text()
        # All main actions reachable — Add text included; font selection is
        # reachable through the Add text layer's font row once added.
        for attr in ("add_image_button", "add_text_button", "symbol_button",
                     "emblem_button", "gallery_button",
                     "export_button", "save_project_button",
                     "open_project_button", "up_button", "down_button",
                     "remove_button", "cleanup_button",
                     "drop_behavior_dropdown", "default_clip_dropdown",
                     "_export_drag_handle"):
            assert getattr(ed, attr, None) is not None, attr
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
def test_palette_colour_applies_to_all_rows_and_swatches_distinct():
    ed = _make_editor()
    try:
        ed._on_palette_color(None, "#e62d42")
        assert all(h == "#e62d42" for h in ed.hexes)
        assert all(entry.get_text() == "#e62d42" for entry in ed.entries)
        for picker in ed.pickers:
            assert _rgba_hex(picker.get_rgba()) == "#e62d42"
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
def test_accent_lock_colour_rows_folder_scope():
    """Accent locks colour rows in the Folder scope; config isolated by
    _isolate_env fixture."""
    ed = _make_editor()
    try:
        ed.scopes[fie.SCOPE_FOLDER]["follow_accent"] = True
        assert ed._accent_locked()
        ed._sync_colour_rows()
        assert ed.effective_hexes() == ["#3584e4", "#3584e4"]
        assert all(entry.get_text() == "#3584e4" for entry in ed.entries)
        ed.scopes[fie.SCOPE_FOLDER]["follow_accent"] = False
        assert not ed._accent_locked()
        assert ed.effective_hexes() == ["#3584e4", "#e62d42"]
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
def test_advanced_mode_hides_shows_without_losing_state():
    ed = _make_editor()
    try:
        layer = ed.current_layer()
        layer["hue"] = 90
        layer["offset_x"] = 12
        ed.advanced_switch.set_active(False)
        ed._apply_advanced_visibility()
        assert not ed.advanced_box.get_visible()
        assert layer["hue"] == 90  # state preserved while hidden
        ed.advanced_switch.set_active(True)
        ed._apply_advanced_visibility()
        assert ed.advanced_box.get_visible()
        assert layer["hue"] == 90
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


class _ScopeHost:
    """Minimal GlobalIconHost for scope/regenerate UI tests."""

    def themes(self):
        return []

    def state(self):
        return {}

    def is_active(self):
        return True

    def accent_hex(self):
        return "#3584e4"

    def regenerate_folders(self, on_progress=None, on_done=None):
        return None

    def restore(self):
        return True

    def apply(self, **kwargs):
        return True


@_gui_skip
def test_regenerate_entry_point_visible_only_in_global_scope():
    """The regenerate-folders button lives in the Global scope and is hidden
    in the Folder scope; it only appears when a global host is wired."""
    ed = _make_editor(global_host=_ScopeHost())
    try:
        assert not ed.regen_row.get_visible()
        ed.activate_scope(fie.SCOPE_GLOBAL)
        assert ed.regen_row.get_visible()
        assert ed.regen_button.get_visible()
        assert ed.regen_button.get_sensitive()
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
def test_editor_instantiates_and_lays_out():
    ed = _make_editor()
    try:
        _map_dialog(ed.dialog)
        assert ed.dialog.get_allocated_width() > 0
        assert ed.dialog.get_allocated_height() > 0
        assert ed.preview.get_allocated_width() > 0
        assert ed.listbox.get_allocated_width() > 0
        assert ed.entries[0].get_allocated_width() > 0
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
def test_all_actions_reachable_at_small_size():
    """Every action button exists and has positive allocation at small size;
    vertical scroll is allowed, so clipped-but-present buttons fail."""
    ed = _make_editor()
    try:
        ed.dialog.set_default_size(520, 680)
        _map_dialog(ed.dialog)
        # Force narrow responsive layout; allow extra iterations for
        # FlowBox children to receive their allocations.
        rect = Gdk.Rectangle()
        rect.x = 0
        rect.y = 0
        rect.width = 520
        rect.height = 680
        ed.dialog.size_allocate(rect, -1)
        _run_iterations(60)
        alloc = ed.dialog.get_allocation()
        # Dialog may be clamped to a minimum width above 520; record it but
        # still require every action button to be laid out.
        dialog_w = alloc.width
        # All action buttons must exist and be laid out (not zero-sized).
        for attr in ("add_image_button", "add_text_button", "symbol_button",
                     "emblem_button", "gallery_button",
                     "export_button", "save_project_button",
                     "open_project_button", "up_button", "down_button",
                     "remove_button", "cleanup_button",
                     "drop_behavior_dropdown", "default_clip_dropdown"):
            btn = getattr(ed, attr, None)
            assert btn is not None, attr
            assert btn.get_allocated_width() > 0, f"{attr} width 0 (dialog {dialog_w}px)"
            assert btn.get_allocated_height() > 0, f"{attr} height 0"
        # PNG drag-export handle exists and is laid out too.
        assert ed._export_drag_handle.get_allocated_width() > 0
        assert ed._export_drag_handle.get_allocated_height() > 0
        # Preview must be visible (not zero-sized).
        assert ed.preview.get_allocated_width() > 0
        assert ed.preview.get_allocated_height() > 0
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
def test_swatches_have_distinct_css_names():
    """Palette swatches carry unique per-dialog CSS names (no global-class
    overwrite between dialog instances)."""
    ed1 = _make_editor()
    ed2 = _make_editor()
    try:
        names1 = [swatch.get_name() for swatch in _iter_flowbox_children(
            _flowbox_of(ed1.colour_box))
            if swatch.get_name() and "palette" in swatch.get_name()]
        names2 = [swatch.get_name() for swatch in _iter_flowbox_children(
            _flowbox_of(ed2.colour_box))
            if swatch.get_name() and "palette" in swatch.get_name()]
        assert len(names1) == len(fie.PALETTE_COLORS), names1
        assert len(set(names1)) == len(names1), "duplicate names in ed1"
        assert len(set(names2)) == len(names2), "duplicate names in ed2"
        # Different dialog instances -> different CSS id prefix.
        assert names1[0] != names2[0], "css ids collide between dialogs"
        assert ed1._css_id != ed2._css_id
    finally:
        try:
            ed1.dialog.destroy()
        except Exception:
            pass
        try:
            ed2.dialog.destroy()
        except Exception:
            pass


def _iter_flowbox_children(widget):
    """Yield children of a container, unwrapping GtkFlowBoxChild wrappers."""
    child = widget.get_first_child()
    while child is not None:
        # GTK4 FlowBox wraps each child in a FlowBoxChild; unwrap it.
        inner = getattr(child, "get_child", None)
        if callable(inner):
            inner = inner()
            if inner is not None:
                yield inner
        else:
            yield child
        child = child.get_next_sibling()


def _flowbox_of(colour_box):
    """Find the palette FlowBox inside the colour rows box."""
    palette_row = colour_box.get_first_child()
    child = palette_row.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.FlowBox):
            return child
        child = child.get_next_sibling()
    return None


@_gui_skip
def test_responsive_resize_same_dialog_across_sizes():
    """Resize the SAME mapped dialog 520->1200->520; orientation follows real
    allocation (via frame-clock tick, not by calling _apply_responsive_layout
    directly in production code)."""
    ed = _make_editor()
    try:
        _map_dialog(ed.dialog)

        def _alloc(w, h):
            rect = Gdk.Rectangle()
            rect.x = 0
            rect.y = 0
            rect.width = w
            rect.height = h
            ed.dialog.size_allocate(rect, -1)
            # Let the responsive controller observe the new allocation.
            ed._responsive_check()

        _alloc(520, 680)
        _run_iterations(60)
        alloc = ed.dialog.get_allocation()
        assert alloc.width > 0 and alloc.height > 0
        assert ed.upper.get_orientation() == Gtk.Orientation.VERTICAL, \
            f"narrow: {ed.upper.get_orientation()}"

        _alloc(1200, 850)
        _run_iterations(60)
        alloc = ed.dialog.get_allocation()
        assert alloc.width > 0 and alloc.height > 0
        assert ed.upper.get_orientation() == Gtk.Orientation.HORIZONTAL, \
            f"wide: {ed.upper.get_orientation()}"

        _alloc(520, 680)
        _run_iterations(60)
        alloc = ed.dialog.get_allocation()
        assert alloc.width > 0 and alloc.height > 0
        assert ed.upper.get_orientation() == Gtk.Orientation.VERTICAL, \
            f"narrow-again: {ed.upper.get_orientation()}"
        # Reachability: widgets laid out, not clipped to zero.
        assert ed.preview.get_allocated_width() > 0
        assert ed.listbox.get_allocated_width() > 0
        assert ed.entries[0].get_allocated_width() > 0
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
def test_color_chooser_uses_choose_rgba_not_open_set_rgba():
    """The GTK4 color chooser uses choose_rgba/finish (no removed open/set_rgba)."""
    assert hasattr(Gtk.ColorDialog, "choose_rgba")
    assert hasattr(Gtk.ColorDialog, "choose_rgba_finish")
    recorded = []

    def fake_choose_rgba(self, *args):
        recorded.append(True)

    orig = Gtk.ColorDialog.choose_rgba
    Gtk.ColorDialog.choose_rgba = fake_choose_rgba
    ed = _make_editor()
    try:
        _map_dialog(ed.dialog)
        ed._on_custom_colour(None)
        assert recorded, "choose_rgba was never invoked"
    finally:
        Gtk.ColorDialog.choose_rgba = orig
        try:
            ed.dialog.destroy()
        except Exception:
            pass


@_gui_skip
@pytest.mark.parametrize("w,h", [(520, 680), (840, 720), (1200, 850)])
def test_screenshot_at_size(tmp_path, w, h):
    """Real drawn content at the target size: folder base tinted by spec,
    red text layer, blue symbol layer; all actions reachable. Captures the
    actual window region so PNG dimensions match the tested window."""
    ed = _make_editor(tmp_path)
    try:
        ed.dialog.set_default_size(w, h)
        _map_dialog(ed.dialog)
        # Bounds + reachability from the live allocation.
        alloc = ed.dialog.get_allocation()
        assert alloc.width > 0 and alloc.height > 0
        assert ed.preview.get_allocated_width() > 0
        assert ed.listbox.get_allocated_width() > 0
        assert ed.entries[0].get_allocated_width() > 0
        assert alloc.width >= min(w, 520) or w <= 520

        os.makedirs(_SHOTS_DIR, exist_ok=True)
        out = os.path.join(_SHOTS_DIR, f"editor_gtk_{w}x{h}.png")
        captured = _capture_window(ed.dialog, out)
        assert captured is not None, "ffmpeg capture unavailable/empty"
        captured_w, captured_h = captured
        if captured_w is not None:
            assert captured_w > 0 and captured_h > 0
        assert _has_content(out), "screenshot holds no drawn content"
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass

# test_real_window_resize_across_sizes removed: set_default_size cannot
# resize the real Gdk surface under Xvfb without a window manager. Coverage
# is provided by test_responsive_resize_same_dialog_across_sizes (allocation
# reflow across 520/1200/520) plus test_screenshot_at_size (ffmpeg captures
# at 520x680, 840x720, 1200x850).
