"""Layer-based folder icon editor (GTK4).

Used by the "Folder Color Revival" Nautilus extension. The editor paints a
stack of layers over the themed folder icon:

  * image  — an arbitrary picture (PNG/JPEG/WebP/SVG)
  * text   — any font installed on the machine, rendered through PangoCairo
  * emblem — an icon of the current icon theme

Every layer carries its own transform (scale, rotation, hue, saturation,
opacity, offset). The module is intentionally standalone: it never imports
"folder-color-revival" (that would be circular) and every string is passed
through the ``tr`` callable supplied by the caller.

It can also *detect* an icon that already lives inside the customised
folder: the images whose name looks like an icon name -- in any language
-- are ranked and the user picks the one to use.
"""

import io
import hashlib
import logging
import math
import os
import re
import sys
import unicodedata
from collections import OrderedDict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, Pango

log = logging.getLogger("folder-color-revival.icon-editor")

try:
    from PIL import Image, ImageEnhance, ImageChops

    _PIL_AVAILABLE = True
except Exception as e:  # pragma: no cover - PIL is a hard dependency
    log.warning(f"PIL unavailable: {e}")
    _PIL_AVAILABLE = False


CANVAS_SIZE = 256
PREVIEW_SIZE = 128

LAYER_IMAGE = "image"
LAYER_TEXT = "text"
LAYER_EMBLEM = "emblem"

_LAYER_TYPES = (LAYER_IMAGE, LAYER_TEXT, LAYER_EMBLEM)

_TYPE_ICONS = {
    LAYER_IMAGE: "image-x-generic-symbolic",
    LAYER_TEXT: "text-x-generic-symbolic",
    LAYER_EMBLEM: "emblem-symbolic-link",
}

_DRAG_ICON = "list-drag-handle-symbolic"

_TYPE_LABELS = {
    LAYER_IMAGE: "Image",
    LAYER_TEXT: "Text",
    LAYER_EMBLEM: "Emblem",
}

# Every layer always carries exactly these keys.
_LAYER_FIELDS = (
    "type", "name", "path", "text", "font", "font_size", "bold", "italic",
    "color", "emblem", "emblem_uri", "opacity", "scale", "rotation",
    "offset_x", "offset_y", "hue", "saturation",
    "monochrome", "invert", "threshold", "mono_color",
    "mask_mode", "mask_path",
)

# The fields that describe WHAT a layer shows (the transform fields below
# are applied afterwards and must not take part in the render cache key).
_CONTENT_FIELDS = (
    "type", "path", "text", "font", "font_size", "bold", "italic", "color",
    "emblem", "emblem_uri",
    "monochrome", "invert", "threshold", "mono_color",
    "mask_mode", "mask_path",
)

_DEFAULTS = {
    "type": LAYER_IMAGE,
    "name": "",
    "path": "",
    "text": "",
    "font": "Sans",
    "font_size": 64,
    "bold": False,
    "italic": False,
    "color": "#ffffff",
    "emblem": "",
    "emblem_uri": "",
    "opacity": 100,
    "scale": 100,
    "rotation": 0,
    "offset_x": 0,
    "offset_y": 0,
    "hue": 0,
    "saturation": 0,
    # Monochrome mode (#32): when True the layer is converted to grayscale,
    # thresholded and tinted with mono_color; invert flips the threshold.
    "monochrome": False,
    "invert": False,
    "threshold": 128,
    "mono_color": "#ffffff",
    # Mask mode (#33): "none" = no mask, "auto" = derive from base alpha so
    # the overlay is clipped to the folder shape, "custom" = user PNG/SVG.
    "mask_mode": "none",
    "mask_path": "",
}

_RANGES = {
    "opacity": (0, 100),
    "scale": (10, 400),
    "rotation": (-180, 180),
    "offset_x": (-CANVAS_SIZE, CANVAS_SIZE),
    "offset_y": (-CANVAS_SIZE, CANVAS_SIZE),
    "hue": (-180, 180),
    "saturation": (-100, 100),
    "threshold": (0, 255),
    "font_size": (8, 256),
}

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")

# Editor scopes. The "folder" scope writes metadata::custom-icon on the
# selected folders; the "global" one installs a derived icon theme (#21).
SCOPE_FOLDER = "folder"
SCOPE_GLOBAL = "global"

# Persisted state schema version of a folder scope. Bumped when a key changes
# meaning; new optional keys do not bump it (#29).
STATE_VERSION = 2

# Imported images: a picture is rejected before it is decoded when it is
# bigger than this, so a stray 500 MB TIFF cannot freeze the dialog (#30).
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_SIDE = 12000

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".bmp", ".gif",
               ".tif", ".tiff")

# Magic numbers of the formats the editor really renders. SVG is text, so it
# is sniffed separately.
_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
)

# Theme sub-directories that really hold icons (Adwaita & friends).
_THEME_SUBDIRS = (
    "", "48x48", "64x64", "256x256", "16x16", "scalable", "scalable/status",
    "scalable/actions", "scalable/emblems", "emblems", "symbolic",
    "symbolic/legacy",
)

_OPEN_EDITORS = []
_CSS_APPLIED = False

_RENDER_CACHE = OrderedDict()
_RENDER_CACHE_MAX = 32

_EMBLEM_PIXBUFS = OrderedDict()
_EMBLEM_PIXBUF_MAX = 32

_GENERATE_COLOR = None
_GENERATE_COLOR_LOOKED_UP = False


# ---------------------------------------------------------------------------
# Layer schema
# ---------------------------------------------------------------------------

def _clamp_int(value, key):
    """Clamp ``value`` into the range of ``key``; invalid values -> default."""
    low, high = _RANGES[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        value = _DEFAULTS[key]
    elif not math.isfinite(value):
        # NaN / Infinity (JSON allows both) are not usable numbers.
        value = _DEFAULTS[key]
    return max(low, min(high, int(round(value))))


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _normalize_hex(value):
    """'#rgb' / '#rrggbb' (with or without '#') -> '#rrggbb', or ''."""
    match = _HEX_RE.match(str(value or "").strip())
    if not match:
        return ""
    digits = match.group(1).lower()
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits


def _derive_name(layer):
    """Human readable name of a layer (may be empty)."""
    if layer.get("type") == LAYER_EMBLEM:
        return str(layer.get("emblem") or "")
    return ""


def default_layer(kind, **overrides):
    """A fresh layer of the given kind with every schema key present."""
    kind = kind if kind in _LAYER_TYPES else LAYER_IMAGE
    layer = dict(_DEFAULTS)
    layer["type"] = kind
    if kind == LAYER_TEXT:
        layer["text"] = "Text"
    elif kind == LAYER_EMBLEM:
        # Emblems are badge-sized by default (25% of the 256px canvas).
        layer["scale"] = 25
    for key, value in overrides.items():
        if key in _DEFAULTS:
            layer[key] = value
    if not layer["name"]:
        layer["name"] = _derive_name(layer)
    return layer


def _legacy_to_layer(state):
    """Migrate the pre-layers state file (single overlay image)."""
    layer = default_layer(LAYER_IMAGE)
    layer["path"] = str(state.get("overlay_path") or "")
    for key in ("opacity", "scale", "offset_x", "offset_y", "rotation"):
        value = state.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            layer[key] = value
    layer["name"] = _derive_name(layer)
    return layer


def _normalize_layer(raw):
    """Normalise one raw layer dict into the strict schema."""
    kind = raw.get("type")
    if kind not in _LAYER_TYPES:
        if "text" in raw:
            kind = LAYER_TEXT
        elif "emblem" in raw:
            kind = LAYER_EMBLEM
        else:
            kind = LAYER_IMAGE
    layer = default_layer(kind)
    for key in _LAYER_FIELDS:
        if key in raw and key != "type":
            layer[key] = raw[key]
    layer["type"] = kind
    layer["name"] = str(layer["name"] or "")
    layer["path"] = str(layer["path"] or "")
    layer["text"] = str(layer["text"] or "")
    layer["font"] = str(layer["font"] or "Sans")
    layer["emblem"] = str(layer["emblem"] or "")
    layer["emblem_uri"] = str(layer["emblem_uri"] or "")
    layer["color"] = _normalize_hex(layer["color"]) or _DEFAULTS["color"]
    layer["bold"] = _as_bool(layer["bold"])
    layer["italic"] = _as_bool(layer["italic"])
    for key in _RANGES:
        layer[key] = _clamp_int(layer[key], key)
    if not layer["name"]:
        layer["name"] = _derive_name(layer)
    return layer


def normalize_layers(raw):
    """Normalise any stored layer payload into a list of schema dicts.

    Accepts ``None``, a list of layer dicts, ``{"layers": [...]}`` and the
    legacy single-overlay state dict.
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        if isinstance(raw.get("layers"), list):
            return [_normalize_layer(item) for item in raw["layers"]
                    if isinstance(item, dict)]
        if "overlay_path" in raw:
            # Legacy state: one image layer — but only when it has a picture.
            layer = _normalize_layer(_legacy_to_layer(raw))
            return [layer] if layer.get("path") else []
        if raw.get("type") in _LAYER_TYPES:
            return [_normalize_layer(raw)]
        return []
    if isinstance(raw, (list, tuple)):
        return [_normalize_layer(item) for item in raw if isinstance(item, dict)]
    return []


def normalize_spec(value):
    """'#rrggbb[;…]' -> 'rrggbb[;…]'; '' when any part is invalid."""
    parts = []
    for chunk in str(value or "").split(";"):
        slug = chunk.strip().lstrip("#").lower()
        if len(slug) != 6 or any(c not in "0123456789abcdef" for c in slug):
            return ""
        parts.append(slug)
    return ";".join(parts)


def pack_state(spec, layers, theme="", base_image=None):
    """Folder state written next to the cached icon (versioned, #29).

    Legacy readers only look at ``spec`` and ``layers``, so the new keys are
    additive: an older extension can still open the file. ``base_image`` is
    the path of a custom base image (#30).
    """
    return {
        "version": STATE_VERSION,
        "spec": normalize_spec(spec),
        "theme": str(theme or ""),
        "layers": normalize_layers(layers),
        "base_image": str(base_image or ""),
    }


def normalize_state(raw):
    """Coerce a stored/foreign folder state into the current schema.

    Accepts the current dict, the legacy single-overlay state and anything
    broken; an unknown or older version is upgraded, never discarded, so an
    icon already applied keeps its colours and layers.
    """
    state = raw if isinstance(raw, dict) else {}
    theme = state.get("theme")
    base_image = state.get("base_image")
    return {
        "version": STATE_VERSION,
        "spec": normalize_spec(state.get("spec")),
        "theme": str(theme) if isinstance(theme, str) and theme else "",
        "layers": normalize_layers(state),
        "base_image": str(base_image or ""),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _pixbuf_to_png(pixbuf):
    """GdkPixbuf -> PNG bytes (or b"" on failure)."""
    try:
        result = pixbuf.save_to_bufferv("png", [], [])
    except Exception as e:
        log.error(f"pixbuf export: {e}")
        return b""
    if isinstance(result, tuple):
        result = result[-1]
    return result or b""


def _pixbuf_to_texture(pixbuf):
    """GdkPixbuf -> Gdk.Texture.

    ``Gdk.Texture.new_for_pixbuf()`` is deprecated in GTK4; re-encoding the
    pixbuf as PNG and handing the bytes over keeps the non-deprecated API.
    """
    if pixbuf is None:
        return None
    data = _pixbuf_to_png(pixbuf)
    if not data:
        return None
    try:
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(bytes(data)))
    except Exception as e:
        log.error(f"texture from bytes: {e}")
        return None


def _pil_from_png(data):
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        log.error(f"png decode: {e}")
        return None


def _rasterize_svg(path, size=None):
    """SVG file -> PIL RGBA image through GdkPixbuf."""
    try:
        if size:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
        else:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    except Exception as e:
        log.error(f"svg rasterize failed ({path}): {e}")
        return None
    data = _pixbuf_to_png(pixbuf)
    if not data:
        return None
    return _pil_from_png(data)


def _open_image(path, size=None):
    """PNG/JPEG/WebP/SVG file -> PIL RGBA image."""
    if not path or not os.path.isfile(path):
        log.error(f"image not found: {path}")
        return None
    if os.path.splitext(path)[1].lower() == ".svg":
        return _rasterize_svg(path, size)
    try:
        img = Image.open(path)
        img.load()
        img = img.convert("RGBA")
    except Exception as e:
        log.error(f"open image failed ({path}): {e}")
        return None
    if size:
        img = _fit_square(img, size)
    return img


def _fit_square(img, size=CANVAS_SIZE):
    """Scale an image to fit inside a square canvas, centred on transparency."""
    img = img.convert("RGBA")
    width, height = img.size
    factor = min(size / max(width, 1), size / max(height, 1))
    new_width = max(1, min(size, int(round(width * factor))))
    new_height = max(1, min(size, int(round(height * factor))))
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((size - new_width) // 2,
                                 (size - new_height) // 2))
    return canvas


def _local_file_path(candidate):
    """A local file path for a path/URI string, or ''."""
    candidate = str(candidate or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("file://"):
        try:
            path = Gio.File.new_for_uri(candidate).get_path()
        except Exception as e:
            log.error(f"emblem uri decode failed ({candidate}): {e}")
            path = ""
        return path if path and os.path.isfile(path) else ""
    if os.path.sep in candidate or candidate.startswith("."):
        path = os.path.abspath(os.path.expanduser(candidate))
        return path if os.path.isfile(path) else ""
    return ""


def image_problem(path):
    """Why ``path`` cannot be used as an image layer ('' when it can).

    Checks the real content, not just the extension: a renamed ``.png`` that
    is actually a script or an archive must never reach the renderer.
    """
    try:
        if not path or not os.path.isfile(path):
            return "missing"
        size = os.path.getsize(path)
        if size <= 0:
            return "empty"
        if size > MAX_IMAGE_BYTES:
            return "too-large"
        with open(path, "rb") as handle:
            head = handle.read(1024)
    except OSError as e:
        log.debug(f"image probe {path}: {e}")
        return "unreadable"
    lowered = head.lstrip()[:512].lower()
    if b"<svg" in lowered:
        return ""
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return ""
    for magic, _kind in _IMAGE_MAGIC:
        if head.startswith(magic):
            return ""
    return "unsupported"


def parse_image_uris(payload):
    """Image paths carried by a drag/clipboard payload.

    Accepts a newline separated ``text/uri-list`` string, a list of strings
    and a ``Gdk.FileList``. Only existing, genuinely supported local images
    survive; remote URIs are never fetched and directories are dropped.
    """
    candidates = []

    def collect(item, depth=0):
        if item is None or depth > 3:
            return
        if isinstance(item, (list, tuple)):
            for entry in item:
                collect(entry, depth + 1)
            return
        if isinstance(item, str):
            for line in item.replace("\r", "\n").split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    candidates.append(line)
            return
        get_files = getattr(item, "get_files", None)
        if callable(get_files):
            try:
                collect(list(get_files() or []), depth + 1)
                return
            except Exception as e:
                log.debug(f"drag file list: {e}")
        get_uri = getattr(item, "get_uri", None)
        if callable(get_uri):
            try:
                uri = get_uri()
            except Exception:
                uri = ""
            if uri:
                candidates.append(uri)

    collect(payload)
    paths = []
    for candidate in candidates:
        path = _local_file_path(candidate)
        if not path or path in paths:
            continue
        if image_problem(path):
            log.warning(f"ignored dropped image {path}: {image_problem(path)}")
            continue
        paths.append(path)
    return paths


def _drop_value_types():
    """GTypes an image drop may arrive in (file list first, then URI text)."""
    types = [GObject.TYPE_STRING]
    files = getattr(Gdk, "FileList", None)
    if files is not None:
        types.insert(0, files)
    return types


def _cache_image_bytes(data, ext=".png"):
    """Persist pasted image bytes in the cache; returns the path or ''."""
    if not data:
        return ""
    try:
        digest = hashlib.md5(data).hexdigest()[:12]
        base = os.path.join(GLib.get_user_cache_dir(), "folder-color", "pasted")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "paste-" + digest + ext)
        if not os.path.exists(path):
            with open(path, "wb") as handle:
                handle.write(data)
        return path
    except Exception as e:
        log.error(f"cache pasted image: {e}")
        return ""




def _icon_theme_file(name):
    """Absolute path of a themed icon, or '' when it cannot be resolved."""
    try:
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        paintable = theme.lookup_icon(
            name, None, CANVAS_SIZE, 1, Gtk.TextDirection.LTR,
            Gtk.IconLookupFlags.FORCE_REGULAR)
        gfile = paintable.get_file() if paintable is not None else None
        path = gfile.get_path() if gfile is not None else ""
    except Exception as e:
        log.error(f"icon theme lookup failed ({name}): {e}")
        path = ""
    if path and os.path.isfile(path):
        return path
    return _search_icon_theme(name)


def _search_icon_theme(name):
    """Fallback: look the icon up in the theme search path."""
    try:
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        dirs = list(theme.get_search_path())
    except Exception as e:
        log.error(f"theme search path: {e}")
        return ""
    for base in dirs:
        for sub in _THEME_SUBDIRS:
            for ext in (".png", ".svg"):
                candidate = os.path.join(base, sub, name + ext)
                if os.path.isfile(candidate):
                    return candidate
    return ""


def _resolve_emblem_path(layer):
    """The icon file of an emblem layer ('' when it cannot be found).

    1. an explicit path/URI stored on the layer wins;
    2. ``name-symbolic`` in the icon theme (vector, crisp);
    3. the plain ``name`` in the icon theme;
    4. a manual search in the theme directories.
    """
    for candidate in (str(layer.get("emblem_uri") or ""),
                      str(layer.get("emblem") or "")):
        path = _local_file_path(candidate)
        if path:
            return path
    name = str(layer.get("emblem") or "").strip()
    if not name:
        return ""
    for candidate in (f"{name}-symbolic", name):
        path = _icon_theme_file(candidate)
        if path:
            return path
    return _search_icon_theme(name)


def _emblem_pixbuf(layer):
    """Small pixbuf of an emblem layer (used by the layer rows)."""
    path = _resolve_emblem_path(layer)
    if not path:
        return None
    cached = _EMBLEM_PIXBUFS.get(path)
    if cached is not None:
        _EMBLEM_PIXBUFS.move_to_end(path)
        return cached
    pixbuf = None
    loaders = (lambda: GdkPixbuf.Pixbuf.new_from_file_at_size(path, 24, 24),
               lambda: GdkPixbuf.Pixbuf.new_from_file(path))
    for loader in loaders:
        try:
            pixbuf = loader()
            break
        except Exception as e:
            log.debug(f"emblem pixbuf ({path}): {e}")
    if pixbuf is not None:
        _EMBLEM_PIXBUFS[path] = pixbuf
        while len(_EMBLEM_PIXBUFS) > _EMBLEM_PIXBUF_MAX:
            _EMBLEM_PIXBUFS.popitem(last=False)
    return pixbuf


def _render_emblem(layer):
    """Emblem icon of the current theme -> PIL RGBA image."""
    path = _resolve_emblem_path(layer)
    if not path:
        log.error(f"emblem not found: {layer.get('emblem')}")
        return None
    if os.path.splitext(path)[1].lower() == ".svg":
        img = _rasterize_svg(path, CANVAS_SIZE)
    else:
        img = _open_image(path)
    if img is None:
        return None
    return _fit_square(img, CANVAS_SIZE)


def _surface_to_image(surface):
    """cairo ARGB32 surface -> PIL RGBA image."""
    width = surface.get_width()
    height = surface.get_height()
    stride = surface.get_stride()
    data = bytes(surface.get_data())
    if sys.byteorder == "little":
        try:
            return Image.frombuffer("RGBA", (width, height), data, "raw",
                                    "BGRa", stride, 1)
        except Exception as e:
            log.error(f"surface to image: {e}")
    import tempfile
    handle, path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    try:
        surface.write_to_png(path)
        img = Image.open(path)
        img.load()
        return img.convert("RGBA")
    except Exception as e:
        log.error(f"surface to image (png): {e}")
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _render_text(layer):
    """Text layer -> PIL RGBA image (any installed font, via PangoCairo)."""
    text = str(layer.get("text") or "")
    if not text.strip():
        return None
    try:
        import cairo
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import PangoCairo
    except Exception as e:
        log.warning(f"cairo/PangoCairo unavailable, text layers disabled: {e}")
        return None
    size = _clamp_int(layer.get("font_size"), "font_size")
    family = str(layer.get("font") or "Sans")
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_absolute_size(size * Pango.SCALE)
    if layer.get("bold"):
        desc.set_weight(Pango.Weight.BOLD)
    if layer.get("italic"):
        desc.set_style(Pango.Style.ITALIC)

    try:
        probe = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        probe_ctx = cairo.Context(probe)
        layout = PangoCairo.create_layout(probe_ctx)
        layout.set_font_description(desc)
        layout.set_text(text, -1)
        width, height = layout.get_pixel_size()
        if width <= 0 or height <= 0:
            return None
        pad = max(2, size // 6)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                     width + pad * 2, height + pad * 2)
        ctx = cairo.Context(surface)
        real = PangoCairo.create_layout(ctx)
        real.set_font_description(desc)
        real.set_text(text, -1)
        red, green, blue, alpha = _hex_to_rgba(layer.get("color"))
        ctx.set_source_rgba(red, green, blue, alpha)
        ctx.move_to(pad, pad)
        PangoCairo.show_layout(ctx, real)
        surface.flush()
    except Exception as e:
        log.error(f"text rendering failed: {e}")
        return None
    return _surface_to_image(surface)


def render_layer(layer):
    """Render a layer dict into a PIL RGBA image (None on failure)."""
    if not isinstance(layer, dict):
        return None
    if not _PIL_AVAILABLE:
        log.error("PIL unavailable — cannot render layers")
        return None
    kind = layer.get("type")
    try:
        if kind == LAYER_TEXT:
            return _render_text(layer)
        if kind == LAYER_EMBLEM:
            return _render_emblem(layer)
        return _open_image(str(layer.get("path") or ""))
    except Exception as e:
        log.error(f"layer render failed ({kind}): {e}")
        return None


def _content_key(layer):
    """Cache key of a layer's CONTENT (transforms are applied later on)."""
    key = tuple(layer.get(field) for field in _CONTENT_FIELDS)
    path = str(layer.get("path") or "")
    if path:
        try:
            key += (os.stat(path).st_mtime_ns,)
        except OSError:
            key += (0,)
    return key


def _render_cached(layer):
    """render_layer() behind a small bounded cache (content keyed)."""
    key = _content_key(layer)
    cached = _RENDER_CACHE.get(key)
    if cached is not None:
        _RENDER_CACHE.move_to_end(key)
        return cached
    img = render_layer(layer)
    if img is None:
        return None
    _RENDER_CACHE[key] = img
    while len(_RENDER_CACHE) > _RENDER_CACHE_MAX:
        _RENDER_CACHE.popitem(last=False)
    return img


# ---------------------------------------------------------------------------
# Transforms & composition
# ---------------------------------------------------------------------------

def _shift_hue(img, degrees):
    """Rotate the hue band of an RGBA image (alpha is preserved)."""
    shift = int(round(degrees * 255 / 360.0)) % 256
    if shift == 0:
        return img
    red, green, blue, alpha = img.split()
    hsv = Image.merge("RGB", (red, green, blue)).convert("HSV")
    hue, sat, val = hsv.split()
    hue = hue.point(lambda value: (value + shift) % 256)
    hsv = Image.merge("HSV", (hue, sat, val)).convert("RGB")
    return Image.merge("RGBA", (*hsv.split(), alpha))


def _shift_saturation(img, percent):
    """Scale the colour saturation (alpha is preserved)."""
    factor = max(0.0, 1.0 + percent / 100.0)
    red, green, blue, alpha = img.split()
    rgb = Image.merge("RGB", (red, green, blue))
    rgb = ImageEnhance.Color(rgb).enhance(factor)
    return Image.merge("RGBA", (*rgb.split(), alpha))


def _apply_monochrome(img, layer):
    """Convert to grayscale, threshold, tint with mono_color (alpha preserved).

    ``monochrome`` must be truthy for anything to happen. ``invert`` flips
    the threshold so dark pixels become the tint colour instead of light ones.
    ``threshold`` is 0-255; ``mono_color`` is '#rrggbb'. The original alpha
    channel is preserved untouched.
    """
    if not layer.get("monochrome"):
        return img
    img = img.convert("RGBA").copy()
    red, green, blue, alpha = img.split()
    gray = Image.merge("RGB", (red, green, blue)).convert("L")
    threshold = int(layer.get("threshold", 128))
    invert = bool(layer.get("invert"))
    # Threshold: above -> white (255), below -> black (0).
    if invert:
        mask = gray.point(lambda v: 255 if v < threshold else 0)
    else:
        mask = gray.point(lambda v: 255 if v > threshold else 0)
    hexa = _normalize_hex(layer.get("mono_color", "#ffffff"))
    if not hexa:
        hexa = "#ffffff"
    rgba = Gdk.RGBA()
    if not rgba.parse(hexa):
        rgba.parse("#ffffff")
    r = int(round(rgba.red * 255))
    g = int(round(rgba.green * 255))
    b = int(round(rgba.blue * 255))
    tinted = Image.merge("RGB", (
        Image.eval(mask, lambda v: r * v // 255),
        Image.eval(mask, lambda v: g * v // 255),
        Image.eval(mask, lambda v: b * v // 255),
    ))
    return Image.merge("RGBA", (*tinted.split(), alpha))


# ---------------------------------------------------------------------------
# Masks (#33)
# ---------------------------------------------------------------------------

_MASK_CACHE_MAX = 16
_MASK_CACHE = OrderedDict()


def _load_mask_image(path, size):
    """Load a mask image (PNG/SVG) -> grayscale ``L`` image sized to ``size``.

    External masks are untrusted data: validate existence/format and return
    ``None`` on any failure so the caller can fall back to the automatic
    mask or skip masking entirely.
    """
    if not path or not os.path.exists(path):
        return None
    cached = _MASK_CACHE.get(path)
    if cached is not None:
        _MASK_CACHE.move_to_end(path)
        return cached
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".svg":
            img = _rasterize_svg(path, size[0])
        else:
            img = _open_image(path)
        if img is None:
            return None
        img = img.convert("L")
        if img.size != size:
            img = img.resize(size, Image.Resampling.LANCZOS)
        _MASK_CACHE[path] = img
        while len(_MASK_CACHE) > _MASK_CACHE_MAX:
            _MASK_CACHE.popitem(last=False)
        return img
    except Exception as e:
        log.error(f"load mask {path}: {e}")
        return None


def _apply_mask(img, mask):
    """Apply grayscale ``mask`` to ``img`` alpha channel (antialiased).

    The mask multiplies the existing alpha, so transparent parts of the mask
    make the layer transparent; opaque parts keep the layer's own alpha.
    """
    img = img.convert("RGBA").copy()
    if mask.size != img.size:
        mask = mask.resize(img.size, Image.Resampling.LANCZOS)
    alpha = img.getchannel("A")
    new_alpha = ImageChops.multiply(alpha, mask)
    img.putalpha(new_alpha)
    return img


def _apply_transforms(img, layer):
    """scale -> rotation -> monochrome -> hue -> saturation -> opacity -> mask."""
    # The copy matters: the render cache hands out shared images.
    img = img.convert("RGBA").copy()
    scale = int(layer.get("scale", 100))
    if scale != 100:
        factor = scale / 100.0
        width = max(1, int(round(img.width * factor)))
        height = max(1, int(round(img.height * factor)))
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    rotation = int(layer.get("rotation", 0))
    if rotation:
        img = img.rotate(rotation, resample=Image.Resampling.BICUBIC,
                         expand=True)
    img = _apply_monochrome(img, layer)
    hue = int(layer.get("hue", 0))
    if hue:
        img = _shift_hue(img, hue)
    saturation = int(layer.get("saturation", 0))
    if saturation:
        img = _shift_saturation(img, saturation)
    opacity = int(layer.get("opacity", 100))
    if opacity != 100:
        factor = opacity / 100.0
        alpha = img.getchannel("A").point(
            lambda value: max(0, min(255, int(round(value * factor)))))
        img.putalpha(alpha)
    # Custom mask (per-layer opt-in). Applied last so it clips the final
    # transformed+opacitied layer, preserving antialiasing edges.
    if layer.get("mask_mode") == "custom":
        mask = _load_mask_image(layer.get("mask_path"), img.size)
        if mask is not None:
            img = _apply_mask(img, mask)
    return img


def compose_layers(base, layers):
    """Compose the base image with the layer stack -> PNG bytes (or None).

    ``layers`` is top-first: index 0 is the visually topmost layer, so the
    stack is painted in reverse order.
    """
    if base is None:
        return None
    if not _PIL_AVAILABLE:
        log.error("PIL unavailable — cannot compose icon")
        return None
    try:
        canvas = base.convert("RGBA")
        if canvas.size != (CANVAS_SIZE, CANVAS_SIZE):
            canvas = canvas.resize((CANVAS_SIZE, CANVAS_SIZE),
                                   Image.Resampling.LANCZOS)
        canvas = canvas.copy()
        # Automatic mask derived from the base image alpha (folder shape).
        # Used to clip overlays that overflow the folder silhouette (#33).
        base_mask = None
        try:
            base_mask = canvas.getchannel("A")
        except Exception:
            base_mask = None
        for layer in reversed(normalize_layers(layers)):
            img = _render_cached(layer)
            if img is None:
                continue
            img = _apply_transforms(img, layer)
            scratch = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE),
                                (0, 0, 0, 0))
            pos_x = (CANVAS_SIZE - img.width) // 2 + int(layer["offset_x"])
            pos_y = (CANVAS_SIZE - img.height) // 2 + int(layer["offset_y"])
            scratch.paste(img, (pos_x, pos_y))
            # "auto" mask: clip to the folder base shape. Only affects the
            # layer that opted in (mask_mode == "auto"); text/emblem are not
            # cut by default unless the user explicitly enables it.
            if layer.get("mask_mode") == "auto" and base_mask is not None:
                scratch = _apply_mask(scratch, base_mask)
            canvas = Image.alpha_composite(canvas, scratch)
        buffer = io.BytesIO()
        canvas.save(buffer, "PNG")
        return buffer.getvalue()
    except Exception as e:
        log.error(f"compose layers: {e}")
        return None


# ---------------------------------------------------------------------------
# PNG export / project reopen (#34)
# ---------------------------------------------------------------------------

def _png_project_state(hexes, layers, theme="", base_image=""):
    """Build the serialisable project state for PNG metadata export."""
    return {
        "version": 1,
        "spec": ";".join(str(h).lstrip("#").lower() for h in (hexes or [])),
        "theme": str(theme or ""),
        "base_image": str(base_image or ""),
        "layers": normalize_layers(layers or []),
    }


def save_png_project(png_bytes, hexes, layers, theme="", base_image=""):
    """Embed project metadata into ``png_bytes`` -> new PNG bytes (or None).

    Uses a PIL PngInfo text chunk ``fcRev`` holding JSON with colours,
    layers, masks and transforms so the project can be reopened editably.
    """
    if not _PIL_AVAILABLE:
        return None
    try:
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        import json
        img = Image.open(io.BytesIO(png_bytes))
        img = img.convert("RGBA")
        meta = PngInfo()
        meta.add_text("fcRev", json.dumps(
            _png_project_state(hexes, layers, theme, base_image),
            ensure_ascii=False))
        out = io.BytesIO()
        img.save(out, "PNG", pnginfo=meta)
        return out.getvalue()
    except Exception as e:
        log.error(f"save png project: {e}")
        return None


def load_png_project(path):
    """Read ``fcRev`` project metadata from a PNG file -> dict or {}.

    Returns an empty dict when the file has no project metadata or cannot
    be read, so callers can fall back to treating it as a plain image layer.
    """
    if not _PIL_AVAILABLE or not path or not os.path.exists(path):
        return {}
    try:
        from PIL import Image
        import json
        img = Image.open(path)
        img.load()
        raw = img.info.get("fcRev")
        if not raw:
            return {}
        state = json.loads(raw)
        if not isinstance(state, dict):
            return {}
        return state
    except Exception as e:
        log.debug(f"load png project {path}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

def _hex_to_rgba(value):
    """'#rrggbb' -> (r, g, b, a) floats in 0..1."""
    hexa = _normalize_hex(value) or "#ffffff"
    red = int(hexa[1:3], 16) / 255.0
    green = int(hexa[3:5], 16) / 255.0
    blue = int(hexa[5:7], 16) / 255.0
    return red, green, blue, 1.0


def _rgba_from_hex(value):
    """'#rrggbb' -> Gdk.RGBA (or None)."""
    hexa = _normalize_hex(value)
    if not hexa:
        return None
    rgba = Gdk.RGBA()
    try:
        if rgba.parse(hexa):
            return rgba
    except Exception as e:
        log.error(f"rgba parse failed ({value}): {e}")
    return None


def _rgba_to_hex(rgba):
    """Gdk.RGBA -> '#rrggbb'."""
    try:
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, round(rgba.red * 255))),
            max(0, min(255, round(rgba.green * 255))),
            max(0, min(255, round(rgba.blue * 255))))
    except Exception:
        return ""


def _generate_color():
    """NameToColor's generate_color() — None when the module is missing."""
    global _GENERATE_COLOR, _GENERATE_COLOR_LOOKED_UP
    if not _GENERATE_COLOR_LOOKED_UP:
        _GENERATE_COLOR_LOOKED_UP = True
        try:
            from name_to_color import generate_color
            _GENERATE_COLOR = generate_color
        except Exception as e:
            log.warning(f"name_to_color unavailable, colour names disabled: {e}")
            _GENERATE_COLOR = None
    return _GENERATE_COLOR


def _resolve_color(text):
    """Colour name (or literal '#rrggbb') -> '#rrggbb', or ''."""
    text = str(text or "").strip()
    if not text:
        return ""
    if text.startswith("#"):
        return _normalize_hex(text)
    generate = _generate_color()
    if generate is None:
        return ""
    try:
        color = generate(text)
    except Exception as e:
        log.error(f"colour name resolve failed ({text}): {e}")
        return ""
    if isinstance(color, list):
        color = color[0] if color else ""
    return _normalize_hex(str(color)[:7])


def _clamp_dialog_size(avail_w, avail_h, base_w=820, base_h=700,
                       margin_x=48, margin_y=140, min_w=520, min_h=460):
    """Limit the dialog's default size to the screen minus a margin.

    Pure and display-free so it can be unit tested. The result never exceeds
    the base size and never drops below the minimum usable size, so the dialog
    stays legible even on a pathologically small screen.
    """
    try:
        avail_w = int(avail_w)
        avail_h = int(avail_h)
    except Exception:
        avail_w, avail_h = 0, 0
    width = base_w
    height = base_h
    if avail_w > 0:
        width = min(base_w, max(min_w, avail_w - margin_x))
    else:
        width = min_w
    if avail_h > 0:
        height = min(base_h, max(min_h, avail_h - margin_y))
    else:
        height = min_h
    return width, height


def _screen_available_size():
    """Best-effort (width, height) of the primary monitor's usable area.

    Wayland's Gdk.Monitor does not always expose get_workarea(), so we try it
    and fall back to get_geometry(). Any failure returns a sane desktop size.
    """
    fallback = (1920, 1080)
    try:
        display = Gdk.Display.get_default()
        if display is None:
            return fallback
        monitor = None
        try:
            monitor = display.get_primary_monitor()
        except Exception:
            monitor = None
        if monitor is None:
            monitors = display.get_monitors()
            if monitors is not None and monitors.get_n_items() > 0:
                monitor = monitors.get_item(0)
        if monitor is None:
            return fallback
        rect = None
        try:
            rect = monitor.get_workarea()
        except Exception:
            rect = None
        if rect is None:
            try:
                rect = monitor.get_geometry()
            except Exception:
                rect = None
        if rect is None:
            return fallback
        width = int(getattr(rect, "width", 0) or 0)
        height = int(getattr(rect, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return fallback
        return width, height
    except Exception as e:
        log.debug(f"screen size probe: {e}")
        return fallback


# ---------------------------------------------------------------------------
# Drag & drop helpers
# ---------------------------------------------------------------------------

def _payload_index(value):
    """The dragged layer index carried by a drag payload.

    Accepts a plain string as well as a ``GObject.Value``.
    """
    if value is None:
        raise ValueError("empty drag payload")
    if hasattr(value, "get_value"):
        value = value.get_value()
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return int(str(value).strip())


def _drop_anchor(source_index, target_index, y, row_height):
    """Where a dragged layer has to be inserted.

    ``y`` is the pointer position inside the target row: above its middle
    inserts the layer BEFORE the target row, below inserts it AFTER. The
    source layer is removed from the stack first, so an anchor that sits
    behind the source is shifted by one.
    """
    if source_index == target_index:
        return None
    anchor = target_index + (1 if y > (row_height // 2) else 0)
    if source_index < anchor:
        anchor -= 1
    return anchor


# ---------------------------------------------------------------------------
# Icon detection
# ---------------------------------------------------------------------------

# Common icon words in many languages, in priority order: the earlier a word
# sits, the stronger the match. The names are compared in their normalised
# form (lower case, no accents, no punctuation), so "ícone.png" and
# "MEU_ICONE.PNG" both match "icone".
_ICON_NAME_HINTS = (
    # english
    "favicon", "icon", "logo", "shield", "badge", "emblem", "banner",
    "flag", "avatar", "symbol", "app", "brand", "cover", "mark", "crest",
    "site", "web", "tile", "shortcut", "default", "main", "header",
    # portuguese
    "icone", "brasao", "escudo", "emblema", "distintivo", "insignia",
    "bandeira", "marca", "simbolo", "capa", "principal", "cabecalho",
    "atalho",
    # spanish
    "icono", "portada",
    # french
    "bouclier", "embleme", "devise", "insigne", "drapeau", "marque",
    "symbole", "couverture",
    # german
    "schild", "wappen", "abzeichen", "siegel", "flagge", "marke", "titelbild",
    # italian
    "icona", "scudo", "stemma", "insegna", "marchio",
    # dutch
    "icoon", "wapen", "embleem", "vaandel", "merk", "symbool",
)

# The preview of every row of the chooser.
_DETECT_PREVIEW_SIZE = 48

# A detected icon is a badge-sized overlay: big enough to be recognised,
# small enough for the folder shape to show through.
_DETECTED_SCALE = 70

# Quick palette colours (Iconic reference): blue, teal, green, yellow,
# orange, red, pink, purple, slate — plus a custom colour picker.
PALETTE_COLORS = (
    ("blue",   "#3584e4"),
    ("teal",   "#2190a4"),
    ("green",  "#3a944a"),
    ("yellow", "#c88800"),
    ("orange", "#ed5b00"),
    ("red",    "#e62d42"),
    ("pink",   "#d56199"),
    ("purple", "#9141ac"),
    ("slate",  "#6f8396"),
)

# Folders that never hold the icon of a project.
_SCAN_SKIP_DIRS = ("node_modules", ".git", "__pycache__", "vendor", "build",
                   "dist", "target", ".venv", "venv")

# How deep the scan goes: the scanned folder is level 0, its sub-folders
# are level 1 and their sub-folders level 2.
_SCAN_MAX_DEPTH = 2

# A hard cap on the number of files the scan looks at (no infinite walks).
_SCAN_MAX_FILES = 4000

# The accepted extensions, best format first.
_ICON_EXTENSIONS = (".png", ".svg", ".jpg", ".jpeg", ".webp")

_ICON_EXT_RANK = {
    ".svg": 0, ".png": 1, ".webp": 2, ".jpg": 3, ".jpeg": 3,
}

# The chooser dialogs are kept here so they are not garbage collected.
_ICON_CHOOSERS = []

# Characters NFKD cannot decompose into base Latin letters (Danish/Norwegian
# ø, German ß, Polish ł, Icelandic đ/þ, eth, æ/œ, dotless i, eng …). Without
# this fold, "logø.png" would never match the hint "logo".
_FOLD_CHARS = str.maketrans({
    "ø": "o", "æ": "ae", "œ": "oe", "đ": "d", "ð": "d", "þ": "th",
    "ß": "ss", "ł": "l", "ı": "i", "ŋ": "n", "ħ": "h", "ŧ": "t",
    "ƿ": "w", "ǥ": "g",
})


def _normalize_stem(text):
    """Lower case, without accents and punctuation: a comparable file stem."""
    folded = str(text or "").lower().translate(_FOLD_CHARS)
    decomposed = unicodedata.normalize("NFKD", folded)
    plain = "".join(char for char in decomposed
                    if not unicodedata.combining(char))
    return "".join(char for char in plain if char.isalnum())


_NORMALIZED_HINTS = tuple(_normalize_stem(hint) for hint in _ICON_NAME_HINTS)


def _icon_match(stem):
    """Best (quality, hint index) of a normalised stem, or None.

    Quality: the stem IS the hint (0), STARTS WITH it (1) or CONTAINS it (2).
    """
    best = None
    for index, hint in enumerate(_NORMALIZED_HINTS):
        if not hint:
            continue
        if stem == hint:
            quality = 0
        elif stem.startswith(hint):
            quality = 1
        elif hint in stem:
            quality = 2
        else:
            continue
        key = (quality, index)
        if best is None or key < best:
            best = key
    return best


def _scan_dirs(directory):
    """The folder path(s) to scan: accepts a path or an iterable of paths."""
    if directory is None:
        items = []
    elif isinstance(directory, str):
        items = [directory]
    elif isinstance(directory, (list, tuple, set, frozenset)):
        items = list(directory)
    else:
        try:
            items = [str(item) for item in directory]
        except Exception:
            items = [str(directory)]
    roots = []
    for item in items:
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            root = os.path.abspath(os.path.expanduser(raw))
        except Exception as e:
            log.error(f"icon scan path invalid ({item}): {e}")
            continue
        if root and os.path.isdir(root) and root not in roots:
            roots.append(root)
    return roots


def detect_icon_candidates(directory, limit=40):
    """Rank the icon-like images inside a folder.

    ``directory`` may be a single folder or an iterable of folders — the
    candidates of every folder are merged and ranked together (a multi-folder
    selection shows one list, each row carrying its own folder).

    Returns a list of absolute file paths, best match first.
    """
    roots = _scan_dirs(directory)
    if not roots:
        return []
    try:
        limit = max(0, int(limit))
    except Exception:
        limit = 40
    if limit <= 0:
        return []

    matches = []
    seen = set()
    visited = 0
    stop = False
    for root in roots:
        if stop:
            break
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                relative = os.path.relpath(dirpath, root)
                depth = 0 if relative in (".", os.curdir, "") else len(
                    relative.split(os.sep))
                # Hidden folders and build/vendor folders never hold the icon.
                dirnames[:] = sorted(
                    name for name in dirnames
                    if not name.startswith(".")
                    and name.lower() not in _SCAN_SKIP_DIRS)
                if depth >= _SCAN_MAX_DEPTH:
                    dirnames[:] = []
                for name in sorted(filenames):
                    visited += 1
                    if visited > _SCAN_MAX_FILES:
                        stop = True
                        break
                    if name.startswith("."):
                        continue
                    stem, ext = os.path.splitext(name)
                    ext = ext.lower()
                    if ext not in _ICON_EXTENSIONS:
                        continue
                    key = _normalize_stem(stem)
                    if not key:
                        continue
                    match = _icon_match(key)
                    if match is None:
                        continue
                    path = os.path.join(dirpath, name)
                    if path in seen:
                        continue
                    seen.add(path)
                    quality, hint_index = match
                    matches.append((quality, hint_index,
                                    _ICON_EXT_RANK.get(ext, len(_ICON_EXT_RANK)),
                                    len(key), name.lower(), name, path))
                if stop:
                    break
        except Exception as e:
            log.error(f"icon scan failed ({root}): {e}")

    matches.sort(key=lambda item: item[:6])
    return [item[-1] for item in matches[:limit]]


def _detect_preview_texture(path, size=_DETECT_PREVIEW_SIZE):
    """A Gdk.Texture with a small preview of the image at ``path``."""
    if not _PIL_AVAILABLE:
        return None
    try:
        if os.path.splitext(path)[1].lower() == ".svg":
            image = _rasterize_svg(path, size)
        else:
            image = _open_image(path, size)
        if image is None:
            return None
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        loader = GdkPixbuf.PixbufLoader.new_with_mime_type("image/png")
        loader.write(buffer.getvalue())
        loader.close()
        pixbuf = loader.get_pixbuf()
    except Exception as e:
        log.error(f"preview failed ({path}): {e}")
        return None
    if pixbuf is None:
        return None
    return _pixbuf_to_texture(pixbuf)


def _detect_candidate_row(path):
    """A chooser row: a small preview, the file name and its folder."""
    row = Gtk.ListBoxRow()
    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

    # A Gtk.Picture honours the size of its paintable; a Gtk.Image would
    # keep the 16x16 icon size and the preview would collapse into a dot.
    texture = _detect_preview_texture(path)
    if texture is not None:
        picture = Gtk.Picture()
        try:
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        except Exception as e:
            log.debug(f"candidate content fit: {e}")
        picture.set_paintable(texture)
    else:
        picture = Gtk.Image.new_from_icon_name("image-missing")
    try:
        picture.set_size_request(_DETECT_PREVIEW_SIZE, _DETECT_PREVIEW_SIZE)
    except Exception as e:
        log.debug(f"candidate size request: {e}")
    content.append(picture)

    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    labels.set_hexpand(True)
    title = Gtk.Label(label=os.path.basename(path))
    title.set_xalign(0)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    labels.append(title)
    folder = Gtk.Label(label=os.path.dirname(path))
    folder.set_xalign(0)
    folder.set_ellipsize(Pango.EllipsizeMode.END)
    folder.add_css_class("dim-label")
    labels.append(folder)
    content.append(labels)

    row.set_child(content)
    return row


def _notify_chosen(on_chosen, path):
    """Call the callback; an exception must never reach Nautilus."""
    if not callable(on_chosen):
        return
    try:
        on_chosen(path)
    except Exception as e:
        log.error(f"icon chosen callback failed: {e}")


def _destroy_icon_chooser(dialog):
    """Destroy the chooser and drop it from the keep-alive list."""
    try:
        _ICON_CHOOSERS.remove(dialog)
    except ValueError:
        pass
    try:
        dialog.destroy()
    except Exception as e:
        log.debug(f"chooser destroy: {e}")


def choose_detected_icon(candidates, tr=None, on_chosen=None, parent=None):
    """Show the chooser for the detected candidates.

    ``on_chosen(path)`` is called with the chosen absolute path, or with
    "" when the user cancels. Never raises into Nautilus.
    """
    translate = tr if callable(tr) else (lambda text: text)
    paths = []
    for item in (candidates or []):
        try:
            value = str(item)
        except Exception:
            continue
        if value and value not in paths:
            paths.append(value)
    if not paths:
        _notify_chosen(on_chosen, "")
        return

    state = {"done": False}

    def finish(path):
        if state["done"]:
            return
        state["done"] = True
        _notify_chosen(on_chosen, path)

    try:
        dialog = Gtk.Dialog(title=translate("Choose an icon"))
        dialog.set_modal(True)
        if parent is not None:
            try:
                dialog.set_transient_for(parent)
            except Exception as e:
                log.debug(f"chooser transient for: {e}")
        dialog.add_buttons(translate("Cancel"), Gtk.ResponseType.CANCEL,
                           translate("Apply"), Gtk.ResponseType.OK)
        try:
            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.set_default_size(560, 460)
        except Exception as e:
            log.debug(f"chooser defaults: {e}")

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for path in paths:
            listbox.append(_detect_candidate_row(path))

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(listbox)
        try:
            scrolled.set_min_content_height(280)
            scrolled.set_max_content_height(420)
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            # The list absorbs the slack, so the action buttons stay glued
            # to the bottom of the dialog instead of floating in the middle.
            scrolled.set_vexpand(True)
        except Exception as e:
            log.debug(f"chooser scroller: {e}")
        dialog.get_content_area().append(scrolled)

        def set_ok_sensitive(sensitive):
            button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
            if button is not None:
                button.set_sensitive(sensitive)

        def on_row_selected(_listbox, row):
            set_ok_sensitive(row is not None)

        def on_response(_dialog, response):
            path = ""
            if response == Gtk.ResponseType.OK:
                row = listbox.get_selected_row()
                index = row.get_index() if row is not None else -1
                if 0 <= index < len(paths):
                    path = paths[index]
            finish(path)
            _destroy_icon_chooser(dialog)

        def on_close(_dialog):
            finish("")
            GLib.idle_add(_destroy_icon_chooser, dialog)

        set_ok_sensitive(False)
        listbox.connect("row-selected", on_row_selected)
        dialog.connect("response", on_response)
        dialog.connect("close", on_close)
        # The best candidate is pre-selected: the user can confirm right away.
        first = listbox.get_row_at_index(0)
        if first is not None:
            listbox.select_row(first)
    except Exception as e:
        log.error(f"icon chooser failed: {e}")
        finish("")
        return

    _ICON_CHOOSERS.append(dialog)
    try:
        # Wayland: presenting synchronously from a click handler leaves the
        # popup with dead buttons, so the dialog is shown one idle turn
        # later (see file-tools.py).
        GLib.idle_add(dialog.present)
    except Exception as e:
        log.error(f"icon chooser present: {e}")


def detect_icon_for_folder(directory, tr=None, on_chosen=None, parent=None):
    """Full flow: scan, report when nothing is found, let the user choose.

    ``directory`` may be a single folder or an iterable of folders (a
    multi-folder selection) — every folder is scanned and the candidates
    are offered together.

    ``on_chosen(path)`` is called with the chosen absolute path, or with ""
    when nothing was found or the user cancelled.
    """
    translate = tr if callable(tr) else (lambda text: text)
    try:
        candidates = detect_icon_candidates(directory)
    except Exception as e:
        log.error(f"icon detection failed: {e}")
        candidates = []
    if not candidates:
        try:
            Gtk.AlertDialog(message=translate("No icon found")).show(parent)
        except Exception as e:
            log.error(f"no icon alert: {e}")
        _notify_chosen(on_chosen, "")
        return
    if len(candidates) == 1:
        _notify_chosen(on_chosen, candidates[0])
        return
    choose_detected_icon(candidates, tr=tr, on_chosen=on_chosen, parent=parent)


# ---------------------------------------------------------------------------
# The editor dialog
# ---------------------------------------------------------------------------

def _image_filter(name):
    filt = Gtk.FileFilter()
    filt.set_name(name)
    for mime in ("image/png", "image/jpeg", "image/webp", "image/svg+xml",
                 "image/bmp", "image/gif", "image/tiff"):
        filt.add_mime_type(mime)
    try:
        filt.add_pixbuf_formats()
    except Exception as e:
        log.debug(f"pixbuf formats unavailable: {e}")
    return filt


def _markup(text):
    return GLib.markup_escape_text(str(text))


def _clear_container(container):
    """Remove every child of a GTK4 container (no get_children() in GTK4)."""
    child = container.get_first_child()
    while child is not None:
        sibling = child.get_next_sibling()
        container.remove(child)
        child = sibling


def _scope_snapshot(scope):
    """Deep-ish copy of what an apply would write (dirty detection)."""
    return {
        "hexes": list(scope.get("hexes") or []),
        "layers": [dict(layer) for layer in scope.get("layers") or []],
        "theme": str(scope.get("theme") or ""),
        "follow_accent": bool(scope.get("follow_accent")),
    }



class _Editor:
    """The layer editor window."""

    def __init__(self, *, title, row_count, hexes, layers, base_builder,
                 on_apply, emblem_icons=None, tr=None, scan_dir=None,
                 on_apply_theme=None, theme_builder=None, global_host=None,
                 on_gallery_list=None, on_gallery_apply=None,
                 on_gallery_remove=None):
        self.tr = tr if callable(tr) else (lambda text: text)
        self.title = title
        self.row_count = max(1, int(row_count or 1))
        self.hexes = self._init_hexes(hexes)
        self.layers = normalize_layers(layers)
        self.base_builder = base_builder
        self.theme_builder = theme_builder
        self.on_apply = on_apply
        self.on_apply_theme = on_apply_theme
        self.global_host = global_host
        self.on_gallery_list = on_gallery_list if callable(on_gallery_list) else None
        self.on_gallery_apply = on_gallery_apply if callable(on_gallery_apply) else None
        self.on_gallery_remove = on_gallery_remove if callable(on_gallery_remove) else None
        self.emblem_icons = list(emblem_icons or [])
        self.scan_dir = _scan_dirs(scan_dir)
        self.selected = 0 if self.layers else -1
        self.syncing = False
        self.rebuilding = False
        self.switching = False
        self.drag_active = False
        self.drag_base = (0, 0)
        self.sliders = {}
        self.widgets = {}
        self.row_labels = []
        self.base_cache = OrderedDict()
        self.font_families = None
        self.file_dialog = None
        self._preview_natural = None
        self.scope = SCOPE_FOLDER
        # Custom base image (#30): when set, the preview and the apply use this
        # image instead of the themed folder icon as the composition base.
        self.base_image_path = None
        self.base_image_pixbuf = None
        self.themes = []
        self.theme_names = [""]
        self.scopes = {}
        self._init_scopes()
        self._build()

    # -- helpers ----------------------------------------------------------
    def _init_scopes(self):
        """Seed the folder scope and, when the host offers it, the global one.

        The active scope's ``hexes``/``layers`` are the very list objects
        handed to the widgets, so a colour edit lands in its own scope and
        switching tabs never copies the layers around (#21).
        """
        folder = {"hexes": self.hexes, "layers": self.layers,
                  "selected": self.selected, "theme": "",
                  "follow_accent": False,
                  "base_image_path": None}
        self.scopes = {SCOPE_FOLDER: folder}
        if self.global_host is None:
            folder["initial"] = _scope_snapshot(folder)
            return
        try:
            self.themes = list(self.global_host.themes() or [])
        except Exception as e:
            log.error(f"global themes: {e}")
            self.themes = []
        try:
            state = self.global_host.state() or {}
        except Exception as e:
            log.error(f"global state: {e}")
            state = {}
        rows = max(self.row_count, int(state.get("row_count") or 1))
        if rows != self.row_count:
            # The global icon may carry more shapes than the folder's theme;
            # pad both scopes so every colour row has a value.
            self.row_count = rows
            self.hexes = self._init_hexes(self.hexes)
            folder["hexes"] = self.hexes
        spec = str(state.get("spec") or "")
        global_hexes = self._init_hexes(
            ["#" + part for part in spec.split(";") if len(part) == 6])
        global_layers = normalize_layers(state.get("layers"))
        self.scopes[SCOPE_GLOBAL] = {
            "hexes": global_hexes,
            "layers": global_layers,
            "selected": 0 if global_layers else -1,
            "theme": str(state.get("theme") or ""),
            "follow_accent": bool(state.get("follow_accent")),
        }
        for scope in self.scopes.values():
            scope["initial"] = _scope_snapshot(scope)
        self.theme_names = [""] + [item["name"] for item in self.themes]

    def _init_hexes(self, hexes):
        values = []
        for value in list(hexes or []):
            values.append(_normalize_hex(value) or "#808080")
        while len(values) < self.row_count:
            values.append("#808080")
        return values[:self.row_count]

    def current_layer(self):
        if 0 <= self.selected < len(self.layers):
            return self.layers[self.selected]
        return None


    def _type_label(self, layer):
        return self.tr(_TYPE_LABELS.get(layer.get("type"),
                                        _TYPE_LABELS[LAYER_IMAGE]))

    def _bold_label(self, text):
        label = Gtk.Label()
        label.set_use_markup(True)
        label.set_xalign(0)
        label.set_markup("<b>" + _markup(text) + "</b>")
        return label

    def _labelled_row(self, title, widget):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=title)
        label.set_xalign(0)
        try:
            label.set_size_request(110, -1)
        except Exception:
            pass
        row.append(label)
        row.append(widget)
        return row

    # -- construction -----------------------------------------------------
    def _build(self):
        dialog = Gtk.Dialog(title=self.title)
        dialog.set_modal(True)
        try:
            avail_w, avail_h = _screen_available_size()
            size_w, size_h = _clamp_dialog_size(avail_w, avail_h)
            dialog.set_default_size(size_w, size_h)
        except Exception as e:
            log.error(f"dialog size: {e}")
        dialog.add_buttons(self.tr("Cancel"), Gtk.ResponseType.CANCEL,
                           self.tr("Apply"), Gtk.ResponseType.OK)
        try:
            dialog.set_default_response(Gtk.ResponseType.OK)
        except Exception:
            pass
        self.dialog = dialog

        self._apply_css()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for margin in ("margin_top", "margin_bottom", "margin_start",
                       "margin_end"):
            try:
                getattr(root, "set_" + margin)(12)
            except Exception:
                pass
        # On screens smaller than the dialog's natural size the content would
        # otherwise be clipped out of view with no way to reach it; a scrolled
        # window (natural size preserved) reveals it via a scrollbar instead.
        scroller = Gtk.ScrolledWindow()
        try:
            scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroller.set_propagate_natural_height(True)
            scroller.set_propagate_natural_width(True)
            scroller.set_vexpand(True)
        except Exception as e:
            log.debug(f"dialog scroller: {e}")
        scroller.set_child(root)
        dialog.get_content_area().append(scroller)

        upper = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        if self.global_host is not None:
            root.append(self._build_scope_tabs())
        root.append(upper)
        upper.append(self._build_preview_column())
        upper.append(self._build_layers_column())

        root.append(Gtk.Separator())
        root.append(self._build_colour_rows())
        if self.global_host is not None:
            root.append(self._build_scope_options())
        root.append(Gtk.Separator())
        root.append(self._bold_label(self.tr("Layer settings")))
        self.settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                    spacing=6)
        root.append(self.settings_box)

        dialog.connect("response", self._on_response)
        self._install_paste_shortcut(dialog)
        self._sync_scope_options()
        self._rebuild_rows()

    # -- scope tabs -------------------------------------------------------
    def _build_scope_tabs(self):
        """Folder / Global tabs (linked toggle buttons, no page stack)."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.add_css_class("linked")
        box.set_halign(Gtk.Align.CENTER)
        self.scope_buttons = {}
        for scope, label in ((SCOPE_FOLDER, self.tr("Folder")),
                             (SCOPE_GLOBAL, self.tr("Global"))):
            button = Gtk.ToggleButton(label=label)
            button.connect("toggled", self._on_scope_toggled, scope)
            self.scope_buttons[scope] = button
            box.append(button)
        self.scope_buttons[SCOPE_GLOBAL].set_group(
            self.scope_buttons[SCOPE_FOLDER])
        self.switching = True
        try:
            self.scope_buttons[SCOPE_FOLDER].set_active(True)
        finally:
            self.switching = False
        return box

    def _on_scope_toggled(self, button, scope):
        if self.switching or not button.get_active():
            return
        self.activate_scope(scope)

    def activate_scope(self, scope):
        """Show another scope; the widgets keep working on its own lists."""
        if scope == self.scope or scope not in self.scopes:
            return
        # Persist the current scope's custom base image before switching.
        self.scopes[self.scope]["base_image_path"] = self.base_image_path
        target = self.scopes[scope]
        self.switching = True
        try:
            button = getattr(self, "scope_buttons", {}).get(scope)
            if button is not None:
                button.set_active(True)
        finally:
            self.switching = False
        self.scope = scope
        self.hexes = target["hexes"]
        self.layers = target["layers"]
        self.selected = target.get("selected", -1)
        self.base_image_path = target.get("base_image_path")
        self.base_image_pixbuf = None
        if self.base_image_path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(self.base_image_path)
                if pb is not None:
                    self.base_image_pixbuf = pb
            except Exception as e:
                log.error(f"restore base image: {e}")
                self.base_image_path = None
        self.base_cache.clear()
        self._sync_colour_rows()
        self._sync_scope_options()
        self._rebuild_rows()

    def _build_scope_options(self):
        """Theme selector (both scopes) + accent switch and restore (global)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        labels = [self.tr("Theme (current)")] + \
            [item["label"] for item in self.themes]
        self.theme_dropdown = Gtk.DropDown.new_from_strings(labels)
        self.theme_dropdown.set_hexpand(True)
        self.theme_dropdown.connect("notify::selected", self._on_theme_selected)
        box.append(self._labelled_row(self.tr("Folder theme"),
                                     self.theme_dropdown))

        self.accent_switch = Gtk.Switch()
        self.accent_switch.set_halign(Gtk.Align.START)
        self.accent_switch.connect("notify::active", self._on_accent_toggled)
        self.accent_row = self._labelled_row(
            self.tr("Use the accent colour"), self.accent_switch)
        box.append(self.accent_row)

        self.restore_button = Gtk.Button(
            label=self.tr("Restore the default folder icon"))
        self.restore_button.add_css_class("destructive-action")
        self.restore_button.connect("clicked", self._on_restore_global)
        self.restore_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                   spacing=6)
        self.restore_row.append(self.restore_button)
        box.append(self.restore_row)
        return box

    def _sync_scope_options(self):
        """Push the active scope's theme/accent state into the widgets."""
        if self.global_host is None:
            return
        scope = self.scopes[self.scope]
        theme = scope.get("theme") or ""
        index = self.theme_names.index(theme) if theme in self.theme_names else 0
        self.syncing = True
        try:
            self.theme_dropdown.set_selected(index)
            self.accent_switch.set_active(bool(scope.get("follow_accent")))
        finally:
            self.syncing = False
        is_global = self.scope == SCOPE_GLOBAL
        for widget in (self.accent_row, self.restore_row):
            widget.set_visible(is_global)
        if is_global:
            try:
                active = bool(self.global_host.is_active())
            except Exception as e:
                log.error(f"global active state: {e}")
                active = False
            self.restore_button.set_sensitive(active)
        self._sync_colour_sensitivity()

    def _sync_colour_sensitivity(self):
        """Colours are the accent's when the global scope follows it."""
        locked = self._accent_locked()
        for entry in getattr(self, "entries", []):
            entry.set_sensitive(not locked)
        for picker in getattr(self, "pickers", []):
            picker.set_sensitive(not locked)

    def _accent_locked(self):
        return (self.scope == SCOPE_GLOBAL
                and bool(self.scopes[SCOPE_GLOBAL].get("follow_accent")))

    def _accent_hex(self):
        getter = getattr(self.global_host, "accent_hex", None)
        if callable(getter):
            try:
                return _normalize_hex(getter()) or "#3584e4"
            except Exception as e:
                log.error(f"accent colour: {e}")
        return "#3584e4"

    def effective_hexes(self):
        """The colours the preview and the apply use (accent wins)."""
        if self._accent_locked():
            return [self._accent_hex()] * self.row_count
        return list(self.hexes)

    def _on_theme_selected(self, dropdown, _pspec):
        if self.syncing:
            return
        index = dropdown.get_selected()
        if index < 0 or index >= len(self.theme_names):
            return
        scope = self.scopes[self.scope]
        theme = self.theme_names[index]
        if theme == scope.get("theme"):
            return
        scope["theme"] = theme
        self.base_cache.clear()
        self._refresh_preview()

    def _on_accent_toggled(self, switch, _pspec):
        if self.syncing or self.scope != SCOPE_GLOBAL:
            return
        self.scopes[SCOPE_GLOBAL]["follow_accent"] = bool(switch.get_active())
        self._sync_colour_sensitivity()
        self.base_cache.clear()
        self._refresh_preview()

    def _on_restore_global(self, _button):
        if self.global_host is None:
            return
        try:
            restored = self.global_host.restore()
        except Exception as e:
            log.error(f"restore global icon: {e}")
            restored = False
        if not restored:
            self._show_alert(self.tr("Could not restore the folder icon."))
            return
        scope = self.scopes[SCOPE_GLOBAL]
        scope["hexes"] = self._init_hexes([])
        scope["layers"] = []
        scope["theme"] = ""
        scope["follow_accent"] = False
        scope["selected"] = -1
        if self.scope == SCOPE_GLOBAL:
            self.hexes = scope["hexes"]
            self.layers = scope["layers"]
            self.selected = -1
            self.base_cache.clear()
            self._sync_colour_rows()
            self._rebuild_rows()
        self._sync_scope_options()

    def _apply_css(self):
        """Small, dialog-scoped polish: framed canvas + bordered swatches."""
        global _CSS_APPLIED
        if _CSS_APPLIED:
            return
        _CSS_APPLIED = True
        css = b"""
        .preview-frame { border: 1px solid alpha(#999999, 0.5); border-radius: 6px; }
        .color-button { border: 1px solid alpha(#999999, 0.7); border-radius: 4px; padding: 2px; }
        /* The theme pads every flowbox child by 3px; the action row must
           keep the tight 6px spacing of a plain box. */
        .add-flow flowboxchild { padding: 0; }
        """
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception as e:
            log.debug(f"css provider: {e}")

    def _build_preview_column(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        # A Gtk.Picture honours the intrinsic size of its paintable; a
        # Gtk.Image would keep the 16x16 icon size and the preview would
        # collapse into a dot.
        self.preview = Gtk.Picture()
        try:
            self.preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        except Exception as e:
            log.error(f"preview content fit: {e}")
        try:
            # A Gtk.Picture fills the space offered by its parent; centring
            # it keeps the preview at its own size (PREVIEW_SIZE pixels).
            self.preview.set_halign(Gtk.Align.CENTER)
            self.preview.set_valign(Gtk.Align.CENTER)
        except Exception as e:
            log.error(f"preview alignment: {e}")

        # Frame the preview so the icon reads as a canvas with a boundary,
        # not a floating image.
        frame = Gtk.Frame()
        try:
            frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
            frame.add_css_class("preview-frame")
        except Exception:
            pass
        frame.set_child(self.preview)
        try:
            frame.set_size_request(PREVIEW_SIZE + 24, PREVIEW_SIZE + 24)
        except Exception:
            pass
        box.append(frame)

        # Compact the shortcut legend into a single wrapped line instead of
        # a five-line wall of text.
        hint = Gtk.Label()
        hint.set_use_markup(True)
        hint.set_xalign(0)
        hint.set_wrap(True)
        hint.set_max_width_chars(34)
        hint.add_css_class("dim-label")
        hint.set_markup("<small>" + " | ".join([
            _markup(self.tr("Drag to move")),
            _markup(self.tr("Scroll to resize")),
            _markup(self.tr("Shift + Scroll to rotate")),
            _markup(self.tr("Alt + Scroll for opacity")),
            _markup(self.tr("Ctrl + Scroll for hue")),
        ]) + "</small>")
        box.append(hint)

        scroll_ctrl = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_ctrl.connect("scroll", self._on_canvas_scroll)
        try:
            scroll_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            scroll_ctrl.set_propagation_limit(Gtk.PropagationLimit.SAME_NATIVE)
        except Exception as e:
            log.error(f"scroll controller: {e}")
        self.preview.add_controller(scroll_ctrl)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.preview.add_controller(drag)
        self._install_drop_targets(frame)
        return box

    # -- image import (#30) -----------------------------------------------
    def _install_drop_targets(self, widget):
        """Accept images dropped from Nautilus, a browser or a file manager.

        Two targets: ``Gdk.FileList`` for file managers that hand over files
        and a plain string for the ``text/uri-list`` payload browsers use.
        Remote URLs never match: only local files survive ``_local_file_path``.
        """
        for value_type in _drop_value_types():
            try:
                target = Gtk.DropTarget.new(value_type, Gdk.DragAction.COPY)
                target.connect("drop", self._on_images_dropped)
                widget.add_controller(target)
            except Exception as e:
                log.debug(f"drop target {value_type}: {e}")

    def _on_images_dropped(self, _target, value, _x, _y):
        paths = parse_image_uris(value)
        if not paths:
            self._show_alert(self.tr("Cannot open this image."))
            return False
        self._add_image_paths(paths)
        return True

    def _on_layer_images_dropped(self, _target, value, _x, _y, index):
        """Dropping on a layer row replaces that image layer."""
        paths = parse_image_uris(value)
        if not paths or not (0 <= index < len(self.layers)):
            return False
        layer = self.layers[index]
        if layer.get("type") != LAYER_IMAGE:
            return False
        layer["path"] = paths[0]
        layer["name"] = _derive_name(layer)
        for extra in paths[1:]:
            self.layers.insert(0, default_layer(LAYER_IMAGE, path=extra))
        self.selected = 0 if len(paths) > 1 else index
        # The rows must not be destroyed while the drop is still running.
        GLib.idle_add(self._deferred_rebuild)
        return True

    def _add_image_paths(self, paths):
        if not paths:
            return False
        for offset, path in enumerate(paths):
            self.layers.insert(offset, default_layer(LAYER_IMAGE, path=path))
        self.selected = 0
        self._rebuild_rows()
        return True

    def _install_paste_shortcut(self, dialog):
        controller = Gtk.EventControllerKey.new()
        controller.connect("key-pressed", self._on_key_pressed)
        dialog.add_controller(controller)

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        control = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if control and keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self.paste_image()
            return True
        return False

    def paste_image(self):
        """Ctrl+V: a copied texture, or a copied file's URI list."""
        if self.dialog is None:
            return
        clipboard = self._clipboard()
        if clipboard is None:
            return
        try:
            clipboard.read_texture_async(None, self._on_paste_texture)
        except Exception as e:
            log.error(f"clipboard texture: {e}")
            self._read_clipboard_uris(clipboard)

    def _clipboard(self):
        try:
            display = self.dialog.get_display() or Gdk.Display.get_default()
            return display.get_clipboard() if display is not None else None
        except Exception as e:
            log.error(f"clipboard: {e}")
            return None

    def _on_paste_texture(self, clipboard, result):
        if self.dialog is None:
            return
        try:
            texture = clipboard.read_texture_finish(result)
        except Exception as e:
            log.debug(f"no image on the clipboard: {e}")
            texture = None
        if texture is not None and self._add_texture(texture):
            return
        self._read_clipboard_uris(clipboard)

    def _read_clipboard_uris(self, clipboard):
        try:
            clipboard.read_value_async(GObject.TYPE_STRING, 0, None,
                                       self._on_paste_text)
        except Exception as e:
            log.debug(f"clipboard text: {e}")

    def _on_paste_text(self, clipboard, result):
        if self.dialog is None:
            return
        try:
            value = clipboard.read_value_finish(result)
        except Exception as e:
            log.debug(f"clipboard text unavailable: {e}")
            return
        text = value if isinstance(value, str) else str(value or "")
        paths = parse_image_uris(text)
        if not paths:
            self._show_alert(self.tr("The clipboard holds no image."))
            return
        self._add_image_paths(paths)

    def _add_texture(self, texture):
        """A clipboard texture becomes a temporary PNG layer."""
        try:
            width = texture.get_width()
            height = texture.get_height()
        except Exception:
            width = height = 0
        if not (0 < width <= MAX_IMAGE_SIDE and 0 < height <= MAX_IMAGE_SIDE):
            self._show_alert(self.tr("Cannot open this image."))
            return False
        try:
            data = bytes(texture.save_to_png_bytes())
        except Exception as e:
            log.error(f"texture export: {e}")
            return False
        path = _cache_image_bytes(data)
        if not path:
            return False
        return self._add_image_paths([path])


    def _build_layers_column(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_hexpand(True)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.append(self._bold_label(self.tr("Layers")))
        self.count_label = Gtk.Label(label="0")
        self.count_label.add_css_class("dim-label")
        header.append(self.count_label)
        box.append(header)

        scrolled = Gtk.ScrolledWindow()
        try:
            scrolled.set_min_content_height(170)
            scrolled.set_max_content_height(250)
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        except Exception as e:
            log.error(f"layers scroller: {e}")
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-selected", self._on_row_selected)
        scrolled.set_child(self.listbox)
        box.append(scrolled)

        hint = Gtk.Label(label=self.tr("Drag to reorder"))
        hint.set_xalign(0)
        hint.add_css_class("dim-label")
        box.append(hint)

        # A FlowBox wraps the buttons when the translated labels are wider
        # than the column (e.g. "Ajouter un emblème…" in French); a plain
        # Box would clip the last button instead.
        add_row = Gtk.FlowBox()
        add_row.add_css_class("add-flow")
        try:
            add_row.set_selection_mode(Gtk.SelectionMode.NONE)
            add_row.set_row_spacing(6)
            add_row.set_column_spacing(6)
        except Exception as e:
            log.error(f"add row: {e}")
        # "Add image" offers three explicit targets so the user never
        # silently overwrites the wrong object (#30):
        #   * Add as layer — new image layer on top of the stack (default)
        #   * Replace selected layer — overwrite the current image layer
        #   * Use as base image — custom background in place of the folder icon
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                              spacing=6)
        for label, action in (
            (self.tr("Add as layer"), "layer"),
            (self.tr("Replace selected layer"), "replace"),
            (self.tr("Use as base image"), "base"),
        ):
            item = Gtk.Button(label=label)
            item.set_hexpand(True)
            item.connect("clicked", self._on_add_image_target, action)
            popover_box.append(item)
        self.add_image_popover = Gtk.Popover()
        self.add_image_popover.set_child(popover_box)
        self.add_image_button = Gtk.MenuButton(
            label=self.tr("Add image…"), popover=self.add_image_popover)
        self.add_image_button.set_tooltip_text(
            self.tr("Choose where the image goes: new layer, selected layer "
                    "or custom base image."))
        add_row.append(self.add_image_button)

        # The "detect" button only makes sense for a real folder.
        if self.scan_dir:
            detect_button = Gtk.Button(label=self.tr("Detect icon…"))
            detect_button.connect("clicked", self._on_detect_icon)
            detect_button.set_tooltip_text(
                self.tr("Finds an icon file already inside the folder"))
            add_row.append(detect_button)

        actions = [(self.tr("Add text…"), self._on_add_text),
                   (self.tr("Add emblem…"), self._on_add_emblem)]
        for label, handler in actions:
            button = Gtk.Button(label=label)
            button.connect("clicked", handler)
            add_row.append(button)
            if handler.__func__ is self._on_add_emblem.__func__:
                self.emblem_button = button
        # No emblem in the theme -> nothing to add.
        self.emblem_button.set_sensitive(bool(self.emblem_icons))

        move_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.up_button = Gtk.Button(label=self.tr("Move up"))
        self.up_button.connect("clicked", self._on_move_up)
        self.down_button = Gtk.Button(label=self.tr("Move down"))
        self.down_button.connect("clicked", self._on_move_down)
        self.remove_button = Gtk.Button(label=self.tr("Remove layer"))
        self.remove_button.add_css_class("destructive-action")
        self.remove_button.connect("clicked", self._on_remove_layer)
        move_row.append(self.up_button)
        move_row.append(self.down_button)
        move_row.append(self.remove_button)
        # Export / reopen project (#34).
        self.export_button = Gtk.Button(label=self.tr("Export PNG…"))
        self.export_button.connect("clicked", self._on_export_png)
        move_row.append(self.export_button)
        self.open_project_button = Gtk.Button(label=self.tr("Open project…"))
        self.open_project_button.connect("clicked", self._on_open_project)
        move_row.append(self.open_project_button)
        # Icon gallery (#36).
        self.gallery_button = Gtk.Button(label=self.tr("Icon gallery…"))
        self.gallery_button.connect("clicked", self._on_open_gallery)
        move_row.append(self.gallery_button)
        box.append(move_row)
        return box

    def _build_colour_rows(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.colour_box = box
        self.entries = []
        self.pickers = []

        # -- quick palette (Iconic reference) ------------------------------
        palette_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        palette_label = Gtk.Label(label=self.tr("Quick colours"))
        palette_label.set_xalign(0)
        try:
            palette_label.set_size_request(56, -1)
        except Exception:
            pass
        palette_row.append(palette_label)
        palette_flow = Gtk.FlowBox()
        palette_flow.add_css_class("add-flow")
        try:
            palette_flow.set_selection_mode(Gtk.SelectionMode.NONE)
            palette_flow.set_row_spacing(6)
            palette_flow.set_column_spacing(6)
        except Exception as e:
            log.error(f"palette flow: {e}")
        for name, hex_color in PALETTE_COLORS:
            swatch = Gtk.Button()
            swatch.set_tooltip_text(f"{name} — {hex_color}")
            swatch.set_size_request(24, 24)
            swatch.add_css_class("color-button")
            # Paint the swatch with its colour via inline style.
            try:
                swatch.set_css_modules(None)
                swatch.set_valign(Gtk.Align.CENTER)
                swatch.set_halign(Gtk.Align.CENTER)
                swatch.set_can_focus(False)
            except Exception:
                pass
            provider = Gtk.CssProvider()
            provider.load_from_data(
                f".palette-swatch {{ background-color: {hex_color}; "
                "border: 1px solid rgba(0,0,0,0.35); border-radius: 6px; "
                "min-width: 24px; min-height: 24px; }}\n".encode("utf-8"))
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            swatch.add_css_class("palette-swatch")
            swatch.set_name(f"palette-{name}")
            swatch.connect("clicked", self._on_palette_color, hex_color)
            palette_flow.append(swatch)
        custom_button = Gtk.Button(label=self.tr("Custom colour…"))
        custom_button.connect("clicked", self._on_custom_colour)
        palette_flow.append(custom_button)
        palette_row.append(palette_flow)
        box.append(palette_row)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        try:
            sep.set_margin_top(4)
            sep.set_margin_bottom(4)
        except Exception:
            pass
        box.append(sep)

        for index in range(self.row_count):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            label = Gtk.Label(label=self.tr("Color %d") % (index + 1))
            label.set_xalign(0)
            try:
                label.set_size_request(56, -1)
            except Exception:
                pass
            row.append(label)
            entry = Gtk.Entry()
            entry.set_placeholder_text(
                self.tr("Name or #hex — e.g. vermelho, Lucas"))
            entry.set_hexpand(True)
            entry.set_text(self.hexes[index])
            picker = Gtk.ColorButton()
            picker.add_css_class("color-button")
            rgba = _rgba_from_hex(self.hexes[index])
            if rgba is not None:
                picker.set_rgba(rgba)
            entry.connect("changed", self._on_entry_changed, index)
            picker.connect("color-set", self._on_picker_set, index)
            row.append(entry)
            row.append(picker)
            box.append(row)
            self.entries.append(entry)
            self.pickers.append(picker)
        return box

    def _sync_colour_rows(self):
        """Load the active scope's hexes into the existing colour widgets."""
        if not getattr(self, "entries", None):
            return
        self.syncing = True
        try:
            for index, entry in enumerate(self.entries):
                value = self.hexes[index] if index < len(self.hexes) \
                    else "#808080"
                entry.set_text(value)
                rgba = _rgba_from_hex(value)
                if rgba is not None:
                    self.pickers[index].set_rgba(rgba)
        finally:
            self.syncing = False


    # -- layer rows -------------------------------------------------------
    def _layer_detail(self, layer):
        kind = layer.get("type")
        if kind == LAYER_TEXT:
            return " ".join(str(layer.get("text") or "").split())[:48]
        if kind == LAYER_EMBLEM:
            return str(layer.get("emblem") or "")
        return os.path.basename(str(layer.get("path") or ""))

    def _type_icon(self, layer):
        """The icon shown in front of a layer row."""
        if layer.get("type") == LAYER_EMBLEM:
            pixbuf = _emblem_pixbuf(layer)
            texture = _pixbuf_to_texture(pixbuf) if pixbuf is not None else None
            if texture is not None:
                # Gtk.Picture shows the emblem at its own size; a Gtk.Image
                # would shrink it to the 16x16 icon size.
                picture = Gtk.Picture()
                try:
                    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                    picture.set_halign(Gtk.Align.CENTER)
                    picture.set_valign(Gtk.Align.CENTER)
                except Exception as e:
                    log.debug(f"emblem content fit: {e}")
                picture.set_paintable(texture)
                return picture
            # No pixbuf -> fall back to the themed emblem icon.
            return Gtk.Image.new_from_icon_name(_TYPE_ICONS[LAYER_EMBLEM])
        return Gtk.Image.new_from_icon_name(
            _TYPE_ICONS.get(layer.get("type"), _TYPE_ICONS[LAYER_IMAGE]))

    def _build_row(self, index, layer):
        row = Gtk.ListBoxRow()
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        handle = Gtk.Image.new_from_icon_name(_DRAG_ICON)
        content.append(handle)
        content.append(self._type_icon(layer))
        name = Gtk.Label(label=layer.get("name") or self._type_label(layer))
        name.set_xalign(0)
        name.set_hexpand(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        content.append(name)
        detail = Gtk.Label(label=self._layer_detail(layer))
        detail.set_xalign(0)
        detail.set_ellipsize(Pango.EllipsizeMode.END)
        detail.add_css_class("dim-label")
        content.append(detail)
        row.set_child(content)

        source = Gtk.DragSource()
        source.set_actions(Gdk.DragAction.MOVE)
        source.connect("prepare", self._on_drag_prepare, index)
        handle.add_controller(source)

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("drop", self._on_drop, index)
        row.add_controller(target)

        # Dropping an image file on a layer row replaces that picture (#30);
        # a plain layer reorder still uses the string target above.
        for value_type in _drop_value_types():
            try:
                file_target = Gtk.DropTarget.new(value_type,
                                                 Gdk.DragAction.COPY)
                file_target.connect("drop", self._on_layer_images_dropped,
                                    index)
                row.add_controller(file_target)
            except Exception as e:
                log.debug(f"row drop target {value_type}: {e}")

        # Right-click context menu: use the image as the custom base or
        # remove the layer (#30).
        ctx_menu = Gtk.Menu()
        base_item = Gtk.MenuItem(label=self.tr("Use as base image"))
        base_item.set_sensitive(layer.get("type") == LAYER_IMAGE and
                                bool(layer.get("path")))
        base_item.connect("activate", self._on_row_use_as_base, index)
        ctx_menu.append(base_item)
        remove_item = Gtk.MenuItem(label=self.tr("Remove layer"))
        remove_item.connect("activate", self._on_row_remove, index)
        ctx_menu.append(remove_item)
        ctx_menu.show_all()

        def _on_right_click(_gesture, n_press, x, y):
            if n_press == 1:
                # Right click only.
                event = _gesture.get_current_event()
                if event is not None and \
                        event.get_button() == Gdk.BUTTON_SECONDARY:
                    self.selected = index
                    self.listbox.select_row(row)
                    ctx_menu.popup_at_widget(row, 0, 0, None)

        click = Gtk.GestureClick()
        click.set_button(Gdk.BUTTON_SECONDARY)
        click.connect("pressed", _on_right_click)
        row.add_controller(click)
        row._ctx_menu = ctx_menu  # keep a reference
        return row, name, detail


    def _rebuild_rows(self):
        self.rebuilding = True
        try:
            _clear_container(self.listbox)
            self.row_labels = []
            for index, layer in enumerate(self.layers):
                row, name, detail = self._build_row(index, layer)
                self.listbox.append(row)
                self.row_labels.append((name, detail))
            if 0 <= self.selected < len(self.layers):
                row = self.listbox.get_row_at_index(self.selected)
                if row is not None:
                    self.listbox.select_row(row)
        finally:
            self.rebuilding = False
        self._rebuild_settings()
        self._update_buttons()
        self._refresh_preview()

    def _update_row_labels(self):
        for index, layer in enumerate(self.layers):
            if index >= len(self.row_labels):
                break
            name, detail = self.row_labels[index]
            name.set_text(layer.get("name") or self._type_label(layer))
            detail.set_text(self._layer_detail(layer))

    def _on_row_selected(self, _listbox, row):
        if self.rebuilding:
            return
        self.selected = row.get_index() if row is not None else -1
        self._rebuild_settings()
        self._update_buttons()

    def _update_buttons(self):
        has_layer = 0 <= self.selected < len(self.layers)
        self.up_button.set_sensitive(has_layer and self.selected > 0)
        self.down_button.set_sensitive(
            has_layer and self.selected < len(self.layers) - 1)
        self.remove_button.set_sensitive(has_layer)

    # -- settings panel ---------------------------------------------------
    def _rebuild_settings(self):
        _clear_container(self.settings_box)
        self.sliders = {}
        self.widgets = {}
        layer = self.current_layer()
        if layer is None:
            label = Gtk.Label(label=self.tr("No layer selected"))
            label.set_xalign(0)
            label.add_css_class("dim-label")
            self.settings_box.append(label)
            return
        kind = layer["type"]
        if kind == LAYER_TEXT:
            self._build_text_controls(layer)
        elif kind == LAYER_EMBLEM:
            self._build_emblem_controls(layer)
        else:
            self._build_image_controls(layer)
        # The transform sliders live in a compact 2-column grid instead of a
        # long single column — that is the biggest vertical saving.
        self.settings_box.append(self._build_transform_grid(layer))

    def _build_transform_grid(self, layer):
        """Opacity / Hue / Saturation / Scale / Rotation / X / Y in 2 columns."""
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(6)
        grid.set_hexpand(True)
        keys = [("opacity", self.tr("Opacity")),
                ("hue", self.tr("Hue")),
                ("saturation", self.tr("Saturation")),
                ("scale", self.tr("Scale")),
                ("rotation", self.tr("Rotation")),
                ("offset_x", self.tr("X offset")),
                ("offset_y", self.tr("Y offset"))]
        for i, (key, title) in enumerate(keys):
            row = i // 2
            col = (i % 2) * 2
            label = Gtk.Label(label=title)
            label.set_xalign(0)
            try:
                label.set_size_request(96, -1)
            except Exception:
                pass
            low, high = _RANGES[key]
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                             low, high, 1)
            scale.set_hexpand(True)
            scale.set_digits(0)
            try:
                scale.set_value_pos(Gtk.PositionType.RIGHT)
            except Exception as e:
                log.debug(f"scale value pos: {e}")
            self.syncing = True
            try:
                scale.set_value(float(layer.get(key, 0)))
            except Exception as e:
                log.debug(f"scale value: {e}")
            self.syncing = False
            scale.connect("value-changed", self._on_slider_changed, key)
            grid.attach(label, col, row, 1, 1)
            grid.attach(scale, col + 1, row, 1, 1)
            self.sliders[key] = scale
        return grid

    def _on_slider_changed(self, scale, key):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer[key] = int(round(scale.get_value()))
        self._refresh_preview()

    def _sync_slider(self, key):
        scale = self.sliders.get(key)
        layer = self.current_layer()
        if scale is None or layer is None:
            return
        self.syncing = True
        try:
            scale.set_value(float(layer.get(key, 0)))
        except Exception as e:
            log.debug(f"scale sync: {e}")
        self.syncing = False

    # -- monochrome controls (#32) -----------------------------------------
    def _on_monochrome_toggled(self, button):
        layer = self.current_layer()
        if layer is None:
            return
        layer["monochrome"] = button.get_active()
        button.set_label(
            self.tr("Monochrome on") if layer["monochrome"]
            else self.tr("Monochrome off"))
        # Enable/disable dependent controls.
        for child in self.settings_box:
            self._set_monochrome_child_sensitive(child, layer["monochrome"])
        self._refresh_preview()

    def _set_monochrome_child_sensitive(self, widget, sensitive):
        """Recursively enable/disable monochrome-dependent child widgets."""
        try:
            widget.set_sensitive(sensitive)
        except Exception:
            pass
        try:
            for child in widget:
                self._set_monochrome_child_sensitive(child, sensitive)
        except Exception:
            pass

    def _on_mono_color_picked(self, _button):
        layer = self.current_layer()
        if layer is None or self.dialog is None:
            return
        dialog = Gtk.ColorDialog()
        rgba = _rgba_from_hex(layer.get("mono_color", "#ffffff"))
        if rgba is None:
            rgba = Gdk.RGBA()
            rgba.parse("#ffffff")
        dialog.set_rgba(rgba)
        dialog.open(self.dialog, None, self._on_mono_color_done)

    def _on_mono_color_done(self, dialog, result):
        try:
            rgba = dialog.open_finish(result)
        except Exception:
            return
        hexa = _rgba_to_hex(rgba)
        if not hexa:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer["mono_color"] = hexa
        # Repaint the swatch.
        for child in self.settings_box:
            self._repaint_mono_swatch(child, hexa)
        self._refresh_preview()

    def _repaint_mono_swatch(self, widget, hexa):
        try:
            if widget.get_name() == "mono-swatch":
                widget.set_tooltip_text(hexa)
                provider = Gtk.CssProvider()
                provider.load_from_data(
                    f".mono-swatch {{ background-color: {hexa}; "
                    "border: 1px solid rgba(0,0,0,0.35); border-radius: 6px; "
                    "min-width: 24px; min-height: 24px; }}\n".encode("utf-8"))
                Gtk.StyleContext.add_provider_for_display(
                    Gdk.Display.get_default(), provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:
            pass
        try:
            for child in widget:
                self._repaint_mono_swatch(child, hexa)
        except Exception:
            pass

    def _on_invert_toggled(self, button):
        layer = self.current_layer()
        if layer is None:
            return
        layer["invert"] = button.get_active()
        button.set_label(
            self.tr("Invert on") if layer["invert"]
            else self.tr("Invert off"))
        self._refresh_preview()

    def _on_threshold_changed(self, scale):
        layer = self.current_layer()
        if layer is None or self.syncing:
            return
        layer["threshold"] = int(round(scale.get_value()))
        self._refresh_preview()

    # -- mask controls (#33) -----------------------------------------------
    def _build_mask_controls(self, layer):
        """Mask mode: none / auto (folder shape) / custom PNG/SVG (#33)."""
        kind = layer.get("type", LAYER_IMAGE)
        if kind not in (LAYER_IMAGE, LAYER_EMBLEM):
            return
        self.settings_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        mask_label = Gtk.Label(label=self.tr("Mask"))
        mask_label.set_xalign(0)
        mask_dropdown = Gtk.DropDown.new_from_strings([
            self.tr("None"),
            self.tr("Clip to folder shape (auto)"),
            self.tr("Custom mask image…"),
        ])
        mode_map = {0: "none", 1: "auto", 2: "custom"}
        mode = layer.get("mask_mode", "none")
        selected = 0
        for idx, m in mode_map.items():
            if m == mode:
                selected = idx
                break
        mask_dropdown.set_selected(selected)
        mask_dropdown.connect("notify::selected", self._on_mask_mode_changed)
        self.widgets["mask_mode"] = mask_dropdown
        self.settings_box.append(
            self._labelled_row(self.tr("Clip overlay to"), mask_dropdown))

        # Custom mask path + pick button.
        self.mask_path_button = Gtk.Button(label=self.tr("Pick mask image"))
        self.mask_path_button.connect("clicked", self._on_pick_mask)
        self.mask_path_button.set_sensitive(mode == "custom" and bool(
            self.widgets.get("mask_mode")))
        self.mask_path_label = Gtk.Label(label=str(layer.get("mask_path") or ""))
        self.mask_path_label.set_xalign(0)
        self.mask_path_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.mask_path_label.add_css_class("dim-label")
        self.mask_path_label.set_sensitive(mode == "custom")
        self.settings_box.append(
            self._labelled_row(self.tr("Mask file"), self.mask_path_button))
        self.settings_box.append(self.mask_path_label)
        self._update_mask_controls_sensitivity(mode)

    def _update_mask_controls_sensitivity(self, mode):
        custom = mode == "custom"
        btn = getattr(self, "mask_path_button", None)
        lbl = getattr(self, "mask_path_label", None)
        if btn is not None:
            btn.set_sensitive(custom)
        if lbl is not None:
            lbl.set_sensitive(custom)

    def _on_mask_mode_changed(self, dropdown):
        layer = self.current_layer()
        if layer is None:
            return
        mode_map = {0: "none", 1: "auto", 2: "custom"}
        mode = mode_map.get(dropdown.get_selected(), "none")
        layer["mask_mode"] = mode
        if mode != "custom":
            layer["mask_path"] = ""
        self._update_mask_controls_sensitivity(mode)
        self._refresh_preview()

    def _on_pick_mask(self, _button):
        layer = self.current_layer()
        if layer is None or self.dialog is None:
            return
        dialog = Gtk.FileDialog(title=self.tr("Pick mask image"))
        filt = _image_filter(self.tr("Mask images"))
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)
        dialog.set_default_filter(filt)
        self.file_dialog = dialog
        try:
            dialog.open(self.dialog, None, self._on_mask_picked)
        except Exception as e:
            log.error(f"mask dialog: {e}")

    def _on_mask_picked(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
            path = gfile.get_path()
        except Exception:
            return
        layer = self.current_layer()
        if layer is None or not path:
            return
        # Validate the mask loads before storing.
        try:
            from PIL import Image
            test = Image.open(path)
            test.load()
        except Exception as e:
            log.error(f"invalid mask {path}: {e}")
            self._show_alert(self.tr("Cannot open this mask image."))
            return
        layer["mask_path"] = path
        label = getattr(self, "mask_path_label", None)
        if label is not None:
            label.set_text(path)
        self._refresh_preview()

    # -- type specific controls -------------------------------------------
    def _build_text_controls(self, layer):
        entry = Gtk.Entry()
        entry.set_placeholder_text(self.tr("Type text"))
        entry.set_hexpand(True)
        self.syncing = True
        entry.set_text(str(layer.get("text") or ""))
        self.syncing = False
        entry.connect("changed", self._on_text_changed)
        self.widgets["text"] = entry

        # Emoji button beside the field: opens the native GTK EmojiChooser and
        # drops the picked emoji in at the cursor.
        emoji_button = Gtk.Button()
        emoji_button.set_tooltip_text(self.tr("Insert emoji"))
        try:
            image = Gtk.Image.new_from_icon_name("face-smile-symbolic")
            if image is not None:
                emoji_button.set_child(image)
        except Exception as e:
            log.debug(f"emoji icon: {e}")
            emoji_button.set_label("😀")
        emoji_button.connect("clicked", self._on_emoji_clicked, entry)
        self.widgets["emoji_button"] = emoji_button

        text_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        text_row.append(entry)
        text_row.append(emoji_button)
        self.settings_box.append(self._labelled_row(self.tr("Text"), text_row))

        families = self._font_family_names()
        dropdown = Gtk.DropDown.new_from_strings(families)
        current = str(layer.get("font") or "Sans")
        if current in families:
            self.syncing = True
            dropdown.set_selected(families.index(current))
            self.syncing = False
        dropdown.connect("notify::selected", self._on_font_changed)
        self.widgets["font"] = dropdown
        self.settings_box.append(
            self._labelled_row(self.tr("Font"), dropdown))

        spin = Gtk.SpinButton.new_with_range(8, 256, 1)
        self.syncing = True
        spin.set_value(int(layer.get("font_size", 64)))
        self.syncing = False
        spin.connect("value-changed", self._on_font_size_changed)
        self.widgets["font_size"] = spin
        self.settings_box.append(self._labelled_row(self.tr("Size"), spin))

        bold = Gtk.CheckButton(label=self.tr("Bold"))
        self.syncing = True
        bold.set_active(bool(layer.get("bold")))
        self.syncing = False
        bold.connect("toggled", self._on_bold_toggled)
        self.widgets["bold"] = bold

        italic = Gtk.CheckButton(label=self.tr("Italic"))
        self.syncing = True
        italic.set_active(bool(layer.get("italic")))
        self.syncing = False
        italic.connect("toggled", self._on_italic_toggled)
        self.widgets["italic"] = italic

        # Bold + Italic share one row to save vertical space.
        style_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        style_row.append(bold)
        style_row.append(italic)
        self.settings_box.append(style_row)

        colour = Gtk.ColorButton()
        colour.add_css_class("color-button")
        rgba = _rgba_from_hex(layer.get("color"))
        if rgba is not None:
            self.syncing = True
            colour.set_rgba(rgba)
            self.syncing = False
        colour.connect("color-set", self._on_text_colour_set)
        self.widgets["color"] = colour
        self.settings_box.append(
            self._labelled_row(self.tr("Text color"), colour))

    def _build_emblem_controls(self, layer):
        names = [str(item.get("icon") or "") for item in self.emblem_icons]
        labels = [str(item.get("label") or item.get("icon") or "")
                  for item in self.emblem_icons]
        uris = [str(item.get("uri") or "") for item in self.emblem_icons]
        dropdown = Gtk.DropDown.new_from_strings(labels or [""])
        dropdown.set_sensitive(bool(names))
        current = str(layer.get("emblem") or "")
        if current in names:
            self.syncing = True
            dropdown.set_selected(names.index(current))
            self.syncing = False
        dropdown.connect("notify::selected", self._on_emblem_changed)
        self.widgets["emblem"] = dropdown
        self.widgets["emblem_names"] = names
        self.widgets["emblem_uris"] = uris
        self.settings_box.append(
            self._labelled_row(self.tr("Select emblem"), dropdown))
        self._build_monochrome_controls(layer)
        self._build_mask_controls(layer)

    def _build_image_controls(self, layer):
        button = Gtk.Button(label=self.tr("Pick image"))
        button.connect("clicked", self._on_pick_image)
        self.settings_box.append(
            self._labelled_row(self.tr("Image"), button))
        path_label = Gtk.Label(label=str(layer.get("path") or ""))
        path_label.set_xalign(0)
        path_label.set_ellipsize(Pango.EllipsizeMode.END)
        path_label.add_css_class("dim-label")
        self.settings_box.append(path_label)
        self._build_monochrome_controls(layer)
        self._build_mask_controls(layer)
        # “Restore default base” — remove the custom base image and go back to
        # the themed folder icon (#31). Only shown when a custom base is set.
        self.restore_base_button = Gtk.Button(
            label=self.tr("Restore the default folder icon"))
        self.restore_base_button.add_css_class("destructive-action")
        self.restore_base_button.connect("clicked", self._on_restore_base_image)
        self.restore_base_button.set_sensitive(bool(self.base_image_path))
        self.settings_box.append(
            self._labelled_row(self.tr("Base image"), self.restore_base_button))

    def _build_monochrome_controls(self, layer):
        """Monochrome toggle + color / invert / threshold (#32)."""
        kind = layer.get("type", LAYER_IMAGE)
        if kind not in (LAYER_IMAGE, LAYER_EMBLEM):
            return
        self.settings_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        mono_label = Gtk.Label(label=self.tr("Monochrome"))
        mono_label.set_xalign(0)
        mono_button = Gtk.ToggleButton(
            label=self.tr("Monochrome on") if layer.get("monochrome")
            else self.tr("Monochrome off"))
        mono_button.set_active(bool(layer.get("monochrome")))
        mono_button.connect("toggled", self._on_monochrome_toggled)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(mono_label)
        row.append(mono_button)
        self.settings_box.append(row)

        # Tint color.
        color_button = Gtk.Button()
        color_button.set_size_request(24, 24)
        color_button.add_css_class("color-button")
        provider = Gtk.CssProvider()
        provider.load_from_data(
            f".mono-swatch {{ background-color: {layer.get('mono_color', '#ffffff')}; "
            "border: 1px solid rgba(0,0,0,0.35); border-radius: 6px; "
            "min-width: 24px; min-height: 24px; }}\n".encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        color_button.add_css_class("mono-swatch")
        color_button.set_name("mono-swatch")
        color_button.set_tooltip_text(layer.get("mono_color", "#ffffff"))
        color_button.connect("clicked", self._on_mono_color_picked)
        self.settings_box.append(
            self._labelled_row(self.tr("Tint color"), color_button))

        # Invert toggle.
        invert_button = Gtk.ToggleButton(
            label=self.tr("Invert on") if layer.get("invert")
            else self.tr("Invert off"))
        invert_button.set_active(bool(layer.get("invert")))
        invert_button.set_sensitive(bool(layer.get("monochrome")))
        invert_button.connect("toggled", self._on_invert_toggled)
        self.settings_box.append(
            self._labelled_row(self.tr("Invert threshold"), invert_button))

        # Threshold slider.
        low, high = _RANGES["threshold"]
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, 1)
        scale.set_hexpand(True)
        scale.set_digits(0)
        scale.set_value(float(layer.get("threshold", 128)))
        scale.set_sensitive(bool(layer.get("monochrome")))
        scale.connect("value-changed", self._on_threshold_changed)
        self.settings_box.append(
            self._labelled_row(self.tr("Threshold"), scale))

    def _font_family_names(self):
        if self.font_families is not None:
            return self.font_families
        names = []
        try:
            import cairo
            gi.require_version("PangoCairo", "1.0")
            from gi.repository import PangoCairo
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
            context = cairo.Context(surface)
            layout = PangoCairo.create_layout(context)
            families = layout.get_context().get_font_map().list_families()
            names = sorted({family.get_name() for family in families})
        except Exception as e:
            log.error(f"font family list failed: {e}")
            names = []
        if not names:
            names = ["Sans"]
        self.font_families = names
        return names

    # -- layer mutation handlers ------------------------------------------
    def _on_text_changed(self, entry):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer["text"] = entry.get_text()
        self._update_row_labels()
        self._refresh_preview()

    def _on_emoji_clicked(self, button, entry):
        """Open the native GTK EmojiChooser and insert the pick at the cursor.

        The chooser is created per click and unparented when it closes, so it
        never outlives the button (settings are rebuilt on every layer change).
        """
        try:
            chooser = Gtk.EmojiChooser()
        except Exception as e:
            log.error(f"emoji chooser: {e}")
            return

        def on_picked(_chooser, emoji):
            try:
                pos = entry.get_position()
                text = entry.get_text() or ""
                # set_text() fires "changed" -> _on_text_changed, which pushes
                # the new text into the layer and refreshes the preview.
                entry.set_text(text[:pos] + emoji + text[pos:])
                entry.set_position(pos + len(emoji))
                entry.grab_focus()
            except Exception as e:
                log.error(f"emoji insert: {e}")
            try:
                _chooser.popdown()
            except Exception:
                pass

        def on_closed(chooser_):
            try:
                chooser_.unparent()
            except Exception:
                pass

        chooser.connect("emoji-picked", on_picked)
        chooser.connect("closed", on_closed)
        try:
            chooser.set_parent(button)
            chooser.popup()
        except Exception as e:
            log.error(f"emoji popup: {e}")
            try:
                chooser.unparent()
            except Exception:
                pass

    def _on_font_changed(self, dropdown, _pspec):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        families = self._font_family_names()
        index = dropdown.get_selected()
        if 0 <= index < len(families):
            layer["font"] = families[index]
            self._refresh_preview()

    def _on_font_size_changed(self, spin):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer["font_size"] = int(spin.get_value())
        self._refresh_preview()

    def _on_bold_toggled(self, button):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer["bold"] = button.get_active()
        self._refresh_preview()

    def _on_italic_toggled(self, button):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        layer["italic"] = button.get_active()
        self._refresh_preview()

    def _on_text_colour_set(self, button):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        hexa = _rgba_to_hex(button.get_rgba())
        if hexa:
            layer["color"] = hexa
            self._refresh_preview()

    def _on_emblem_changed(self, dropdown, _pspec):
        if self.syncing:
            return
        layer = self.current_layer()
        if layer is None:
            return
        names = self.widgets.get("emblem_names") or []
        uris = self.widgets.get("emblem_uris") or []
        index = dropdown.get_selected()
        if 0 <= index < len(names):
            layer["emblem"] = names[index]
            layer["emblem_uri"] = uris[index] if index < len(uris) else ""
            layer["name"] = _derive_name(layer)
            self._update_row_labels()
            self._refresh_preview()

    # -- adding / removing / ordering -------------------------------------
    def _on_add_image_target(self, _menu_item, action):
        """User chose a target from the Add image menu (#30).

        ``action`` is one of: "layer" (new layer), "replace" (selected layer)
        or "base" (custom base image).
        """
        if self.dialog is None:
            return
        self._pending_image_target = action
        self._open_image_picker()

    def _open_image_picker(self):
        """Open the file picker for image import.

        The pending target (``_pending_image_target``) decides what happens
        with the chosen images: add as layer, replace the selected image layer
        or use as the custom base image.
        """
        action = getattr(self, "_pending_image_target", "layer")
        dialog = Gtk.FileDialog(title=self.tr("Pick image"))
        filt = _image_filter(self.tr("Images"))
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)
        dialog.set_default_filter(filt)
        self.file_dialog = dialog
        try:
            dialog.open_multiple(self.dialog, None, self._on_images_picked)
        except Exception as e:
            log.error(f"file dialog: {e}")

    def _on_add_image(self, _button):
        """Add image… default action: add chosen images as new layers (#30)."""
        self._pending_image_target = "layer"
        self._open_image_picker()

    def _on_images_picked(self, dialog, result):
        if self.dialog is None:
            log.debug("editor closed — ignoring the image selection")
            return
        try:
            model = dialog.open_multiple_finish(result)
        except Exception as e:
            log.debug(f"image selection cancelled: {e}")
            return
        paths = []
        for index in range(model.get_n_items()):
            gfile = model.get_item(index)
            path = gfile.get_path() if gfile is not None else None
            if path:
                paths.append(path)
        if not paths:
            return
        action = getattr(self, "_pending_image_target", "layer")
        if action == "base":
            # Single image becomes the custom base image. When several were
            # picked, use the first and warn.
            if len(paths) > 1:
                self._show_alert(self.tr(
                    "Using the first image as the base image; the others were "
                    "ignored."))
            self._set_base_image(paths[0])
            self._rebuild_rows()
            self._refresh_preview()
            return
        if action == "replace":
            layer = self.current_layer()
            if layer is None or layer.get("type") != LAYER_IMAGE:
                self._show_alert(self.tr(
                    "Select an image layer to replace."))
                return
            layer["path"] = paths[0]
            layer["name"] = _derive_name(layer)
            for extra in paths[1:]:
                self.layers.insert(0, default_layer(LAYER_IMAGE, path=extra))
            self.selected = 0 if len(paths) > 1 else self.selected
            self._update_row_labels()
            self._refresh_preview()
            return
        # Default: add every chosen image as a new layer on top of the stack.
        for offset, path in enumerate(paths):
            self.layers.insert(offset, default_layer(LAYER_IMAGE, path=path))
        self.selected = 0
        self._rebuild_rows()

    def _set_base_image(self, path):
        """Load ``path`` as the custom base image (#30).

        Replaces the themed folder icon in the preview/composition. Passing
        ``None`` or an empty string clears the custom base.
        """
        self.base_image_path = path or None
        self.base_image_pixbuf = None
        if path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(path)
                if pb is not None:
                    self.base_image_pixbuf = pb
            except Exception as e:
                log.error(f"load base image: {e}")
                self.base_image_path = None
                self.base_image_pixbuf = None
                self._show_alert(self.tr("Cannot open this image."))
        self._update_restore_base_button()

    def _on_restore_base_image(self, _button):
        """Clear the custom base image and restore the themed folder icon (#31)."""
        self._set_base_image(None)
        self._update_restore_base_button()
        self._rebuild_rows()
        self._refresh_preview()

    def _update_restore_base_button(self):
        """Show/hide/enable the restore-base button according to state."""
        button = getattr(self, "restore_base_button", None)
        if button is not None:
            button.set_sensitive(bool(self.base_image_path))

    def _on_row_use_as_base(self, _menu_item, index):
        """Use the image layer at ``index`` as the custom base image (#30)."""
        if not (0 <= index < len(self.layers)):
            return
        layer = self.layers[index]
        if layer.get("type") != LAYER_IMAGE or not layer.get("path"):
            return
        self._set_base_image(layer["path"])
        self.selected = index
        self._rebuild_rows()
        self._refresh_preview()

    def _on_row_remove(self, _menu_item, index):
        """Remove the layer at ``index`` from the context menu (#30)."""
        if not (0 <= index < len(self.layers)):
            return
        self.layers.pop(index)
        self.selected = min(index, len(self.layers) - 1)
        self._rebuild_rows()


    def _on_detect_icon(self, _button):
        """Look for an icon inside the folder and add the picked one."""
        if not self.scan_dir:
            return

        def on_chosen(path):
            if not path or self.dialog is None:
                return
            self.layers.insert(0, default_layer(LAYER_IMAGE, path=path,
                                                scale=_DETECTED_SCALE))
            self.selected = 0
            self._rebuild_rows()

        detect_icon_for_folder(self.scan_dir, tr=self.tr, on_chosen=on_chosen,
                               parent=self.dialog)

    def _on_add_text(self, _button):
        self.layers.insert(0, default_layer(LAYER_TEXT, text="Text"))
        self.selected = 0
        self._rebuild_rows()

    def _on_add_emblem(self, _button):
        name = ""
        uri = ""
        if self.emblem_icons:
            first = self.emblem_icons[0]
            name = str(first.get("icon") or "")
            uri = str(first.get("uri") or "")
        self.layers.insert(0, default_layer(LAYER_EMBLEM, emblem=name,
                                            emblem_uri=uri))
        self.selected = 0
        self._rebuild_rows()

    def _on_pick_image(self, _button):
        layer = self.current_layer()
        if layer is None or self.dialog is None:
            return
        dialog = Gtk.FileDialog(title=self.tr("Pick image"))
        filt = _image_filter(self.tr("Images"))
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)
        dialog.set_default_filter(filt)
        self.file_dialog = dialog
        try:
            dialog.open(self.dialog, None, self._on_image_picked)
        except Exception as e:
            log.error(f"file dialog: {e}")

    def _on_image_picked(self, dialog, result):
        if self.dialog is None:
            log.debug("editor closed — ignoring the image selection")
            return
        try:
            gfile = dialog.open_finish(result)
            path = gfile.get_path()
        except Exception as e:
            log.debug(f"image selection cancelled: {e}")
            return
        layer = self.current_layer()
        if layer is None or not path:
            return
        if _open_image(path) is None:
            log.error(f"cannot open image: {path}")
            return
        layer["path"] = path
        self._update_row_labels()
        self._refresh_preview()

    def _on_remove_layer(self, _button):
        if not (0 <= self.selected < len(self.layers)):
            return
        self.layers.pop(self.selected)
        self.selected = min(self.selected, len(self.layers) - 1)
        self._rebuild_rows()

    # -- PNG export / project reopen (#34) ---------------------------------
    def _compose_current_png(self):
        """Compose the current editor state into PNG bytes (or None)."""
        spec = ";".join(self.effective_hexes())
        base = self._base_for(spec)
        return compose_layers(base, self.layers)

    def _on_export_png(self, _button):
        """Export the current composition as a PNG with embedded project metadata (#34)."""
        if self.dialog is None:
            return
        png = self._compose_current_png()
        if not png:
            self._show_alert(self.tr("Nothing to export."))
            return
        # Embed project metadata so the PNG can be reopened editably.
        theme = ""
        try:
            theme = str((self.scopes.get(self.scope) or {}).get("theme") or "")
        except Exception:
            pass
        png = save_png_project(
            png, self.effective_hexes(), self.layers, theme,
            self.base_image_path or "")
        if png is None:
            self._show_alert(self.tr("Could not embed project metadata."))
            return
        dialog = Gtk.FileDialog(title=self.tr("Export PNG"))
        filt = _image_filter(self.tr("PNG image"))
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)
        dialog.set_default_filter(filt)
        self.file_dialog = dialog
        try:
            dialog.save(self.dialog, None, self._on_export_png_done, png)
        except Exception as e:
            log.error(f"export dialog: {e}")

    def _on_export_png_done(self, dialog, result, png_bytes):
        try:
            gfile = dialog.save_finish(result)
            path = gfile.get_path()
        except Exception:
            return
        if not path:
            return
        import os as _os
        if _os.path.exists(path):
            # Confirm overwrite.
            alert = Gtk.AlertDialog.new(
                self.tr("The file already exists. Replace it?"))
            # Modal confirmation is best-effort; proceed on accept.
            try:
                alert.show(self.dialog)
            except Exception:
                pass
        try:
            with open(path, "wb") as f:
                f.write(png_bytes)
        except Exception as e:
            log.error(f"write png {path}: {e}")
            self._show_alert(self.tr("Could not write the PNG file."))
            return
        # Offer to open the containing folder.
        try:
            folder = _os.path.dirname(path)
            if folder:
                Gtk.show_uri_on_window(
                    self.dialog, f"file://{folder}", Gdk.CURRENT_TIME)
        except Exception:
            pass

    def _on_open_project(self, _button):
        """Open a previously exported PNG and restore its project state (#34)."""
        if self.dialog is None:
            return
        dialog = Gtk.FileDialog(title=self.tr("Open project"))
        filt = _image_filter(self.tr("PNG image"))
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)
        dialog.set_default_filter(filt)
        self.file_dialog = dialog
        try:
            dialog.open(self.dialog, None, self._on_open_project_done)
        except Exception as e:
            log.error(f"open project dialog: {e}")

    def _on_open_project_done(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
            path = gfile.get_path()
        except Exception:
            return
        if not path:
            return
        state = load_png_project(path)
        if not state:
            self._show_alert(self.tr("No project data in this PNG."))
            return
        # Restore colours.
        spec = str(state.get("spec") or "")
        hexes = ["#" + part for part in spec.split(";") if len(part) == 6]
        if hexes:
            self.hexes = self._init_hexes(hexes)
            scope = self.scopes.get(self.scope)
            if scope is not None:
                scope["hexes"] = self.hexes
        # Restore layers.
        layers = state.get("layers")
        if isinstance(layers, list):
            self.layers = normalize_layers(layers)
            scope = self.scopes.get(self.scope)
            if scope is not None:
                scope["layers"] = self.layers
            self.selected = 0 if self.layers else -1
        # Restore theme and base image.
        scope = self.scopes.get(self.scope)
        if scope is not None:
            scope["theme"] = str(state.get("theme") or "")
            scope["base_image_path"] = str(state.get("base_image") or "")
            self.base_image_path = scope["base_image_path"]
            self.base_image_pixbuf = None
            if self.base_image_path:
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file(self.base_image_path)
                    if pb is not None:
                        self.base_image_pixbuf = pb
                except Exception as e:
                    log.error(f"restore base image: {e}")
                    self.base_image_path = None
        self.base_cache.clear()
        self._sync_colour_rows()
        self._rebuild_rows()
        self._refresh_preview()

    # -- icon gallery (#36) -------------------------------------------------
    def _on_open_gallery(self, _button):
        """Open the managed icon gallery (#36)."""
        if self.dialog is None:
            return
        if self.on_gallery_list is None:
            self._show_alert(self.tr("Gallery is not available."))
            return
        try:
            entries = self.on_gallery_list() or []
        except Exception as e:
            log.error(f"gallery list: {e}")
            self._show_alert(self.tr("Could not list the gallery."))
            return

        win = Gtk.Window(title=self.tr("Icon gallery"))
        win.set_transient_for(self.dialog)
        win.set_modal(True)
        win.set_default_size(700, 500)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        flow = Gtk.FlowBox()
        flow.set_valign(Gtk.Align.START)
        flow.set_max_children_per_line(4)
        flow.set_column_spacing(12)
        flow.set_row_spacing(12)
        flow.set_homogeneous(True)

        for entry in entries:
            card = self._gallery_card(entry)
            flow.append(card)

        scrolled.set_child(flow)
        vbox.append(scrolled)

        close_btn = Gtk.Button(label=self.tr("Close"))
        close_btn.set_halign(Gtk.Align.END)
        close_btn.connect("clicked", lambda _b: win.close())
        vbox.append(close_btn)

        win.set_child(vbox)
        win.show()

    def _gallery_card(self, entry):
        """Build a gallery card: thumbnail + name + apply/remove (#36)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_hexpand(True)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        content_hash = str(entry.get("hash") or "")
        png_path = str(entry.get("png") or "")

        # Thumbnail.
        picture = Gtk.Picture()
        try:
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_halign(Gtk.Align.CENTER)
            picture.set_valign(Gtk.Align.CENTER)
        except Exception:
            pass
        texture = _pixbuf_to_texture(
            GdkPixbuf.Pixbuf.new_from_file_at_size(png_path, 120, 120)
            if png_path and os.path.exists(png_path) else None)
        if texture is not None:
            picture.set_paintable(texture)
        box.append(picture)

        # Name.
        name = str(entry.get("name") or "")
        if not name:
            name = self.tr("Untitled")
        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0.5)
        name_label.set_wrap(True)
        name_label.set_max_width_chars(18)
        box.append(name_label)

        # Date.
        updated = str(entry.get("updated") or "")[:16]
        date_label = Gtk.Label(label=updated)
        date_label.set_xalign(0.5)
        date_label.add_css_class("dim-label")
        date_label.set_margin_bottom(6)
        box.append(date_label)

        # Buttons.
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row.set_halign(Gtk.Align.CENTER)

        apply_btn = Gtk.Button(label=self.tr("Apply"))
        apply_btn.connect("clicked", self._on_gallery_apply_card, content_hash)
        btn_row.append(apply_btn)

        used_by = entry.get("used_by") or []
        remove_btn = Gtk.Button(label=self.tr("Remove"))
        remove_btn.add_css_class("destructive-action")
        remove_btn.set_sensitive(not used_by)
        if used_by:
            remove_btn.set_tooltip_text(
                self.tr("In use by {n} folder(s)").format(n=len(used_by)))
        remove_btn.connect("clicked", self._on_gallery_remove_card, content_hash)
        btn_row.append(remove_btn)

        box.append(btn_row)
        return box

    def _on_gallery_apply_card(self, _button, content_hash):
        """Apply a gallery entry to the current folder (#36)."""
        if self.on_gallery_apply is None:
            return
        try:
            entry = self.on_gallery_apply(content_hash)
        except Exception as e:
            log.error(f"gallery apply: {e}")
            self._show_alert(self.tr("Could not apply the gallery icon."))
            return
        if entry is None:
            return
        # Restore the editor state from the gallery entry so the user can
        # keep editing.
        spec = str(entry.get("spec") or "")
        hexes = ["#" + part for part in spec.split(";") if len(part) == 6]
        if hexes:
            self.hexes = self._init_hexes(hexes)
            scope = self.scopes.get(self.scope)
            if scope is not None:
                scope["hexes"] = self.hexes
        layers = entry.get("layers")
        if isinstance(layers, list):
            self.layers = normalize_layers(layers)
            scope = self.scopes.get(self.scope)
            if scope is not None:
                scope["layers"] = self.layers
            self.selected = 0 if self.layers else -1
        scope = self.scopes.get(self.scope)
        if scope is not None:
            scope["theme"] = str(entry.get("theme") or "")
            scope["base_image_path"] = str(entry.get("base_image") or "")
            self.base_image_path = scope["base_image_path"]
            self.base_image_pixbuf = None
            if self.base_image_path:
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file(self.base_image_path)
                    if pb is not None:
                        self.base_image_pixbuf = pb
                except Exception as e:
                    log.error(f"restore base image: {e}")
                    self.base_image_path = None
        self.base_cache.clear()
        self._sync_colour_rows()
        self._rebuild_rows()
        self._refresh_preview()

    def _on_gallery_remove_card(self, _button, content_hash):
        """Remove a gallery entry (#36)."""
        if self.on_gallery_remove is None:
            return
        try:
            ok = self.on_gallery_remove(content_hash)
        except Exception as e:
            log.error(f"gallery remove: {e}")
            ok = False
        if not ok:
            self._show_alert(self.tr("Cannot remove an icon in use."))
            return
        self._on_open_gallery(None)

    def _on_move_up(self, _button):
        self._move_selected(-1)

    def _on_move_down(self, _button):
        self._move_selected(1)

    def _move_selected(self, delta):
        index = self.selected
        target = index + delta
        if index < 0 or target < 0 or target >= len(self.layers):
            return
        layer = self.layers.pop(index)
        self.layers.insert(target, layer)
        self.selected = target
        self._rebuild_rows()

    def _on_drag_prepare(self, _source, _x, _y, index):
        value = GObject.Value(GObject.TYPE_STRING, str(index))
        return Gdk.ContentProvider.new_for_value(value)

    def _on_drop(self, target, value, _x, y, index):
        try:
            source_index = _payload_index(value)
        except (TypeError, ValueError) as e:
            log.debug(f"unparsable drag payload {value!r}: {e}")
            return False
        if source_index == index or not (0 <= source_index < len(self.layers)):
            return False
        row = target.get_widget() if target is not None else None
        height = row.get_height() if row is not None else 0
        if height <= 0:
            height = 40  # the row is not allocated yet
        anchor = _drop_anchor(source_index, index, y, height)
        if anchor is None:
            return False
        layer = self.layers.pop(source_index)
        self.layers.insert(anchor, layer)
        self.selected = anchor
        # The rows must not be destroyed while the drag is still running.
        GLib.idle_add(self._deferred_rebuild)
        return True

    def _deferred_rebuild(self):
        if self.dialog is None:
            return False
        self._rebuild_rows()
        return False

    # -- colour rows ------------------------------------------------------
    def _set_row(self, index, hexa, from_entry=True, from_picker=True):
        if self.syncing:
            return
        self.syncing = True
        try:
            self.hexes[index] = hexa
            rgba = _rgba_from_hex(hexa)
            if from_picker and rgba is not None:
                try:
                    self.pickers[index].set_rgba(rgba)
                except Exception as e:
                    log.debug(f"picker update: {e}")
            if from_entry and self.entries[index].get_text().strip() != hexa:
                try:
                    self.entries[index].set_text(hexa)
                except Exception as e:
                    log.debug(f"entry update: {e}")
        finally:
            self.syncing = False
        self._refresh_preview()

    def _on_entry_changed(self, entry, index):
        if self.syncing:
            return
        raw = entry.get_text()
        if ";" in raw:
            chunks = [chunk.strip() for chunk in raw.split(";")]
            for offset, chunk in enumerate(chunks):
                target = index + offset
                if target >= self.row_count:
                    break
                resolved = _resolve_color(chunk)
                if resolved:
                    self._set_row(target, resolved)
            return
        resolved = _resolve_color(raw)
        if resolved:
            self._set_row(index, resolved, from_entry=False)

    def _on_picker_set(self, picker, index):
        hexa = _rgba_to_hex(picker.get_rgba())
        if hexa:
            self._set_row(index, hexa, from_picker=False)

    def _on_palette_color(self, _button, hex_color):
        """Apply a quick palette colour to every colour row (#31)."""
        resolved = _normalize_hex(hex_color) or hex_color
        if not resolved:
            return
        self.syncing = True
        try:
            for index in range(self.row_count):
                self.hexes[index] = resolved
                if index < len(self.entries):
                    self.entries[index].set_text(resolved)
                    rgba = _rgba_from_hex(resolved)
                    if rgba is not None and index < len(self.pickers):
                        self.pickers[index].set_rgba(rgba)
        finally:
            self.syncing = False
        self._refresh_preview()

    def _on_custom_colour(self, _button):
        """Open a colour picker and apply the chosen colour to all rows (#31)."""
        try:
            dialog = Gtk.ColorDialog()
            rgba = _rgba_from_hex(self.hexes[0] if self.hexes else "#808080")
            if rgba is None:
                rgba = Gdk.RGBA()
                rgba.parse("#808080")
            dialog.set_rgba(rgba)
            dialog.open(self.dialog, None, self._on_custom_colour_done)
        except Exception as e:
            log.error(f"custom colour dialog: {e}")

    def _on_custom_colour_done(self, dialog, result):
        try:
            rgba = dialog.open_finish(result)
        except Exception as e:
            log.debug(f"custom colour cancelled: {e}")
            return
        hexa = _rgba_to_hex(rgba)
        if not hexa:
            return
        self.syncing = True
        try:
            for index in range(self.row_count):
                self.hexes[index] = hexa
                if index < len(self.entries):
                    self.entries[index].set_text(hexa)
                    if index < len(self.pickers):
                        self.pickers[index].set_rgba(rgba)
        finally:
            self.syncing = False
        self._refresh_preview()

    # -- preview ----------------------------------------------------------
    def _active_theme(self):
        scope = self.scopes.get(self.scope) or {}
        return str(scope.get("theme") or "")

    def _base_for(self, spec):
        """Base folder image for ``spec`` in the active scope's theme.

        When a custom base image was chosen (#30), it takes precedence over
        the themed folder icon. ``theme_builder(spec, theme)`` is preferred
        because it can render another theme's folder shape; without it the
        legacy single-argument builder is used.
        """
        if self.base_image_pixbuf is not None:
            try:
                data = _pixbuf_to_png(self.base_image_pixbuf)
                if data:
                    return _pil_from_png(data)
            except Exception as e:
                log.error(f"base image pixbuf: {e}")
        theme = self._active_theme()
        key = spec if not theme else spec + "|" + theme
        if key in self.base_cache:
            return self.base_cache[key]
        image = None
        try:
            if self.theme_builder is not None:
                image = self.theme_builder(spec, theme)
            else:
                image = self.base_builder(spec)
        except Exception as e:
            log.error(f"base image failed: {e}")
        self.base_cache[key] = image
        while len(self.base_cache) > 3:
            self.base_cache.popitem(last=False)
        return image

    def _refresh_preview(self):
        spec = ";".join(self.effective_hexes())
        data = compose_layers(self._base_for(spec), self.layers)
        if data:
            try:
                loader = GdkPixbuf.PixbufLoader.new_with_mime_type("image/png")
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
                if pixbuf is not None and pixbuf.get_width() != PREVIEW_SIZE:
                    pixbuf = pixbuf.scale_simple(PREVIEW_SIZE, PREVIEW_SIZE,
                                                 GdkPixbuf.InterpType.BILINEAR)
                texture = _pixbuf_to_texture(pixbuf)
                if texture is None:
                    log.error("preview texture could not be built")
                else:
                    self.preview.set_paintable(texture)
                    self._check_preview_size()
            except Exception as e:
                log.error(f"preview pixbuf: {e}")
        self._update_count()

    def _check_preview_size(self):
        """Warn when the preview does not measure PREVIEW_SIZE pixels."""
        try:
            natural = self.preview.measure(
                Gtk.Orientation.HORIZONTAL, -1).natural
        except Exception as e:
            log.debug(f"preview measure: {e}")
            return
        if natural == self._preview_natural:
            return
        self._preview_natural = natural
        if natural != PREVIEW_SIZE:
            log.warning(f"preview measures {natural}px, "
                        f"expected {PREVIEW_SIZE}px")

    def _update_count(self):
        self.count_label.set_text(str(len(self.layers)))

    # -- canvas interaction -----------------------------------------------
    def _on_canvas_scroll(self, controller, _dx, dy):
        layer = self.current_layer()
        if layer is None:
            return Gdk.EVENT_PROPAGATE
        state = controller.get_current_event_state() or 0
        step = max(1, int(round(abs(dy))))
        sign = 1 if dy < 0 else -1
        if state & Gdk.ModifierType.CONTROL_MASK:
            key = "hue"
        elif state & Gdk.ModifierType.SHIFT_MASK:
            key = "rotation"
        elif state & Gdk.ModifierType.ALT_MASK:
            key = "opacity"
        else:
            key = "scale"
        low, high = _RANGES[key]
        layer[key] = max(low, min(high, int(layer.get(key, 0)) + sign * 5 * step))
        self._sync_slider(key)
        self._refresh_preview()
        return Gdk.EVENT_STOP

    def _on_drag_begin(self, _gesture, _x, _y):
        layer = self.current_layer()
        self.drag_active = layer is not None
        self.drag_base = ((layer["offset_x"], layer["offset_y"])
                          if layer is not None else (0, 0))

    def _on_drag_update(self, _gesture, offset_x, offset_y):
        if not self.drag_active:
            return
        layer = self.current_layer()
        if layer is None:
            return
        allocation = self.preview.get_allocated_width() or PREVIEW_SIZE
        factor = CANVAS_SIZE / float(allocation)
        new_x = self.drag_base[0] + int(offset_x * factor)
        new_y = self.drag_base[1] + int(offset_y * factor)
        new_x = max(-CANVAS_SIZE, min(CANVAS_SIZE, new_x))
        new_y = max(-CANVAS_SIZE, min(CANVAS_SIZE, new_y))
        if (new_x, new_y) == (layer["offset_x"], layer["offset_y"]):
            return
        layer["offset_x"] = new_x
        layer["offset_y"] = new_y
        self._sync_slider("offset_x")
        self._sync_slider("offset_y")
        self._refresh_preview()

    def _on_drag_end(self, gesture, offset_x, offset_y):
        self._on_drag_update(gesture, offset_x, offset_y)
        self.drag_active = False

    # -- dialog result ----------------------------------------------------
    def _show_alert(self, message):
        """Show an error alert; never let it raise back into Nautilus."""
        try:
            parent = self.dialog
            Gtk.AlertDialog(message=message).show(parent)
        except Exception as e:
            log.error(f"alert: {e}")

    def _scope_dirty(self, scope_name):
        """True when the scope differs from the snapshot taken at open."""
        scope = self.scopes.get(scope_name) or {}
        snapshot = scope.get("initial")
        if snapshot is None:
            return True
        return _scope_snapshot(scope) != snapshot

    def _apply_folder_scope(self):
        """Folder scope: colours/layers first, then the theme when changed."""
        scope = self.scopes[SCOPE_FOLDER]
        theme = str(scope.get("theme") or "")
        initial_theme = str((scope.get("initial") or {}).get("theme") or "")
        if theme != initial_theme and callable(self.on_apply_theme):
            try:
                if self.on_apply_theme(theme) is False:
                    return False
            except Exception as e:
                log.error(f"apply folder theme: {e}")
                return False
        try:
            return self.on_apply(list(scope["hexes"]),
                                 normalize_layers(scope["layers"]),
                                 base_image=scope.get("base_image_path"))
        except Exception as e:
            log.error(f"apply failed: {e}")
            return False

    def _apply_global_scope(self):
        """Global scope: only when something actually changed."""
        if self.global_host is None:
            return True
        if not self._scope_dirty(SCOPE_GLOBAL):
            return True
        scope = self.scopes[SCOPE_GLOBAL]
        spec = ";".join(str(value).lstrip("#").lower()
                        for value in scope["hexes"])
        try:
            return self.global_host.apply(
                spec=spec,
                layers=normalize_layers(scope["layers"]),
                theme=str(scope.get("theme") or ""),
                follow_accent=bool(scope.get("follow_accent")),
                base_image=scope.get("base_image_path"))
        except Exception as e:
            log.error(f"apply global icon: {e}")
            return False

    def _on_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            self.scopes[self.scope]["selected"] = self.selected
            # Only an explicit False means "the host could not apply this";
            # older hosts return None on success.
            if self._apply_folder_scope() is False:
                # Keep the dialog open so the user can fix the problem and
                # retry (or cancel).
                self._show_alert(self.tr("Cannot open this image."))
                return
            if self._apply_global_scope() is False:
                self._show_alert(self.tr("Could not apply the global icon."))
                return
        self.dialog = None
        try:
            dialog.destroy()
        except Exception as e:
            log.debug(f"dialog destroy: {e}")
        try:
            _OPEN_EDITORS.remove(self)
        except ValueError:
            pass


def open_editor(*, title, row_count, hexes, layers, base_builder, on_apply,
                emblem_icons=None, tr=None, scan_dir=None,
                on_apply_theme=None, theme_builder=None, global_host=None,
                on_gallery_list=None, on_gallery_apply=None,
                on_gallery_remove=None):
    """Open the layer editor dialog.

    ``base_builder(spec)`` returns the folder icon base image (PIL) for the
    given colour spec, ``on_apply(hexes, layers)`` is called when the user
    confirms the dialog. ``scan_dir`` is the folder being customised: when
    it is set the editor offers to detect an icon inside it.

    ``theme_builder(spec, theme)`` renders the base of a *named* icon theme
    ('' means the current one); ``on_apply_theme(theme)`` reports the folder
    theme selected in the Folder tab. ``global_host`` enables the Global tab
    (#21): it must provide ``themes()``, ``state()``, ``apply(...)``,
    ``restore()``, ``is_active()`` and ``accent_hex()``.

    ``on_gallery_list()`` -> list of gallery entries; ``on_gallery_apply(hash)``
    -> entry state (or None); ``on_gallery_remove(hash)`` -> bool (#36).
    """
    try:
        editor = _Editor(title=title, row_count=row_count, hexes=hexes,
                         layers=layers, base_builder=base_builder,
                         on_apply=on_apply, emblem_icons=emblem_icons, tr=tr,
                         scan_dir=scan_dir, on_apply_theme=on_apply_theme,
                         theme_builder=theme_builder, global_host=global_host,
                         on_gallery_list=on_gallery_list,
                         on_gallery_apply=on_gallery_apply,
                         on_gallery_remove=on_gallery_remove)
    except Exception as e:
        log.error(f"icon editor could not be opened: {e}")
        return
    _OPEN_EDITORS.append(editor)
    try:
        # Wayland: presenting synchronously from a menu-activate handler leaves
        # pointer events stuck on the dying Nautilus menu, so the dialog shows
        # up with dead buttons. One idle turn lets the menu dismiss first.
        GLib.idle_add(editor.dialog.present)
    except Exception as e:
        log.error(f"icon editor dialog: {e}")
        try:
            _OPEN_EDITORS.remove(editor)
        except ValueError:
            pass
