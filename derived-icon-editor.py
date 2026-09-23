#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Derived Icon Editor – Nautilus Python Extension
# AUTHOR: Tof
# VERSION: 1.0
# LICENSE: GNU General Public License v3.0
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# NAME: Derived Icon Editor – Nautilus Python Extension
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-adw-1, python3-pil
# INSTALL:
#   cp derived-icon-editor.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

import os
import locale

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Gdk, Gio, GLib, GdkPixbuf, Pango, Nautilus

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label":   "Éditeur d'icône dérivée…",
        "title":        "Éditeur d'icône dérivée",
        "base_label":   "Base",
        "overlay_label": "Calque",
        "add_layer":    "Ajouter un calque…",
        "remove":       "Supprimer",
        "opacity":      "Opacité",
        "scale":        "Échelle",
        "offset_x":     "Décalage X",
        "offset_y":     "Décalage Y",
        "rotation":     "Rotation",
        "no_overlay":   "Aucun calque",
        "save":         "Enregistrer",
        "err_open":     "Impossible d'ouvrir cette image.",
        "err_pil":      "Pillow (PIL) est requis pour utiliser cette extension.",
        "image_filter": "Images",
        "pick_overlay": "Choisir une image de calque",
        "hint":         "Les calques sont fusionnés sur la base et enregistrés en PNG 256×256.",
        "postpend":     "-derivée",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":   "Editor für abgeleitete Symbole…",
        "title":        "Editor für abgeleitete Symbole",
        "base_label":   "Basis",
        "overlay_label": "Ebene",
        "add_layer":    "Ebene hinzufügen…",
        "remove":       "Entfernen",
        "opacity":      "Deckkraft",
        "scale":        "Skalierung",
        "offset_x":     "Versatz X",
        "offset_y":     "Versatz Y",
        "rotation":     "Drehung",
        "no_overlay":   "Keine Ebene",
        "save":         "Speichern",
        "err_open":     "Dieses Bild konnte nicht geöffnet werden.",
        "err_pil":      "Pillow (PIL) wird für diese Erweiterung benötigt.",
        "image_filter": "Bilder",
        "pick_overlay": "Ebenenbild auswählen",
        "hint":         "Ebenen werden über die Basis gelegt und als 256×256-PNG gespeichert.",
        "postpend":     "-abgeleitet",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":   "Editor de icono derivado…",
        "title":        "Editor de icono derivado",
        "base_label":   "Base",
        "overlay_label": "Capa",
        "add_layer":    "Añadir capa…",
        "remove":       "Quitar",
        "opacity":      "Opacidad",
        "scale":        "Escala",
        "offset_x":     "Desplazamiento X",
        "offset_y":     "Desplazamiento Y",
        "rotation":     "Rotación",
        "no_overlay":   "Sin capa",
        "save":         "Guardar",
        "err_open":     "No se pudo abrir esta imagen.",
        "err_pil":      "Se requiere Pillow (PIL) para usar esta extensión.",
        "image_filter": "Imágenes",
        "pick_overlay": "Elegir imagen de capa",
        "hint":         "Las capas se fusionan sobre la base y se guardan como PNG de 256×256.",
        "postpend":     "-derivado",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":   "Editor de ícone derivado…",
        "title":        "Editor de ícone derivado",
        "base_label":   "Base",
        "overlay_label": "Camada",
        "add_layer":    "Adicionar camada…",
        "remove":       "Remover",
        "opacity":      "Opacidade",
        "scale":        "Escala",
        "offset_x":     "Deslocamento X",
        "offset_y":     "Deslocamento Y",
        "rotation":     "Rotação",
        "no_overlay":   "Sem camada",
        "save":         "Salvar",
        "err_open":     "Não foi possível abrir esta imagem.",
        "err_pil":      "Pillow (PIL) é necessária para usar esta extensão.",
        "image_filter": "Imagens",
        "pick_overlay": "Escolher imagem da camada",
        "hint":         "As camadas são compostas sobre a base e salvas como PNG 256×256.",
        "postpend":     "-derivado",
    }
else:
    T = {
        "menu_label":   "Derived Icon Editor…",
        "title":        "Derived Icon Editor",
        "base_label":   "Base",
        "overlay_label": "Overlay",
        "add_layer":    "Add layer…",
        "remove":       "Remove",
        "opacity":      "Opacity",
        "scale":        "Scale",
        "offset_x":     "X offset",
        "offset_y":     "Y offset",
        "rotation":     "Rotation",
        "no_overlay":   "No overlay",
        "save":         "Save",
        "err_open":     "Cannot open this image.",
        "err_pil":      "Pillow (PIL) is required to use this extension.",
        "image_filter": "Images",
        "pick_overlay": "Choose overlay image",
        "hint":         "Layers are composited over the base and saved as a 256×256 PNG.",
        "postpend":     "-derived",
    }

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANVAS_SIZE  = 256
PREVIEW_SIZE = 320
IMAGE_MIMES  = ("image/png", "image/jpeg", "image/webp")

_CSS_INSTALLED = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nautilus_window():
    app = Gtk.Application.get_default()
    if app is None:
        return None
    win = app.get_active_window()
    return win or (app.get_windows()[0] if app.get_windows() else None)


def _show_message(msg: str):
    Gtk.AlertDialog(message=msg).show(_nautilus_window())


def _fit_contain(img, size=CANVAS_SIZE):
    """Scale an image to fit inside a square canvas, centered on transparency."""
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
    """Scale, rotate and apply opacity to the overlay layer."""
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


def _pil_to_pixbuf(img):
    """Convert a PIL RGBA image into a GdkPixbuf.Pixbuf."""
    rgba = img.convert("RGBA")
    data = rgba.tobytes()
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(data),
        GdkPixbuf.Colorspace.RGB, True, 8,
        rgba.width, rgba.height, rgba.width * 4)


def _install_css():
    global _CSS_INSTALLED
    if _CSS_INSTALLED:
        return
    try:
        provider = Gtk.CssProvider()
        css = ".derived-frame { background-color: #161616; border-radius: 12px; }"
        try:
            provider.load_from_data(css)
        except TypeError:
            provider.load_from_data(css.encode("utf-8"), -1)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _CSS_INSTALLED = True
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Derived icon editor window
# ---------------------------------------------------------------------------

class DerivedIconEditorWindow(Adw.Window):
    __gtype_name__ = "DerivedIconEditorWindow"

    def __init__(self, image_path: str, base_image):
        super().__init__(title=T["title"])
        self.set_default_size(880, 560)

        self._path         = image_path
        self._base         = base_image
        self._base_canvas  = _fit_contain(self._base)
        self._overlay      = None
        self._overlay_path = None
        self._opacity      = 100
        self._scale        = 100
        self._offset_x     = 0
        self._offset_y     = 0
        self._rotation     = 0
        self._sliders      = []

        _install_css()
        self._build_ui()
        self._refresh_preview()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        tv = Adw.ToolbarView()

        header = Adw.HeaderBar()

        save_btn = Gtk.Button(label=T["save"])
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", lambda _: self._on_save())
        header.pack_end(save_btn)

        tv.add_top_bar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(18)
        outer.set_margin_end(18)

        outer.append(self._build_preview())
        outer.append(self._build_controls())

        tv.set_content(outer)
        self.set_content(tv)

    def _build_preview(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        frame = Gtk.Box()
        frame.add_css_class("derived-frame")
        frame.set_size_request(PREVIEW_SIZE + 16, PREVIEW_SIZE + 16)
        frame.set_valign(Gtk.Align.START)

        self._preview_img = Gtk.Image()
        self._preview_img.set_halign(Gtk.Align.CENTER)
        self._preview_img.set_valign(Gtk.Align.CENTER)
        frame.append(self._preview_img)

        col.append(frame)

        caption = Gtk.Label(label=f"{CANVAS_SIZE} × {CANVAS_SIZE} px")
        caption.add_css_class("dim-label")
        caption.set_halign(Gtk.Align.CENTER)
        col.append(caption)
        return col

    def _build_controls(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        col.set_hexpand(True)

        # -- Base --
        base_lbl = Gtk.Label(label=f"<b>{T['base_label']}</b>")
        base_lbl.set_use_markup(True)
        base_lbl.set_halign(Gtk.Align.START)
        col.append(base_lbl)

        w, h = self._base.size
        base_info = Gtk.Label(label=f"{os.path.basename(self._path)}  ({w} × {h})")
        base_info.set_halign(Gtk.Align.START)
        base_info.set_ellipsize(Pango.EllipsizeMode.END)
        base_info.set_tooltip_text(self._path)
        base_info.add_css_class("dim-label")
        col.append(base_info)

        col.append(Gtk.Separator())

        # -- Overlay --
        ov_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ov_lbl = Gtk.Label(label=f"<b>{T['overlay_label']}</b>")
        ov_lbl.set_use_markup(True)
        ov_lbl.set_halign(Gtk.Align.START)
        ov_row.append(ov_lbl)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        ov_row.append(spacer)

        add_btn = Gtk.Button(label=T["add_layer"])
        add_btn.connect("clicked", lambda _: self._on_add_layer())
        ov_row.append(add_btn)

        self._remove_btn = Gtk.Button(label=T["remove"])
        self._remove_btn.add_css_class("destructive-action")
        self._remove_btn.connect("clicked", lambda _: self._remove_overlay())
        self._remove_btn.set_sensitive(False)
        ov_row.append(self._remove_btn)

        col.append(ov_row)

        self._overlay_status = Gtk.Label(label=T["no_overlay"])
        self._overlay_status.set_halign(Gtk.Align.START)
        self._overlay_status.set_ellipsize(Pango.EllipsizeMode.END)
        self._overlay_status.add_css_class("dim-label")
        col.append(self._overlay_status)

        col.append(Gtk.Separator())

        # -- Sliders --
        self._make_slider(col, "_opacity",  T["opacity"],  0,   100, 1, self._opacity, lambda v: f"{v}%")
        self._make_slider(col, "_scale",    T["scale"],   10,   300, 1, self._scale,   lambda v: f"{v}%")
        self._make_slider(col, "_offset_x", T["offset_x"], -256, 256, 1, self._offset_x, lambda v: f"{v}px")
        self._make_slider(col, "_offset_y", T["offset_y"], -256, 256, 1, self._offset_y, lambda v: f"{v}px")
        self._make_slider(col, "_rotation", T["rotation"], -180, 180, 1, self._rotation, lambda v: f"{v}°")

        hint = Gtk.Label(label=T["hint"])
        hint.set_wrap(True)
        hint.set_halign(Gtk.Align.START)
        hint.set_margin_top(10)
        hint.add_css_class("dim-label")
        col.append(hint)

        return col

    def _make_slider(self, parent, attr, label, low, high, step, value, fmt):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2)
        parent.append(row)

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_size_request(96, -1)
        row.append(lbl)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
        scale.set_value(value)
        scale.set_hexpand(True)
        scale.set_draw_value(False)

        val = Gtk.Label(label=fmt(int(value)))
        val.set_halign(Gtk.Align.END)
        val.set_size_request(52, -1)

        def on_change(s):
            v = int(round(s.get_value()))
            setattr(self, attr, v)
            val.set_label(fmt(v))
            self._refresh_preview()

        scale.connect("value-changed", on_change)

        row.append(scale)
        row.append(val)

        self._sliders.append(scale)
        scale.set_sensitive(False)

    # -- Overlay management -------------------------------------------------

    def _on_add_layer(self):
        dlg = Gtk.FileDialog(title=T["pick_overlay"])
        dlg.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self._path)))

        filt = Gtk.FileFilter()
        filt.set_name(T["image_filter"])
        for m in IMAGE_MIMES:
            filt.add_mime_type(m)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dlg.set_filters(store)
        dlg.set_default_filter(filt)

        dlg.open(self, None, self._on_overlay_picked)

    def _on_overlay_picked(self, dlg, result):
        try:
            path = dlg.open_finish(result).get_path()
        except Exception:
            return
        try:
            ov = Image.open(path).convert("RGBA")
            ov.load()
        except Exception:
            _show_message(T["err_open"])
            return
        self._overlay = ov
        self._overlay_path = path
        self._overlay_status.set_label(os.path.basename(path))
        self._overlay_status.set_tooltip_text(path)
        for s in self._sliders:
            s.set_sensitive(True)
        self._remove_btn.set_sensitive(True)
        self._refresh_preview()

    def _remove_overlay(self):
        self._overlay = None
        self._overlay_path = None
        self._overlay_status.set_label(T["no_overlay"])
        self._overlay_status.set_tooltip_text("")
        for s in self._sliders:
            s.set_sensitive(False)
        self._remove_btn.set_sensitive(False)
        self._refresh_preview()

    # -- Composition --------------------------------------------------------

    def _compose(self):
        canvas = self._base_canvas.copy()
        if self._overlay is not None:
            ov = _transform_overlay(
                self._overlay, self._opacity, self._scale, self._rotation)
            cx = (CANVAS_SIZE - ov.width) // 2 + self._offset_x
            cy = (CANVAS_SIZE - ov.height) // 2 + self._offset_y
            canvas.alpha_composite(ov, (cx, cy))
        return canvas

    def _refresh_preview(self):
        canvas = self._compose()
        pb = _pil_to_pixbuf(canvas)
        pb = pb.scale_simple(
            PREVIEW_SIZE, PREVIEW_SIZE, GdkPixbuf.InterpType.NEAREST)
        self._preview_img.set_from_pixbuf(pb)

    # -- Save ---------------------------------------------------------------

    def _on_save(self):
        base, _ = os.path.splitext(os.path.basename(self._path))
        dlg = Gtk.FileDialog(title=T["save"])
        dlg.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self._path)))
        dlg.set_initial_name(f"{base}{T['postpend']}.png")
        dlg.save(self, None, self._on_save_done)

    def _on_save_done(self, dlg, result):
        try:
            path = dlg.save_finish(result).get_path()
        except Exception:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            self._compose().save(path, "PNG")
        except Exception as exc:
            _show_message(str(exc))
            return
        Gtk.AlertDialog(message=f"✓  {os.path.basename(path)}").show(self)


# ---------------------------------------------------------------------------
# Nautilus extension
# ---------------------------------------------------------------------------

class DerivedIconExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "DerivedIconExtension"

    _windows = []

    def get_file_items(self, files):
        imgs = [
            f for f in files
            if f.get_uri_scheme() == "file"
            and f.get_mime_type() in IMAGE_MIMES
        ]
        if len(imgs) != 1:
            return []

        item = Nautilus.MenuItem(
            name="DerivedIconEditor::Edit",
            label=T["menu_label"],
            tip="Open the layer-based derived icon editor",
        )
        item.connect("activate", self._on_activate, imgs[0])
        return [item]

    def get_background_items(self, folder):
        return []

    def _on_activate(self, _item, nfile):
        if not HAS_PIL:
            _show_message(T["err_pil"])
            return

        path = nfile.get_location().get_path()
        try:
            base = Image.open(path).convert("RGBA")
            base.load()
        except Exception:
            _show_message(T["err_open"])
            return

        win = DerivedIconEditorWindow(path, base)
        DerivedIconExtension._windows.append(win)
        win.connect("close-request",
                    lambda w: (DerivedIconExtension._windows.remove(w)
                               if w in DerivedIconExtension._windows else None,
                               False)[1])
        win.present()