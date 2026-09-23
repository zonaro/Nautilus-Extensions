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
import logging
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
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)

from gi.repository import Nautilus, Gtk, Gdk, GObject, Gio, GLib

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
        return Gtk.Settings.get_default().get_property("gtk-icon-theme-name") or "hicolor"
    except Exception:
        return "hicolor"


def _theme_folder_svg_text():
    """Raw SVG text of the current theme's 'folder' icon, or ''."""
    try:
        display = Gdk.Display.get_default()
        if display is None:
            return ""
        icon_theme = Gtk.IconTheme.get_for_display(display)
        paintable = icon_theme.lookup_icon(
            "folder", None, 128, 1,
            Gtk.TextDirection.LTR, Gtk.IconLookupFlags.FORCE_REGULAR,
        )
        if paintable is None:
            return ""
        gfile = paintable.get_file()
        if gfile is None:
            return ""
        path = gfile.get_path()
        if not path or not path.lower().endswith(".svg"):
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        log.error(f"theme folder svg: {e}")
        return ""


def _any_folder_svg_text():
    """Theme SVG if available, else first folder.svg from any installed theme."""
    svg = _theme_folder_svg_text()
    if svg:
        return svg
    bases = [os.path.join(str(Path.home()), ".icons"),
             os.path.join(str(Path.home()), ".local", "share", "icons"),
             "/usr/local/share/icons",
             "/usr/share/icons"]
    candidates = []
    try:
        for base in bases:
            if not os.path.isdir(base):
                continue
            for theme in sorted(os.listdir(base)):
                scalable = os.path.join(base, theme, "scalable", "places", "folder.svg")
                if os.path.isfile(scalable):
                    candidates.append(scalable)
                places = os.path.join(base, theme, "places")
                if os.path.isdir(places):
                    for size in sorted(os.listdir(places), reverse=True):
                        sized = os.path.join(places, size, "folder.svg")
                        if os.path.isfile(sized):
                            candidates.append(sized)
    except Exception as e:
        log.error(f"theme scan: {e}")
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            if "<svg" in text:
                return text
        except Exception:
            continue
    return ""


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


def _ensure_custom_icon(spec):
    """Write (if needed) and return the file:// URI of the cached SVG icon.

    spec is '#rrggbb' or '#rrggbb;#rrggbb' (back;front). Preferred: current
    theme's folder icon, desaturated + tinted. Fallback: generic folder.
    Filename embeds theme + colors so the Nautilus icon cache (keyed by
    URI) stays correct across theme switches.
    """
    parts = _split_color_spec(spec)
    if not parts:
        return ""
    slug = "-".join(parts)
    theme = re.sub(r"[^a-z0-9-]+", "",
                   str(_current_theme_name()).lower().replace("_", "-"))
    path = os.path.join(_custom_cache_dir(), f"folder-{theme}-{slug}.svg")
    if not os.path.exists(path):
        svg = ""
        theme_svg = _any_folder_svg_text()
        if theme_svg:
            svg = _tint_svg_multi(theme_svg, parts)
        if not svg:
            svg = _folder_svg(parts[0])
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)
        except Exception as e:
            log.error(f"custom icon write: {e}")
            return ""
    try:
        return Gio.File.new_for_path(path).get_uri()
    except Exception as e:
        log.error(f"custom icon uri: {e}")
        return ""

# ---------------------------------------------------------------------------
# FIX 1 : i18n — les placeholders @GETTEXT_PACKAGE@ / @LOCALEDIR@ n'étaient
# jamais remplacés (script prévu pour être compilé via autotools).
# On tombe back sur gettext standard sans domaine custom.
# ---------------------------------------------------------------------------
try:
    from gettext import gettext as _
except Exception:
    def _(s): return s

COLOR  = _("Color")
EMBLEM = _("Emblem")
CUSTOM_COLOR_LABEL = _("Custom color…")

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
                name="FolderColorMenu::colors", label=COLOR, icon="color-picker")
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

            if _CUSTOM_COLOR_AVAILABLE:
                item = Nautilus.MenuItem(
                    name="FolderColorMenu::custom_color",
                    label=CUSTOM_COLOR_LABEL,
                    icon="color-picker",
                )
                item.connect("activate", self._menu_activate_custom_color, items)
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

    def _show_custom_color_dialog(self, paths):
        """Modal dialog: one name entry + color picker per icon shape."""
        sample = os.path.basename(paths[0].rstrip("/")) or paths[0]
        theme_svg = _any_folder_svg_text()
        _root, shapes = _svg_shapes(theme_svg) if theme_svg else (None, [])
        row_count = len(shapes) if shapes else 1
        state = {"hexes": ["#808080"] * row_count}

        dialog = Gtk.Dialog(title=CUSTOM_COLOR_LABEL)
        dialog.set_modal(True)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL,
                           _("Apply"), Gtk.ResponseType.OK)
        try:
            dialog.set_default_response(Gtk.ResponseType.OK)
        except Exception:
            pass

        content = dialog.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        try:
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            box.set_margin_start(12)
            box.set_margin_end(12)
        except Exception:
            pass
        content.append(box)

        box.append(Gtk.Label(label=sample))

        scroll = Gtk.ScrolledWindow()
        try:
            scroll.set_min_content_height(min(64 * row_count, 300))
            scroll.set_propagate_natural_height(True)
        except Exception:
            pass
        box.append(scroll)
        rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        try:
            scroll.set_child(rows_box)
        except Exception:
            box.append(rows_box)

        preview = Gtk.Image()
        try:
            preview.set_pixel_size(128)
        except Exception:
            pass
        box.append(preview)

        hex_label = Gtk.Label(label=state["hexes"][0])
        try:
            hex_label.add_css_class("monospace")
        except Exception:
            pass
        box.append(hex_label)

        entries = []
        pickers = []
        syncing = {"busy": False}

        def resolve_name(text):
            """Color name -> '#rrggbb' or '' when invalid."""
            text = str(text or "").strip()
            if not text:
                return ""
            try:
                color = generate_color(text)
            except Exception as e:
                log.error(f"custom color resolve: {e}")
                return ""
            if isinstance(color, list):
                color = color[0] if color else ""
            color = str(color)[:7].lower()
            if len(color) != 7 or not color.startswith("#"):
                return ""
            if len(_split_color_spec(color)) != 1:
                return ""
            return color

        def draw_preview(*_args):
            """Render the real (themed, tinted) icon into the preview image."""
            parts = [h.lstrip("#") for h in state["hexes"]]
            svg = ""
            if theme_svg:
                svg = _tint_svg_multi(theme_svg, parts)
            if not svg:
                svg = _folder_svg(parts[0])
            preview_path = os.path.join(_custom_cache_dir(), "folder-preview.svg")
            try:
                with open(preview_path, "w", encoding="utf-8") as f:
                    f.write(svg)
                preview.set_from_file(preview_path)
            except Exception as e:
                log.error(f"custom color preview: {e}")
            hex_label.set_text(" + ".join(state["hexes"]))

        def set_row(index, hex_color, from_entry=True, from_picker=True):
            if syncing["busy"]:
                return
            syncing["busy"] = True
            try:
                state["hexes"][index] = hex_color
                rgba = self._hex_to_rgba(hex_color)
                if from_picker and rgba is not None:
                    try:
                        pickers[index].set_rgba(rgba)
                    except Exception:
                        pass
                if from_entry and entries[index].get_text().strip() != hex_color:
                    try:
                        entries[index].set_text(hex_color)
                    except Exception:
                        pass
                draw_preview()
            finally:
                syncing["busy"] = False

        def on_entry_changed(entry, index):
            raw = entry.get_text()
            if ";" in raw:
                chunks = [c.strip() for c in raw.split(";")]
                for offset, chunk in enumerate(chunks):
                    target = index + offset
                    if target >= row_count:
                        break
                    resolved = resolve_name(chunk)
                    if resolved:
                        set_row(target, resolved)
                return
            resolved = resolve_name(raw)
            if resolved:
                set_row(index, resolved, from_entry=False)

        def on_picker_set(picker, index):
            try:
                hex_color = self._rgba_to_hex(picker.get_rgba())
            except Exception:
                return
            if hex_color:
                set_row(index, hex_color, from_picker=False)

        for i in range(row_count):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.append(Gtk.Label(label=_("Color %d") % (i + 1)))
            entry = Gtk.Entry()
            entry.set_placeholder_text(_("Name or #hex — e.g. vermelho, Lucas"))
            entry.set_hexpand(True)
            entry.set_activates_default(True)
            picker = Gtk.ColorButton()
            try:
                rgba = self._hex_to_rgba(state["hexes"][i])
                if rgba is not None:
                    picker.set_rgba(rgba)
            except Exception:
                pass
            entry.connect("changed", on_entry_changed, i)
            try:
                picker.connect("color-set", on_picker_set, i)
            except Exception:
                pass
            row.append(entry)
            row.append(picker)
            rows_box.append(row)
            entries.append(entry)
            pickers.append(picker)

        def on_response(dlg, response):
            try:
                if response == Gtk.ResponseType.OK:
                    spec = ";".join(state["hexes"])
                    for path in paths:
                        self.foldercolor.set_custom_color(path, spec)
            finally:
                try:
                    dlg.destroy()
                except Exception:
                    pass

        dialog.connect("response", on_response)
        draw_preview()
        try:
            dialog.present()
        except Exception as e:
            log.error(f"custom color dialog: {e}")

    def _menu_activate_restore(self, menu, items):
        for item in items:
            if not item.is_gone():
                self.foldercolor.set_restore(item.get_location().get_path())
