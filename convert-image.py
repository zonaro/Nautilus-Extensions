#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Convert Image – Nautilus Python Extension
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
# NAME: Convert Image – Nautilus Python Extension
# DESC: Format conversion tools in a "Convert Image" submenu.
#       Port of Contextrion's icon import/conversion flow (no DLL
#       extraction, which is Windows-only): PNG / JPEG / WebP / ICO /
#       square 256x256 PNG. The original file is never overwritten.
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-adw-1, python3-pil
# INSTALL:
#   cp convert-image.py ~/.local/share/nautilus-python/extensions/
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
from gi.repository import GObject, Gtk, Adw, Gio, Nautilus

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
        "menu_label":     "Convertir l'image",
        "menu_tip":       "Convertir les images sélectionnées dans un autre format (Pillow)",
        "to_png":         "Convertir en PNG",
        "to_jpeg":        "Convertir en JPEG",
        "to_webp":        "Convertir en WebP",
        "to_ico":         "Enregistrer en ICO",
        "to_square":      "Carré 256×256 PNG",
        "tip_ico":        "Fichier .ico multi-tailles (16–256) — sous Linux, sert surtout "
                          "aux favicons (compatibles partout)",
        "processing":     "Conversion…",
        "done_title":     "Conversion terminée",
        "done_msg":       "{count} image(s) convertie(s) avec succès.",
        "done_failed":    "{count} image(s) convertie(s), {failed} échec(s).",
        "done_skip":      "{skipped} fichier(s) ignoré(s) (déjà au format cible).",
        "err_nothing":    "Aucune conversion nécessaire — {count} fichier(s) déjà au format cible.",
        "cancel":         "Annuler",
        "err_pillow":     "Pillow n'est pas installé. Installez-le avec : pip install Pillow",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":     "Bild konvertieren",
        "menu_tip":       "Ausgewählte Bilder in ein anderes Format konvertieren (Pillow)",
        "to_png":         "In PNG konvertieren",
        "to_jpeg":        "In JPEG konvertieren",
        "to_webp":        "In WebP konvertieren",
        "to_ico":         "Als ICO speichern",
        "to_square":      "Quadrat 256×256 PNG",
        "tip_ico":        "Mehrgrößen-.ico (16–256) — unter Linux hauptsächlich für "
                          "Favicons nützlich (plattformübergreifend)",
        "processing":     "Konvertierung…",
        "done_title":     "Konvertierung abgeschlossen",
        "done_msg":       "{count} Bild(er) erfolgreich konvertiert.",
        "done_failed":    "{count} Bild(er) konvertiert, {failed} fehlgeschlagen.",
        "done_skip":      "{skipped} Datei(en) übersprungen (bereits im Zielformat).",
        "err_nothing":    "Keine Konvertierung nötig — {count} Datei(en) bereits im Zielformat.",
        "cancel":         "Abbrechen",
        "err_pillow":     "Pillow ist nicht installiert. Installieren Sie es mit: pip install Pillow",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":     "Convertir imagen",
        "menu_tip":       "Convertir las imágenes seleccionadas a otro formato (Pillow)",
        "to_png":         "Convertir a PNG",
        "to_jpeg":        "Convertir a JPEG",
        "to_webp":        "Convertir a WebP",
        "to_ico":         "Guardar como ICO",
        "to_square":      "Cuadrado 256×256 PNG",
        "tip_ico":        "Archivo .ico multitamaño (16–256) — en Linux sirve sobre todo "
                          "para favicons (compatible en cualquier plataforma)",
        "processing":     "Convirtiendo…",
        "done_title":     "Conversión completada",
        "done_msg":       "{count} imagen(es) convertida(s) correctamente.",
        "done_failed":    "{count} imagen(es) convertida(s), {failed} fallo(s).",
        "done_skip":      "{skipped} archivo(s) omitido(s) (ya en el formato destino).",
        "err_nothing":    "No hace falta conversión — {count} archivo(s) ya tienen el formato destino.",
        "cancel":         "Cancelar",
        "err_pillow":     "Pillow no está instalado. Instálelo con: pip install Pillow",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":     "Converter imagem",
        "menu_tip":       "Converter as imagens selecionadas para outro formato (Pillow)",
        "to_png":         "Converter para PNG",
        "to_jpeg":        "Converter para JPEG",
        "to_webp":        "Converter para WebP",
        "to_ico":         "Salvar como ICO",
        "to_square":      "Quadrado 256×256 PNG",
        "tip_ico":        "Arquivo .ico multi-tamanho (16–256) — no Linux serve "
                          "principalmente para favicons (cross-platform)",
        "processing":     "Convertendo…",
        "done_title":     "Conversão concluída",
        "done_msg":       "{count} imagem(ns) convertida(s) com sucesso.",
        "done_failed":    "{count} imagem(ns) convertida(s), {failed} falha(s).",
        "done_skip":      "{skipped} arquivo(s) ignorado(s) (já no formato de destino).",
        "err_nothing":    "Nenhuma conversão necessária — {count} arquivo(s) já estão no formato de destino.",
        "cancel":         "Cancelar",
        "err_pillow":     "O Pillow não está instalado. Instale com: pip install Pillow",
    }
else:
    T = {
        "menu_label":     "Convert Image",
        "menu_tip":       "Convert selected images to another format (Pillow)",
        "to_png":         "Convert to PNG",
        "to_jpeg":        "Convert to JPEG",
        "to_webp":        "Convert to WebP",
        "to_ico":         "Save as ICO",
        "to_square":      "Square 256×256 PNG",
        "tip_ico":        "Multi-size .ico (16–256) — on Linux mainly useful for "
                          "favicons (cross-platform)",
        "processing":     "Converting…",
        "done_title":     "Conversion complete",
        "done_msg":       "{count} image(s) converted successfully.",
        "done_failed":    "{count} image(s) converted, {failed} failed.",
        "done_skip":      "{skipped} file(s) skipped (already in the target format).",
        "err_nothing":    "No conversion needed — {count} file(s) already have the target format.",
        "cancel":         "Cancel",
        "err_pillow":     "Pillow is not installed. Install it with: pip install Pillow",
    }

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".ico", ".tiff")
_JPEG_QUALITY = 92
_SQUARE_SUFFIX = "-256x256.png"
_SQUARE_SIZE = 256
_ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


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


def _out_path(src: str, ext: str) -> str:
    base, _ = os.path.splitext(src)
    return base + ext


def _same_path(a: str, b: str) -> bool:
    return os.path.abspath(a).lower() == os.path.abspath(b).lower()


# ---------------------------------------------------------------------------
# Pillow operations (pure, run inside worker threads)
# ---------------------------------------------------------------------------

def op_to_png(src):
    dst = _out_path(src, ".png")
    if _same_path(dst, src):
        return None
    with Image.open(src) as im:
        im.convert("RGBA").save(dst, "PNG")
    return dst


def op_to_jpeg(src):
    dst = _out_path(src, ".jpg")
    if _same_path(dst, src):
        return None
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[3])
        flat.save(dst, "JPEG", quality=_JPEG_QUALITY,
                  optimize=True, progressive=True)
    return dst


def op_to_webp(src):
    dst = _out_path(src, ".webp")
    if _same_path(dst, src):
        return None
    with Image.open(src) as im:
        im.convert("RGBA").save(dst, "WEBP")
    return dst


def op_to_ico(src):
    dst = _out_path(src, ".ico")
    if _same_path(dst, src):
        return None
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        rgba.save(dst, format="ICO", sizes=_ICO_SIZES)
    return dst


def op_to_square(src):
    base, ext = os.path.splitext(src)
    dst = base + _SQUARE_SUFFIX
    if ext.lower() == ".png" and _same_path(dst, src):
        return None
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        w, h = rgba.size
        scale = min(_SQUARE_SIZE / w, _SQUARE_SIZE / h)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        if (nw, nh) != (w, h):
            rgba = rgba.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (_SQUARE_SIZE, _SQUARE_SIZE),
                           (0, 0, 0, 0))
        canvas.paste(rgba, ((_SQUARE_SIZE - nw) // 2, (_SQUARE_SIZE - nh) // 2),
                     rgba)
        canvas.save(dst, "PNG")
    return dst


# ---------------------------------------------------------------------------
# Batch progress dialog
# ---------------------------------------------------------------------------

class ProgressDialog(Adw.Window):
    __gtype_name__ = "ConvertImageProgressDialog"

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
        self._skipped = 0
        self._processed = 0

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
        self._bar.set_fraction(self._processed / max(len(self._tasks), 1))
        self._status_lbl.set_label("{0}/{1}".format(
            self._processed, len(self._tasks)))

    def _run(self):
        for task in self._tasks:
            if self._cancelled:
                break
            try:
                if task() is None:
                    self._skipped += 1
                else:
                    self._done += 1
            except Exception:
                self._failed += 1
            self._processed += 1
            GObject.idle_add(self._set_status)
        GObject.idle_add(self._finish)

    def _finish(self):
        if self._cancelled:
            self.destroy()
            return
        if self._done or self._failed:
            if self._failed:
                line = T["done_failed"].format(count=self._done,
                                               failed=self._failed)
            else:
                line = T["done_msg"].format(count=self._done)
        elif self._skipped:
            line = T["err_nothing"].format(count=self._skipped)
        else:
            line = T["done_msg"].format(count=0)
        if self._skipped:
            line += "\n" + T["done_skip"].format(skipped=self._skipped)
        _show_message(line)
        self.destroy()


# ---------------------------------------------------------------------------
# Nautilus extension with submenu
# ---------------------------------------------------------------------------

class ConvertImageExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "ConvertImageExtension"

    def _add(self, submenu, name, label, cb, *args, tip=None):
        item = Nautilus.MenuItem(
            name="ConvertImage::{0}".format(name),
            label=label,
            tip=tip or T["menu_tip"],
        )
        item.connect("activate", cb, *args)
        submenu.append_item(item)

    def get_file_items(self, files):
        paths = _paths_from_files(files)
        if not paths:
            return []
        if any(not _is_image_path(p) for p in paths):
            return []

        top = Nautilus.MenuItem(
            name="ConvertImage::Top",
            label=T["menu_label"],
            tip=T["menu_tip"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)

        self._add(submenu, "ToPNG", T["to_png"],
                  self._cb_to, paths, op_to_png)
        self._add(submenu, "ToJPEG", T["to_jpeg"],
                  self._cb_to, paths, op_to_jpeg)
        self._add(submenu, "ToWebP", T["to_webp"],
                  self._cb_to, paths, op_to_webp)
        self._add(submenu, "ToICO", T["to_ico"],
                  self._cb_to, paths, op_to_ico, tip=T["tip_ico"])
        self._add(submenu, "Square256", T["to_square"],
                  self._cb_to, paths, op_to_square)

        return [top]

    def get_background_items(self, folder):
        return []

    def _guard_pillow(self):
        if Image is None:
            _show_message(T["err_pillow"])
            return False
        return True

    def _start_batch(self, tasks):
        ProgressDialog(tasks).present()

    def _cb_to(self, _item, paths, op):
        if not self._guard_pillow():
            return
        self._start_batch([lambda p=p, op=op: op(p) for p in paths])