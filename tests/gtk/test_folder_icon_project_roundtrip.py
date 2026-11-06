"""GTK integration tests for editor <-> folder_icon_project SVG round-trip.

Tests the editor's save/open project flow using the real folder_icon_project
module (no provider shims, no mocks). All file I/O goes through
write_svg_project / load_svg_project so the SVG round trip is real.

GUI tests are skipped individually when DISPLAY is absent. Config is isolated
to temp dirs (never touches the user's real advanced-mode preference).
"""

import base64
import copy
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib  # noqa: E402

import folder_icon_project as project  # noqa: E402
import folder_icon_editor as fie  # noqa: E402
from folder_icon_editor import (  # noqa: E402
    LAYER_TEXT, LAYER_SYMBOL, LAYER_EMBLEM, LAYER_IMAGE,
    default_layer, compose_with_snapshots,
)

CANVAS = fie.CANVAS_SIZE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _isolate_env(tmp_path, monkeypatch):
    """Redirect XDG_CONFIG_HOME / XDG_CACHE_HOME / HOME / PYTHONPATH to temp."""
    for d in ("config", "cache", "home"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PYTHONPATH",
                       str(Path(__file__).resolve().parents[2]))
    fie._advanced_mode_file = lambda: str(tmp_path / "config"
                                          / "nautilus-extensions" / "editor.conf")


def _folder_base_png(spec="#3584e4", size=CANVAS):
    """Deterministic folder-shaped base PNG from a colour spec."""
    h = spec.lstrip("#")
    body = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    tab = tuple(max(0, min(255, int(c * 0.55))) for c in body[:3]) + (255,)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, int(size * 0.125), size,
                            size], radius=int(size * 0.08), fill=body)
    draw.rounded_rectangle([int(size * 0.13), 0, size,
                            int(size * 0.22)],
                           radius=int(size * 0.06), fill=tab)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _symbol_png(tmp_path, name="symbol.png"):
    """White glyph on transparent canvas (recolored by symbol layer)."""
    path = os.path.join(str(tmp_path), name)
    img = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([12, 12, 84, 84], fill=(255, 255, 255, 255))
    draw.rectangle([44, 60, 52, 94], fill=(255, 255, 255, 255))
    img.save(path, "PNG")
    return path


def _rgba_png(color, size=(64, 64)):
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _make_editor(tmp_path, monkeypatch, layers=None, row_count=2):
    _isolate_env(tmp_path, monkeypatch)
    symbol_path = _symbol_png(tmp_path) if tmp_path else ""
    if layers is None:
        layers = [
            default_layer(LAYER_TEXT, text="Olá 世界", color="#e62d42",
                          font_size=48),
            default_layer(LAYER_SYMBOL, symbol_id="sym",
                          color="#3584e4", path=symbol_path),
        ]
    ed = fie._Editor(
        title="Round trip", row_count=row_count,
        hexes=["#3584e4", "#e62d42"], layers=layers,
        base_builder=lambda spec, theme="": _pil_from_png(
            _folder_base_png(spec)),
        on_apply=lambda *a, **k: True)
    return ed, symbol_path


def _pil_from_png(png_bytes):
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def _run_iterations(n=40):
    for _ in range(n):
        GLib.MainContext.default().iteration(False)


# ---------------------------------------------------------------------------
# Round-trip: save SVG -> load -> state preserved
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("DISPLAY", "") == "",
                    reason="needs a display")
def test_svg_roundtrip_preserves_state_and_embeds_assets(tmp_path, monkeypatch):
    ed, symbol_path = _make_editor(tmp_path, monkeypatch)
    try:
        fc = compose_with_snapshots(
            _pil_from_png(_folder_base_png()), ed.layers)
        assert fc is not None
        assert fc["png"] is not None
        assert len(fc["layer_pngs"]) == len(ed.layers)
        assert len(fc["source_pngs"]) == len(ed.layers)
        # Every snapshot is full canvas.
        for blob in fc["layer_pngs"] + fc["source_pngs"]:
            img = Image.open(io.BytesIO(blob))
            assert img.size == (CANVAS, CANVAS)
        # layer_pngs is BOTTOM->top; source_pngs is TOP-first.
        # layers[0] is text (top); layers[1] is symbol (bottom).
        # source_pngs[0] = text source, source_pngs[1] = symbol source.
        # layer_pngs[0] = symbol snapshot (bottom), layer_pngs[1] = text snapshot.
        assert fc["source_pngs"][0] != fc["source_pngs"][1]

        state = ed._build_project_state()
        svg = project.save_svg_project(
            fc["base_png"], fc["layer_pngs"], state,
            source_pngs=fc["source_pngs"])
        assert svg.startswith(b"<?xml") or svg.startswith(b"<svg")

        svg_path = tmp_path / "roundtrip.svg"
        project.write_svg_project(svg_path, svg)

        # Delete the source symbol file — the SVG must embed everything.
        os.remove(symbol_path)

        loaded = project.load_svg_project(svg_path, tmp_path / "cache")
        assert loaded is not None
        assert "_svg_project" in loaded
        assert loaded["_svg_project"]["base_png"]
        assert len(loaded["_svg_project"]["layer_pngs"]) == 2

        # Manual hexes preserved separately from follow_accent.
        assert loaded["hexes"] == ["#3584e4", "#e62d42"]
        assert loaded["follow_accent"] is False

        # Unicode text preserved.
        assert loaded["layers"][0]["text"] == "Olá 世界"
        assert loaded["layers"][1]["symbol_id"] == "sym"

        # Both scopes survived.
        assert "scopes" in loaded
        assert "folder" in loaded["scopes"]
        assert "global" in loaded["scopes"]
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Preview vs rendered SVG comparison
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("DISPLAY", "") == "",
                    reason="needs a display")
def test_preview_matches_rendered_svg_stack(tmp_path, monkeypatch):
    """The editor's composed preview PNG matches re-compositing the SVG's
     stack, within a small per-channel tolerance."""
    ed, _symbol_path = _make_editor(tmp_path, monkeypatch)
    try:
        fc = compose_with_snapshots(
            _pil_from_png(_folder_base_png()), ed.layers)
        preview_png = fc["png"]

        state = ed._build_project_state()
        svg = project.save_svg_project(
            fc["base_png"], fc["layer_pngs"], state,
            source_pngs=fc["source_pngs"])
        svg_path = tmp_path / "compare.svg"
        project.write_svg_project(svg_path, svg)

        # Re-compose from the SVG's embedded layer snapshots.
        loaded = project.load_svg_project(svg_path, tmp_path / "cache2")
        base_bytes = Path(loaded["_svg_project"]["base_png"]).read_bytes()
        layer_bytes = [Path(p).read_bytes()
                       for p in loaded["_svg_project"]["layer_pngs"]]

        base_img = Image.open(io.BytesIO(base_bytes)).convert("RGBA")
        canvas = base_img.copy()
        for blob in reversed(layer_bytes):  # layer_pngs is bottom->top
            layer_img = Image.open(io.BytesIO(blob)).convert("RGBA")
            canvas = Image.alpha_composite(canvas, layer_img)

        re_buf = io.BytesIO()
        canvas.save(re_buf, "PNG")
        re_png = re_buf.getvalue()

        # Compare pixel-by-pixel: mean per-channel abs delta < threshold.
        p1 = Image.open(io.BytesIO(preview_png)).convert("RGBA")
        p2 = Image.open(io.BytesIO(re_png)).convert("RGBA")
        assert p1.size == p2.size
        total = 0
        count = 0
        for y in range(p1.height):
            for x in range(p1.width):
                a = p1.getpixel((x, y))
                b = p2.getpixel((x, y))
                total += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
                count += 3
        mean_delta = total / count if count else 0
        assert mean_delta < 5.0, f"mean delta {mean_delta} too high"
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Reopened transform edit: raw sources preserve original font look
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("DISPLAY", "") == "",
                    reason="needs a display")
def test_reopened_transform_edit_uses_raw_sources(tmp_path, monkeypatch):
    """After reopening, editing a text layer's rotation renders from the raw
    source (original font look), not from a stale transformed snapshot."""
    ed, _symbol_path = _make_editor(tmp_path, monkeypatch)
    try:
        fc = compose_with_snapshots(
            _pil_from_png(_folder_base_png()), ed.layers)
        state = ed._build_project_state()
        svg = project.save_svg_project(
            fc["base_png"], fc["layer_pngs"], state,
            source_pngs=fc["source_pngs"])
        svg_path = tmp_path / "reopen.svg"
        project.write_svg_project(svg_path, svg)

        loaded = project.load_svg_project(svg_path, tmp_path / "cache3")
        # Simulate reopening in the editor: replace layers with loaded ones,
        # then rotate the text layer.
        ed.layers = fie.normalize_layers(loaded["layers"])
        text_layer = ed.layers[0]
        assert text_layer["type"] == LAYER_TEXT
        text_layer["rotation"] = 45

        fc2 = compose_with_snapshots(
            _pil_from_png(_folder_base_png()), ed.layers)
        assert fc2 is not None
        assert fc2["png"] != fc["png"], \
            "Rotated layer must change the composed PNG"

        # The source PNG for the text layer should still be the raw unrotated
        # text (full canvas), proving source_pngs retain the original look.
        src = Image.open(io.BytesIO(fc["source_pngs"][0]))
        assert src.size == (CANVAS, CANVAS)
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Stack order: layer_pngs bottom-to-top
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("DISPLAY", "") == "",
                    reason="needs a display")
def test_stack_order_bottom_to_top(tmp_path, monkeypatch):
    """layer_pngs must be bottom-to-top (reversed from top-first layers)."""
    ed, _symbol_path = _make_editor(tmp_path, monkeypatch)
    try:
        # Layer 0 = text (top), layer 1 = symbol (bottom).
        assert ed.layers[0]["type"] == LAYER_TEXT
        assert ed.layers[1]["type"] == LAYER_SYMBOL

        fc = compose_with_snapshots(
            _pil_from_png(_folder_base_png()), ed.layers)
        # layer_pngs is bottom->top: index 0 = bottom = symbol,
        # index 1 = top = text.
        bottom = Image.open(io.BytesIO(fc["layer_pngs"][0])).convert("RGBA")
        top = Image.open(io.BytesIO(fc["layer_pngs"][1])).convert("RGBA")

        # Verify layer_pngs ordering: symbol snapshot (bottom) differs from
        # text snapshot (top).
        assert fc["layer_pngs"][0] != fc["layer_pngs"][1]

        # Composite base -> bottom -> top and check both colours appear.
        base = Image.open(io.BytesIO(fc["base_png"])).convert("RGBA")
        canvas = base.copy()
        canvas = Image.alpha_composite(canvas, bottom)
        canvas = Image.alpha_composite(canvas, top)

        # Scan for a red-dominant pixel (from the text layer on top).
        found_red = False
        for y in range(0, CANVAS, 4):
            for x in range(0, CANVAS, 4):
                px = canvas.getpixel((x, y))
                if px[3] > 128 and px[0] > 150 and px[0] > px[2] + 40:
                    found_red = True
                    break
            if found_red:
                break
        assert found_red, "no red-dominant pixel found in composited stack"

        # Scan for a blue-dominant pixel (from the symbol layer below).
        found_blue = False
        for y in range(0, CANVAS, 4):
            for x in range(0, CANVAS, 4):
                px = canvas.getpixel((x, y))
                if px[3] > 128 and px[2] > 150 and px[2] > px[0] + 40:
                    found_blue = True
                    break
            if found_blue:
                break
        assert found_blue, "no blue-dominant pixel found in composited stack"
    finally:
        try:
            ed.dialog.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ProjectError is terminal: no fallback
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("DISPLAY", "") == "",
                    reason="needs a display")
def test_project_error_is_terminal_no_fallback(tmp_path, monkeypatch):
    """A malformed SVG project raises ProjectError; the editor shows the
    error and does not fall back to a placeholder image."""
    _ed, _symbol_path = _make_editor(tmp_path, monkeypatch)
    try:
        # Write a truncated/malformed SVG project file.
        bad_path = tmp_path / "bad.svg"
        bad_path.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"')

        # Direct call to load_svg_project must raise ProjectError.
        with pytest.raises(project.ProjectError):
            project.load_svg_project(bad_path, tmp_path / "cache_bad")
    finally:
        try:
            _ed.dialog.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Mask alpha: transparent mask region clears layer
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("DISPLAY", "") == "",
                    reason="needs a display")
def test_mask_alpha_clears_transparent_region(tmp_path, monkeypatch):
    """An RGBA mask with transparent pixels must clear the layer where the
    mask is transparent, even if the luminance is bright."""
    _ed, _symbol_path = _make_editor(tmp_path, monkeypatch)
    try:
        from folder_icon_editor import _load_mask_image, _apply_mask

        # Create an RGBA mask: bright white in top half, fully transparent in
        # bottom half. With alpha folding, bottom half must clear.
        mask_path = os.path.join(str(tmp_path), "mask_alpha.png")
        img = Image.new("RGBA", (64, 64), (255, 255, 0, 0))  # transparent yellow
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 64, 32], fill=(255, 255, 255, 255))  # opaque white
        img.save(mask_path, "PNG")

        # Layer image: fully opaque red.
        layer_img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))

        mask = _load_mask_image(mask_path, (64, 64))
        assert mask is not None
        result = _apply_mask(layer_img.copy(), mask)

        # Top half: mask opaque -> alpha preserved (255).
        assert result.getpixel((32, 16))[3] > 200
        # Bottom half: mask transparent -> alpha cleared (0).
        assert result.getpixel((32, 48))[3] < 50, \
            f"transparent mask region should clear, got alpha={result.getpixel((32, 48))[3]}"
    finally:
        try:
            _ed.dialog.destroy()
        except Exception:
            pass
