#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Colorize Image – Nautilus Python Extension
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
# NAME: Colorize Image – Nautilus Python Extension
# DESC: Tint images with a target color, preserving luminance and alpha
#       (port of Contextrion IconColorizer.cs / ColorMatrix)
# REQUIRES: python3-nautilus (>= 4.0), python3-pil, python3-gi, gir1.2-adw-1
# INSTALL:
#   cp colorize-image.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

import os
import locale
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Gio, Gdk, Nautilus

try:
    from PIL import Image
except ImportError:
    Image = None

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label":    "Coloriser…",
        "dialog_title":  "Coloriser les images",
        "color_label":   "Couleur",
        "strength_label": "Intensité",
        "processing":    "Traitement…",
        "done_title":    "Traitement terminé",
        "done_msg":      "{count} image(s) colorisée(s) avec succès.",
        "done_failed":   "{count} image(s) traitée(s), {failed} échec(s).",
        "cancel":        "Annuler",
        "ok":            "Appliquer",
        "err_pillow":    "Pillow n'est pas installé. Installez-le avec : pip install Pillow",
        "s_colorize":    "-colorisé",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":    "Colorieren…",
        "dialog_title":  "Bilder colorieren",
        "color_label":   "Farbe",
        "strength_label": "Intensität",
        "processing":    "Verarbeitung…",
        "done_title":    "Verarbeitung abgeschlossen",
        "done_msg":      "{count} Bild(er) erfolgreich coloriert.",
        "done_failed":   "{count} Bild(er) verarbeitet, {failed} fehlgeschlagen.",
        "cancel":        "Abbrechen",
        "ok":            "Anwenden",
        "err_pillow":    "Pillow ist nicht installiert. Installieren Sie es mit: pip install Pillow",
        "s_colorize":    "-coloriert",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":    "Colorear…",
        "dialog_title":  "Colorear imágenes",
        "color_label":   "Color",
        "strength_label": "Intensidad",
        "processing":    "Procesando…",
        "done_title":    "Procesamiento completado",
        "done_msg":      "{count} imagen(es) coloreada(s) correctamente.",
        "done_failed":   "{count} imagen(es) procesada(s), {failed} fallo(s).",
        "cancel":        "Cancelar",
        "ok":            "Aplicar",
        "err_pillow":    "Pillow no está instalado. Instálelo con: pip install Pillow",
        "s_colorize":    "-coloreada",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":    "Colorir…",
        "dialog_title":  "Colorir imagens",
        "color_label":   "Cor",
        "strength_label": "Intensidade",
        "processing":    "Processando…",
        "done_title":    "Processamento concluído",
        "done_msg":      "{count} imagem(ns) colorida(s) com sucesso.",
        "done_failed":   "{count} imagem(ns) processada(s), {failed} falha(s).",
        "cancel":        "Cancelar",
        "ok":            "Aplicar",
        "err_pillow":    "O Pillow não está instalado. Instale com: pip install Pillow",
        "s_colorize":    "-colorida",
    }
else:
    T = {
        "menu_label":    "Colorize…",
        "dialog_title":  "Colorize Images",
        "color_label":   "Color",
        "strength_label": "Strength",
        "processing":    "Processing…",
        "done_title":    "Processing complete",
        "done_msg":      "{count} image(s) colorized successfully.",
        "done_failed":   "{count} image(s) processed, {failed} failed.",
        "cancel":        "Cancel",
        "ok":            "Apply",
        "err_pillow":    "Pillow is not installed. Install it with: pip install Pillow",
        "s_colorize":    "-colorized",
    }

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
            ".webp": "WEBP", ".bmp": "BMP"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nautilus_window():
    app = Gtk.Application.get_default()
    if app is None:
        return None
    win = app.get_active_window()
    if win is not None:
        return win
    windows = app.get_windows()
    return windows[0] if windows else None


def _show_message(msg: str):
    Gtk.AlertDialog(message=msg).show(_nautilus_window())


def _paths_from_files(files):
    out = []
    for f in files:
        if f.get_uri_scheme() == "file":
            p = f.get_location().get_path()
            if p:
                out.append(p)
    return out


def _is_image_path(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def _suffix(src: str, suffix: str, force_ext=None) -> str:
    base, ext = os.path.splitext(src)
    if force_ext:
        ext = force_ext if force_ext.startswith(".") else "." + force_ext
    return f"{base}{suffix}{ext}"


def _save(img, dst: str):
    """Sauvegarde img dans dst en gérant alpha selon le format cible."""
    ext = os.path.splitext(dst)[1].lower()
    fmt = _FORMATS.get(ext, "PNG")
    mode = img.mode
    if mode in ("RGBA", "LA", "PA"):
        if fmt not in ("PNG", "WEBP"):
            flat = Image.new("RGB", img.size, (255, 255, 255))
            flat.paste(img, mask=img.split()[-1])
            img = flat
    elif mode == "P":
        img = img.convert("RGB" if fmt not in ("PNG", "WEBP") else "RGBA")
    img.save(dst, fmt)


def _hex_lut(factor: int) -> list:
    return [int(i * factor / 255) for i in range(256)]


# ---------------------------------------------------------------------------
# Pillow operation (pure, runs inside worker thread)
# ---------------------------------------------------------------------------

def op_colorize(src, rgba_color, strength):
    """Multiplie chaque canal RGB par la cible (équivalent ColorMatrix) en
    conservant la luminance (niveaux de gris) et l'alpha, puis blend selon
    la force. Jamais in-place : sortie séparée avec suffixe traduit."""
    dst = _suffix(src, T["s_colorize"])
    r = min(255, max(0, int(rgba_color.red * 255)))
    g = min(255, max(0, int(rgba_color.green * 255)))
    b = min(255, max(0, int(rgba_color.blue * 255)))
    alpha = min(100, max(0, strength))
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        lum = rgba.convert("L")
        colored = Image.merge(
            "RGB",
            (lum.point(_hex_lut(r)), lum.point(_hex_lut(g)), lum.point(_hex_lut(b))),
        ).convert("RGBA")
        colored.putalpha(rgba.split()[3])
        if alpha == 0:
            result = rgba
        elif alpha == 100:
            result = colored
        else:
            result = Image.blend(rgba, colored, alpha / 100.0)
        _save(result, dst)
    return dst


# ---------------------------------------------------------------------------
# Batch progress dialog
# ---------------------------------------------------------------------------

class ProgressDialog(Adw.Window):
    __gtype_name__ = "ColorizeImageProgressDialog"

    def __init__(self, tasks):
        super().__init__(title=T["done_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_deletable(False)
        self.set_default_size(360, -1)

        self._tasks = tasks
        self._cancelled = False
        self._done = 0
        self._failed = 0

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        box.append(Gtk.Label(label=T["processing"]))

        self._bar = Gtk.ProgressBar()
        self._bar.set_pulse_step(0.06)
        box.append(self._bar)

        self._status_lbl = Gtk.Label(label="0/{0}".format(len(tasks)))
        self._status_lbl.add_css_class("dim-label")
        box.append(self._status_lbl)

        self._cancel_btn = Gtk.Button(label=T["cancel"])
        self._cancel_btn.connect("clicked", self._on_cancel)
        box.append(self._cancel_btn)

        toolbar_view.set_content(box)
        self.set_content(toolbar_view)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        GObject.timeout_add(80, self._pulse)

    def _pulse(self):
        if self._thread.is_alive():
            self._bar.pulse()
            return True
        return False

    def _on_cancel(self, _btn):
        self._cancelled = True
        self._cancel_btn.set_sensitive(False)

    def _set_status(self):
        self._bar.set_fraction(self._done / max(len(self._tasks), 1))
        self._status_lbl.set_label("{0}/{1}".format(self._done, len(self._tasks)))

    def _run(self):
        for task in self._tasks:
            if self._cancelled:
                break
            try:
                task()
            except Exception:
                self._failed += 1
            self._done += 1
            GObject.idle_add(self._set_status)
        GObject.idle_add(self._finish)

    def _finish(self):
        if self._cancelled:
            self.destroy()
            return
        if self._failed:
            msg = T["done_failed"].format(count=self._done, failed=self._failed)
        else:
            msg = T["done_msg"].format(count=self._done)
        _show_message(msg)
        self.destroy()


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class ColorizeDialog(Adw.Window):
    __gtype_name__ = "ColorizeImageSettingsDialog"

    def __init__(self, callback):
        super().__init__(title=T["dialog_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(400, -1)
        self._callback = callback

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(Adw.HeaderBar())

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(18)
        outer.set_margin_end(18)

        outer.append(self._section_label(T["color_label"]))
        self._color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = 0.25, 0.45, 0.95, 1.0
        self._color_btn.set_rgba(rgba)
        self._color_btn.set_halign(Gtk.Align.START)
        outer.append(self._color_btn)

        outer.append(self._section_label(T["strength_label"]))
        strength_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._strength_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._strength_scale.set_value(100)
        self._strength_scale.set_hexpand(True)
        self._strength_scale.set_draw_value(False)
        self._strength_lbl = Gtk.Label(label="100%")
        self._strength_scale.connect(
            "value-changed",
            lambda s: self._strength_lbl.set_text("{0}%".format(int(s.get_value()))))
        strength_box.append(self._strength_scale)
        strength_box.append(self._strength_lbl)
        outer.append(strength_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(6)

        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", lambda _: self._respond(False))
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label=T["ok"])
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _: self._respond(True))
        btn_box.append(ok_btn)

        outer.append(btn_box)
        toolbar_view.set_content(outer)
        self.set_content(toolbar_view)

    def _section_label(self, text):
        lbl = Gtk.Label(label="<b>{0}</b>".format(text))
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        return lbl

    def _respond(self, ok: bool):
        if not ok:
            self._callback(None)
            self.destroy()
            return
        self._callback({
            "color": self._color_btn.get_rgba(),
            "strength": int(self._strength_scale.get_value()),
        })
        self.destroy()


# ---------------------------------------------------------------------------
# Nautilus extension
# ---------------------------------------------------------------------------

class ColorizeImageExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "ColorizeImageExtension"

    def get_file_items(self, files):
        paths = _paths_from_files(files)
        if not paths:
            return []
        if any(not _is_image_path(p) for p in paths):
            return []

        item = Nautilus.MenuItem(
            name="ColorizeImage::Colorize",
            label=T["menu_label"],
            tip="Tint the selected image(s) preserving luminance and alpha",
        )
        item.connect("activate", self._on_activate, paths)
        return [item]

    def get_background_items(self, folder):
        return []

    def _guard_pillow(self):
        if Image is None:
            _show_message(T["err_pillow"])
            return False
        return True

    def _start_batch(self, tasks):
        ProgressDialog(tasks).present()

    def _on_activate(self, _item, paths):
        if not self._guard_pillow():
            return

        def on_settings(settings):
            if settings is None:
                return
            color = settings["color"]
            strength = settings["strength"]
            self._start_batch(
                [lambda p=p, c=color, s=strength: op_colorize(p, c, s)
                 for p in paths])

        ColorizeDialog(callback=on_settings).present()