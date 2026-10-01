#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Clone Repository – Nautilus Python Extension
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
# NAME: Clone Repository – Nautilus Python Extension
# DESC: Clone a git repository into the current folder (dialog with
#       clipboard auto-paste and optional `gh` autocomplete); inside an
#       existing repository the clone entry is hidden and a Git submenu
#       offers Pull/Push/Fetch/Status/Log/Commit/Branch/Stash
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
        "git_menu":     "Git",
        "pull":         "Pull",
        "push":         "Push",
        "fetch":        "Fetch",
        "status":       "État",
        "log":          "Journal",
        "commit":       "Commiter…",
        "commit_ok":    "Commiter",
        "branch":       "Branche…",
        "stash":        "Stash",
        "stash_pop":    "Stash Pop",
        "running":      "Exécution…",
        "close":        "Fermer",
        "done_ok":      "Terminé.",
        "current":      "(actuelle)",
        "clean_tree":   "Arborescence propre, rien à commiter.",
        "err_git":      "La commande git a échoué :\n{detail}",
        "commit_title": "Commiter les changements",
        "commit_msg":   "Message de commit",
        "commit_hint":  "ex. : corrige le bug de connexion",
        "commit_stage": "Indexer toutes les modifications (git add -A)",
        "err_no_msg":   "Le message de commit ne peut pas être vide.",
        "commit_done":  "Commit créé.",
        "branch_title": "Branches",
        "branch_new":   "Nouvelle branche…",
        "branch_hint":  "ex. : ma-fonctionnalité",
        "branch_create": "Créer et basculer",
        "branch_done":  "Basculé sur « {name} ».",
        "stash_done":   "Modifications remisées.",
        "stash_pop_done": "Stash appliqué.",
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
        "git_menu":     "Git",
        "pull":         "Pull",
        "push":         "Push",
        "fetch":        "Fetch",
        "status":       "Status",
        "log":          "Verlauf",
        "commit":       "Committen…",
        "commit_ok":    "Committen",
        "branch":       "Branch…",
        "stash":        "Stash",
        "stash_pop":    "Stash Pop",
        "running":      "Läuft…",
        "close":        "Schließen",
        "done_ok":      "Fertig.",
        "current":      "(aktuell)",
        "clean_tree":   "Arbeitsbaum sauber, nichts zu committen.",
        "err_git":      "Git-Befehl fehlgeschlagen:\n{detail}",
        "commit_title": "Änderungen committen",
        "commit_msg":   "Commit-Nachricht",
        "commit_hint":  "z. B. Login-Fehler behoben",
        "commit_stage": "Alle Änderungen stagen (git add -A)",
        "err_no_msg":   "Die Commit-Nachricht darf nicht leer sein.",
        "commit_done":  "Commit erstellt.",
        "branch_title": "Branches",
        "branch_new":   "Neuer Branch…",
        "branch_hint":  "z. B. mein-feature",
        "branch_create": "Erstellen & wechseln",
        "branch_done":  "Zu „{name}“ gewechselt.",
        "stash_done":   "Änderungen gestasht.",
        "stash_pop_done": "Stash angewendet.",
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
        "git_menu":     "Git",
        "pull":         "Pull",
        "push":         "Push",
        "fetch":        "Fetch",
        "status":       "Estado",
        "log":          "Historial",
        "commit":       "Hacer commit…",
        "commit_ok":    "Confirmar",
        "branch":       "Rama…",
        "stash":        "Stash",
        "stash_pop":    "Stash Pop",
        "running":      "Ejecutando…",
        "close":        "Cerrar",
        "done_ok":      "Hecho.",
        "current":      "(actual)",
        "clean_tree":   "Árbol limpio, nada que confirmar.",
        "err_git":      "El comando git falló:\n{detail}",
        "commit_title": "Confirmar cambios",
        "commit_msg":   "Mensaje del commit",
        "commit_hint":  "ej.: corrige el error de acceso",
        "commit_stage": "Añadir todos los cambios (git add -A)",
        "err_no_msg":   "El mensaje no puede estar vacío.",
        "commit_done":  "Commit creado.",
        "branch_title": "Ramas",
        "branch_new":   "Nueva rama…",
        "branch_hint":  "ej.: mi-funcionalidad",
        "branch_create": "Crear y cambiar",
        "branch_done":  "Cambiado a «{name}».",
        "stash_done":   "Cambios guardados en el stash.",
        "stash_pop_done": "Stash aplicado.",
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
        "git_menu":     "Git",
        "pull":         "Pull",
        "push":         "Push",
        "fetch":        "Fetch",
        "status":       "Status",
        "log":          "Histórico",
        "commit":       "Commitar…",
        "commit_ok":    "Commitar",
        "branch":       "Branch…",
        "stash":        "Stash",
        "stash_pop":    "Stash Pop",
        "running":      "Executando…",
        "close":        "Fechar",
        "done_ok":      "Concluído.",
        "current":      "(atual)",
        "clean_tree":   "Árvore limpa, nada a commitar.",
        "err_git":      "Comando git falhou:\n{detail}",
        "commit_title": "Commitar alterações",
        "commit_msg":   "Mensagem do commit",
        "commit_hint":  "ex.: corrige o bug de login",
        "commit_stage": "Adicionar todas as alterações (git add -A)",
        "err_no_msg":   "A mensagem não pode estar vazia.",
        "commit_done":  "Commit criado.",
        "branch_title": "Branches",
        "branch_new":   "Nova branch…",
        "branch_hint":  "ex.: minha-funcionalidade",
        "branch_create": "Criar e trocar",
        "branch_done":  "Trocado para «{name}».",
        "stash_done":   "Alterações guardadas no stash.",
        "stash_pop_done": "Stash aplicado.",
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
        "git_menu":     "Git",
        "pull":         "Pull",
        "push":         "Push",
        "fetch":        "Fetch",
        "status":       "Status",
        "log":          "History",
        "commit":       "Commit…",
        "commit_ok":    "Commit",
        "branch":       "Branch…",
        "stash":        "Stash",
        "stash_pop":    "Stash Pop",
        "running":      "Running…",
        "close":        "Close",
        "done_ok":      "Done.",
        "current":      "(current)",
        "clean_tree":   "Working tree clean, nothing to commit.",
        "err_git":      "Git command failed:\n{detail}",
        "commit_title": "Commit changes",
        "commit_msg":   "Commit message",
        "commit_hint":  "e.g. fix login bug",
        "commit_stage": "Stage all changes (git add -A)",
        "err_no_msg":   "Commit message cannot be empty.",
        "commit_done":  "Commit created.",
        "branch_title": "Branches",
        "branch_new":   "New branch…",
        "branch_hint":  "e.g. my-feature",
        "branch_create": "Create & switch",
        "branch_done":  "Switched to “{name}”.",
        "stash_done":   "Changes stashed.",
        "stash_pop_done": "Stash applied.",
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


def _is_inside_repo(path: str) -> bool:
    if os.path.exists(os.path.join(path, ".git")):
        return True
    if shutil.which("git") is None:
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5)
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except Exception:  # noqa: BLE001
        return False


def _git_output(repo_dir: str, args, timeout=15) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_dir] + args,
        capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git error").strip())
    return (proc.stdout or "").strip()


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


class _BusyWindow(Adw.Window):
    __gtype_name__ = "CloneRepoBusyWindow"

    def __init__(self, title=None, label=None):
        super().__init__(title=title or T["dialog_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(360, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.append(Gtk.Spinner(spinning=True))
        box.append(Gtk.Label(label=label or T["cloning"]))
        self.set_content(box)


class _OutputWindow(Adw.Window):
    __gtype_name__ = "CloneRepoOutputWindow"

    def __init__(self, title, text):
        super().__init__(title=title)
        self.set_modal(False)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(560, 420)

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(12)
        body.set_margin_bottom(16)
        body.set_margin_start(16)
        body.set_margin_end(16)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(text)
        scroll.set_child(view)
        body.append(scroll)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        close_btn = Gtk.Button(label=T["close"])
        close_btn.add_css_class("suggested-action")
        close_btn.connect("clicked", lambda _: self.destroy())
        btn_box.append(close_btn)
        body.append(btn_box)

        tv.set_content(body)
        self.set_content(tv)


class CommitDialog(Adw.Window):
    __gtype_name__ = "CloneRepoCommitDialog"

    def __init__(self):
        super().__init__(title=T["commit_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(440, -1)
        self._callback = None

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(16)
        body.set_margin_bottom(16)
        body.set_margin_start(18)
        body.set_margin_end(18)

        lbl = Gtk.Label(label="<b>{0}</b>".format(T["commit_msg"]))
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        body.append(lbl)

        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text(T["commit_hint"])
        self._entry.set_hexpand(True)
        self._entry.set_activates_default(True)
        self._entry.connect("activate", lambda _: self._apply())
        body.append(self._entry)

        self._stage = Gtk.CheckButton(label=T["commit_stage"])
        self._stage.set_active(True)
        body.append(self._stage)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", lambda _: self._dismiss())
        btn_box.append(cancel_btn)
        ok_btn = Gtk.Button(label=T["commit_ok"])
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _: self._apply())
        btn_box.append(ok_btn)
        body.append(btn_box)

        tv.set_content(body)
        self.set_content(tv)

    def set_callback(self, cb):
        self._callback = cb

    def _dismiss(self):
        if self._callback:
            self._callback(None)
        self.destroy()

    def _apply(self):
        msg = self._entry.get_text().strip()
        if not msg:
            _show_message(T["err_no_msg"])
            return
        if self._callback:
            self._callback({"message": msg, "stage": self._stage.get_active()})
        self.destroy()


class BranchDialog(Adw.Window):
    __gtype_name__ = "CloneRepoBranchDialog"

    def __init__(self, repo_dir: str):
        super().__init__(title=T["branch_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(420, 400)
        self._repo_dir = repo_dir
        self._callback = None

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(16)
        body.set_margin_bottom(16)
        body.set_margin_start(18)
        body.set_margin_end(18)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(160)
        self._list = Gtk.ListBox()
        self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list.connect("row-activated", self._on_row_activated)
        scroll.set_child(self._list)
        body.append(scroll)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text(T["branch_hint"])
        self._entry.set_hexpand(True)
        self._entry.set_activates_default(True)
        self._entry.connect("activate", lambda _: self._create())
        row.append(self._entry)
        create_btn = Gtk.Button(label=T["branch_create"])
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", lambda _: self._create())
        row.append(create_btn)
        body.append(row)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", lambda _: self.destroy())
        btn_box.append(cancel_btn)
        body.append(btn_box)

        tv.set_content(body)
        self.set_content(tv)

        threading.Thread(target=self._load_branches, daemon=True).start()

    def set_callback(self, cb):
        self._callback = cb

    def _load_branches(self):
        try:
            current = _git_output(self._repo_dir, ["branch", "--show-current"])
        except Exception:  # noqa: BLE001
            current = ""
        try:
            raw = _git_output(self._repo_dir, ["branch", "--format=%(refname:short)"])
            branches = [b.strip() for b in raw.splitlines() if b.strip()]
        except Exception:  # noqa: BLE001
            branches = []
        GLib.idle_add(self._fill, branches, current)

    def _fill(self, branches, current):
        for name in branches:
            row = Gtk.ListBoxRow()
            label = name + (" " + T["current"] if name == current else "")
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_top(6)
            lbl.set_margin_bottom(6)
            lbl.set_margin_start(10)
            lbl.set_margin_end(10)
            row.set_child(lbl)
            row._branch_name = name
            self._list.append(row)
        return False

    def _on_row_activated(self, _list, row):
        name = getattr(row, "_branch_name", "")
        if name and self._callback:
            self._callback({"name": name, "create": False})
        self.destroy()

    def _create(self):
        name = self._entry.get_text().strip()
        if not name:
            return
        if self._callback:
            self._callback({"name": name, "create": True})
        self.destroy()


# ---------------------------------------------------------------------------
# Nautilus extension
#
# Plain folder  -> "Clone Repository…" (clone into it).
# Git repository -> "Git" submenu with everyday operations; the clone entry
#                   is hidden because the folder already is a repository.
# ---------------------------------------------------------------------------

class CloneRepositoryExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "CloneRepositoryExtension"

    def _make_clone_item(self, target_dir: str):
        item = Nautilus.MenuItem(
            name="CloneRepository::Clone",
            label=T["menu_label"],
            tip=T["dialog_title"],
        )
        item.connect("activate", self._cb_clone, target_dir)
        return item

    def _make_git_menu(self, repo_dir: str):
        top = Nautilus.MenuItem(
            name="CloneRepository::Git",
            label=T["git_menu"],
            tip=T["git_menu"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)
        self._op(submenu, "Pull", T["pull"], self._cb_pull, repo_dir)
        self._op(submenu, "Push", T["push"], self._cb_push, repo_dir)
        self._op(submenu, "Fetch", T["fetch"], self._cb_fetch, repo_dir)
        self._op(submenu, "Status", T["status"], self._cb_status, repo_dir)
        self._op(submenu, "Log", T["log"], self._cb_log, repo_dir)
        self._op(submenu, "Commit", T["commit"], self._cb_commit, repo_dir)
        self._op(submenu, "Branch", T["branch"], self._cb_branch, repo_dir)
        self._op(submenu, "Stash", T["stash"], self._cb_stash, repo_dir)
        self._op(submenu, "StashPop", T["stash_pop"], self._cb_stash_pop,
                  repo_dir)
        return top

    def _op(self, submenu, name, label, cb, repo_dir):
        item = Nautilus.MenuItem(
            name="CloneRepository::Git{0}".format(name),
            label=label,
            tip=label,
        )
        item.connect("activate", cb, repo_dir)
        submenu.append_item(item)

    def get_background_items(self, folder):
        if folder.get_uri_scheme() != "file":
            return []
        path = folder.get_location().get_path()
        if not path or not os.path.isdir(path):
            return []
        if _is_inside_repo(path):
            return [self._make_git_menu(path)]
        return [self._make_clone_item(path)]

    def get_file_items(self, files):
        paths = _paths_from_files(files)
        if len(paths) == 1 and os.path.isdir(paths[0]):
            if _is_inside_repo(paths[0]):
                return [self._make_git_menu(paths[0])]
            return [self._make_clone_item(paths[0])]
        return []

    def _need_git(self) -> bool:
        if shutil.which("git") is None:
            _show_message(T["err_no_git"])
            return False
        return True

    # -- clone ----------------------------------------------------------
    def _cb_clone(self, _item, target_dir: str):
        if not self._need_git():
            return
        if not os.path.isdir(target_dir):
            _show_message(T["err_no_dest"])
            return
        dlg = CloneDialog()
        dlg.set_callback(
            lambda s: s is not None and self._do_clone(target_dir, s["url"]))
        dlg.present()

    def _do_clone(self, target_dir: str, url: str):
        progress = _BusyWindow(T["dialog_title"], T["cloning"])
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

    # -- generic git runner ---------------------------------------------
    def _run_git(self, repo_dir: str, args, title: str,
                 success=None, show_output=False, empty_fallback=None):
        busy = _BusyWindow(title, T["running"])
        busy.present()
        threading.Thread(
            target=self._git_thread,
            args=(repo_dir, args, busy, title,
                  success, show_output, empty_fallback),
            daemon=True).start()

    def _git_thread(self, repo_dir, args, busy, title,
                    success, show_output, empty_fallback):
        try:
            proc = subprocess.run(
                ["git", "-C", repo_dir] + args,
                capture_output=True, text=True, timeout=300)
            out = ((proc.stdout or "")
                   + ("\n" + proc.stderr if proc.stderr else "")).strip()
            ok = proc.returncode == 0
        except Exception as exc:  # noqa: BLE001
            ok, out = False, str(exc)
        GLib.idle_add(self._finish_git, busy, ok, out, title,
                      success, show_output, empty_fallback)

    def _finish_git(self, busy, ok: bool, out: str, title: str,
                    success, show_output: bool, empty_fallback):
        try:
            busy.destroy()
        except Exception:  # noqa: BLE001
            pass
        if ok:
            if show_output:
                _OutputWindow(title, out or empty_fallback
                              or T["done_ok"]).present()
            elif success:
                _show_message(success)
        else:
            tail = "\n".join(out.splitlines()[-12:]) if out else ""
            _show_message(T["err_git"].format(detail=tail))
        return False

    # -- everyday operations --------------------------------------------
    def _cb_pull(self, _item, repo_dir: str):
        if not self._need_git():
            return
        self._run_git(repo_dir, ["pull"], T["pull"],
                      show_output=True, empty_fallback=T["done_ok"])

    def _cb_push(self, _item, repo_dir: str):
        if not self._need_git():
            return
        self._run_git(repo_dir, ["push"], T["push"],
                      show_output=True, empty_fallback=T["done_ok"])

    def _cb_fetch(self, _item, repo_dir: str):
        if not self._need_git():
            return
        self._run_git(repo_dir, ["fetch", "--prune"], T["fetch"],
                      show_output=True, empty_fallback=T["done_ok"])

    def _cb_status(self, _item, repo_dir: str):
        if not self._need_git():
            return
        self._run_git(repo_dir, ["status", "--short", "--branch"], T["status"],
                      show_output=True, empty_fallback=T["clean_tree"])

    def _cb_log(self, _item, repo_dir: str):
        if not self._need_git():
            return
        self._run_git(repo_dir,
                      ["log", "--oneline", "--graph", "--decorate", "-30"],
                      T["log"], show_output=True,
                      empty_fallback=T["done_ok"])

    def _cb_commit(self, _item, repo_dir: str):
        if not self._need_git():
            return
        dlg = CommitDialog()
        dlg.set_callback(
            lambda s: s is not None and self._do_commit(repo_dir, s))
        dlg.present()

    def _do_commit(self, repo_dir: str, s):
        busy = _BusyWindow(T["commit_title"], T["running"])
        busy.present()
        threading.Thread(
            target=self._commit_thread,
            args=(repo_dir, s["message"], s["stage"], busy),
            daemon=True).start()

    def _commit_thread(self, repo_dir, message, stage, busy):
        try:
            if stage:
                proc = subprocess.run(
                    ["git", "-C", repo_dir, "add", "-A"],
                    capture_output=True, text=True, timeout=120)
                if proc.returncode != 0:
                    raise RuntimeError(
                        (proc.stderr or proc.stdout or "").strip())
            proc = subprocess.run(
                ["git", "-C", repo_dir, "commit", "-m", message],
                capture_output=True, text=True, timeout=120)
            out = ((proc.stdout or "")
                   + ("\n" + proc.stderr if proc.stderr else "")).strip()
            ok = proc.returncode == 0
        except Exception as exc:  # noqa: BLE001
            ok, out = False, str(exc)
        GLib.idle_add(self._finish_commit, busy, ok, out)

    def _finish_commit(self, busy, ok: bool, out: str):
        try:
            busy.destroy()
        except Exception:  # noqa: BLE001
            pass
        if ok:
            _show_message(T["commit_done"])
        else:
            tail = "\n".join(out.splitlines()[-12:]) if out else ""
            _show_message(T["err_git"].format(detail=tail))
        return False

    def _cb_branch(self, _item, repo_dir: str):
        if not self._need_git():
            return
        dlg = BranchDialog(repo_dir)
        dlg.set_callback(
            lambda s: s is not None and self._do_branch(repo_dir, s))
        dlg.present()

    def _do_branch(self, repo_dir: str, s):
        args = (["checkout", "-b", s["name"]] if s["create"]
                else ["checkout", s["name"]])
        self._run_git(repo_dir, args, T["branch_title"],
                      success=T["branch_done"].format(name=s["name"]))

    def _cb_stash(self, _item, repo_dir: str):
        if not self._need_git():
            return
        self._run_git(repo_dir, ["stash", "push"], T["stash"],
                      success=T["stash_done"])

    def _cb_stash_pop(self, _item, repo_dir: str):
        if not self._need_git():
            return
        self._run_git(repo_dir, ["stash", "pop"], T["stash_pop"],
                      success=T["stash_pop_done"])
