#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Paste Into File — Nautilus Python Extension
# DESC: Save clipboard content (text, image or files) as a file
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
# NAME: Paste Into File – Nautilus Python Extension
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
# INSTALL:
#   cp paste-into-file.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

import locale
import os
import threading
import time
import traceback
import zipfile

import gi
gi.require_version("Gtk",     "4.0")
gi.require_version("Adw",     "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Gdk, GdkPixbuf, Gio, GLib, Nautilus

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label":     "Coller dans un fichier",
        "dialog_title":   "Coller le contenu du presse-papiers dans un fichier",
        "name_label":     "Nom du fichier",
        "type_label":     "Contenu du presse-papiers",
        "type_text":      "Texte (.txt)",
        "type_png":       "Image (.png)",
        "type_jpg":       "Image (.jpg)",
        "type_zip":       "Fichiers ({n} élément(s)) (.zip)",
        "save":           "Enregistrer",
        "cancel":         "Annuler",
        "saving":         "Création de l'archive…",
        "done":           "Enregistré : {name}",
        "err_empty":      "Le presse-papiers est vide ou contient un contenu non pris en charge.",
        "err_name":       "Le nom du fichier ne peut pas être vide.",
        "err_save":       "Impossible d'enregistrer le fichier.",
        "overwrite_head": "Remplacer le fichier ?",
        "overwrite_body": "Un fichier nommé «{name}» existe déjà. Voulez-vous le remplacer ?",
        "overwrite_ok":   "Remplacer",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":     "In Datei einfügen",
        "dialog_title":   "Zwischenablage in Datei einfügen",
        "name_label":     "Dateiname",
        "type_label":     "Zwischenablage-Inhalt",
        "type_text":      "Text (.txt)",
        "type_png":       "Bild (.png)",
        "type_jpg":       "Bild (.jpg)",
        "type_zip":       "Dateien ({n} Element(e)) (.zip)",
        "save":           "Speichern",
        "cancel":         "Abbrechen",
        "saving":         "Archiv wird erstellt…",
        "done":           "Gespeichert: {name}",
        "err_empty":      "Die Zwischenablage ist leer oder der Inhalt wird nicht unterstützt.",
        "err_name":       "Der Dateiname darf nicht leer sein.",
        "err_save":       "Die Datei konnte nicht gespeichert werden.",
        "overwrite_head": "Datei ersetzen?",
        "overwrite_body": "Eine Datei namens „{name}“ ist bereits vorhanden. Möchten Sie sie ersetzen?",
        "overwrite_ok":   "Ersetzen",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":     "Pegar en un archivo",
        "dialog_title":   "Pegar el portapapeles en un archivo",
        "name_label":     "Nombre del archivo",
        "type_label":     "Contenido del portapapeles",
        "type_text":      "Texto (.txt)",
        "type_png":       "Imagen (.png)",
        "type_jpg":       "Imagen (.jpg)",
        "type_zip":       "Archivos ({n} elemento(s)) (.zip)",
        "save":           "Guardar",
        "cancel":         "Cancelar",
        "saving":         "Creando archivo…",
        "done":           "Guardado: {name}",
        "err_empty":      "El portapapeles está vacío o contiene contenido no compatible.",
        "err_name":       "El nombre del archivo no puede estar vacío.",
        "err_save":       "No se pudo guardar el archivo.",
        "overwrite_head": "¿Reemplazar archivo?",
        "overwrite_body": "Ya existe un archivo llamado «{name}». ¿Quieres reemplazarlo?",
        "overwrite_ok":   "Reemplazar",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":     "Colar em arquivo",
        "dialog_title":   "Colar conteúdo da área de transferência em arquivo",
        "name_label":     "Nome do arquivo",
        "type_label":     "Conteúdo da área de transferência",
        "type_text":      "Texto (.txt)",
        "type_png":       "Imagem (.png)",
        "type_jpg":       "Imagem (.jpg)",
        "type_zip":       "Arquivos ({n} item(ns)) (.zip)",
        "save":           "Salvar",
        "cancel":         "Cancelar",
        "saving":         "Criando arquivo compactado…",
        "done":           "Salvo: {name}",
        "err_empty":      "A área de transferência está vazia ou contém conteúdo não suportado.",
        "err_name":       "O nome do arquivo não pode ficar vazio.",
        "err_save":       "Não foi possível salvar o arquivo.",
        "overwrite_head": "Substituir arquivo?",
        "overwrite_body": "Já existe um arquivo chamado “{name}”. Deseja substituí-lo?",
        "overwrite_ok":   "Substituir",
    }
else:
    T = {
        "menu_label":     "Paste Into File",
        "dialog_title":   "Paste Clipboard Into File",
        "name_label":     "File name",
        "type_label":     "Clipboard content",
        "type_text":      "Text (.txt)",
        "type_png":       "Image (.png)",
        "type_jpg":       "Image (.jpg)",
        "type_zip":       "Files ({n} item(s)) (.zip)",
        "save":           "Save",
        "cancel":         "Cancel",
        "saving":         "Creating archive…",
        "done":           "Saved: {name}",
        "err_empty":      "The clipboard is empty or contains unsupported content.",
        "err_name":       "The file name cannot be empty.",
        "err_save":       "Could not save the file.",
        "overwrite_head": "Replace file?",
        "overwrite_body": "A file named “{name}” already exists. Do you want to replace it?",
        "overwrite_ok":   "Replace",
    }

FILE_MIMES = {
    "text/uri-list",
    "application/x-gtk-file-list",
    "x-special/gnome-copied-files",
    "application/x-gnome-copied-files",
}
TEXT_MIMES = {
    "text/plain",
    "text/plain;charset=utf-8",
    "utf8_string",
    "text",
    "string",
}
ZIP_THREAD_THRESHOLD = 25 * 1024 * 1024
ZIP_THREAD_ITEMS = 30


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

def _default_name() -> str:
    return time.strftime("Clipboard_%Y%m%d_%H%M%S")

def _sanitize_name(name: str) -> str:
    name = name.replace("/", "-").replace("\\", "-")
    name = "".join(ch for ch in name if ch >= " ")
    return name.strip(" .")

def _ensure_extension(name: str, ext: str) -> str:
    ext = ext.lower()
    if name.lower().endswith(ext):
        return name
    if ext == ".jpg" and name.lower().endswith(".jpeg"):
        return name
    return name + ext

def _detect_kind(fmts):
    mimes = [m.lower() for m in fmts.get_mime_types()]
    if (fmts.contain_gtype(Gdk.FileList.__gtype__)
            or any(m in FILE_MIMES for m in mimes)):
        return "files"
    if (fmts.contain_gtype(GdkPixbuf.Pixbuf.__gtype__)
            or fmts.contain_gtype(Gdk.Texture.__gtype__)
            or any(m.startswith("image/") for m in mimes)):
        return "image"
    if (fmts.contain_gtype(GObject.TYPE_STRING)
            or any(m in TEXT_MIMES for m in mimes)):
        return "text"
    return None

def _image_extension(mimes) -> str:
    lowered = [m.lower() for m in mimes]
    if any("image/jpeg" == m or "image/jpg" == m for m in lowered):
        if not any("image/png" == m for m in lowered):
            return ".jpg"
    return ".png"

def _parse_uri_list(text: str):
    uris = []
    if not text:
        return uris
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = line.split(None, 1)[0].lower() if " " in line else line.lower()
        if head in ("copy", "cut", "move", "link"):
            continue
        if line.startswith("file://"):
            uris.append(line)
    return uris


# ---------------------------------------------------------------------------
# Progress window (threaded zip)
# ---------------------------------------------------------------------------

class _ZipCancelled(Exception):
    pass

class ZipProgressWindow(Adw.Window):
    __gtype_name__ = "PasteIntoFileZipProgressWindow"

    def __init__(self, cancel_event):
        super().__init__(title=T["dialog_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_deletable(False)
        self.set_default_size(340, -1)
        self._cancel = cancel_event

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        box.append(Gtk.Label(label=T["saving"]))

        self._bar = Gtk.ProgressBar()
        self._bar.set_pulse_step(0.05)
        box.append(self._bar)

        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", self._on_cancel)
        box.append(cancel_btn)

        toolbar_view.set_content(box)
        self.set_content(toolbar_view)

        self._timer = GObject.timeout_add(80, self._pulse)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, _widget):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _pulse(self):
        if self._timer is not None:
            self._bar.pulse()
            return True
        return False

    def _on_cancel(self, _btn):
        self._cancel.set()
        self.destroy()


# ---------------------------------------------------------------------------
# Preview dialog (file name + detected type)
# ---------------------------------------------------------------------------

class PasteIntoFileDialog(Adw.Window):
    __gtype_name__ = "PasteIntoFileDialog"

    def __init__(self, type_text, default_name, callback):
        super().__init__(title=T["dialog_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(420, -1)
        self._callback = callback

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(Adw.HeaderBar())

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(18)
        outer.set_margin_end(18)

        type_lbl = Gtk.Label(label=f"<b>{T['type_label']}</b>")
        type_lbl.set_use_markup(True)
        type_lbl.set_halign(Gtk.Align.START)
        outer.append(type_lbl)

        self._type_value = Gtk.Label(label=type_text)
        self._type_value.set_halign(Gtk.Align.START)
        self._type_value.add_css_class("dim-label")
        outer.append(self._type_value)

        name_lbl = Gtk.Label(label=f"<b>{T['name_label']}</b>")
        name_lbl.set_use_markup(True)
        name_lbl.set_halign(Gtk.Align.START)
        outer.append(name_lbl)

        self._name_entry = Gtk.Entry()
        self._name_entry.set_text(default_name)
        self._name_entry.connect("activate", lambda _e: self._respond(True))
        outer.append(self._name_entry)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(6)

        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", lambda _: self._respond(False))
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label=T["save"])
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _: self._respond(True))
        btn_box.append(ok_btn)

        outer.append(btn_box)
        toolbar_view.set_content(outer)
        self.set_content(toolbar_view)

        self._name_entry.grab_focus()
        self._name_entry.select_region(0, -1)

    def _respond(self, ok: bool):
        if not ok:
            self._callback(None)
            self.destroy()
            return
        name = self._name_entry.get_text().strip()
        if not name:
            Gtk.AlertDialog(message=T["err_name"]).show(self)
            return
        self._callback({"name": name})
        self.destroy()


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def _build_zip(out_path, uris, cancel_event=None):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED,
                         allowZip64=True) as zf:
        for uri in uris:
            if cancel_event is not None and cancel_event.is_set():
                raise _ZipCancelled()
            item = Gio.File.new_for_uri(uri).get_path()
            if item is None or not os.path.lexists(item):
                continue
            base = os.path.basename(item.rstrip("/\\")) or os.path.basename(item)
            if os.path.isdir(item):
                if not os.listdir(item):
                    zf.writestr(base + "/", "")
                    continue
                for root, dirs, files in os.walk(item):
                    if cancel_event is not None and cancel_event.is_set():
                        raise _ZipCancelled()
                    dirs.sort()
                    for d in dirs:
                        rel = os.path.relpath(os.path.join(root, d), item)
                        zf.writestr(os.path.join(base, rel) + "/", "")
                    for f in sorted(files):
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, item)
                        zf.write(full, os.path.join(base, rel))
            else:
                zf.write(item, base)


# ---------------------------------------------------------------------------
# Nautilus Extension
# ---------------------------------------------------------------------------

class PasteIntoFileExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "PasteIntoFileExtension"

    def get_file_items(self, files):
        return []

    def get_background_items(self, folder):
        if folder is None:
            return []
        path = folder.get_location().get_path()
        if not path or not os.path.isdir(path):
            return []
        item = Nautilus.MenuItem(
            name  = "PasteIntoFile::Paste",
            label = T["menu_label"],
            tip   = "Save clipboard content (text, image or files) as a file",
            icon  = "edit-paste-symbolic",
        )
        item.connect("activate", self._on_activate, path)
        return [item]

    def _on_activate(self, _item, folder_path):
        try:
            display = Gdk.Display.get_default()
            if display is None:
                return
            clipboard = display.get_clipboard()
            fmts = clipboard.get_formats()
        except Exception:
            return

        mimes = fmts.get_mime_types()
        kind = _detect_kind(fmts)
        if kind is None:
            _show_message(T["err_empty"])
            return

        if kind == "files":
            if fmts.contain_gtype(Gdk.FileList.__gtype__):
                clipboard.read_value_async(
                    Gdk.FileList.__gtype__, 0, None,
                    self._on_got_files, folder_path)
            else:
                clipboard.read_text_async(
                    None, self._on_got_uri_text, folder_path)
        elif kind == "image":
            clipboard.read_texture_async(
                None, self._on_got_texture,
                (folder_path, _image_extension(mimes)))
        else:
            clipboard.read_text_async(None, self._on_got_text, folder_path)

    def _on_got_text(self, clipboard, result, folder_path):
        text = None
        try:
            text = clipboard.read_text_finish(result)
        except Exception:
            pass
        if text is None or not text.strip():
            _show_message(T["err_empty"])
            return
        self._open_dialog("text", text, ".txt", 1, folder_path)

    def _on_got_uri_text(self, clipboard, result, folder_path):
        text = None
        try:
            text = clipboard.read_text_finish(result)
        except Exception:
            pass
        uris = _parse_uri_list(text) if text else []
        if not uris:
            _show_message(T["err_empty"])
            return
        self._open_dialog("files", uris, ".zip", len(uris), folder_path)

    def _on_got_texture(self, clipboard, result, ctx):
        folder_path, ext = ctx
        texture = None
        try:
            texture = clipboard.read_texture_finish(result)
        except Exception:
            pass
        if texture is None:
            _show_message(T["err_empty"])
            return
        self._open_dialog("image", texture, ext, 1, folder_path)

    def _on_got_files(self, clipboard, result, folder_path):
        fl = None
        try:
            fl = clipboard.read_value_finish(result)
        except Exception:
            pass
        uris = [f.get_uri() for f in fl.get_files()] if fl else []
        if not uris:
            _show_message(T["err_empty"])
            return
        self._open_dialog("files", uris, ".zip", len(uris), folder_path)

    def _open_dialog(self, kind, payload, ext, n_items, folder_path):
        if kind == "text":
            type_text = T["type_text"]
        elif kind == "image":
            type_text = T["type_jpg"] if ext == ".jpg" else T["type_png"]
        else:
            type_text = T["type_zip"].format(n=n_items)

        def on_name(result):
            if result is None:
                return
            name = _sanitize_name(result["name"])
            if not name:
                _show_message(T["err_name"])
                return
            dest = os.path.join(folder_path, _ensure_extension(name, ext))
            self._proceed_save(dest, kind, payload, ext, n_items)

        PasteIntoFileDialog(
            type_text=type_text,
            default_name=_default_name(),
            callback=on_name,
        ).present()

    def _proceed_save(self, dest, kind, payload, ext, n_items):
        if os.path.lexists(dest):
            dlg = Adw.MessageDialog(
                transient_for=_nautilus_window(),
                heading=T["overwrite_head"],
                body=T["overwrite_body"].format(name=os.path.basename(dest)))
            dlg.add_response("cancel", T["cancel"])
            dlg.add_response("ok", T["overwrite_ok"])
            dlg.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.connect("response", self._on_overwrite_response,
                        dest, kind, payload, ext, n_items)
            dlg.present()
            return
        self._save(dest, kind, payload, ext, n_items)

    def _on_overwrite_response(self, dlg, response,
                               dest, kind, payload, ext, n_items):
        if response == "ok":
            self._save(dest, kind, payload, ext, n_items)

    def _save(self, dest, kind, payload, ext, n_items):
        try:
            if kind == "text":
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(payload)
                self._done(dest)
            elif kind == "image":
                self._save_image(dest, payload, ext)
            else:
                self._save_zip(dest, payload, n_items)
        except Exception:
            traceback.print_exc()
            _show_message(T["err_save"])

    def _save_image(self, dest, texture, ext):
        pb = Gdk.pixbuf_get_from_texture(texture)
        if pb is None:
            _show_message(T["err_save"])
            return
        if ext in (".jpg", ".jpeg"):
            if pb.get_has_alpha():
                w, h = pb.get_width(), pb.get_height()
                rgb = GdkPixbuf.Pixbuf.new(
                    GdkPixbuf.Colorspace.RGB, False, 8, w, h)
                pb.copy_area(0, 0, w, h, rgb, 0, 0)
                pb = rgb
            pb.savev(dest, "jpeg", ["quality"], ["90"])
        else:
            pb.savev(dest, "png", [], [])
        self._done(dest)

    def _is_zip_heavy(self, uris):
        heavy = len(uris) > ZIP_THREAD_ITEMS
        total = 0
        for uri in uris:
            path = Gio.File.new_for_uri(uri).get_path()
            if path is None or not os.path.lexists(path):
                continue
            if os.path.isdir(path):
                return True
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        return heavy or total > ZIP_THREAD_THRESHOLD

    def _save_zip(self, dest, uris, n_items):
        if not uris:
            _show_message(T["err_save"])
            return
        if not self._is_zip_heavy(uris):
            try:
                _build_zip(dest, uris)
            except Exception:
                traceback.print_exc()
                _show_message(T["err_save"])
                return
            self._done(dest)
            return

        cancel = threading.Event()
        progress = ZipProgressWindow(cancel)
        progress.present()

        def on_finish(cancelled):
            if progress:
                try:
                    progress.destroy()
                except Exception:
                    pass
            if not cancelled:
                self._done(dest)

        threading.Thread(
            target=self._zip_worker,
            args=(dest, uris, cancel, on_finish),
            daemon=True,
        ).start()

    def _zip_worker(self, dest, uris, cancel, on_finish):
        cancelled = False
        try:
            _build_zip(dest, uris, cancel)
            cancelled = cancel.is_set()
        except _ZipCancelled:
            cancelled = True
        except Exception:
            traceback.print_exc()
            GLib.idle_add(_show_message, T["err_save"])
            cancelled = True
        if cancelled:
            try:
                os.remove(dest)
            except OSError:
                pass
        GLib.idle_add(on_finish, cancelled)

    def _done(self, dest):
        _show_message(T["done"].format(name=os.path.basename(dest)))