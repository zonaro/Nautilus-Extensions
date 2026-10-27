#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Move and Symlink – Nautilus Python Extension
# AUTHOR: Kaizonaro
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
# NAME: Move and Symlink
# DESC: Moves the selected files and folders to a destination folder and
#       leaves a symlink behind at each original path. Absolute links by
#       default, relative links on request, and never overwrites an existing
#       name (a -1, -2, ... suffix is used instead).
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-adw-1
# INSTALL:
#   cp move-and-symlink.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

import locale
import os
import shutil

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Gio, GLib, Nautilus

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
try:
    from nautilus_i18n import resolve_locale
except ImportError:  # nautilus_i18n.py not installed next to this file
    def resolve_locale():
        return locale.getlocale()[0] or ""

_lang = resolve_locale()

if _lang.startswith("fr"):
    T = {
        "menu_label":  "Déplacer et créer un lien symbolique…",
        "ok":          "Appliquer",
        "cancel":      "Annuler",
        "dest_label":  "Dossier de destination",
        "dest_hint":   "/chemin/vers/destination",
        "browse":      "Choisir…",
        "relative":    "Lien relatif",
        "done":        "{n} élément(s) déplacé(s) et lié(s).",
        "err_no_dest": "Choisissez un dossier de destination valide.",
        "re_symlink":  "déjà un lien symbolique",
        "re_same_dir": "déjà dans ce dossier",
        "re_inside":   "la destination se trouve à l'intérieur de la source",
        "re_missing":  "source introuvable",
        "re_move":     "échec du déplacement : {error}",
        "re_link":     "échec de la création du lien : {error}",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":  "Verschieben und symbolischen Link erstellen…",
        "ok":          "Anwenden",
        "cancel":      "Abbrechen",
        "dest_label":  "Zielordner",
        "dest_hint":   "/pfad/zum/ziel",
        "browse":      "Wählen…",
        "relative":    "Relativer Link",
        "done":        "{n} Element(e) verschoben und verlinkt.",
        "err_no_dest": "Bitte wählen Sie einen gültigen Zielordner.",
        "re_symlink":  "bereits ein symbolischer Link",
        "re_same_dir": "bereits in diesem Ordner",
        "re_inside":   "Das Ziel liegt innerhalb der Quelle",
        "re_missing":  "Quelle nicht gefunden",
        "re_move":     "Verschieben fehlgeschlagen: {error}",
        "re_link":     "Link konnte nicht erstellt werden: {error}",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":  "Mover y crear enlace simbólico…",
        "ok":          "Aplicar",
        "cancel":      "Cancelar",
        "dest_label":  "Carpeta de destino",
        "dest_hint":   "/ruta/al/destino",
        "browse":      "Elegir…",
        "relative":    "Enlace relativo",
        "done":        "{n} elemento(s) movido(s) y vinculado(s).",
        "err_no_dest": "Elija una carpeta de destino válida.",
        "re_symlink":  "ya es un enlace simbólico",
        "re_same_dir": "ya está en esta carpeta",
        "re_inside":   "el destino está dentro de la carpeta de origen",
        "re_missing":  "origen no encontrado",
        "re_move":     "no se pudo mover: {error}",
        "re_link":     "no se pudo crear el enlace: {error}",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":  "Mover e criar link simbólico…",
        "ok":          "Aplicar",
        "cancel":      "Cancelar",
        "dest_label":  "Pasta de destino",
        "dest_hint":   "/caminho/para/destino",
        "browse":      "Escolher…",
        "relative":    "Link relativo",
        "done":        "{n} item(ns) movido(s) e vinculado(s).",
        "err_no_dest": "Escolha uma pasta de destino válida.",
        "re_symlink":  "já é um link simbólico",
        "re_same_dir": "já está nessa pasta",
        "re_inside":   "o destino está dentro da pasta de origem",
        "re_missing":  "origem não encontrada",
        "re_move":     "falha ao mover: {error}",
        "re_link":     "falha ao criar o link: {error}",
    }
else:
    T = {
        "menu_label":  "Move and create symlink…",
        "ok":          "Apply",
        "cancel":      "Cancel",
        "dest_label":  "Destination folder",
        "dest_hint":   "/path/to/destination",
        "browse":      "Browse…",
        "relative":    "Relative link",
        "done":        "{n} item(s) moved and linked.",
        "err_no_dest": "Please choose a valid destination folder.",
        "re_symlink":  "already a symlink",
        "re_same_dir": "already in this folder",
        "re_inside":   "destination is inside the source folder",
        "re_missing":  "source not found",
        "re_move":     "move failed: {error}",
        "re_link":     "symlink failed: {error}",
    }


# ---------------------------------------------------------------------------
# Nautilus / GTK helpers
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


# ---------------------------------------------------------------------------
# Pure move/symlink logic (no display needed, covered by unit tests)
# ---------------------------------------------------------------------------

class PlanError(Exception):
    """One item cannot be planned; ``reason`` is a key of ``T``."""

    def __init__(self, reason, **fmt):
        super().__init__(reason)
        self.reason = reason
        self.fmt = fmt

    def message(self):
        return T[self.reason].format(**self.fmt)


def _unique_path(path: str) -> str:
    """Return ``path`` or the first free ``-1``, ``-2``, ... variant."""
    if not os.path.exists(path) and not os.path.islink(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = "{0}-{1}{2}".format(base, i, ext)
        if not os.path.exists(cand) and not os.path.islink(cand):
            return cand
        i += 1


def _same_or_inside(path: str, parent: str) -> bool:
    """True when ``path`` is ``parent`` or lies below it (realpath based)."""
    path_r = os.path.realpath(path)
    parent_r = os.path.realpath(parent)
    if path_r == parent_r:
        return True
    return path_r.startswith(parent_r.rstrip(os.sep) + os.sep)


def _relative_link(target: str, link_path: str) -> str:
    """Return the link value that points to ``target`` from ``link_path``."""
    return os.path.relpath(target, os.path.dirname(os.path.abspath(link_path)))


def _plan_move(src: str, dest_dir: str, relative: bool = False):
    """Plan one move.

    Returns ``(target_path, link_target)``: the final location of the item and
    the value to write into the symlink created at ``src``. Raises
    ``PlanError`` carrying a ``T`` reason key when the item must be skipped.
    """
    if os.path.islink(src):
        raise PlanError("re_symlink")
    if not os.path.lexists(src):
        raise PlanError("re_missing")
    if not dest_dir or not os.path.isdir(dest_dir):
        raise PlanError("err_no_dest")

    dest_dir = os.path.abspath(dest_dir)
    src = os.path.abspath(src)

    if os.path.realpath(os.path.dirname(src)) == os.path.realpath(dest_dir):
        raise PlanError("re_same_dir")
    if os.path.isdir(src) and _same_or_inside(dest_dir, src):
        raise PlanError("re_inside")

    target = _unique_path(os.path.join(dest_dir, os.path.basename(src)))
    link_target = _relative_link(target, src) if relative else target
    return target, link_target


def _apply_move(src: str, dest_dir: str, relative: bool = False):
    """Move one item and leave a symlink behind.

    Returns ``None`` on success or a human-readable reason on failure. A
    failed move never leaves the item relocated without its link: the move is
    rolled back when creating the symlink fails.
    """
    try:
        target, link_target = _plan_move(src, dest_dir, relative)
    except PlanError as exc:
        return exc.message()

    try:
        shutil.move(src, target)
    except Exception as exc:  # noqa: BLE001 - report and keep going
        return T["re_move"].format(error=exc)

    try:
        os.symlink(link_target, src)
    except Exception as exc:  # noqa: BLE001 - report and keep going
        try:
            shutil.move(target, src)
        except Exception:  # noqa: BLE001 - best-effort rollback
            pass
        return T["re_link"].format(error=exc)
    return None


def _run_move(paths, dest_dir: str, relative: bool = False):
    """Move every path; return ``(moved_count, ["name — reason", ...])``."""
    moved = 0
    failures = []
    for src in paths:
        reason = _apply_move(src, dest_dir, relative)
        if reason is None:
            moved += 1
        else:
            name = os.path.basename(os.path.normpath(src)) or src
            failures.append("{0} — {1}".format(name, reason))
    return moved, failures


# ---------------------------------------------------------------------------
# Dialog
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

    def present(self):
        # Wayland: presenting synchronously from a menu-activate handler leaves
        # pointer events stuck on the dying Nautilus menu, so the popup shows up
        # with dead buttons. One idle turn lets the menu dismiss first.
        GLib.idle_add(super().present)

    def _section(self, text):
        lbl = Gtk.Label(label="<b>{0}</b>".format(text))
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        return lbl

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


class MoveSymlinkDialog(_BaseDialog):
    __gtype_name__ = "MoveAndSymlinkDialog"

    def __init__(self):
        super().__init__(title=T["menu_label"])

    def _build(self, body):
        body.append(self._section(T["dest_label"]))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._dest = Gtk.Entry()
        self._dest.set_placeholder_text(T["dest_hint"])
        self._dest.set_hexpand(True)
        self._dest.set_activates_default(True)
        row.append(self._dest)
        btn = Gtk.Button(label=T["browse"])
        btn.connect("clicked", self._on_browse)
        row.append(btn)
        body.append(row)

        self._relative = Gtk.CheckButton(label=T["relative"])
        self._relative.set_active(False)
        body.append(self._relative)

    def _on_browse(self, _btn):
        dlg = Gtk.FileDialog(title=T["menu_label"])
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
        return {"dest": dest, "relative": self._relative.get_active()}


# ---------------------------------------------------------------------------
# Nautilus extension
# ---------------------------------------------------------------------------

class MoveAndSymlinkExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "MoveAndSymlinkExtension"

    def get_file_items(self, files):
        paths = _paths_from_files(files)
        if not paths:
            return []

        item = Nautilus.MenuItem(
            name="MoveAndSymlink::MoveSymlink",
            label=T["menu_label"],
            tip=T["menu_label"],
        )
        item.connect("activate", self._cb_move, paths)
        return [item]

    def _cb_move(self, _item, paths):
        dlg = MoveSymlinkDialog()
        dlg.set_callback(lambda vals: self._apply(paths, vals))
        dlg.present()

    def _apply(self, paths, vals):
        if vals is None:
            return
        moved, failures = _run_move(paths, vals["dest"], vals["relative"])
        message = T["done"].format(n=moved)
        if failures:
            Gtk.AlertDialog(
                message=message,
                detail="\n".join(failures),
            ).show(_nautilus_window())
        else:
            _show_message(message)
