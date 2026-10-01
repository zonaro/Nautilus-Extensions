#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Clone Repository – Nautilus Python Extension
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
# NAME: Clone Repository – Nautilus Python Extension
# DESC: Clone a git repository into the current folder (dialog with
#       clipboard auto-paste and optional `gh` autocomplete)
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-gtk-4.0,
#           gir1.2-adw-1, git (gh CLI optional, for autocomplete only)
# INSTALL:
#   cp clone-repository.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

import json
import locale
import os
import re
import shutil
import subprocess
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Gdk, GLib, Gio, Nautilus

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label":   "Cloner le dépôt…",
        "dialog_title": "Cloner un dépôt git",
        "url_label":    "URL du dépôt",
        "url_hint":     "ex. : https://github.com/utilisateur/depot.git",
        "clone":        "Cloner",
        "cancel":       "Annuler",
        "cloning":      "Clonage en cours…",
        "done":         "Dépôt cloné : {name}",
        "err_invalid":  "URL de dépôt git invalide.",
        "err_no_git":   "git est requis (paquet « git »).",
        "err_no_dest":  "Dossier de destination introuvable.",
        "err_failed":   "Échec du clonage :\n{detail}",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":   "Repository klonen…",
        "dialog_title": "Git-Repository klonen",
        "url_label":    "Repository-URL",
        "url_hint":     "z. B. https://github.com/benutzer/repo.git",
        "clone":        "Klonen",
        "cancel":       "Abbrechen",
        "cloning":      "Wird geklont…",
        "done":         "Repository geklont: {name}",
        "err_invalid":  "Ungültige Git-Repository-URL.",
        "err_no_git":   "git wird benötigt (Paket „git“).",
        "err_no_dest":  "Zielordner nicht gefunden.",
        "err_failed":   "Klonen fehlgeschlagen:\n{detail}",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":   "Clonar repositorio…",
        "dialog_title": "Clonar un repositorio git",
        "url_label":    "URL del repositorio",
        "url_hint":     "ej.: https://github.com/usuario/repo.git",
        "clone":        "Clonar",
        "cancel":       "Cancelar",
        "cloning":      "Clonando…",
        "done":         "Repositorio clonado: {name}",
        "err_invalid":  "URL de repositorio git no válida.",
        "err_no_git":   "Se requiere git (paquete «git»).",
        "err_no_dest":  "Carpeta de destino no encontrada.",
        "err_failed":   "Error al clonar:\n{detail}",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":   "Clonar repositório…",
        "dialog_title": "Clonar um repositório git",
        "url_label":    "URL do repositório",
        "url_hint":     "ex.: https://github.com/usuario/repo.git",
        "clone":        "Clonar",
        "cancel":       "Cancelar",
        "cloning":      "Clonando…",
        "done":         "Repositório clonado: {name}",
        "err_invalid":  "URL de repositório git inválida.",
        "err_no_git":   "git é necessário (pacote «git»).",
        "err_no_dest":  "Pasta de destino não encontrada.",
        "err_failed":   "Falha ao clonar:\n{detail}",
    }
else:
    T = {
        "menu_label":   "Clone Repository…",
        "dialog_title": "Clone a git repository",
        "url_label":    "Repository URL",
        "url_hint":     "e.g. https://github.com/user/repo.git",
        "clone":        "Clone",
        "cancel":       "Cancel",
        "cloning":      "Cloning…",
        "done":         "Repository cloned: {name}",
        "err_invalid":  "Invalid git repository URL.",
        "err_no_git":   "git is required (package «git»).",
        "err_no_dest":  "Destination folder not found.",
        "err_failed":   "Clone failed:\n{detail}",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^(https?://|ssh://|git://|ftp://)\S+$", re.IGNORECASE)
_SCP_RE = re.compile(r"^[\w.\-]+@[\w.\-]+:.+$")
_SHORTHAND_RE = re.compile(r"^[\w.\-]+/[\w.\-]+(/[\w.\-]+)*$")


def _is_git_url(text: str) -> bool:
    s = (text or "").strip().strip("\"'")
    if not s or any(c.isspace() for c in s):
        return False
    if _URL_RE.match(s):
        return "." in s and ("/" in s or s.endswith(".git"))
    if _SCP_RE.match(s):
        return True
    if _SHORTHAND_RE.match(s):
        return True
    return False


def _normalize_url(text: str) -> str:
    s = (text or "").strip().strip("\"'")
    if _SHORTHAND_RE.match(s) and "://" not in s and "@" not in s:
        if not s.endswith(".git"):
            s += ".git"
        return "https://github.com/" + s
    return s


def _repo_dir_name(url: str) -> str:
    s = url.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    s = s.split("?")[0].split("#")[0]
    for sep in ("/", ":"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
    return s.strip()


_GH_CACHE = {"repos": None}


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _fetch_gh_repos():
    """Return [{label, url}] from `gh repo list`, [] when unavailable.

    Never raises: `gh` missing / not authenticated / offline silently
    disables autocomplete.
    """
    if _GH_CACHE["repos"] is not None:
        return _GH_CACHE["repos"]
    repos = []
    if _gh_available():
        try:
            proc = subprocess.run(
                ["gh", "repo", "list", "--limit", "100",
                 "--json", "nameWithOwner,url"],
                capture_output=True, text=True, timeout=15)
            if proc.returncode == 0 and proc.stdout.strip():
                for item in json.loads(proc.stdout):
                    label = item.get("nameWithOwner", "")
                    url = item.get("url", "")
                    if label:
                        repos.append({"label": label, "url": url or label})
        except Exception:  # noqa: BLE001 - autocomplete is best-effort
            repos = []
    repos.sort(key=lambda r: r["label"].lower())
    _GH_CACHE["repos"] = repos
    return repos


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
# Dialogs
# ---------------------------------------------------------------------------

class CloneDialog(Adw.Window):
    __gtype_name__ = "CloneRepositoryDialog"

    def __init__(self):
        super().__init__(title=T["dialog_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(460, -1)
        self._callback = None
        self._repos = []

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(16)
        body.set_margin_bottom(16)
        body.set_margin_start(18)
        body.set_margin_end(18)

        lbl = Gtk.Label(label="<b>{0}</b>".format(T["url_label"]))
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        body.append(lbl)

        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text(T["url_hint"])
        self._entry.set_hexpand(True)
        self._entry.set_activates_default(True)
        self._entry.connect("changed", self._on_changed)
        self._entry.connect("activate", lambda _: self._apply())
        body.append(self._entry)

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_min_content_height(40)
        self._scroll.set_max_content_height(180)
        self._scroll.set_propagate_natural_height(True)
        self._scroll.set_visible(False)
        self._list = Gtk.ListBox()
        self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list.connect("row-activated", self._on_row_activated)
        self._scroll.set_child(self._list)
        body.append(self._scroll)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", lambda _: self._dismiss())
        btn_box.append(cancel_btn)
        ok_btn = Gtk.Button(label=T["clone"])
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _: self._apply())
        btn_box.append(ok_btn)
        body.append(btn_box)

        tv.set_content(body)
        self.set_content(tv)

        self._autopaste_clipboard()
        threading.Thread(target=self._load_gh_repos, daemon=True).start()

    def set_callback(self, cb):
        self._callback = cb

    # -- clipboard auto-paste -------------------------------------------
    def _autopaste_clipboard(self):
        try:
            display = Gdk.Display.get_default()
            if display is None:
                return
            display.get_clipboard().read_text_async(None, self._on_clip, None)
        except Exception:  # noqa: BLE001 - silently ignore
            pass

    def _on_clip(self, clipboard, result, _data):
        try:
            text = clipboard.read_text_finish(result)
        except Exception:  # noqa: BLE001
            return
        if text and _is_git_url(text) and not self._entry.get_text().strip():
            GLib.idle_add(self._entry.set_text, text.strip())

    # -- gh autocomplete (silently disabled when `gh` is missing) -------
    def _load_gh_repos(self):
        repos = _fetch_gh_repos()
        GLib.idle_add(self._store_repos, repos)

    def _store_repos(self, repos):
        self._repos = repos
        self._on_changed(self._entry)
        return False

    def _on_changed(self, _entry):
        query = self._entry.get_text().strip().lower()
        while (row := self._list.get_row_at_index(0)) is not None:
            self._list.remove(row)
        if not query or not self._repos:
            self._scroll.set_visible(False)
            return
        shown = 0
        for repo in self._repos:
            if query in repo["label"].lower() or query in repo["url"].lower():
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                box.set_margin_top(4)
                box.set_margin_bottom(4)
                box.set_margin_start(8)
                box.set_margin_end(8)
                name_lbl = Gtk.Label(label=repo["label"])
                name_lbl.set_halign(Gtk.Align.START)
                url_lbl = Gtk.Label(label=repo["url"])
                url_lbl.set_halign(Gtk.Align.START)
                url_lbl.add_css_class("dim-label")
                box.append(name_lbl)
                box.append(url_lbl)
                row.set_child(box)
                row._repo_url = repo["url"]
                self._list.append(row)
                shown += 1
                if shown >= 8:
                    break
        self._scroll.set_visible(shown > 0)

    def _on_row_activated(self, _list, row):
        url = getattr(row, "_repo_url", "")
        if url:
            self._entry.set_text(url)
            self._entry.set_position(-1)
        self._scroll.set_visible(False)

    # -- ok / cancel -----------------------------------------------------
    def _dismiss(self):
        if self._callback:
            self._callback(None)
        self.destroy()

    def _apply(self):
        raw = self._entry.get_text().strip()
        if not _is_git_url(raw):
            _show_message(T["err_invalid"])
            return
        if self._callback:
            self._callback({"url": _normalize_url(raw)})
        self.destroy()


class _CloningWindow(Adw.Window):
    __gtype_name__ = "CloneRepositoryProgress"

    def __init__(self):
        super().__init__(title=T["dialog_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(360, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.append(Gtk.Spinner(spinning=True))
        box.append(Gtk.Label(label=T["cloning"]))
        self.set_content(box)


# ---------------------------------------------------------------------------
# Nautilus extension (background menu: clone into the current folder)
# ---------------------------------------------------------------------------

class CloneRepositoryExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "CloneRepositoryExtension"

    def _make_item(self, target_dir: str):
        item = Nautilus.MenuItem(
            name="CloneRepository::Clone",
            label=T["menu_label"],
            tip=T["dialog_title"],
        )
        item.connect("activate", self._cb_clone, target_dir)
        return item

    def get_background_items(self, folder):
        if folder.get_uri_scheme() != "file":
            return []
        path = folder.get_location().get_path()
        if not path or not os.path.isdir(path):
            return []
        return [self._make_item(path)]

    def get_file_items(self, files):
        paths = _paths_from_files(files)
        if len(paths) == 1 and os.path.isdir(paths[0]):
            return [self._make_item(paths[0])]
        return []

    def _cb_clone(self, _item, target_dir: str):
        if shutil.which("git") is None:
            _show_message(T["err_no_git"])
            return
        if not os.path.isdir(target_dir):
            _show_message(T["err_no_dest"])
            return
        dlg = CloneDialog()
        dlg.set_callback(
            lambda s: s is not None and self._do_clone(target_dir, s["url"]))
        dlg.present()

    def _do_clone(self, target_dir: str, url: str):
        progress = _CloningWindow()
        progress.present()
        threading.Thread(
            target=self._clone_thread,
            args=(target_dir, url, progress), daemon=True).start()

    def _clone_thread(self, target_dir: str, url: str, progress):
        try:
            proc = subprocess.run(
                ["git", "clone", "--progress", url],
                cwd=target_dir, capture_output=True, text=True, timeout=600)
            detail = (proc.stderr or proc.stdout or "").strip()
        except Exception as exc:  # noqa: BLE001
            proc = None
            detail = str(exc)
        GLib.idle_add(self._finish_clone, progress, proc, detail, url)

    def _finish_clone(self, progress, proc, detail: str, url: str):
        try:
            progress.destroy()
        except Exception:  # noqa: BLE001
            pass
        if proc is not None and proc.returncode == 0:
            name = _repo_dir_name(url) or url
            _show_message(T["done"].format(name=name))
        else:
            tail = "\n".join(detail.splitlines()[-8:]) if detail else url
            _show_message(T["err_failed"].format(detail=tail))
        return False
