#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Image Tools – Nautilus Python Extension
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
# NAME: Image Tools – Nautilus Python Extension
# DESC: Pillow-based image processing tools in an "Image Tools" submenu
# REQUIRES: python3-nautilus (>= 4.0), python3-pil, python3-gi, gir1.2-adw-1
# INSTALL:
#   cp image-tools.py ~/.local/share/nautilus-python/extensions/
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
    from PIL import Image, ImageOps, ImageDraw, ImageFont
except ImportError:
    Image = None

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label":     "Outils d'image",
        "menu_tip":       "Outils de traitement d'image (Pillow)",
        "grayscale":      "Niveaux de gris",
        "invert":         "Négatif",
        "crop":           "Recadrage centré…",
        "circle":         "Cercle",
        "resize":         "Redimensionner…",
        "combine":        "Fusionner les images…",
        "watermark":      "Filigrane…",
        "optimize":       "Optimiser pour le Web…",
        "processing":     "Traitement…",
        "done_title":     "Traitement terminé",
        "done_msg":       "{count} image(s) traitée(s) avec succès.",
        "done_failed":    "{count} image(s) traitée(s), {failed} échec(s).",
        "cancel":         "Annuler",
        "ok":             "Appliquer",
        "choose":         "Choisir…",
        "err_pillow":     "Pillow n'est pas installé. Installez-le avec : pip install Pillow",
        "err_empty":      "Le texte du filigrane ne peut pas être vide.",
        "err_choose":     "Veuillez choisir une image de filigrane.",
        "err_combine":    "Sélectionnez au moins deux images.",
        "crop_title":     "Recadrage centré",
        "crop_width":     "Largeur",
        "crop_height":    "Hauteur",
        "resize_title":   "Redimensionner",
        "resize_width":   "Largeur max",
        "resize_height":  "Hauteur max",
        "optimize_title": "Optimiser pour le Web",
        "optimize_max":   "Dimension max",
        "optimize_qual":  "Qualité",
        "watermark_title": "Filigrane",
        "wm_mode_text":   "Texte",
        "wm_mode_image":  "Image",
        "wm_text_hint":   "Texte du filigrane",
        "wm_pick_image":  "Image du filigrane…",
        "combine_title":  "Fusionner les images",
        "combine_vertical":   "Verticale",
        "combine_horizontal": "Horizontale",
        "s_grayscale":  "-gris",
        "s_invert":     "-négatif",
        "s_crop":       "-recadré",
        "s_circle":     "-cercle",
        "s_resize":     "-redimensionné",
        "s_watermark":  "-filigrané",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":     "Bildwerkzeuge",
        "menu_tip":       "Bildbearbeitungswerkzeuge (Pillow)",
        "grayscale":      "Graustufen",
        "invert":         "Negativ",
        "crop":           "Zentriert zuschneiden…",
        "circle":         "Kreis",
        "resize":         "Größe ändern…",
        "combine":        "Bilder zusammenfügen…",
        "watermark":      "Wasserzeichen…",
        "optimize":       "Für Web optimieren…",
        "processing":     "Verarbeitung…",
        "done_title":     "Verarbeitung abgeschlossen",
        "done_msg":       "{count} Bild(er) erfolgreich verarbeitet.",
        "done_failed":    "{count} Bild(er) verarbeitet, {failed} fehlgeschlagen.",
        "cancel":         "Abbrechen",
        "ok":             "Anwenden",
        "choose":         "Auswählen…",
        "err_pillow":     "Pillow ist nicht installiert. Installieren Sie es mit: pip install Pillow",
        "err_empty":      "Der Wasserzeichentext darf nicht leer sein.",
        "err_choose":     "Bitte ein Wasserzeichenbild auswählen.",
        "err_combine":    "Wählen Sie mindestens zwei Bilder aus.",
        "crop_title":     "Zentriert zuschneiden",
        "crop_width":     "Breite",
        "crop_height":    "Höhe",
        "resize_title":   "Größe ändern",
        "resize_width":   "Max. Breite",
        "resize_height":  "Max. Höhe",
        "optimize_title": "Für Web optimieren",
        "optimize_max":   "Max. Dimension",
        "optimize_qual":  "Qualität",
        "watermark_title": "Wasserzeichen",
        "wm_mode_text":   "Text",
        "wm_mode_image":  "Bild",
        "wm_text_hint":   "Wasserzeichentext",
        "wm_pick_image":  "Wasserzeichenbild…",
        "combine_title":  "Bilder zusammenfügen",
        "combine_vertical":   "Vertikal",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-graustufen",
        "s_invert":     "-negativ",
        "s_crop":       "-beschnitten",
        "s_circle":     "-kreis",
        "s_resize":     "-skaliert",
        "s_watermark":  "-wasserzeichen",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":     "Herramientas de imagen",
        "menu_tip":       "Herramientas de edición de imágenes (Pillow)",
        "grayscale":      "Escala de grises",
        "invert":         "Negativo",
        "crop":           "Recorte centrado…",
        "circle":         "Círculo",
        "resize":         "Redimensionar…",
        "combine":        "Combinar imágenes…",
        "watermark":      "Marca de agua…",
        "optimize":       "Optimizar para web…",
        "processing":     "Procesando…",
        "done_title":     "Procesamiento completado",
        "done_msg":       "{count} imagen(es) procesada(s) correctamente.",
        "done_failed":    "{count} imagen(es) procesada(s), {failed} fallo(s).",
        "cancel":         "Cancelar",
        "ok":             "Aplicar",
        "choose":         "Elegir…",
        "err_pillow":     "Pillow no está instalado. Instálelo con: pip install Pillow",
        "err_empty":      "El texto de la marca de agua no puede estar vacío.",
        "err_choose":     "Seleccione una imagen de marca de agua.",
        "err_combine":    "Seleccione al menos dos imágenes.",
        "crop_title":     "Recorte centrado",
        "crop_width":     "Ancho",
        "crop_height":    "Alto",
        "resize_title":   "Redimensionar",
        "resize_width":   "Ancho máx.",
        "resize_height":  "Alto máx.",
        "optimize_title": "Optimizar para web",
        "optimize_max":   "Dimensión máx.",
        "optimize_qual":  "Calidad",
        "watermark_title": "Marca de agua",
        "wm_mode_text":   "Texto",
        "wm_mode_image":  "Imagen",
        "wm_text_hint":   "Texto de la marca de agua",
        "wm_pick_image":  "Imagen de marca de agua…",
        "combine_title":  "Combinar imágenes",
        "combine_vertical":   "Vertical",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-grises",
        "s_invert":     "-negativo",
        "s_crop":       "-recortado",
        "s_circle":     "-circulo",
        "s_resize":     "-redimensionada",
        "s_watermark":  "-marca-agua",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":     "Ferramentas de imagem",
        "menu_tip":       "Ferramentas de edição de imagens (Pillow)",
        "grayscale":      "Escala de cinza",
        "invert":         "Negativo",
        "crop":           "Recorte central…",
        "circle":         "Círculo",
        "resize":         "Redimensionar…",
        "combine":        "Combinar imagens…",
        "watermark":      "Marca d'água…",
        "optimize":       "Otimizar para web…",
        "processing":     "Processando…",
        "done_title":     "Processamento concluído",
        "done_msg":       "{count} imagem(ns) processada(s) com sucesso.",
        "done_failed":    "{count} imagem(ns) processada(s), {failed} falha(s).",
        "cancel":         "Cancelar",
        "ok":             "Aplicar",
        "choose":         "Escolher…",
        "err_pillow":     "O Pillow não está instalado. Instale com: pip install Pillow",
        "err_empty":      "O texto da marca d'água não pode ficar vazio.",
        "err_choose":     "Escolha uma imagem de marca d'água.",
        "err_combine":    "Selecione pelo menos duas imagens.",
        "crop_title":     "Recorte central",
        "crop_width":     "Largura",
        "crop_height":    "Altura",
        "resize_title":   "Redimensionar",
        "resize_width":   "Largura máx.",
        "resize_height":  "Altura máx.",
        "optimize_title": "Otimizar para web",
        "optimize_max":   "Dimensão máx.",
        "optimize_qual":  "Qualidade",
        "watermark_title": "Marca d'água",
        "wm_mode_text":   "Texto",
        "wm_mode_image":  "Imagem",
        "wm_text_hint":   "Texto da marca d'água",
        "wm_pick_image":  "Imagem da marca d'água…",
        "combine_title":  "Combinar imagens",
        "combine_vertical":   "Vertical",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-cinza",
        "s_invert":     "-negativo",
        "s_crop":       "-recortada",
        "s_circle":     "-circulo",
        "s_resize":     "-redimensionada",
        "s_watermark":  "-marca-dagua",
    }
else:
    T = {
        "menu_label":     "Image Tools",
        "menu_tip":       "Image processing tools (Pillow)",
        "grayscale":      "Grayscale",
        "invert":         "Invert",
        "crop":           "Crop Center…",
        "circle":         "Circle",
        "resize":         "Resize…",
        "combine":        "Combine Images…",
        "watermark":      "Watermark…",
        "optimize":       "Optimize for Web…",
        "processing":     "Processing…",
        "done_title":     "Processing complete",
        "done_msg":       "{count} image(s) processed successfully.",
        "done_failed":    "{count} image(s) processed, {failed} failed.",
        "cancel":         "Cancel",
        "ok":             "Apply",
        "choose":         "Choose…",
        "err_pillow":     "Pillow is not installed. Install it with: pip install Pillow",
        "err_empty":      "Watermark text cannot be empty.",
        "err_choose":     "Please choose a watermark image.",
        "err_combine":    "Select at least two images.",
        "crop_title":     "Crop Center",
        "crop_width":     "Width",
        "crop_height":    "Height",
        "resize_title":   "Resize",
        "resize_width":   "Max width",
        "resize_height":  "Max height",
        "optimize_title": "Optimize for Web",
        "optimize_max":   "Max dimension",
        "optimize_qual":  "Quality",
        "watermark_title": "Watermark",
        "wm_mode_text":   "Text",
        "wm_mode_image":  "Image",
        "wm_text_hint":   "Watermark text",
        "wm_pick_image":  "Watermark image…",
        "combine_title":  "Combine Images",
        "combine_vertical":   "Vertical",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-grayscale",
        "s_invert":     "-inverted",
        "s_crop":       "-cropped",
        "s_circle":     "-circle",
        "s_resize":     "-resized",
        "s_watermark":  "-watermarked",
    }

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
            ".webp": "WEBP", ".bmp": "BMP"}
_COMBINE_OUTPUT = "combined_images.png"


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


# ---------------------------------------------------------------------------
# Pillow operations (pure, run inside worker threads)
# ---------------------------------------------------------------------------

def op_grayscale(src):
    dst = _suffix(src, T["s_grayscale"])
    with Image.open(src) as im:
        _save(im.convert("L"), dst)
    return dst


def op_invert(src):
    dst = _suffix(src, T["s_invert"])
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        rgb = ImageOps.invert(rgba.convert("RGB"))
        rgb.putalpha(rgba.split()[3])
        _save(rgb, dst)
    return dst


def op_crop(src, w, h):
    dst = _suffix(src, T["s_crop"])
    with Image.open(src) as im:
        iw, ih = im.size
        cw, ch = min(w, iw), min(h, ih)
        left, top = (iw - cw) // 2, (ih - ch) // 2
        _save(im.crop((left, top, left + cw, top + ch)), dst)
    return dst


def op_circle(src):
    dst = _suffix(src, T["s_circle"])
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        iw, ih = rgba.size
        side = min(iw, ih)
        left, top = (iw - side) // 2, (ih - side) // 2
        sq = rgba.crop((left, top, left + side, top + side))
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, side, side), fill=255)
        sq.putalpha(mask)
        _save(sq, dst)
    return dst


def op_resize(src, w, h):
    dst = _suffix(src, T["s_resize"])
    with Image.open(src) as im:
        im.load()
        work = im.copy()
        work.thumbnail((w, h), Image.LANCZOS)
        _save(work, dst)
    return dst


def op_combine(paths, vertical):
    first = paths[0]
    out_path = os.path.join(os.path.dirname(first) or ".", _COMBINE_OUTPUT)
    imgs = []
    try:
        for p in paths:
            imgs.append(Image.open(p).convert("RGBA"))
        if vertical:
            width = max(i.width for i in imgs)
            height = sum(i.height for i in imgs)
        else:
            width = sum(i.width for i in imgs)
            height = max(i.height for i in imgs)
        canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        offset = 0
        for img in imgs:
            if vertical:
                pos = ((width - img.width) // 2, offset)
                offset += img.height
            else:
                pos = (offset, (height - img.height) // 2)
                offset += img.width
            canvas.paste(img, pos, img)
        canvas.save(out_path, "PNG")
    finally:
        for img in imgs:
            img.close()
    return out_path


def op_watermark(src, settings):
    dst = _suffix(src, T["s_watermark"])
    with Image.open(src) as im:
        base = im.convert("RGBA")
        bw, bh = base.size
        if settings["mode"] == "image":
            with Image.open(settings["image"]) as wm_img:
                wm = wm_img.convert("RGBA")
                scale = min(0.5 * bw / wm.width, 0.5 * bh / wm.height)
                if 0 < scale < 1:
                    wm = wm.resize(
                        (max(1, int(wm.width * scale)),
                         max(1, int(wm.height * scale))), Image.LANCZOS)
                wm.putalpha(128)
                x, y = (bw - wm.width) // 2, (bh - wm.height) // 2
                base.paste(wm, (x, y), wm)
        else:
            text = settings["text"]
            size = 64
            while size > 8:
                font = ImageFont.load_default(size=size)
                probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
                bbox = probe.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if tw <= bw * 0.9 and th <= bh * 0.9:
                    break
                size //= 2
            font = ImageFont.load_default(size=size)
            probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            bbox = probe.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw = ImageDraw.Draw(base)
            draw.text(((bw - tw) // 2 - bbox[0], (bh - th) // 2 - bbox[1]),
                      text, font=font, fill=(0, 0, 0, 128))
        _save(base, dst)
    return dst


def op_optimize(src, max_dim, quality):
    dst = _suffix(src, "_optimized", force_ext=".jpg")
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        rgba.thumbnail((max_dim, max_dim), Image.LANCZOS)
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[3])
        flat.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
    return dst


# ---------------------------------------------------------------------------
# Batch progress dialog
# ---------------------------------------------------------------------------

class ProgressDialog(Adw.Window):
    __gtype_name__ = "ImageToolsProgressDialog"

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
# Settings dialogs
# ---------------------------------------------------------------------------

class _BaseDialog(Adw.Window):
    def __init__(self, title):
        super().__init__(title=title)
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(360, -1)
        self._callback = None

        self._tv = Adw.ToolbarView()
        self._tv.add_top_bar(Adw.HeaderBar())

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._body.set_margin_top(16)
        self._body.set_margin_bottom(16)
        self._body.set_margin_start(18)
        self._body.set_margin_end(18)
        self._build(self._body)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", lambda _: self._dismiss())
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label=T["ok"])
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _: self._apply())
        btn_box.append(ok_btn)

        self._body.append(btn_box)
        self._tv.set_content(self._body)
        self.set_content(self._tv)

    def _section(self, text):
        lbl = Gtk.Label(label="<b>{0}</b>".format(text))
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        return lbl

    def _spin(self, low, high, step, default):
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        spin.set_value(default)
        return spin

    def set_callback(self, cb):
        self._callback = cb

    def _build(self, body):
        raise NotImplementedError

    def _values(self):
        raise NotImplementedError

    def _dismiss(self):
        if self._callback:
            self._callback(None)
        self.destroy()

    def _apply(self):
        vals = self._values()
        if vals is None:
            return
        if self._callback:
            self._callback(vals)
        self.destroy()


class CropDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsCropDialog"

    def _build(self, body):
        body.append(self._section(T["crop_width"]))
        self._w = self._spin(1, 100000, 1, 512)
        body.append(self._w)
        body.append(self._section(T["crop_height"]))
        self._h = self._spin(1, 100000, 1, 512)
        body.append(self._h)

    def _values(self):
        return {"w": int(self._w.get_value()), "h": int(self._h.get_value())}


class ResizeDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsResizeDialog"

    def _build(self, body):
        body.append(self._section(T["resize_width"]))
        self._w = self._spin(1, 100000, 1, 1024)
        body.append(self._w)
        body.append(self._section(T["resize_height"]))
        self._h = self._spin(1, 100000, 1, 1024)
        body.append(self._h)

    def _values(self):
        return {"w": int(self._w.get_value()), "h": int(self._h.get_value())}


class OptimizeDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsOptimizeDialog"

    def _build(self, body):
        body.append(self._section(T["optimize_max"]))
        self._max = self._spin(100, 20000, 10, 1920)
        body.append(self._max)
        body.append(self._section(T["optimize_qual"]))
        self._qual = self._spin(1, 100, 1, 82)
        body.append(self._qual)

    def _values(self):
        return {"max": int(self._max.get_value()),
                "qual": int(self._qual.get_value())}


class WatermarkDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsWatermarkDialog"

    def _build(self, body):
        body.append(self._section(T["wm_mode_text"]))
        self._text_entry = Gtk.Entry()
        self._text_entry.set_placeholder_text(T["wm_text_hint"])
        body.append(self._text_entry)

        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._text_radio = Gtk.CheckButton(label=T["wm_mode_text"])
        self._text_radio.set_active(True)
        self._image_radio = Gtk.CheckButton(label=T["wm_mode_image"])
        self._image_radio.set_group(self._text_radio)
        mode_box.append(self._text_radio)
        mode_box.append(self._image_radio)
        body.append(mode_box)

        self._image_btn = Gtk.Button(label=T["wm_pick_image"])
        self._image_btn.connect("clicked", self._pick_image)
        body.append(self._image_btn)

        self._image_path = None
        self._text_radio.connect("toggled", self._sync_sensitive)
        self._image_radio.connect("toggled", self._sync_sensitive)
        self._sync_sensitive()

    def _sync_sensitive(self, *_):
        is_text = self._text_radio.get_active()
        self._text_entry.set_sensitive(is_text)
        self._image_btn.set_sensitive(not is_text)

    def _pick_image(self, _btn):
        filt = Gtk.FileFilter()
        filt.set_name(T["wm_mode_image"])
        for mime in ("image/png", "image/jpeg", "image/webp", "image/bmp"):
            filt.add_mime_type(mime)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dlg = Gtk.FileDialog(title=T["wm_pick_image"])
        dlg.set_filters(store)
        dlg.set_default_filter(filt)
        dlg.open(_nautilus_window(), None, self._on_picked)

    def _on_picked(self, dlg, result):
        try:
            path = dlg.open_finish(result).get_path()
        except Exception:
            return
        if path:
            self._image_path = path
            self._image_btn.set_label(os.path.basename(path))

    def _values(self):
        if self._text_radio.get_active():
            text = self._text_entry.get_text().strip()
            if not text:
                _show_message(T["err_empty"])
                return None
            return {"mode": "text", "text": text, "image": ""}
        if not self._image_path:
            _show_message(T["err_choose"])
            return None
        return {"mode": "image", "text": "", "image": self._image_path}


class CombineDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsCombineDialog"

    def _build(self, body):
        self._v = Gtk.CheckButton(label=T["combine_vertical"])
        self._v.set_active(True)
        self._h = Gtk.CheckButton(label=T["combine_horizontal"])
        self._h.set_group(self._v)
        body.append(self._v)
        body.append(self._h)

    def _values(self):
        return {"vertical": self._v.get_active()}


# ---------------------------------------------------------------------------
# Nautilus extension with submenu
# ---------------------------------------------------------------------------

class ImageToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "ImageToolsExtension"

    def _add(self, submenu, name, label, cb, *args):
        item = Nautilus.MenuItem(
            name="ImageTools::{0}".format(name),
            label=label,
            tip=T["menu_tip"],
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
            name="ImageTools::Top",
            label=T["menu_label"],
            tip=T["menu_tip"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)

        self._add(submenu, "Grayscale", T["grayscale"],
                  self._cb_simple, paths, op_grayscale)
        self._add(submenu, "Invert", T["invert"],
                  self._cb_simple, paths, op_invert)
        self._add(submenu, "Crop", T["crop"], self._cb_crop, paths)
        self._add(submenu, "Circle", T["circle"],
                  self._cb_simple, paths, op_circle)
        self._add(submenu, "Resize", T["resize"], self._cb_resize, paths)
        self._add(submenu, "Combine", T["combine"], self._cb_combine, paths)
        self._add(submenu, "Watermark", T["watermark"],
                  self._cb_watermark, paths)
        self._add(submenu, "Optimize", T["optimize"], self._cb_optimize, paths)

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

    def _cb_simple(self, _item, paths, op):
        if not self._guard_pillow():
            return
        self._start_batch([lambda p=p, op=op: op(p) for p in paths])

    def _cb_crop(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = CropDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_crop(p, s["w"], s["h"]) for p in paths]))
        dlg.present()

    def _cb_resize(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = ResizeDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_resize(p, s["w"], s["h"]) for p in paths]))
        dlg.present()

    def _cb_combine(self, _item, paths):
        if not self._guard_pillow():
            return
        if len(paths) < 2:
            _show_message(T["err_combine"])
            return
        dlg = CombineDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda: op_combine(paths, s["vertical"])]))
        dlg.present()

    def _cb_watermark(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = WatermarkDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_watermark(p, s) for p in paths]))
        dlg.present()

    def _cb_optimize(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = OptimizeDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_optimize(p, s["max"], s["qual"])
                 for p in paths]))
        dlg.present()