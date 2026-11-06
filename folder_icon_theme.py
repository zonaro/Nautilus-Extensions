"""Global folder icon theme support for Folder Color Revival (#21).

The per-folder customizer writes ``metadata::custom-icon`` on individual
folders. This module adds the *global* scope: a derived icon theme installed
under ``~/.local/share/icons/zonaro-folder-<digest>`` that overrides only the
``folder`` icon and inherits everything else from the user's current theme.
Activating it through ``org.gnome.desktop.interface icon-theme`` changes the
icon of every folder that has no individual customization.

It also owns the pieces that need to survive outside a single dialog session:

* the GNOME accent colour map (``accent-color`` -> ``#rrggbb``),
* discovery of the installed icon themes that carry a folder icon,
* writing/pruning the derived theme (PNG sizes + ``index.theme``),
* the persisted global state (``~/.config/nautilus-extensions/…json``),
* a single accent watcher shared by the whole extension process.

Every helper is defensive: a missing Gio, a broken JSON file, an unreadable
theme or a vanished accent setting degrades to a documented fallback instead
of raising inside Nautilus.
"""

import hashlib
import io
import json
import logging
import os
import re
import tempfile
from pathlib import Path

log = logging.getLogger("folder-color-revival.icon-theme")

# State file schema version. Bump it when a key changes meaning, never when a
# new optional key is merely added (readers ignore unknown keys).
STATE_VERSION = 1

# Prefix of the themes this module owns; anything else is the user's.
DERIVED_PREFIX = "zonaro-folder-"

STATE_FILENAME = "folder-icon-global.json"

# Sizes written into the derived theme. 256 is the editor canvas; the smaller
# ones keep the shell's small-icon views crisp.
ICON_SIZES = (32, 48, 64, 128, 256)

# GNOME 47+ accent palette (libadwaita's AdwAccentColor values). "blue" is the
# default when accent-color is unset or unknown.
ACCENT_COLORS = {
    "blue": "#3584e4",
    "teal": "#2190a4",
    "green": "#3a944a",
    "yellow": "#c88800",
    "orange": "#ed5b00",
    "red": "#e62d42",
    "pink": "#d56199",
    "purple": "#9141ac",
    "slate": "#6f8396",
}

DEFAULT_ACCENT = "blue"

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Set by watch_accent(): one Gio.Settings connection per process is enough,
# a second dialog must not stack another handler on the same key.
_ACCENT_HANDLER = None
_ACCENT_SETTINGS = None


# ---------------------------------------------------------------------------
# Accent colour
# ---------------------------------------------------------------------------

def normalize_accent(name):
    """Accent setting value -> palette key; unknown/empty -> 'blue'."""
    value = str(name or "").strip().lower()
    if value in ACCENT_COLORS:
        return value
    return DEFAULT_ACCENT


def accent_hex(name, fallback=""):
    """Palette key -> '#rrggbb'.

    An unknown key falls back to ``fallback`` when it is a valid hex colour,
    otherwise to the default accent. A raw ``#rrggbb`` passed as ``name`` (a
    future/unknown GNOME accent) is usable as-is instead of painting the
    folder black.
    """
    value = str(name or "").strip().lower()
    if value in ACCENT_COLORS:
        return ACCENT_COLORS[value]
    match = _HEX_RE.match(value)
    if match:
        return "#" + match.group(1).lower()
    match = _HEX_RE.match(str(fallback or "").strip())
    if match:
        return "#" + match.group(1).lower()
    return ACCENT_COLORS[DEFAULT_ACCENT]


def resolve_accent_hex(setting_value=None):
    """Hex colour for a raw ``accent-color`` value (None reads the setting)."""
    if setting_value is None:
        setting_value = get_accent_name()
    return accent_hex(setting_value)


# ---------------------------------------------------------------------------
# Icon theme discovery
# ---------------------------------------------------------------------------

def icon_base_dirs():
    """Directories that may hold icon themes, most specific first."""
    home = str(Path.home())
    dirs = [os.path.join(home, ".icons"),
            os.path.join(home, ".local", "share", "icons")]
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for entry in data_dirs.split(":"):
        if entry.strip():
            dirs.append(os.path.join(entry.strip(), "icons"))
    # Stable de-duplication, order preserved (user themes win).
    seen = set()
    result = []
    for path in dirs:
        if path in seen or not os.path.isdir(path):
            continue
        seen.add(path)
        result.append(path)
    return result


def safe_theme_name(name):
    """True when ``name`` is a plain directory name (no traversal)."""
    value = str(name or "")
    return bool(value) and bool(_SAFE_NAME_RE.match(value)) \
        and not value.startswith(".")


def theme_directories(theme):
    """Existing directories of ``theme`` across the icon base dirs."""
    if not safe_theme_name(theme):
        return []
    return [os.path.join(base, theme) for base in icon_base_dirs()
            if os.path.isdir(os.path.join(base, theme))]


def _folder_icon_in(theme_dir):
    """Path of a theme's 'folder' icon, SVG first, or ''."""
    scalable = os.path.join(theme_dir, "scalable", "places", "folder.svg")
    if os.path.isfile(scalable):
        return scalable
    places = os.path.join(theme_dir, "places")
    candidates = []
    for root, _dirs, files in os.walk(places):
        for name in ("folder.svg", "folder.png", "folder.xpm"):
            if name in files:
                candidates.append(os.path.join(root, name))
    if not candidates:
        return ""
    # SVG beats PNG, bigger beats smaller, so the rasteriser has the best
    # source available.
    def rank(path):
        svg = path.endswith(".svg")
        match = re.search(r"(\d+)x\d+", path)
        return (0 if svg else 1, -(int(match.group(1)) if match else 0), path)

    return sorted(candidates, key=rank)[0]


def theme_folder_icon(theme):
    """'folder' icon file of ``theme`` ('' when the theme has none)."""
    for theme_dir in theme_directories(theme):
        found = _folder_icon_in(theme_dir)
        if found:
            return found
    return ""


def _theme_label(theme_dir, fallback):
    """'Name' from index.theme, else the directory name."""
    index = os.path.join(theme_dir, "index.theme")
    try:
        with open(index, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("Name="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return value
    except OSError:
        pass
    return fallback


def discover_folder_themes(exclude_derived=True):
    """Installed themes that can supply a folder icon.

    Returns a list of ``{"name", "label", "path"}`` dicts sorted by label.
    Derived themes are skipped by default: inheriting one of our own themes
    would nest the derived icon into itself.
    """
    found = {}
    for base in icon_base_dirs():
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            continue
        for entry in entries:
            if entry in found or not safe_theme_name(entry):
                continue
            if exclude_derived and entry.startswith(DERIVED_PREFIX):
                continue
            theme_dir = os.path.join(base, entry)
            if not os.path.isdir(theme_dir):
                continue
            if not os.path.isfile(os.path.join(theme_dir, "index.theme")):
                continue
            if not _folder_icon_in(theme_dir):
                continue
            found[entry] = {"name": entry,
                            "label": _theme_label(theme_dir, entry),
                            "path": theme_dir}
    return sorted(found.values(), key=lambda item: (item["label"].lower(),
                                                    item["name"]))


# ---------------------------------------------------------------------------
# Derived theme (the global override)
# ---------------------------------------------------------------------------

def derived_theme_root():
    """~/.local/share/icons — where our derived themes live."""
    home = str(Path.home())
    return os.path.join(home, ".local", "share", "icons")


def derived_theme_name(theme, spec, layers=None, extra=""):
    """Deterministic name of the derived theme for a state.

    Same state -> same directory, so re-applying rewrites in place and the
    shell's icon cache (keyed by theme name) is invalidated by the rewrite.
    ``extra`` folds inputs that are not part of the palette/layers (a custom
    base image fingerprint, the accent-follow flag) into the digest, so two
    different compositions never share a cached theme name.
    """
    digest = hashlib.md5(json.dumps(
        {"theme": str(theme or ""), "spec": str(spec or ""),
         "layers": layers or [], "extra": str(extra or "")},
        sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return DERIVED_PREFIX + digest


def list_derived_themes(root=None):
    """Paths of every derived theme installed on the system."""
    base = root or derived_theme_root()
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return []
    return [os.path.join(base, entry) for entry in entries
            if entry.startswith(DERIVED_PREFIX)
            and os.path.isdir(os.path.join(base, entry))]


def _resize_png(data, size):
    """PNG bytes resized to ``size``; the original bytes when PIL is absent."""
    try:
        from PIL import Image
    except Exception:  # pragma: no cover - PIL ships with the extension
        return data
    try:
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        if image.size != (size, size):
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as e:
        log.error(f"resize derived icon: {e}")
        return data


def write_derived_theme(name, base_theme, png_bytes, root=None):
    """Create/refresh a derived theme directory.

    ``png_bytes`` is the 256px icon; smaller sizes are generated from it.
    Returns the theme directory, or '' when it could not be written.
    """
    if not safe_theme_name(name) or not name.startswith(DERIVED_PREFIX):
        log.error(f"refusing unsafe derived theme name: {name!r}")
        return ""
    if not png_bytes:
        return ""
    base = root or derived_theme_root()
    target = os.path.join(base, name)
    lines = [
        "[Icon Theme]",
        f"Name={name}",
        "Comment=Global folder icon managed by Folder Color Revival",
        "Example=folder",
        f"Inherits={base_theme}",
        "Directories=" + ",".join(f"{size}x{size}/places"
                                  for size in ICON_SIZES),
        "",
    ]
    try:
        for size in ICON_SIZES:
            folder = os.path.join(target, f"{size}x{size}", "places")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "folder.png")
            data = png_bytes if size == ICON_SIZES[-1] \
                else _resize_png(png_bytes, size)
            # Atomic per file: Nautilus may read while we rewrite.
            fd, temp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temp, path)
            lines.extend([f"[{size}x{size}/places]",
                          "Context=Places", f"Size={size}", "Type=Fixed",
                          "MaxSize=%d" % size, "MinSize=%d" % size, ""])
        index = os.path.join(target, "index.theme")
        fd, temp = tempfile.mkstemp(dir=target, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(temp, index)
        # A stale icon-theme.cache would keep the old folder icon visible.
        cache = os.path.join(target, "icon-theme.cache")
        if os.path.isfile(cache):
            try:
                os.unlink(cache)
            except OSError:
                pass
    except Exception as e:
        log.error(f"write derived theme {name}: {e}")
        return ""
    return target


def prune_derived_themes(keep=None, root=None):
    """Delete every derived theme except ``keep``; returns removed names."""
    removed = []
    for path in list_derived_themes(root):
        name = os.path.basename(path)
        if keep and name == keep:
            continue
        if remove_theme_dir(path):
            removed.append(name)
    return removed


def remove_theme_dir(path):
    """Remove one theme directory (only our own derived themes)."""
    name = os.path.basename(str(path))
    if not name.startswith(DERIVED_PREFIX):
        return False
    try:
        for root, dirs, files in os.walk(path, topdown=False):
            for entry in files:
                os.unlink(os.path.join(root, entry))
            for entry in dirs:
                os.rmdir(os.path.join(root, entry))
        os.rmdir(path)
        return True
    except OSError as e:
        log.error(f"remove derived theme {name}: {e}")
        return False


def remove_derived_themes(root=None):
    """Delete every derived theme; returns the removed names."""
    return prune_derived_themes(keep=None, root=root)


def fallback_theme_name():
    """A safe non-derived theme to activate after our theme is removed.

    Prefers the GNOME defaults and then any discovered theme, so a restore
    never leaves ``icon-theme`` pointing at a directory it just deleted.
    """
    for candidate in ("Adwaita", "hicolor"):
        if theme_directories(candidate):
            return candidate
    themes = discover_folder_themes()
    return themes[0]["name"] if themes else "hicolor"


def read_index_theme(theme_dir):
    """Parse the ``[Icon Theme]`` group of an index.theme file."""
    values = {}
    try:
        with open(os.path.join(theme_dir, "index.theme"), "r",
                  encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("["):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


# ---------------------------------------------------------------------------
# Gio-backed helpers (guarded: importable without a session bus)
# ---------------------------------------------------------------------------

def _interface_settings():
    try:
        from gi.repository import Gio
        return Gio.Settings.new("org.gnome.desktop.interface")
    except Exception as e:
        log.debug(f"interface settings unavailable: {e}")
        return None


def get_icon_theme():
    """Current icon theme name ('' when it cannot be read)."""
    settings = _interface_settings()
    if settings is None:
        return ""
    try:
        return str(settings.get_string("icon-theme") or "")
    except Exception as e:
        log.debug(f"icon-theme read: {e}")
        return ""


def set_icon_theme(name):
    """Activate an icon theme; False when Gio refuses it."""
    settings = _interface_settings()
    if settings is None or not safe_theme_name(name):
        return False
    try:
        settings.set_string("icon-theme", name)
        return True
    except Exception as e:
        log.error(f"icon-theme write: {e}")
        return False


def get_accent_name():
    """Raw 'accent-color' value ('' when the key does not exist)."""
    settings = _interface_settings()
    if settings is None:
        return ""
    try:
        return str(settings.get_string("accent-color") or "")
    except Exception as e:
        # GNOME < 47 has no accent-color key at all.
        log.debug(f"accent-color read: {e}")
        return ""


def watch_accent(callback):
    """Call ``callback(hex_colour)`` whenever the system accent changes.

    One connection per process: a second editor dialog must not stack
    handlers on the same key. Returns True when the watcher is active.
    """
    global _ACCENT_HANDLER, _ACCENT_SETTINGS
    if _ACCENT_HANDLER is not None:
        return True
    settings = _interface_settings()
    if settings is None:
        return False

    def _on_changed(_settings, _key):
        colour = resolve_accent_hex()
        try:
            callback(colour)
        except Exception as e:  # never break the shell's settings loop
            log.error(f"accent callback: {e}")

    try:
        _ACCENT_HANDLER = settings.connect("changed::accent-color", _on_changed)
        _ACCENT_SETTINGS = settings
    except Exception as e:
        log.debug(f"accent watcher: {e}")
        return False
    return True


def unwatch_accent():
    """Disconnect the accent watcher (tests / extension reload)."""
    global _ACCENT_HANDLER, _ACCENT_SETTINGS
    if _ACCENT_SETTINGS is not None and _ACCENT_HANDLER is not None:
        try:
            _ACCENT_SETTINGS.disconnect(_ACCENT_HANDLER)
        except Exception:
            pass
    _ACCENT_HANDLER = None
    _ACCENT_SETTINGS = None


# ---------------------------------------------------------------------------
# Persisted global state
# ---------------------------------------------------------------------------

def state_dir():
    base = os.environ.get("XDG_CONFIG_HOME") \
        or os.path.join(str(Path.home()), ".config")
    return os.path.join(base, "nautilus-extensions")


def state_path():
    return os.path.join(state_dir(), STATE_FILENAME)


def _normalize_spec(value):
    """'#rrggbb[;…]' -> 'rrggbb[;…]'; '' when any part is invalid."""
    parts = []
    for chunk in str(value or "").split(";"):
        slug = chunk.strip().lstrip("#").lower()
        if len(slug) != 6 or any(c not in "0123456789abcdef" for c in slug):
            return ""
        parts.append(slug)
    return ";".join(parts)


def normalize_state(raw):
    """Coerce a stored/foreign dict into the current state schema.

    Unknown keys are dropped, every value is validated and a missing/older
    state is upgraded with defaults instead of being discarded.
    """
    state = {}
    source = raw if isinstance(raw, dict) else {}
    state["version"] = STATE_VERSION
    state["spec"] = _normalize_spec(source.get("spec"))
    layers = source.get("layers")
    state["layers"] = layers if isinstance(layers, list) else []
    theme = source.get("theme")
    state["theme"] = theme if safe_theme_name(theme) else ""
    previous = source.get("base_theme")
    state["base_theme"] = previous if safe_theme_name(previous) else ""
    restored = source.get("previous_theme")
    state["previous_theme"] = restored if safe_theme_name(restored) else ""
    state["follow_accent"] = bool(source.get("follow_accent"))
    image = source.get("base_image")
    # A custom base image (#30) must survive a load/save round-trip: losing it
    # silently fell back to the themed folder icon on the next accent change.
    state["base_image"] = (
        image.strip() if isinstance(image, str) and "\x00" not in image
        else "")
    name = source.get("derived_theme")
    state["derived_theme"] = name if (
        safe_theme_name(name) and len(str(name)) > len(DERIVED_PREFIX)
        and str(name).startswith(DERIVED_PREFIX)) else ""
    try:
        state["row_count"] = max(1, min(8, int(source.get("row_count") or 1)))
    except (TypeError, ValueError):
        state["row_count"] = 1
    return state


def load_state(path=None):
    """Persisted global state, normalized; empty state when absent/broken."""
    target = path or state_path()
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return normalize_state({})
    return normalize_state(data)


def save_state(state, path=None):
    """Write the state atomically; False when it could not be written."""
    target = path or state_path()
    payload = normalize_state(state)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=os.path.dirname(target),
                                    suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(temp, target)
        return True
    except Exception as e:
        log.error(f"save global state: {e}")
        return False


def clear_state(path=None):
    """Remove the persisted global state."""
    try:
        os.unlink(path or state_path())
        return True
    except OSError:
        return False


def state_is_active(state=None):
    """True when the derived theme of ``state`` is the active icon theme."""
    data = state if isinstance(state, dict) else load_state()
    name = data.get("derived_theme") or ""
    return bool(name) and get_icon_theme() == name
