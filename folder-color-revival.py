# Folder Color Revival - based on Folder Color 0.4.1
# Original: https://github.com/costales/folder-color
# Copyright (C) 2012-2024 Marcos Alvarez Costales
# Revival / Debug for Nautilus 43+ / GTK4 / python3-nautilus 4.0
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import os
import re
import sys
import io
import json
import hashlib
import tempfile
import locale
import logging
import configparser
import gi
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Debug logging — set DEBUG=1 to enable:
#   DEBUG=1 nautilus --no-desktop 2>&1 | grep "folder-color"
# ---------------------------------------------------------------------------
_DEBUG = os.environ.get("DEBUG", "0") == "1"
logging.basicConfig(
    stream=sys.stderr,
    format="[folder-color-revival] %(levelname)s: %(message)s",
)
log = logging.getLogger("folder-color-revival")
log.setLevel(logging.DEBUG if _DEBUG else logging.WARNING)

log.debug("Extension loading...")

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)

from gi.repository import Nautilus, Gtk, Gdk, GObject, Gio, GLib, GdkPixbuf, Pango

# ---------------------------------------------------------------------------
# NameToColor integration — "infinite" custom folder colors.
# generate_color() is a faithful Python port of NameToColor's generateColor()
# (NameToColor.js + pt-BR pack). Any name -> deterministic #rrggbb.
# If the module is missing (partial install), the "Custom color…" item
# is simply hidden and everything else keeps working.
# ---------------------------------------------------------------------------
try:
    from name_to_color import generate_color
    _CUSTOM_COLOR_AVAILABLE = True
except Exception as e:
    log.warning(f"name_to_color unavailable, custom colors disabled: {e}")
    _CUSTOM_COLOR_AVAILABLE = False

# ---------------------------------------------------------------------------
# Folder icon editor — layered composer (images, text, emblems) drawn over
# the themed folder icon. Optional module: when it is missing the extension
# keeps working with the plain colour picker only.
# ---------------------------------------------------------------------------
try:
    from folder_icon_editor import (
        compose_layers,
        default_layer,
        detect_icon_for_folder,
        normalize_layers,
        open_editor,
    )
    _ICON_EDITOR_AVAILABLE = True
except Exception as e:
    log.warning(f"folder_icon_editor unavailable, icon editor disabled: {e}")
    _ICON_EDITOR_AVAILABLE = False

    def normalize_layers(raw):
        """Fallback when folder_icon_editor is missing: no layers at all."""
        return []

    compose_layers = None
    default_layer = None
    detect_icon_for_folder = None
    open_editor = None

# Disk cache for generated folder icons. One deterministic file per color,
# so Nautilus (which keys its icon cache by URI) never serves a stale icon.
_CUSTOM_CACHE_SUBDIR = "folder-color"


def _custom_cache_dir():
    try:
        base = GLib.get_user_cache_dir()
    except Exception:
        base = os.path.join(str(Path.home()), ".cache")
    path = os.path.join(base, _CUSTOM_CACHE_SUBDIR)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        log.error(f"custom cache dir: {e}")
    return path


def _shade(hex_color, factor):
    """Lighten (>1) or darken (<1) a #rrggbb color by channel scaling."""
    h = str(hex_color).lstrip("#")[:6]
    out = []
    for i in (0, 2, 4):
        try:
            channel = int(h[i:i + 2], 16)
        except ValueError:
            channel = 128
        out.append(max(0, min(255, round(channel * factor))))
    return "#{:02x}{:02x}{:02x}".format(*out)


def _folder_svg(hex_color, hex_color2=None):
    """Two-tone generic folder: back tab = 1st color, front flap = 2nd (or 1st)."""
    back_base  = "#" + str(hex_color).lstrip("#")[:6].lower()
    front_base = ("#" + str(hex_color2).lstrip("#")[:6].lower()
                  if hex_color2 else back_base)
    back_light = _shade(back_base, 1.22)
    front_light = _shade(front_base, 1.22)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="back" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{back_light}"/>
      <stop offset="1" stop-color="{back_base}"/>
    </linearGradient>
    <linearGradient id="front" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{front_light}"/>
      <stop offset="1" stop-color="{front_base}"/>
    </linearGradient>
  </defs>
  <path d="M10 32c0-5 4-9 9-9h22l9 11h58c5 0 9 4 9 9v7H10z" fill="url(#back)"/>
  <path d="M10 32c0-5 4-9 9-9h22l9 11h58c5 0 9 4 9 9v7H10z" fill="none" stroke="#000000" stroke-opacity="0.25"/>
  <rect x="10" y="46" width="108" height="64" rx="10" fill="url(#front)"/>
  <rect x="10" y="46" width="108" height="64" rx="10" fill="none" stroke="#000000" stroke-opacity="0.3"/>
  <rect x="10" y="46" width="108" height="10" rx="5" fill="#ffffff" fill-opacity="0.18"/>
</svg>
"""


def _current_theme_name():
    try:
        theme = Gio.Settings.new("org.gnome.desktop.interface").get_string("icon-theme")
        if theme:
            return theme
    except Exception:
        pass
    try:
        return Gtk.Settings.get_default().get_property("gtk-icon-theme-name") or "hicolor"
    except Exception:
        return "hicolor"


def _theme_folder_svg_text():
    """Raw SVG text of the CURRENT theme's 'folder' icon, or ''.

    Filesystem lookup inside the current theme dirs only — never the
    display fallback chain (which would silently return another theme).
    """
    for theme_dir in _theme_dir_candidates(_current_theme_name()):
        scalable = os.path.join(theme_dir, "scalable", "places", "folder.svg")
        if os.path.isfile(scalable):
            try:
                with open(scalable, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                if "<svg" in text:
                    return text
            except Exception:
                continue
        places = os.path.join(theme_dir, "places")
        if not os.path.isdir(places):
            continue
        try:
            sizes = sorted(os.listdir(places), reverse=True)
        except Exception:
            continue
        for size in sizes:
            sized = os.path.join(places, size, "folder.svg")
            if os.path.isfile(sized):
                try:
                    with open(sized, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    if "<svg" in text:
                        return text
                except Exception:
                    continue
    return ""


def _icon_base_dirs():
    return [os.path.join(str(Path.home()), ".icons"),
            os.path.join(str(Path.home()), ".local", "share", "icons"),
            "/usr/local/share/icons",
            "/usr/share/icons"]


def _current_theme_png_path():
    """A colored folder PNG variant from the CURRENT theme dirs, or ''."""
    for theme_dir in _theme_dir_candidates(_current_theme_name()):
        found = _find_variant_png(theme_dir)
        if found:
            return found
    return ""


def _theme_dir_candidates(theme):
    """Existing directories for a theme name across icon base dirs."""
    found = []
    for base in _icon_base_dirs():
        path = os.path.join(base, theme)
        if os.path.isdir(path):
            found.append(path)
    return found


def _find_variant_png(theme_dir):
    """Largest plain 'folder-<color>.png' variant inside a theme dir."""
    best = None
    best_key = (-1, "")
    try:
        for root, _dirs, files in os.walk(theme_dir):
            if os.path.basename(root) != "places" and "places" not in root.split(os.sep):
                continue
            size = 0
            parent = os.path.basename(os.path.dirname(root))
            if "x" in parent:
                try:
                    size = int(parent.split("x")[0])
                except ValueError:
                    pass
            elif os.path.basename(root) == "scalable" or parent == "scalable":
                size = 10000
            for name in files:
                if not name.startswith("folder-") or not name.endswith(".png"):
                    continue
                stem = name[len("folder-"):-len(".png")]
                single = "-" not in stem
                key = (size + (50000 if single else 0), name)
                full = os.path.join(root, name)
                if key > best_key:
                    best_key = key
                    best = full
    except Exception as e:
        log.error(f"variant scan: {e}")
    return best


def _current_theme_png_path():
    """A colored folder PNG variant from the CURRENT theme dirs, or ''."""
    for theme_dir in _theme_dir_candidates(_current_theme_name()):
        found = _find_variant_png(theme_dir)
        if found:
            return found
    return ""


def _tint_png_file(path, hex_color):
    """Desaturate a PNG icon to gray, then multiply-tint. Returns PNG bytes."""
    try:
        from PIL import Image
    except Exception as e:
        log.error(f"PIL unavailable: {e}")
        return b""
    try:
        target = str(hex_color).lstrip("#")[:6].lower()
        tr, tg, tb = (int(target[i:i + 2], 16) for i in (0, 2, 4))
        img = Image.open(path).convert("RGBA")
        gray = img.convert("L")
        r = gray.point(lambda v: v * tr // 255)
        g = gray.point(lambda v: v * tg // 255)
        b = gray.point(lambda v: v * tb // 255)
        tinted = Image.merge("RGBA", (r, g, b, img.split()[3]))
        import io
        buffer = io.BytesIO()
        tinted.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as e:
        log.error(f"tint png: {e}")
        return b""


def _luminance(hex_color):
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return 128
    return round(0.299 * r + 0.587 * g + 0.114 * b)


def _tint_svg(svg_text, hex_color):
    """Single-color tint (whole icon)."""
    return _tint_svg_multi(svg_text, [hex_color])


_SHAPE_TAGS = {"path", "rect", "circle", "ellipse", "polygon", "polyline"}
_URL_RE = re.compile(r"url\(\s*#([^)]+?)\s*\)")
_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")


def _tint_one_color(hex_digits, target):
    """Multiply-tint a hex paint color with the target color."""
    if len(hex_digits) == 3:
        hex_digits = "".join(c * 2 for c in hex_digits)
    gray = _luminance(hex_digits) / 255.0
    try:
        tr, tg, tb = (int(target[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, round(tr * gray))),
        max(0, min(255, round(tg * gray))),
        max(0, min(255, round(tb * gray))))


def _svg_shapes(svg_text):
    """Parse SVG and return (root, shape_elements) with namespaces stripped."""
    try:
        root = ET.fromstring(svg_text)
    except Exception as e:
        log.error(f"tint svg parse: {e}")
        return None, []
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.rsplit("}", 1)[1]
    return root, [el for el in root.iter() if el.tag in _SHAPE_TAGS]


def _tint_svg_multi(svg_text, hex_list):
    """Tint a theme SVG with one color per shape (first shape -> 1st color).

    Shape i uses hex_list[min(i, len-1)]: with two shapes/colors the back
    takes color 1 and everything else color 2; extra shapes share the last
    color. Gradient stops referenced via url(#id) are tinted with their
    shape's color, preserving shading. Works with any theme SVG.
    """
    targets = [str(h).lstrip("#")[:6].lower() for h in hex_list]
    if (not targets or any(len(t) != 6
            or any(c not in "0123456789abcdef" for c in t) for t in targets)):
        return ""
    root, shapes = _svg_shapes(svg_text)
    if root is None or not shapes:
        return ""
    gradients = {}
    for el in root.iter():
        if el.tag in ("linearGradient", "radialGradient") and el.get("id"):
            gradients[el.get("id").strip()] = el

    def tinted_paint(value, target):
        """Tint a fill/stop-color value, preserving url()/none/currentColor."""
        url_match = _URL_RE.search(value or "")
        if url_match:
            return None, url_match.group(1)
        hex_match = _HEX_RE.search(value or "")
        if hex_match:
            return _tint_one_color(hex_match.group(1), target), None
        return None, None

    def apply_style(element, target):
        """Tint fill:/stop-color: declarations inside a style attribute."""
        style = element.get("style") or ""
        if "fill" not in style and "stop-color" not in style:
            return
        tinted, _ = tinted_paint(style, target)
        if tinted:
            try:
                element.set("style", _HEX_RE.sub(tinted, style, count=1))
            except Exception:
                pass

    last = len(targets) - 1
    for index, shape in enumerate(shapes):
        target = targets[min(index, last)]
        tinted, gradient_id = tinted_paint((shape.get("fill") or "").strip(), target)
        if tinted:
            shape.set("fill", tinted)
        elif gradient_id:
            gradient = gradients.get(gradient_id)
            if gradient is not None:
                for stop in gradient.iter():
                    if stop.tag != "stop":
                        continue
                    stop_tinted, _ = tinted_paint(
                        (stop.get("stop-color") or "").strip(), target)
                    if stop_tinted:
                        stop.set("stop-color", stop_tinted)
                    apply_style(stop, target)
        apply_style(shape, target)
    try:
        return ET.tostring(root, encoding="unicode")
    except Exception as e:
        log.error(f"tint svg serialize: {e}")
        return ""


def _split_color_spec(spec):
    """'rrggbb[;rrggbb...]' -> [hex, ...] or [] when any part is invalid."""
    parts = []
    for chunk in str(spec or "").split(";"):
        slug = chunk.strip().lstrip("#").lower()
        if len(slug) != 6 or any(c not in "0123456789abcdef" for c in slug):
            return []
        parts.append(slug)
    return parts


def _custom_icon_data(spec):
    """Tinted folder icon (bytes, ext) — no cache write.

    Sources in order: theme folder SVG (multi-tint) -> theme folder PNG
    variant (whole-icon tint) -> generic folder (first color).
    """
    parts = _split_color_spec(spec)
    if not parts:
        return None, None
    theme_svg = _theme_folder_svg_text()
    variant_png = "" if theme_svg else _current_theme_png_path()
    if theme_svg:
        svg = _tint_svg_multi(theme_svg, parts)
        if svg:
            return svg.encode("utf-8"), ".svg"
    if variant_png:
        data = _tint_png_file(variant_png, parts[0])
        if data:
            return data, ".png"
    return _folder_svg(parts[0]).encode("utf-8"), ".svg"


def _ensure_custom_icon(spec):
    """Write (if needed) and return the file:// URI of the cached icon.

    spec is '#rrggbb[;#rrggbb...]'. Filename embeds theme + colors +
    extension so the Nautilus icon cache (keyed by URI) stays correct.
    """
    parts = _split_color_spec(spec)
    if not parts:
        return ""
    slug = "-".join(parts)
    theme = re.sub(r"[^a-z0-9-]+", "",
                   str(_current_theme_name()).lower().replace("_", "-"))
    data, ext = _custom_icon_data(spec)
    if data is None:
        return ""
    path = os.path.join(_custom_cache_dir(), f"folder-{theme}-{slug}{ext}")
    if not os.path.exists(path):
        try:
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:
            log.error(f"custom icon write: {e}")
            return ""
    try:
        return Gio.File.new_for_path(path).get_uri()
    except Exception as e:
        log.error(f"custom icon uri: {e}")
        return ""


# ---------------------------------------------------------------------------
# Overlay composition — PNG/SVG image placed over the colored folder icon
# (port of the derived icon editor, fused into the custom color dialog).
# ---------------------------------------------------------------------------

CANVAS_SIZE = 256
_OVERLAY_MIMES = ("image/png", "image/jpeg", "image/webp", "image/svg+xml")


def _fit_square(img, size=CANVAS_SIZE):
    """Scale an image to fit inside a square canvas, centered on transparency."""
    from PIL import Image
    img = img.convert("RGBA")
    w, h = img.size
    scale = min(size / max(w, 1), size / max(h, 1))
    nw = max(1, min(size, int(round(w * scale))))
    nh = max(1, min(size, int(round(h * scale))))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((size - nw) // 2, (size - nh) // 2))
    return canvas


def _transform_overlay(img, opacity, scale_pct, rot_deg):
    """Scale, rotate and apply opacity to the overlay image."""
    from PIL import Image
    ov = img.convert("RGBA")
    w, h = ov.size
    f = scale_pct / 100.0
    nw = max(1, int(round(w * f)))
    nh = max(1, int(round(h * f)))
    if (nw, nh) != (w, h):
        ov = ov.resize((nw, nh), Image.Resampling.LANCZOS)
    rot = rot_deg % 360
    if rot:
        ov = ov.rotate(rot, resample=Image.Resampling.BICUBIC, expand=True)
    alpha = opacity / 100.0
    if alpha < 1.0:
        ov = ov.copy()
        ov.putalpha(ov.getchannel("A").point(lambda v: int(v * alpha)))
    return ov


def _svg_rasterize(svg_bytes):
    """Rasterize SVG bytes to a PIL RGBA image via GdkPixbuf."""
    from PIL import Image
    fd, path = tempfile.mkstemp(suffix=".svg")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(svg_bytes)
        pb = GdkPixbuf.Pixbuf.new_from_file(path)
        res = pb.save_to_bufferv("png", [], [])
        if isinstance(res, tuple):
            res = res[-1]
        return Image.open(io.BytesIO(res)).convert("RGBA")
    except Exception as e:
        log.error(f"svg rasterize: {e}")
        return None
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def _open_overlay(path):
    """Open a PNG/JPEG/WebP/SVG overlay as a PIL RGBA image."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".svg":
        try:
            with open(path, "rb") as f:
                return _svg_rasterize(f.read())
        except Exception as e:
            log.error(f"open svg overlay: {e}")
            return None
    try:
        from PIL import Image
        img = Image.open(path)
        img.load()
        return img.convert("RGBA")
    except Exception as e:
        log.error(f"open overlay: {e}")
        return None


def _base_pil_image(spec):
    """Colored folder icon as a 256×256 PIL RGBA image (best effort)."""
    try:
        from PIL import Image
    except Exception as e:
        log.error(f"PIL unavailable: {e}")
        return None
    parts = _split_color_spec(spec)
    if not parts:
        return None
    theme_svg = _theme_folder_svg_text()
    if theme_svg:
        svg = _tint_svg_multi(theme_svg, parts)
        if svg:
            img = _svg_rasterize(svg.encode("utf-8"))
            if img is not None:
                return _fit_square(img)
    variant_png = "" if theme_svg else _current_theme_png_path()
    if variant_png:
        data = _tint_png_file(variant_png, parts[0])
        if data:
            try:
                return _fit_square(
                    Image.open(io.BytesIO(data)).convert("RGBA"))
            except Exception as e:
                log.error(f"base png: {e}")
    svg = _folder_svg(parts[0])
    img = _svg_rasterize(svg.encode("utf-8"))
    if img is not None:
        return _fit_square(img)
    return None


def _compose_final(spec, state):
    """PNG bytes (256×256): colored folder icon + the layer stack."""
    try:
        base = _base_pil_image(spec)
        if base is None:
            return None
        if _ICON_EDITOR_AVAILABLE:
            return compose_layers(base, normalize_layers(state))
        # Fallback for a partial install: the legacy single-overlay state.
        canvas = base.copy()
        opath = (state or {}).get("overlay_path")
        if opath:
            ov = _open_overlay(opath)
            if ov is not None:
                ov = _transform_overlay(
                    ov,
                    int(state.get("opacity", 100)),
                    int(state.get("scale", 100)),
                    int(state.get("rotation", 0)),
                )
                cx = (CANVAS_SIZE - ov.width) // 2 + int(state.get("offset_x", 0))
                cy = (CANVAS_SIZE - ov.height) // 2 + int(state.get("offset_y", 0))
                canvas.alpha_composite(ov, (cx, cy))
        buf = io.BytesIO()
        try:
            canvas.save(buf, "PNG")
            return buf.getvalue()
        except Exception as e:
            log.error(f"compose icon: {e}")
            return None
    except Exception as e:
        log.error(f"compose icon: {e}")
        return None


def _ensure_overlay_icon(spec, state):
    """Cache (and return the file:// URI of) the composed PNG icon."""
    parts = _split_color_spec(spec)
    if not parts:
        return ""
    if _ICON_EDITOR_AVAILABLE:
        if not normalize_layers(state):
            return ""
    elif not (state or {}).get("overlay_path"):
        return ""
    slug = "-".join(parts)
    theme = re.sub(r"[^a-z0-9-]+", "",
                   str(_current_theme_name()).lower().replace("_", "-"))
    digest = hashlib.md5(
        json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()[:10]
    path = os.path.join(
        _custom_cache_dir(), f"folder-{theme}-{slug}-{digest}.png")
    if not os.path.exists(path):
        data = _compose_final(spec, state)
        if data is None:
            return ""
        try:
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:
            log.error(f"overlay icon write: {e}")
            return ""
    try:
        return Gio.File.new_for_path(path).get_uri()
    except Exception as e:
        log.error(f"overlay icon uri: {e}")
        return ""


def _overlay_state_path(path):
    key = hashlib.md5(str(path).encode("utf-8")).hexdigest()
    return os.path.join(_custom_cache_dir(), f"state-{key}.json")


def _save_overlay_state(path, state):
    try:
        with open(_overlay_state_path(path), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        log.error(f"save overlay state: {e}")


def _load_overlay_state(path):
    """Saved state of a folder (dict) or None.

    A corrupted/foreign file (e.g. a JSON list) must never reach the
    callers as a non-dict — `.get()` on it would raise inside Nautilus.
    """
    try:
        with open(_overlay_state_path(path), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _clear_overlay_state(path):
    try:
        os.unlink(_overlay_state_path(path))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Current colour of a folder — the editor must open with the colour the
# folder actually has, otherwise applying it back would repaint the folder
# with the grey default and lose the user's colour.
# ---------------------------------------------------------------------------

def _spec_from_custom_icon(uri):
    """Recover the colour spec from a cached custom-icon filename.

    'file:///…/folder-adwaita-3366ff-f5c211.svg'          -> '3366ff;f5c211'
    'file:///…/folder-adwaita-3366ff-f5c211-<digest>.png'  -> '3366ff;f5c211'
    'file:///…/folder-adwaita-3366ff.svg'                  -> '3366ff'
    Returns '' when the URI carries no recoverable hex parts.
    """
    if not uri:
        return ""
    try:
        name = str(uri).split("?")[0].split("#")[0].rstrip("/").split("/")[-1]
    except Exception:
        return ""
    if not name:
        return ""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    best = []
    run = []
    for part in stem.split("-"):
        if len(part) == 6 and all(c in "0123456789abcdef" for c in part.lower()):
            run.append(part.lower())
            continue
        if len(run) >= len(best):
            best = run
        run = []
    if len(run) >= len(best):
        best = run
    return ";".join(best)


def _folder_custom_attrs(path):
    """(custom_icon_uri, custom_icon_name) of the folder; ('', '') on failure."""
    try:
        info = Gio.File.new_for_path(path).query_info(
            "metadata::custom-icon,metadata::custom-icon-name", 0, None)
        uri = info.get_attribute_as_string("metadata::custom-icon") or ""
        name = info.get_attribute_as_string("metadata::custom-icon-name") or ""
        return str(uri), str(name)
    except Exception as e:
        log.error(f"custom attrs {path}: {e}")
        return "", ""


def _color_name_to_hex(name):
    """Theme colour name -> '#rrggbb' (empty when it cannot be resolved)."""
    if not name or not _CUSTOM_COLOR_AVAILABLE:
        return ""
    try:
        result = generate_color(name)
        if isinstance(result, list):
            result = result[0] if result else ""
        result = str(result)[:7]
        if len(result) == 7:
            return result.lower()
    except Exception as e:
        log.error(f"builtin color resolve: {e}")
    return ""


def _theme_color_entry(icon_name, colors):
    """The theme colour entry matching a themed icon name, or None."""
    if not icon_name:
        return None
    entries = colors or []
    for entry in entries:
        try:
            if entry.get("icon") == icon_name:
                return entry
        except Exception:
            continue
    tail = str(icon_name).rsplit("-", 1)[-1].lower()
    for entry in entries:
        try:
            if str(entry.get("name", "")).lower() == tail:
                return entry
        except Exception:
            continue
    return None


def _current_color_specs(path, colors=None):
    """The folder's CURRENT colour.

    Returns (spec, hexes):
      spec  — 'rrggbb' or 'rrggbb;rrggbb' ('' when unknown)
      hexes — list of '#rrggbb' (empty when unknown)

    Resolution order:
      1. the layer-state file's 'spec'
      2. the cached custom icon filename (via _spec_from_custom_icon)
      3. a themed colour icon (metadata::custom-icon-name)
      4. otherwise ('', [])
    """
    saved = _load_overlay_state(path)
    if isinstance(saved, dict):
        parts = _split_color_spec(saved.get("spec") or "")
        if parts:
            return ";".join(parts), ["#" + part for part in parts]

    uri, icon_name = _folder_custom_attrs(path)
    parts = _split_color_spec(_spec_from_custom_icon(uri))
    if parts:
        return ";".join(parts), ["#" + part for part in parts]

    entry = _theme_color_entry(icon_name, colors)
    if entry is not None:
        hex_color = _color_name_to_hex(entry.get("name", ""))
        if hex_color:
            return hex_color.lstrip("#"), ["#" + hex_color.lstrip("#")]

    return "", []


def _apply_icon_state(foldercolor, paths, hexes, layers, initial_hexes):
    """Apply the editor result to the folders.

    Returns True when everything was applied (or there was nothing to change).
    """
    paths = [p for p in (paths or []) if p]
    if not paths:
        return True
    spec = ";".join(str(h).lstrip("#").lower() for h in (hexes or []))
    initial_spec = ";".join(str(h).lstrip("#").lower()
                             for h in (initial_hexes or []))

    if not layers:
        # Nothing to change -> do not touch the folder at all. This is what
        # keeps a folder coloured through the normal colour menu from being
        # repainted with the editor's grey default.
        current = _load_overlay_state(paths[0])
        current_layers = None
        try:
            current_layers = normalize_layers(current) if current else []
        except Exception as e:
            log.error(f"normalize layers: {e}")
        # An unknown layer state is never a no-op: applying is safer than
        # silently dropping the layers of the folder.
        if current_layers is not None and not current_layers \
                and spec == initial_spec:
            return True

    ok = True
    for path in paths:
        try:
            if layers:
                state = {"spec": spec, "layers": layers}
                if foldercolor.set_custom_overlay_color(path, spec, state):
                    _save_overlay_state(path, state)
                else:
                    log.error(f"overlay color not applied: {path}")
                    ok = False
            else:
                result = foldercolor.set_custom_color(path, spec)
                if result is False:
                    log.error(f"custom color not applied: {path}")
                    ok = False
                else:
                    # Remember the colour spec so the editor opens with the
                    # right colours next time (no layers -> plain colour icon).
                    _save_overlay_state(path, {"spec": spec})
        except Exception as e:
            log.error(f"apply icon state {path}: {e}")
            ok = False
    return ok

# ---------------------------------------------------------------------------
# Dolphin folder colors — fallback chain:
#   1. Nautilus/user customization (metadata::custom-icon*)   -> kept as-is
#   2. Dolphin customization (<folder>/.directory Icon=)      -> applied here
#   3. Default theme icon                                    -> nothing to do
#
# Dolphin persists folder colors/icons as Icon= inside the folder's
# ".directory" Desktop Entry (INI) file. The value is either a themed icon
# name ("folder-red", "folder-blue", ...), a path ("./icon.png" or absolute)
# or a "file://" URI. Source: KIO KFileItem::iconFromDirectoryFile + Dolphin's
# SetFolderIconItemAction.
# ---------------------------------------------------------------------------

DOLPHIN_COLOR_MAP = {
    "folder-red":    "#da4453",
    "folder-yellow": "#f5c211",
    "folder-orange": "#f28200",
    "folder-green":  "#37a251",
    "folder-cyan":   "#2ac3de",
    "folder-blue":   "#3daee9",
    "folder-violet": "#9b59b6",
    "folder-brown":  "#9c6b3c",
    "folder-grey":   "#979797",
}


def _read_dolphin_folder_spec(path):
    """Best-effort Dolphin customization for a folder, or None.

    Reads <folder>/.directory (Desktop Entry INI) and returns a dict:
      {"kind": "color", "spec": "#rrggbb"}       — Icon=folder-<color>
      {"kind": "icon",  "name": "<theme icon>"}  — Icon=<icon name>
      {"kind": "file",  "uri": "file:///..."}    — Icon=<path or file://>
    """
    dot = os.path.join(path, ".directory")
    if not os.path.isfile(dot):
        return None
    try:
        cp = configparser.ConfigParser()
        with open(dot, "r", encoding="utf-8", errors="replace") as f:
            cp.read_file(f)
        icon = (cp.get("Desktop Entry", "Icon", fallback="") or "").strip()
    except Exception:
        return None
    if not icon:
        return None
    if icon.startswith("file://"):
        f = Gio.File.new_for_uri(icon)
        p = f.get_path()
        if p and os.path.isfile(p):
            return {"kind": "file", "uri": f.get_uri()}
        return None
    if icon.startswith("./") or os.path.isabs(icon):
        p = os.path.abspath(os.path.join(path, icon[2:])) if icon.startswith("./") else icon
        if os.path.isfile(p):
            return {"kind": "file", "uri": Gio.File.new_for_path(p).get_uri()}
        return None
    if icon in DOLPHIN_COLOR_MAP:
        return {"kind": "color", "spec": DOLPHIN_COLOR_MAP[icon]}
    return {"kind": "icon", "name": icon}


def _has_custom_metadata(path):
    """Rule 1: true when the extension/user already customized the folder."""
    try:
        item_aux = Gio.File.new_for_path(path)
        info = item_aux.query_info(
            "metadata::custom-icon,metadata::custom-icon-name", 0, None)
        return bool(info.get_attribute_as_string("metadata::custom-icon") or
                    info.get_attribute_as_string("metadata::custom-icon-name"))
    except Exception:
        return False


def _icon_theme_has(name):
    try:
        return Gtk.IconTheme.get_for_display(
            Gdk.Display.get_default()).has_icon(name)
    except Exception:
        return False


def _apply_dolphin_folder_spec(path, spec):
    """Persist the Dolphin-resolved icon as Nautilus metadata."""
    try:
        item_aux = Gio.File.new_for_path(path)
        info = item_aux.query_info(
            "metadata::custom-icon,metadata::custom-icon-name", 0, None)
    except Exception as e:
        log.error(f"dolphin spec query {path}: {e}")
        return False
    kind = spec.get("kind")
    if kind == "color":
        uri = _ensure_custom_icon(spec.get("spec", ""))
        if not uri:
            return False
        info.set_attribute_string("metadata::custom-icon", uri)
        info.set_attribute("metadata::custom-icon-name",
                           Gio.FileAttributeType.INVALID, 0)
    elif kind == "file":
        info.set_attribute_string("metadata::custom-icon", spec.get("uri", ""))
        info.set_attribute("metadata::custom-icon-name",
                           Gio.FileAttributeType.INVALID, 0)
    elif kind == "icon":
        if not _icon_theme_has(spec.get("name", "")):
            return False
        info.set_attribute_string("metadata::custom-icon-name",
                                  spec.get("name", ""))
        info.set_attribute("metadata::custom-icon",
                           Gio.FileAttributeType.INVALID, 0)
    else:
        return False
    try:
        item_aux.set_attributes_from_info(info, 0, None)
        return True
    except Exception as e:
        log.error(f"dolphin spec apply {path}: {e}")
        return False


# ---------------------------------------------------------------------------
# Blocklist — "Default" from the context menu must stick: the folder is
# recorded here so the auto fallback never re-applies the Dolphin color.
# ---------------------------------------------------------------------------

def _dolphin_blocklist_path():
    return os.path.join(_custom_cache_dir(), "dolphin-ignore.json")


_DOLPHIN_BLOCKLIST = None


def _dolphin_blocklist():
    global _DOLPHIN_BLOCKLIST
    if _DOLPHIN_BLOCKLIST is None:
        try:
            with open(_dolphin_blocklist_path(), "r", encoding="utf-8") as f:
                _DOLPHIN_BLOCKLIST = set(json.load(f))
        except Exception:
            _DOLPHIN_BLOCKLIST = set()
    return _DOLPHIN_BLOCKLIST


def _save_dolphin_blocklist():
    try:
        with open(_dolphin_blocklist_path(), "w", encoding="utf-8") as f:
            json.dump(sorted(_dolphin_blocklist()), f)
    except Exception as e:
        log.error(f"dolphin blocklist save: {e}")


class DolphinFolderManager:
    """Shared resolver state between the InfoProvider and the menu."""

    def __init__(self):
        self.seen    = set()
        self.blocked = _dolphin_blocklist()
        self.pending = {}

    def update_file_info_full(self, provider, handle, closure, file):
        if file.get_uri_scheme() != "file":
            return Nautilus.OperationResult.COMPLETE
        try:
            path = file.get_location().get_path()
            if not path or not file.is_directory():
                return Nautilus.OperationResult.COMPLETE
        except Exception:
            return Nautilus.OperationResult.COMPLETE
        if path in self.seen or path in self.blocked:
            return Nautilus.OperationResult.COMPLETE
        self.seen.add(path)
        self.pending[handle] = (provider, closure, path)
        GLib.idle_add(self._process, handle)
        return Nautilus.OperationResult.IN_PROGRESS

    def cancel_update(self, handle):
        self.pending.pop(handle, None)

    def _process(self, handle):
        job = self.pending.pop(handle, None)
        if job is None:
            return False
        provider, closure, path = job
        try:
            if not _has_custom_metadata(path):            # rule 1: user wins
                spec = _read_dolphin_folder_spec(path)    # rule 2: Dolphin
                if spec:
                    _apply_dolphin_folder_spec(path, spec)
        except Exception as e:
            log.error(f"dolphin folder {path}: {e}")
        finally:
            try:
                Nautilus.info_provider_update_complete_invoke(
                    closure, provider, handle, Nautilus.OperationResult.COMPLETE)
            except Exception as e:
                log.error(f"dolphin complete {path}: {e}")
        return False

    def block(self, path):
        self.blocked.add(path)
        _save_dolphin_blocklist()


_DOLPHIN_MANAGER = None


def _dolphin_manager():
    global _DOLPHIN_MANAGER
    if _DOLPHIN_MANAGER is None:
        _DOLPHIN_MANAGER = DolphinFolderManager()
    return _DOLPHIN_MANAGER


class DolphinColorProvider(GObject.GObject, Nautilus.InfoProvider):
    """Applies Dolphin folder colors as a fallback when the folder has no
    Nautilus/user customization of its own."""

    __gtype_name__ = "DolphinColorProvider"

    def __init__(self):
        super().__init__()
        self.manager = _dolphin_manager()

    def update_file_info_full(self, provider, handle, closure, file):
        return self.manager.update_file_info_full(provider, handle, closure, file)

    def cancel_update(self, provider, handle):
        self.manager.cancel_update(handle)

# ---------------------------------------------------------------------------
# i18n — same pattern as the other extensions: hardcoded tables per locale
# detected via locale.getlocale(). English is the fallback (identity).
# ---------------------------------------------------------------------------
try:
    from nautilus_i18n import resolve_locale
except ImportError:  # nautilus_i18n.py not installed next to this file
    def resolve_locale():
        return locale.getlocale()[0] or ""

_lang = resolve_locale()

if _lang.startswith("fr"):
    _T = {
        "Customize…": "Personnaliser…",
        "Customize icon…": "Personnaliser l'icône…",
        "Detect icon…": "Détecter une icône…",
        "Finds an icon file already inside the folder": "Recherche un fichier d'icône déjà présent dans le dossier",
        "Emblem": "Emblème",
        "Black": "Noir",
        "Blue": "Bleu",
        "Brown": "Marron",
        "Cyan": "Cyan",
        "Green": "Vert",
        "Grey": "Gris",
        "Magenta": "Magenta",
        "Orange": "Orange",
        "Pink": "Rose",
        "Purple": "Violet",
        "Red": "Rouge",
        "Violet": "Violette",
        "White": "Blanc",
        "Yellow": "Jaune",
        "Important": "Important",
        "In Progress": "En cours",
        "Favorite": "Favori",
        "Finished": "Terminé",
        "New": "Nouveau",
        "Default": "Par défaut",
        "Cancel": "Annuler",
        "Apply": "Appliquer",
        "Color %d": "Couleur %d",
        "Name or #hex — e.g. vermelho, Lucas": "Nom ou #hex — ex. rouge, Lucas",
        "Layers": "Calques",
        "Add image…": "Ajouter une image…",
        "Add text…": "Ajouter du texte…",
        "Add emblem…": "Ajouter un emblème…",
        "Choose an icon": "Choisir une icône",
        "No icon found": "Aucune icône trouvée dans ce dossier",
        "Remove layer": "Supprimer le calque",
        "Move up": "Monter",
        "Move down": "Descendre",
        "No layers": "Aucun calque",
        "Layer settings": "Réglages du calque",
        "No layer selected": "Aucun calque sélectionné",
        "Drag to reorder": "Glisser pour réorganiser",
        "Image": "Image",
        "Text": "Texte",
        "Font": "Police",
        "Size": "Taille",
        "Bold": "Gras",
        "Italic": "Italique",
        "Text color": "Couleur du texte",
        "Select emblem": "Choisir un emblème",
        "Type text": "Saisir le texte",
        "Insert emoji": "Insérer un emoji",
        "Opacity": "Opacité",
        "Scale": "Échelle",
        "X offset": "Décalage X",
        "Y offset": "Décalage Y",
        "Rotation": "Rotation",
        "Hue": "Teinte",
        "Saturation": "Saturation",
        "Pick image": "Choisir une image",
        "Images": "Images",
        "Cannot open this image.": "Impossible d'ouvrir cette image.",
        "Drag to move": "Glisser pour déplacer",
        "Scroll to resize": "Molette pour redimensionner",
        "Shift + Scroll to rotate": "Maj + Molette pour pivoter",
        "Alt + Scroll for opacity": "Alt + Molette pour l'opacité",
        "Ctrl + Scroll for hue": "Ctrl + Molette pour la teinte",
    }
elif _lang.startswith("de"):
    _T = {
        "Customize…": "Anpassen…",
        "Customize icon…": "Symbol anpassen…",
        "Detect icon…": "Symbol erkennen…",
        "Finds an icon file already inside the folder": "Sucht eine Symbol-Datei, die bereits im Ordner liegt",
        "Emblem": "Emblem",
        "Black": "Schwarz",
        "Blue": "Blau",
        "Brown": "Braun",
        "Cyan": "Cyan",
        "Green": "Grün",
        "Grey": "Grau",
        "Magenta": "Magenta",
        "Orange": "Orange",
        "Pink": "Rosa",
        "Purple": "Lila",
        "Red": "Rot",
        "Violet": "Violett",
        "White": "Weiß",
        "Yellow": "Gelb",
        "Important": "Wichtig",
        "In Progress": "In Bearbeitung",
        "Favorite": "Favorit",
        "Finished": "Fertig",
        "New": "Neu",
        "Default": "Standard",
        "Cancel": "Abbrechen",
        "Apply": "Anwenden",
        "Color %d": "Farbe %d",
        "Name or #hex — e.g. vermelho, Lucas": "Name oder #hex — z.B. rot, Lucas",
        "Layers": "Ebenen",
        "Add image…": "Bild hinzufügen…",
        "Add text…": "Text hinzufügen…",
        "Add emblem…": "Emblem hinzufügen…",
        "Choose an icon": "Symbol auswählen",
        "No icon found": "Kein Symbol im Ordner gefunden",
        "Remove layer": "Ebene entfernen",
        "Move up": "Nach oben",
        "Move down": "Nach unten",
        "No layers": "Keine Ebene",
        "Layer settings": "Ebeneneinstellungen",
        "No layer selected": "Keine Ebene ausgewählt",
        "Drag to reorder": "Ziehen zum Umsortieren",
        "Image": "Bild",
        "Text": "Text",
        "Font": "Schrift",
        "Size": "Größe",
        "Bold": "Fett",
        "Italic": "Kursiv",
        "Text color": "Textfarbe",
        "Select emblem": "Emblem auswählen",
        "Type text": "Text eingeben",
        "Insert emoji": "Emoji einfügen",
        "Opacity": "Deckkraft",
        "Scale": "Skalierung",
        "X offset": "Versatz X",
        "Y offset": "Versatz Y",
        "Rotation": "Drehung",
        "Hue": "Farbton",
        "Saturation": "Sättigung",
        "Pick image": "Bild auswählen",
        "Images": "Bilder",
        "Cannot open this image.": "Dieses Bild konnte nicht geöffnet werden.",
        "Drag to move": "Ziehen zum Verschieben",
        "Scroll to resize": "Scrollen zum Skalieren",
        "Shift + Scroll to rotate": "Umschalt + Scrollen zum Drehen",
        "Alt + Scroll for opacity": "Alt + Scrollen für Deckkraft",
        "Ctrl + Scroll for hue": "Strg + Scrollen für Farbton",
    }
elif _lang.startswith("es"):
    _T = {
        "Customize…": "Personalizar…",
        "Customize icon…": "Personalizar icono…",
        "Detect icon…": "Detectar icono…",
        "Finds an icon file already inside the folder": "Busca un archivo de icono que ya esté dentro de la carpeta",
        "Emblem": "Emblema",
        "Black": "Negro",
        "Blue": "Azul",
        "Brown": "Marrón",
        "Cyan": "Cian",
        "Green": "Verde",
        "Grey": "Gris",
        "Magenta": "Magenta",
        "Orange": "Naranja",
        "Pink": "Rosa",
        "Purple": "Morado",
        "Red": "Rojo",
        "Violet": "Violeta",
        "White": "Blanco",
        "Yellow": "Amarillo",
        "Important": "Importante",
        "In Progress": "En curso",
        "Favorite": "Favorito",
        "Finished": "Terminado",
        "New": "Nuevo",
        "Default": "Predeterminado",
        "Cancel": "Cancelar",
        "Apply": "Aplicar",
        "Color %d": "Color %d",
        "Name or #hex — e.g. vermelho, Lucas": "Nombre o #hex — ej. rojo, Lucas",
        "Layers": "Capas",
        "Add image…": "Añadir imagen…",
        "Add text…": "Añadir texto…",
        "Add emblem…": "Añadir emblema…",
        "Choose an icon": "Elegir un icono",
        "No icon found": "No se encontró ningún icono en esta carpeta",
        "Remove layer": "Quitar capa",
        "Move up": "Subir",
        "Move down": "Bajar",
        "No layers": "Sin capas",
        "Layer settings": "Ajustes de capa",
        "No layer selected": "Ninguna capa seleccionada",
        "Drag to reorder": "Arrastrar para reordenar",
        "Image": "Imagen",
        "Text": "Texto",
        "Font": "Fuente",
        "Size": "Tamaño",
        "Bold": "Negrita",
        "Italic": "Cursiva",
        "Text color": "Color del texto",
        "Select emblem": "Elegir emblema",
        "Type text": "Escribir texto",
        "Insert emoji": "Insertar emoji",
        "Opacity": "Opacidad",
        "Scale": "Escala",
        "X offset": "Desplazamiento X",
        "Y offset": "Desplazamiento Y",
        "Rotation": "Rotación",
        "Hue": "Tono",
        "Saturation": "Saturación",
        "Pick image": "Elegir imagen",
        "Images": "Imágenes",
        "Cannot open this image.": "No se pudo abrir esta imagen.",
        "Drag to move": "Arrastrar para mover",
        "Scroll to resize": "Rueda para redimensionar",
        "Shift + Scroll to rotate": "Mayús + Rueda para rotar",
        "Alt + Scroll for opacity": "Alt + Rueda para opacidad",
        "Ctrl + Scroll for hue": "Ctrl + Rueda para tono",
    }
elif _lang.startswith("pt"):
    _T = {
        "Customize…": "Personalizar…",
        "Customize icon…": "Personalizar ícone…",
        "Detect icon…": "Detectar ícone…",
        "Finds an icon file already inside the folder": "Procura um arquivo de ícone que já está dentro da pasta",
        "Emblem": "Emblema",
        "Black": "Preto",
        "Blue": "Azul",
        "Brown": "Marrom",
        "Cyan": "Ciano",
        "Green": "Verde",
        "Grey": "Cinza",
        "Magenta": "Magenta",
        "Orange": "Laranja",
        "Pink": "Rosa",
        "Purple": "Roxo",
        "Red": "Vermelho",
        "Violet": "Violeta",
        "White": "Branco",
        "Yellow": "Amarelo",
        "Important": "Importante",
        "In Progress": "Em andamento",
        "Favorite": "Favorito",
        "Finished": "Concluído",
        "New": "Novo",
        "Default": "Padrão",
        "Cancel": "Cancelar",
        "Apply": "Aplicar",
        "Color %d": "Cor %d",
        "Name or #hex — e.g. vermelho, Lucas": "Nome ou #hex — ex. vermelho, Lucas",
        "Layers": "Camadas",
        "Add image…": "Adicionar imagem…",
        "Add text…": "Adicionar texto…",
        "Add emblem…": "Adicionar emblema…",
        "Choose an icon": "Escolher um ícone",
        "No icon found": "Nenhum ícone encontrado nesta pasta",
        "Remove layer": "Remover camada",
        "Move up": "Subir",
        "Move down": "Descer",
        "No layers": "Sem camadas",
        "Layer settings": "Ajustes da camada",
        "No layer selected": "Nenhuma camada selecionada",
        "Drag to reorder": "Arrastar para reordenar",
        "Image": "Imagem",
        "Text": "Texto",
        "Font": "Fonte",
        "Size": "Tamanho",
        "Bold": "Negrito",
        "Italic": "Itálico",
        "Text color": "Cor do texto",
        "Select emblem": "Escolher emblema",
        "Type text": "Digitar texto",
        "Insert emoji": "Inserir emoji",
        "Opacity": "Opacidade",
        "Scale": "Escala",
        "X offset": "Deslocamento X",
        "Y offset": "Deslocamento Y",
        "Rotation": "Rotação",
        "Hue": "Matiz",
        "Saturation": "Saturação",
        "Pick image": "Escolher imagem",
        "Images": "Imagens",
        "Cannot open this image.": "Não foi possível abrir esta imagem.",
        "Drag to move": "Arrastar para mover",
        "Scroll to resize": "Scroll para redimensionar",
        "Shift + Scroll to rotate": "Shift + Scroll para girar",
        "Alt + Scroll for opacity": "Alt + Scroll para opacidade",
        "Ctrl + Scroll for hue": "Ctrl + Scroll para matiz",
    }
else:
    _T = {}


def _(s):
    return _T.get(s, s)

CUSTOMIZE = _("Customize…")
CUSTOMIZE_ICON_LABEL = _("Customize icon…")
EMBLEM = _("Emblem")


COLORS_ALL = {
    "black":   _("Black"),
    "blue":    _("Blue"),
    "brown":   _("Brown"),
    "cyan":    _("Cyan"),
    "green":   _("Green"),
    "grey":    _("Grey"),
    "magenta": _("Magenta"),
    "orange":  _("Orange"),
    "pink":    _("Pink"),
    "purple":  _("Purple"),
    "red":     _("Red"),
    "violet":  _("Violet"),
    "white":   _("White"),
    "yellow":  _("Yellow"),
}

EMBLEMS_ALL = {
    "emblem-important": _("Important"),
    "emblem-urgent":    _("In Progress"),
    "emblem-favorite":  _("Favorite"),
    "emblem-default":   _("Finished"),
    "emblem-new":       _("New"),
}

ICON_SIZES = {
    "extra-large": 256,
    "large":       128,
    "medium":       96,
    "small-plus":   64,
    "small":        48,
}

# ---------------------------------------------------------------------------
# FIX 2 : USER_DIRS était construit au niveau MODULE, avant l'initialisation
# complète de GLib/Nautilus → freeze garanti.
# On le construit à la demande, une seule fois, dans une fonction lazy.
# ---------------------------------------------------------------------------
_USER_DIRS = None

def _get_user_dirs():
    global _USER_DIRS
    if _USER_DIRS is None:
        _USER_DIRS = {
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_DESKTOP):      "desktop",
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_DOCUMENTS):    "documents",
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_DOWNLOAD):     "downloads",
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_MUSIC):        "music",
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_PICTURES):     "pictures",
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_PUBLIC_SHARE): "public",
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_TEMPLATES):    "templates",
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_VIDEOS):       "videos",
        }
    return _USER_DIRS


# ---------------------------------------------------------------------------
# FolderColor
# ---------------------------------------------------------------------------

class FolderColor:
    """Folder Color logic"""

    def __init__(self):
        self.is_modified = False
        self.colors      = []
        self.emblems     = []
        self.icon_size   = 96  # valeur par défaut safe

        # FIX 3 : Gio.Settings.new() planterait si le schéma n'est pas installé.
        # On enveloppe dans un try/except et on ne connecte le signal que si ça marche.
        try:
            self.gio_settings = Gio.Settings.new("org.gnome.nautilus.icon-view")
            self.icon_size    = ICON_SIZES.get(
                self.gio_settings.get_string("default-zoom-level"), 96)
            self.gio_settings.connect(
                "changed::default-zoom-level", self.on_changed_zoom_level)
        except Exception as e:
            log.warning(f"GSettings unavailable: {e}")
            self.gio_settings = None

        # FIX 4 : set_colors_theme() / set_emblems_theme() faisaient des lookups
        # d'icônes lourds dans __init__, bloquant le thread principal de Nautilus.
        # On les diffère au premier vrai usage via GLib.idle_add (hors init).
        GLib.idle_add(self._lazy_load_theme)

    def _lazy_load_theme(self):
        """Chargement différé des thèmes — exécuté quand Nautilus est idle."""
        log.debug("Lazy loading icon theme...")
        self.set_colors_theme()
        self.set_emblems_theme()
        log.debug(f"Theme loaded: {len(self.colors)} colors, {len(self.emblems)} emblems")
        return False  # ne pas répéter

    def on_changed_zoom_level(self, settings, key="default-zoom-level"):
        self.icon_size = ICON_SIZES.get(settings.get_string(key), 96)
        self.set_colors_theme()
        self.set_emblems_theme()

    def _get_icon(self, icon_name, is_color=True):
        """Lookup d'icône dans le thème courant."""
        try:
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            size_aux   = self.icon_size if is_color else 24
            icon       = icon_theme.lookup_icon(
                icon_name, None, size_aux, 1,
                Gtk.TextDirection.LTR, Gtk.IconLookupFlags.FORCE_REGULAR,
            )
            if icon_theme.has_icon(icon_name):
                return {"icon": Path(icon.get_icon_name()).stem,
                        "uri":  icon.get_file().get_uri()}
        except Exception:
            pass
        return {"icon": "", "uri": ""}

    def set_colors_theme(self):
        self.colors.clear()
        icon_options = [
            "folder-", "folder_color_", "folder_",          # thème courant
            "folder-", "folder_color_", "folder_",          # hicolor fallback
        ]
        for color in COLORS_ALL:
            for i, option in enumerate(icon_options):
                icon_aux = self._get_icon(option + color)
                if i < 3 and icon_aux["icon"] and "/hicolor/" not in icon_aux["uri"]:
                    self.colors.append({"icon": icon_aux["icon"],
                                        "name": color,
                                        "label": COLORS_ALL[color],
                                        "uri":   icon_aux["uri"]})
                    break
                if i >= 3 and icon_aux["icon"]:
                    self.colors.append({"icon": icon_aux["icon"],
                                        "name": color,
                                        "label": COLORS_ALL[color],
                                        "uri":   icon_aux["uri"]})
                    break

    def set_emblems_theme(self):
        self.emblems.clear()
        for emblem in EMBLEMS_ALL:
            icon_aux = self._get_icon(emblem, False)
            if icon_aux["icon"]:
                self.emblems.append({"icon": icon_aux["icon"],
                                     "label": EMBLEMS_ALL[emblem],
                                     "uri":   icon_aux["uri"]})

    def get_colors_theme(self):
        return self.colors

    def get_emblems_theme(self):
        return self.emblems

    def _get_skel_folder(self, folder, color, uri=True):
        user_dirs  = _get_user_dirs()
        color_param = color
        if folder in user_dirs:
            skel_color = "-".join([color["icon"], user_dirs[folder]])
            if "_" in skel_color:
                skel_color = skel_color.replace("-", "_")
            color_aux = self._get_icon(skel_color)
            if color_aux["icon"]:
                color_param = color_aux
        return color_param["uri"] if uri else color_param["icon"]

    def set_color(self, item, color, uri=True):
        if self.is_modified:
            self._set_restore_folder(item)
        try:
            item_aux = Gio.File.new_for_path(item)
            attr     = "metadata::custom-icon" if uri else "metadata::custom-icon-name"
            info     = item_aux.query_info(attr, 0, None)
            info.set_attribute_string(attr, self._get_skel_folder(item, color, uri))
            item_aux.set_attributes_from_info(info, 0, None)
            self._reload_icon(item)
        except Exception as e:
            log.error(f"set_color: {e}")

    def set_custom_color(self, item, spec):
        """Apply a generated color spec ('#rrggbb' or '#rrggbb;#rrggbb').

        Cached SVG via metadata::custom-icon. Clears metadata::custom-icon-name
        (mutually exclusive) so Nautilus never prefers a stale theme icon.
        """
        uri = _ensure_custom_icon(spec)
        if not uri:
            return
        if self.is_modified:
            self._set_restore_folder(item)
        try:
            item_aux = Gio.File.new_for_path(item)
            info     = item_aux.query_info(
                "metadata::custom-icon,metadata::custom-icon-name", 0, None)
            info.set_attribute_string("metadata::custom-icon", uri)
            info.set_attribute("metadata::custom-icon-name",
                               Gio.FileAttributeType.INVALID, 0)
            item_aux.set_attributes_from_info(info, 0, None)
            self._reload_icon(item)
        except Exception as e:
            log.error(f"set_custom_color: {e}")

    def set_custom_overlay_color(self, item, spec, state):
        uri = _ensure_overlay_icon(spec, state)
        if not uri:
            return False
        if self.is_modified:
            self._set_restore_folder(item)
        try:
            item_aux = Gio.File.new_for_path(item)
            info = item_aux.query_info(
                "metadata::custom-icon,metadata::custom-icon-name", 0, None)
            info.set_attribute_string("metadata::custom-icon", uri)
            info.set_attribute("metadata::custom-icon-name",
                               Gio.FileAttributeType.INVALID, 0)
            item_aux.set_attributes_from_info(info, 0, None)
            self._reload_icon(item)
            return True
        except Exception as e:
            log.error(f"set_custom_overlay_color: {e}")
            return False

    def set_emblem(self, item, emblem):
        try:
            emblems  = [emblem["icon"], None]
            item_aux = Gio.File.new_for_path(item)
            info     = item_aux.query_info("metadata::emblems", 0, None)
            info.set_attribute_stringv("metadata::emblems", emblems)
            item_aux.set_attributes_from_info(info, 0, None)
            self._reload_icon(item)
        except Exception as e:
            log.error(f"set_emblem: {e}")

    def set_restore(self, item):
        self._set_restore_folder(item)
        self._set_restore_emblem(item)
        self._reload_icon(item)

    def _set_restore_folder(self, item):
        try:
            item_aux = Gio.File.new_for_path(item)
            info     = item_aux.query_info("metadata::custom-icon-name", 0, None)
            info.set_attribute("metadata::custom-icon",
                               Gio.FileAttributeType.INVALID, 0)
            info.set_attribute("metadata::custom-icon-name",
                               Gio.FileAttributeType.INVALID, 0)
            item_aux.set_attributes_from_info(info, 0, None)
        except Exception as e:
            log.error(f"restore_folder: {e}")

    def _set_restore_emblem(self, item):
        try:
            item_aux = Gio.File.new_for_path(item)
            info     = item_aux.query_info("metadata::emblems", 0, None)
            info.set_attribute("metadata::emblems",
                               Gio.FileAttributeType.INVALID, 0)
            item_aux.set_attributes_from_info(info, 0, None)
        except Exception as e:
            print(f"[folder-color] restore_emblem error: {e}")

    def _reload_icon(self, item):
        try:
            os.utime(item, None)
        except Exception:
            pass

    def get_is_modified(self, items):
        for item in items:
            try:
                item_path = item.get_location().get_path()
                item_file = Gio.File.new_for_path(item_path)
                info      = item_file.query_info("metadata", 0, None)
                if (info.get_attribute_as_string("metadata::custom-icon-name") or
                        info.get_attribute_as_string("metadata::custom-icon") or
                        info.get_attribute_as_string("metadata::emblems")):
                    self.is_modified = True
                    return True
            except Exception:
                continue
        self.is_modified = False
        return False


# ---------------------------------------------------------------------------
# Nautilus Menu Provider
# ---------------------------------------------------------------------------

def _nautilus_window():
    """The active Nautilus window, or None (used as a dialog transient)."""
    app = Gtk.Application.get_default()
    if app is None:
        return None
    win = app.get_active_window()
    if win is not None:
        return win
    try:
        windows = app.get_windows()
    except Exception:
        return None
    return windows[0] if windows else None


class FolderColorMenu(GObject.GObject, Nautilus.MenuProvider):
    # FIX 5 : __gtype_name__ explicite pour éviter les conflits de types GLib
    # avec d'autres extensions ou entre rechargements.
    __gtype_name__ = "FolderColorMenu"

    def __init__(self):
        GObject.Object.__init__(self)
        self.all_dirs    = True
        self.foldercolor = FolderColor()
        self.theme       = ""
        # Ne pas appeler _load_theme() ici — déjà différé dans FolderColor.__init__

    def get_file_items(self, items):
        if not self._check_show_menu(items):
            return []

        # Rechargement du thème si changé depuis la dernière fois
        current_theme = Gtk.Settings.get_default().get_property("gtk-icon-theme-name")
        if self.theme != current_theme:
            self.theme = current_theme
            self.foldercolor.set_colors_theme()
            self.foldercolor.set_emblems_theme()

        log.debug(f"get_file_items: {len(items)} item(s), all_dirs={self.all_dirs}")
        return self._show_menu(items) or []

    def _check_show_menu(self, items):
        if not items:
            return False
        self.all_dirs = True
        for item in items:
            if item.get_uri_scheme() != "file":
                return False
            if not item.is_directory():
                self.all_dirs = False
        return True

    def _show_menu(self, items):
        colors     = self.foldercolor.get_colors_theme()
        emblems    = self.foldercolor.get_emblems_theme()
        is_modified = self.foldercolor.get_is_modified(items)

        if self.all_dirs and colors:
            top_menuitem = Nautilus.MenuItem(
                name="FolderColorMenu::customize", label=CUSTOMIZE, icon="color-picker")
        elif emblems:
            top_menuitem = Nautilus.MenuItem(
                name="FolderColorMenu::colors", label=EMBLEM, icon="color-picker")
        else:
            return []

        submenu = Nautilus.Menu()
        top_menuitem.set_submenu(submenu)

        # Couleurs
        if self.all_dirs:
            for color in colors:
                item = Nautilus.MenuItem(
                    name="FolderColorMenu::color_" + color["icon"],
                    label=color["label"],
                    icon=color["icon"],
                )
                item.connect("activate", self._menu_activate_color, items, color)
                submenu.append_item(item)

            if _ICON_EDITOR_AVAILABLE:
                item = Nautilus.MenuItem(
                    name="FolderColorMenu::customize_icon",
                    label=CUSTOMIZE_ICON_LABEL,
                    icon="color-picker",
                )
                item.connect("activate", self._menu_activate_custom_color, items)
                submenu.append_item(item)

                item = Nautilus.MenuItem(
                    name="FolderColorMenu::detect_icon",
                    label=_("Detect icon…"),
                    icon="edit-find",
                )
                item.connect("activate", self._menu_activate_detect_icon, items)
                submenu.append_item(item)

        # Emblèmes
        if emblems:
            if self.all_dirs and colors:
                submenu.append_item(Nautilus.MenuItem(
                    name="FolderColorMenu::sep_emblems",
                    label="―――", sensitive=False))
            for emblem in emblems:
                item = Nautilus.MenuItem(
                    name="FolderColorMenu::emblem_" + emblem["icon"],
                    label=emblem["label"],
                    icon=emblem["icon"],
                )
                item.connect("activate", self._menu_activate_emblem, items, emblem)
                submenu.append_item(item)

        # Restaurer
        if is_modified:
            submenu.append_item(Nautilus.MenuItem(
                name="FolderColorMenu::sep_restore",
                label="―――", sensitive=False))
            item = Nautilus.MenuItem(
                name="FolderColorMenu::restore",
                label=_("Default"), icon="undo")
            item.connect("activate", self._menu_activate_restore, items)
            submenu.append_item(item)

        return (top_menuitem,)

    def _menu_activate_color(self, menu, items, color):
        # Built-in colors go through the exact same pipeline as custom
        # colors: English name -> generate_color() -> tinted theme icon.
        hex_color = ""
        if _CUSTOM_COLOR_AVAILABLE:
            try:
                result = generate_color(color.get("name", ""))
                if isinstance(result, list):
                    result = result[0] if result else ""
                result = str(result)[:7]
                if len(result) == 7:
                    hex_color = result.lower()
            except Exception as e:
                log.error(f"builtin color resolve: {e}")
        for item in items:
            if item.is_gone():
                continue
            path = item.get_location().get_path()
            if hex_color:
                self.foldercolor.set_custom_color(path, hex_color)
            else:
                self.foldercolor.set_color(path, color)

    def _menu_activate_emblem(self, menu, items, emblem):
        for item in items:
            if not item.is_gone():
                self.foldercolor.set_emblem(item.get_location().get_path(), emblem)

    def _menu_activate_custom_color(self, menu, items):
        paths = [item.get_location().get_path()
                 for item in items if not item.is_gone()]
        if not paths:
            return
        self._show_custom_color_dialog(paths)

    def _menu_activate_detect_icon(self, menu, items):
        """Detect an icon inside the folder and add it to the editor."""
        paths = [item.get_location().get_path()
                 for item in items if not item.is_gone()]
        paths = [p for p in paths if p]
        if not paths:
            return

        def on_chosen(path):
            if not path:
                return
            self._show_custom_color_dialog(paths, extra_image=path)

        try:
            # Every selected folder is scanned and their candidates are
            # offered in one list; the chosen image becomes a layer of the
            # state that is applied to the whole selection (the editor's
            # model is one state for all selected folders).
            detect_icon_for_folder(paths, tr=_, on_chosen=on_chosen,
                                   parent=_nautilus_window())
        except Exception as e:
            log.error(f"detect icon: {e}")

    @staticmethod
    def _rgba_to_hex(rgba):
        try:
            return "#{:02x}{:02x}{:02x}".format(
                max(0, min(255, round(rgba.red * 255))),
                max(0, min(255, round(rgba.green * 255))),
                max(0, min(255, round(rgba.blue * 255))))
        except Exception:
            return ""

    @staticmethod
    def _hex_to_rgba(hex_color):
        rgba = Gdk.RGBA()
        try:
            if rgba.parse(str(hex_color)):
                return rgba
        except Exception:
            pass
        return None

    @staticmethod
    def _hexes_from_state(saved, row_count):
        """Rebuild the per-shape colour list from a saved state."""
        hexes = ["#808080"] * row_count
        if not saved or not isinstance(saved, dict):
            return hexes
        parts = _split_color_spec(saved.get("spec") or "")
        if not parts:
            return hexes
        if len(parts) > 1:
            hexes = ["#" + part for part in parts[:row_count]]
            hexes += ["#808080"] * (row_count - len(hexes))
        else:
            hexes = ["#" + parts[0]] * row_count
        return hexes

    def _show_custom_color_dialog(self, paths, extra_image=None):
        """Layer editor: per-shape colours + image/text/emblem layers.

        ``extra_image`` is an image picked by the "Detect icon…" flow: it is
        added as the topmost layer (index 0) before the editor opens.
        """
        if not _ICON_EDITOR_AVAILABLE:
            log.error("icon editor unavailable")
            return

        theme_svg = _theme_folder_svg_text()
        _root, shapes = _svg_shapes(theme_svg) if theme_svg else (None, [])
        row_count = len(shapes) if shapes else 1

        saved = _load_overlay_state(paths[0]) or {}
        # The editor must open with the colour the folder actually has,
        # otherwise applying it back would repaint it with the grey default.
        spec, _current_hexes = _current_color_specs(
            paths[0], self.foldercolor.get_colors_theme())
        hexes = self._hexes_from_state({"spec": spec} if spec else {}, row_count)
        layers = normalize_layers(saved)
        if extra_image:
            # scale 70 mirrors folder_icon_editor._DETECTED_SCALE, which is
            # private to that module (not exported), so the literal is kept
            # in sync by hand.
            layers = normalize_layers(
                [default_layer("image", path=extra_image, scale=70)] + layers)

        def on_apply(new_hexes, new_layers):
            try:
                return _apply_icon_state(self.foldercolor, paths, new_hexes,
                                         new_layers, hexes)
            except Exception as e:
                log.error(f"apply icon state: {e}")
                return False

        open_editor(
            title=CUSTOMIZE_ICON_LABEL,
            row_count=row_count,
            hexes=hexes,
            layers=layers,
            base_builder=_base_pil_image,
            emblem_icons=self.foldercolor.get_emblems_theme(),
            tr=_,
            on_apply=on_apply,
            scan_dir=paths,
        )

    def _menu_activate_restore(self, menu, items):
        manager = _dolphin_manager()
        for item in items:
            if not item.is_gone():
                path = item.get_location().get_path()
                self.foldercolor.set_restore(path)
                manager.block(path)
