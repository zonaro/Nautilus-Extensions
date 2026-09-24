#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: File Tools – Nautilus Python Extension
# AUTHOR: Tof
# VERSION: 1.1
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
# NAME: File Tools – Nautilus Python Extension
# DESC: Utility toolset in the context menu root (friendly rename, clipboard,
#       empty-folder cleanup, timestamp folders, symlinks, base64, content)
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-adw-1
# INSTALL:
#   cp file-tools.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

import os
import locale
import base64
import mimetypes
import threading
import unicodedata
from datetime import date

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Gdk, GLib, Gio, GdkPixbuf, Nautilus

try:
    from PIL import Image as _PILImage
    _HAS_PIL = True
except ImportError:
    _PILImage = None
    _HAS_PIL = False

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "friendly_name":  "Nom convivial",
        "copy_path":      "Copier le chemin",
        "enum_rename":    "Renommage séquentiel…",
        "clean_empty":    "Supprimer les dossiers vides",
        "timestamp_folder": "Créer un dossier daté (AAAA/MM/JJ)",
        "symlink":        "Créer un lien symbolique…",
        "to_base64":      "Copier en Base64 (data URI)",
        "copy_content":   "Copier le contenu",
        "ok":             "Appliquer",
        "cancel":         "Annuler",
        "dest_label":     "Dossier de destination",
        "dest_hint":      "ex. : /chemin/vers/dossier",
        "browse":         "Choisir…",
        "err_no_dest":    "Choisissez un dossier de destination.",
        "pattern_label":  "Modèle de nom (contient #)",
        "pattern_hint":   "ex. : fichier (#).txt",
        "start_label":    "Numéro de départ",
        "link_label":     "Nom du lien",
        "link_hint":      "ex. : mon-lien",
        "done_renamed":   "{n} élément(s) renommé(s).",
        "done_path":      "{n} chemin(s) copié(s).",
        "done_cleaned":   "{n} dossier(s) vide(s) supprimé(s).",
        "done_created":   "{n} dossier(s) daté(s) créé(s).",
        "done_link":      "{n} lien(s) symbolique(s) créé(s).",
        "done_base64":    "{n} fichier(s) copié(s) en Base64 (data URI).",
        "done_content":   "Contenu de {n} fichier(s) .txt copié.",
        "err_missing":    "Introuvable ou inexistant :\n{name}",
        "err_hash":       "Le modèle doit contenir « # ».",
        "err_dir_only":   "Cette action nécessite la sélection d'un dossier.",
        "err_no_file":    "Aucun fichier .txt sélectionné.",
        "err_no_clip":    "Presse-papiers indisponible.",
        "done_content_img": "{n} image(s) combinée(s) et copiée(s).",
        "err_mixed":      "Sélectionnez des fichiers texte ou des images, pas les deux.",
        "err_pil":        "Pillow est requis (python3-pil).",
    }
elif _lang.startswith("de"):
    T = {
        "friendly_name":  "Freundlicher Name",
        "copy_path":      "Pfad kopieren",
        "enum_rename":    "Nummeriert umbenennen…",
        "clean_empty":    "Leere Ordner löschen",
        "timestamp_folder": "Datumsordner erstellen (JJJJ/MM/TT)",
        "symlink":        "Symbolischen Link erstellen…",
        "to_base64":      "Als Base64 kopieren (data URI)",
        "copy_content":   "Inhalt kopieren",
        "ok":             "Anwenden",
        "cancel":         "Abbrechen",
        "dest_label":     "Zielordner",
        "dest_hint":      "z. B. /pfad/zum/ordner",
        "browse":         "Wählen…",
        "err_no_dest":    "Bitte wählen Sie einen Zielordner.",
        "pattern_label":  "Namensmuster (enthält #)",
        "pattern_hint":   "z. B. datei (#).txt",
        "start_label":    "Startnummer",
        "link_label":     "Linkname",
        "link_hint":      "z. B. mein-link",
        "done_renamed":   "{n} Element(e) umbenannt.",
        "done_path":      "{n} Pfad(e) kopiert.",
        "done_cleaned":   "{n} leere(r) Ordner gelöscht.",
        "done_created":   "{n} Datumsordner erstellt.",
        "done_link":      "{n} symbolische(r) Link(s) erstellt.",
        "done_base64":    "{n} Datei(en) als Base64 (data URI) kopiert.",
        "done_content":   "Inhalt von {n} .txt-Datei(en) kopiert.",
        "err_missing":    "Nicht gefunden oder nicht vorhanden:\n{name}",
        "err_hash":       "Das Muster muss „#“ enthalten.",
        "err_dir_only":   "Für diese Aktion muss ein Ordner ausgewählt werden.",
        "err_no_file":    "Keine .txt-Datei ausgewählt.",
        "err_no_clip":    "Zwischenablage nicht verfügbar.",
        "done_content_img": "{n} Bild(er) kombiniert und kopiert.",
        "err_mixed":      "Wählen Sie entweder Textdateien oder Bilder, nicht beides.",
        "err_pil":        "Pillow wird benötigt (python3-pil).",
    }
elif _lang.startswith("es"):
    T = {
        "friendly_name":  "Nombre amigable",
        "copy_path":      "Copiar ruta",
        "enum_rename":    "Renombrar secuencial…",
        "clean_empty":    "Eliminar carpetas vacías",
        "timestamp_folder": "Crear carpeta con fecha (AAAA/MM/DD)",
        "symlink":        "Crear enlace simbólico…",
        "to_base64":      "Copiar como Base64 (data URI)",
        "copy_content":   "Copiar contenido",
        "ok":             "Aplicar",
        "cancel":         "Cancelar",
        "dest_label":     "Carpeta de destino",
        "dest_hint":      "ej.: /ruta/a/carpeta",
        "browse":         "Elegir…",
        "err_no_dest":    "Elija una carpeta de destino.",
        "pattern_label":  "Patrón de nombre (contiene #)",
        "pattern_hint":   "ej.: archivo (#).txt",
        "start_label":    "Número inicial",
        "link_label":     "Nombre del enlace",
        "link_hint":      "ej.: mi-enlace",
        "done_renamed":   "{n} elemento(s) renombrado(s).",
        "done_path":      "{n} ruta(s) copiada(s).",
        "done_cleaned":   "{n} carpeta(s) vacía(s) eliminada(s).",
        "done_created":   "{n} carpeta(s) con fecha creada(s).",
        "done_link":      "{n} enlace(s) simbólico(s) creado(s).",
        "done_base64":    "{n} archivo(s) copiado(s) como Base64 (data URI).",
        "done_content":   "Contenido de {n} archivo(s) .txt copiado.",
        "err_missing":    "No encontrado o inexistente:\n{name}",
        "err_hash":       "El patrón debe contener « # ».",
        "err_dir_only":   "Esta acción requiere seleccionar una carpeta.",
        "err_no_file":    "Ningún archivo .txt seleccionado.",
        "err_no_clip":    "Portapapeles no disponible.",
        "done_content_img": "{n} imagen(es) combinada(s) y copiada(s).",
        "err_mixed":      "Seleccione archivos de texto o imágenes, no ambos.",
        "err_pil":        "Se requiere Pillow (python3-pil).",
    }
elif _lang.startswith("pt"):
    T = {
        "friendly_name":  "Nome amigável",
        "copy_path":      "Copiar caminho",
        "enum_rename":    "Renomear sequencial…",
        "clean_empty":    "Remover pastas vazias",
        "timestamp_folder": "Criar pasta com data (AAAA/MM/DD)",
        "symlink":        "Criar link simbólico…",
        "to_base64":      "Copiar como Base64 (data URI)",
        "copy_content":   "Copiar conteúdo",
        "ok":             "Aplicar",
        "cancel":         "Cancelar",
        "dest_label":     "Pasta de destino",
        "dest_hint":      "ex.: /caminho/para/pasta",
        "browse":         "Escolher…",
        "err_no_dest":    "Escolha uma pasta de destino.",
        "pattern_label":  "Padrão de nome (contém #)",
        "pattern_hint":   "ex.: arquivo (#).txt",
        "start_label":    "Número inicial",
        "link_label":     "Nome do link",
        "link_hint":      "ex.: meu-link",
        "done_renamed":   "{n} item(ns) renomeado(s).",
        "done_path":      "{n} caminho(s) copiado(s).",
        "done_cleaned":   "{n} pasta(s) vazia(s) removida(s).",
        "done_created":   "{n} pasta(s) com data criada(s).",
        "done_link":      "{n} link(s) simbólico(s) criado(s).",
        "done_base64":    "{n} arquivo(s) copiado(s) como Base64 (data URI).",
        "done_content":   "Conteúdo de {n} arquivo(s) .txt copiado.",
        "err_missing":    "Não encontrado ou inexistente:\n{name}",
        "err_hash":       "O padrão deve conter « # ».",
        "err_dir_only":   "Esta ação requer a seleção de uma pasta.",
        "err_no_file":    "Nenhum arquivo .txt selecionado.",
        "err_no_clip":    "Área de transferência indisponível.",
        "done_content_img": "{n} imagem(ns) combinada(s) e copiada(s).",
        "err_mixed":      "Selecione arquivos de texto ou imagens, não ambos.",
        "err_pil":        "Pillow é necessário (python3-pil).",
    }
else:
    T = {
        "friendly_name":  "Friendly Name",
        "copy_path":      "Copy Path",
        "enum_rename":    "Sequential Rename…",
        "clean_empty":    "Remove Empty Folders",
        "timestamp_folder": "Create Timestamp Folder (YYYY/MM/DD)",
        "symlink":        "Create Symlink…",
        "to_base64":      "Copy as Base64 (data URI)",
        "copy_content":   "Copy Content",
        "ok":             "Apply",
        "cancel":         "Cancel",
        "dest_label":     "Destination folder",
        "dest_hint":      "e.g. /path/to/folder",
        "browse":         "Browse…",
        "err_no_dest":    "Please choose a destination folder.",
        "pattern_label":  "Name pattern (contains #)",
        "pattern_hint":   "e.g. file (#).txt",
        "start_label":    "Start number",
        "link_label":     "Link name",
        "link_hint":      "e.g. my-link",
        "done_renamed":   "{n} item(s) renamed.",
        "done_path":      "{n} path(s) copied.",
        "done_cleaned":   "{n} empty folder(s) removed.",
        "done_created":   "{n} timestamp folder(s) created.",
        "done_link":      "{n} symlink(s) created.",
        "done_base64":    "{n} file(s) copied as Base64 (data URI).",
        "done_content":   "Content of {n} .txt file(s) copied.",
        "err_missing":    "Not found or missing:\n{name}",
        "err_hash":       "The pattern must contain « # ».",
        "err_dir_only":   "This action requires selecting a folder.",
        "err_no_file":    "No .txt files selected.",
        "err_no_clip":    "Clipboard unavailable.",
        "done_content_img": "{n} image(s) combined and copied.",
        "err_mixed":      "Select either text files or image files, not both.",
        "err_pil":        "Pillow is required (python3-pil).",
    }


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


def _clipboard():
    display = Gdk.Display.get_default()
    return display.get_clipboard() if display else None


def _paths_from_files(files):
    out = []
    for f in files:
        if f.get_uri_scheme() == "file":
            p = f.get_location().get_path()
            if p:
                out.append(p)
    return out


def _unique_path(path: str) -> str:
    if not os.path.exists(path) and not os.path.islink(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = "{0}-{1}{2}".format(base, i, ext)
        if not os.path.exists(cand) and not os.path.islink(cand):
            return cand
        i += 1


def _friendly_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace(" ", "-")
    s = s.translate(str.maketrans("", "", "()#:,"))
    return s


def _is_text_file(path: str) -> bool:
    if path.lower().endswith(".txt"):
        return True
    mime, _ = mimetypes.guess_type(path)
    return bool(mime and mime.startswith("text/"))


_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _is_image_file(path: str) -> bool:
    return path.lower().endswith(_IMAGE_EXTS)


def _is_content_file(path: str) -> bool:
    return os.path.isfile(path) and (_is_text_file(path) or _is_image_file(path))


def _pil_to_pixbuf(img):
    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    w, h = rgba.size
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(rgba.tobytes()), GdkPixbuf.Colorspace.RGB,
        True, 8, w, h, w * 4)


def _warn_missing(names):
    if names:
        _show_message(T["err_missing"].format(name="\n".join(names)))


def _show_result(name, n):
    if n:
        _show_message(T[name].format(n=n))


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class _BaseDialog(Adw.Window):
    def __init__(self, title):
        super().__init__(title=title)
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(400, -1)
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


class RenameDialog(_BaseDialog):
    __gtype_name__ = "FileToolsRenameDialog"

    def __init__(self, default_pattern=""):
        self._default_pattern = default_pattern
        super().__init__(title=T["enum_rename"])

    def _build(self, body):
        body.append(self._section(T["pattern_label"]))
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text(T["pattern_hint"])
        self._entry.set_text(self._default_pattern)
        self._entry.set_activates_default(True)
        body.append(self._entry)

        body.append(self._section(T["start_label"]))
        self._start = self._spin(0, 99999, 1, 1)
        body.append(self._start)

    def _values(self):
        pattern = self._entry.get_text().strip()
        if "#" not in pattern:
            _show_message(T["err_hash"])
            return None
        return {"pattern": pattern, "start": int(self._start.get_value())}


class SymlinkDialog(_BaseDialog):
    __gtype_name__ = "FileToolsSymlinkDialog"

    def __init__(self, default_link=""):
        self._default_link = default_link
        super().__init__(title=T["symlink"])

    def _build(self, body):
        body.append(self._section(T["dest_label"]))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._dest = Gtk.Entry()
        self._dest.set_placeholder_text(T["dest_hint"])
        self._dest.set_hexpand(True)
        row.append(self._dest)
        btn = Gtk.Button(label=T["browse"])
        btn.connect("clicked", self._on_browse)
        row.append(btn)
        body.append(row)

        body.append(self._section(T["link_label"]))
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text(T["link_hint"])
        self._entry.set_text(self._default_link)
        self._entry.set_activates_default(True)
        body.append(self._entry)

    def _on_browse(self, _btn):
        dlg = Gtk.FileDialog(title=T["symlink"])
        try:
            cur = self._dest.get_text().strip()
            if cur and os.path.isdir(cur):
                dlg.set_initial_folder(Gio.File.new_for_path(cur))
        except Exception:  # noqa: BLE001
            pass
        dlg.select_folder(_nautilus_window(), None, self._on_folder_done)

    def _on_folder_done(self, dlg, result):
        try:
            folder = dlg.select_folder_finish(result)
            if folder is not None:
                self._dest.set_text(folder.get_path() or "")
        except Exception:  # noqa: BLE001
            pass

    def _values(self):
        dest = self._dest.get_text().strip()
        if not dest or not os.path.isdir(dest):
            _show_message(T["err_no_dest"])
            return None
        name = self._entry.get_text().strip() or self._default_link
        if not name:
            return None
        return {"dest": dest, "name": name}


# ---------------------------------------------------------------------------
# Nautilus extension with root context menu items
# ---------------------------------------------------------------------------

class FileToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "FileToolsExtension"

    def _add(self, items, name, label, cb, paths):
        item = Nautilus.MenuItem(
            name="FileTools::{0}".format(name),
            label=label,
            tip=label,
        )
        item.connect("activate", cb, paths)
        items.append(item)

    def get_file_items(self, files):
        paths = _paths_from_files(files)
        if not paths:
            return []

        items = []
        self._add(items, "FriendlyName",  T["friendly_name"],  self._cb_friendly, paths)
        self._add(items, "CopyPath",      T["copy_path"],      self._cb_copy_path, paths)
        self._add(items, "EnumRename",    T["enum_rename"],    self._cb_enum_rename, paths)

        if all(os.path.isdir(p) for p in paths):
            self._add(items, "CleanEmpty",    T["clean_empty"],    self._cb_clean_empty, paths)
            self._add(items, "TimestampFolder", T["timestamp_folder"], self._cb_timestamp, paths)

        self._add(items, "Symlink",       T["symlink"],        self._cb_symlink, paths)

        if all(os.path.isfile(p) for p in paths):
            self._add(items, "ToBase64",      T["to_base64"],      self._cb_to_base64, paths)

        if all(_is_content_file(p) for p in paths):
            self._add(items, "CopyContent",   T["copy_content"],   self._cb_copy_content, paths)

        return items

    def get_background_items(self, folder):
        if folder.get_uri_scheme() != "file":
            return []
        path = folder.get_location().get_path()
        if not path:
            return []
        items = []
        self._add(items, "CleanEmpty",    T["clean_empty"],    self._cb_clean_empty, [path])
        self._add(items, "TimestampFolder", T["timestamp_folder"], self._cb_timestamp, [path])
        return items

    def _cb_friendly(self, _item, paths):
        existing, missing = [], []
        for p in paths:
            (existing if os.path.exists(p) else missing).append(p)
        _warn_missing(missing)

        renamed = 0
        for p in existing:
            d = os.path.dirname(p)
            friendly = _friendly_name(os.path.basename(p))
            if friendly == os.path.basename(p):
                continue
            try:
                os.rename(p, os.path.join(d, _unique_path(friendly)))
                renamed += 1
            except OSError as exc:
                _show_message(str(exc))
        _show_result("done_renamed", renamed)

    def _cb_copy_path(self, _item, paths):
        clip = _clipboard()
        if clip is None:
            _show_message(T["err_no_clip"])
            return
        existing, missing = [], []
        for p in paths:
            (existing if os.path.exists(p) else missing).append(p)
        _warn_missing(missing)
        if not existing:
            return
        clip.set("\n".join(existing) + "\n")
        _show_result("done_path", len(existing))

    def _cb_enum_rename(self, _item, paths):
        default = ""
        if len(paths) == 1:
            base, ext = os.path.splitext(os.path.basename(paths[0]))
            default = "{0} (#){1}".format(base, ext)
        dlg = RenameDialog(default_pattern=default)
        dlg.set_callback(
            lambda s: s is not None and self._do_enum_rename(paths, s))
        dlg.present()

    def _do_enum_rename(self, paths, s):
        existing, missing = [], []
        for p in paths:
            (existing if os.path.exists(p) else missing).append(p)
        _warn_missing(missing)

        renamed = 0
        for i, p in enumerate(existing):
            name = s["pattern"].replace("#", str(s["start"] + i))
            try:
                os.rename(p, os.path.join(os.path.dirname(p), _unique_path(name)))
                renamed += 1
            except OSError as exc:
                _show_message(str(exc))
        _show_result("done_renamed", renamed)

    def _cb_clean_empty(self, _item, paths):
        existing, missing, not_dirs = [], [], []
        for p in paths:
            if os.path.isdir(p):
                existing.append(p)
            elif os.path.exists(p):
                not_dirs.append(p)
            else:
                missing.append(p)
        _warn_missing(missing)
        if not_dirs:
            _show_message(T["err_dir_only"])
        if not existing:
            return

        removed = 0
        for target in existing:
            try:
                for root, _dirs, _files in os.walk(target, topdown=False):
                    if root == target:
                        continue
                    try:
                        os.rmdir(root)
                        removed += 1
                    except OSError:
                        pass
            except OSError:
                pass
        _show_result("done_cleaned", removed)

    def _cb_timestamp(self, _item, paths):
        rel = date.today().strftime("%Y/%m/%d")
        existing, missing, not_dirs = [], [], []
        for p in paths:
            if os.path.isdir(p):
                existing.append(p)
            elif os.path.exists(p):
                not_dirs.append(p)
            else:
                missing.append(p)
        _warn_missing(missing)
        if not_dirs:
            _show_message(T["err_dir_only"])
        if not existing:
            return

        created = 0
        for p in existing:
            try:
                os.makedirs(os.path.join(p, rel), exist_ok=True)
                created += 1
            except OSError as exc:
                _show_message(str(exc))
        _show_result("done_created", created)

    def _cb_symlink(self, _item, paths):
        default = os.path.basename(paths[0]) if paths else ""
        dlg = SymlinkDialog(default_link=default)
        dlg.set_callback(
            lambda s: s is not None
            and self._do_symlink(paths, s["dest"], s["name"]))
        dlg.present()

    def _do_symlink(self, paths, dest, name):
        existing, missing = [], []
        for p in paths:
            (existing if os.path.exists(p) else missing).append(p)
        _warn_missing(missing)

        created = 0
        for p in existing:
            dst = os.path.join(dest, _unique_path(name))
            try:
                os.symlink(p, dst)
                created += 1
            except OSError as exc:
                _show_message(str(exc))
        _show_result("done_link", created)

    def _cb_to_base64(self, _item, paths):
        existing = [p for p in paths if os.path.isfile(p)]
        _warn_missing([p for p in paths if not os.path.exists(p)])
        if not existing:
            return
        threading.Thread(target=self._do_to_base64, args=(existing,),
                         daemon=True).start()

    def _do_to_base64(self, paths):
        uris = []
        for p in paths:
            try:
                with open(p, "rb") as fh:
                    payload = base64.b64encode(fh.read()).decode("ascii")
            except OSError as exc:
                GLib.idle_add(_show_message, str(exc))
                continue
            mime, _ = mimetypes.guess_type(p)
            mime = mime or "application/octet-stream"
            uris.append("data:{0};base64,{1}".format(mime, payload))
        GLib.idle_add(self._finish_base64, uris)

    def _finish_base64(self, uris):
        if not uris:
            return
        clip = _clipboard()
        if clip is None:
            _show_message(T["err_no_clip"])
            return
        clip.set("\n".join(uris))
        _show_result("done_base64", len(uris))

    def _cb_copy_content(self, _item, paths):
        existing_txt = [p for p in paths
                        if os.path.isfile(p) and _is_text_file(p)]
        existing_img = [p for p in paths
                        if os.path.isfile(p) and _is_image_file(p)
                        and p not in existing_txt]
        _warn_missing([p for p in paths if not os.path.exists(p)])
        if existing_txt and existing_img:
            _show_message(T["err_mixed"])
            return
        if existing_img:
            if not _HAS_PIL:
                _show_message(T["err_pil"])
                return
            threading.Thread(target=self._do_copy_images, args=(existing_img,),
                             daemon=True).start()
            return
        others = [p for p in paths
                  if os.path.exists(p) and p not in existing_txt]
        if others and not existing_txt:
            _show_message(T["err_no_file"])
        if not existing_txt:
            return
        threading.Thread(target=self._do_copy_content, args=(existing_txt,),
                         daemon=True).start()

    def _do_copy_content(self, paths):
        parts = []
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except OSError as exc:
                GLib.idle_add(_show_message, str(exc))
                continue
            parts.append("==== {0} ====\n{1}\n\n".format(
                os.path.basename(p), content.rstrip()))
        GLib.idle_add(self._finish_content, parts)

    def _finish_content(self, parts):
        if not parts:
            return
        clip = _clipboard()
        if clip is None:
            _show_message(T["err_no_clip"])
            return
        clip.set("".join(parts))
        _show_result("done_content", len(parts))

    def _do_copy_images(self, paths):
        imgs = []
        for p in paths:
            try:
                im = _PILImage.open(p)
                im.load()
                imgs.append(im.convert("RGBA"))
            except Exception as exc:
                GLib.idle_add(_show_message, str(exc))
        if not imgs:
            return
        width = max(im.width for im in imgs)
        height = sum(im.height for im in imgs)
        canvas = _PILImage.new("RGBA", (width, height), (255, 255, 255, 0))
        y = 0
        for im in imgs:
            canvas.paste(im, ((width - im.width) // 2, y), im)
            y += im.height
        try:
            pixbuf = _pil_to_pixbuf(canvas)
        except Exception as exc:
            GLib.idle_add(_show_message, str(exc))
            return
        GLib.idle_add(self._finish_image_content, pixbuf, len(imgs))

    def _finish_image_content(self, pixbuf, n):
        clip = _clipboard()
        if clip is None:
            _show_message(T["err_no_clip"])
            return
        try:
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception as exc:
            _show_message(str(exc))
            return
        clip.set_texture(texture)
        _show_result("done_content_img", n)