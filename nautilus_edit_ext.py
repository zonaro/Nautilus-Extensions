#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Nautilus Edit With — Nautilus Python Extension
# DESC: Open text files with any installed text editor (alphabetical submenu)
# AUTHOR: Tof
# VERSION: 2.0
# LICENSE: GNU General Public License v3.0
#

from gi.repository import Nautilus, GObject, Gio
import subprocess
import shutil


class EditFileExtension(GObject.GObject, Nautilus.MenuProvider):
    """Extension Nautilus pour ouvrir des fichiers texte avec n'importe quel éditeur installé"""

    # Fallback si la base MIME ne retourne rien (binaire -> label joli)
    FALLBACK_EDITORS = (
        ("code", "Visual Studio Code"),
        ("codium", "VSCodium"),
        ("gedit", "gedit"),
        ("gnome-text-editor", "Text Editor"),
        ("kate", "Kate"),
        ("geany", "Geany"),
        ("xed", "xed"),
        ("mousepad", "Mousepad"),
        ("pluma", "Pluma"),
        ("leafpad", "Leafpad"),
        ("subl", "Sublime Text"),
        ("atom", "Atom"),
        ("emacs", "Emacs"),
        ("gvim", "GVim"),
        ("nvim", "Neovim"),
        ("vim", "Vim"),
        ("nano", "Nano"),
    )

    # Extensions considérées comme éditables (élargi vs v1 limitée à 7)
    EDITABLE_EXTENSIONS = (
        '.py', '.sh', '.txt', '.md', '.markdown', '.json', '.yml', '.yaml',
        '.toml', '.ini', '.cfg', '.conf', '.config', '.env', '.log',
        '.csv', '.tsv', '.xml', '.html', '.htm', '.css', '.scss',
        '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx',
        '.c', '.h', '.cpp', '.hpp', '.cc', '.java', '.rs', '.go',
        '.rb', '.php', '.pl', '.lua', '.sql', '.r', '.tex',
        '.rst', '.adoc', '.dockerfile', '.gitignore', '.editorconfig',
    )
    # Fichiers sans extension mais éditables (Makefile, Dockerfile, README, ...)
    EDITABLE_BASENAMES = frozenset({
        'dockerfile', 'makefile', 'cmakelists.txt', 'readme', 'license',
        'authors', 'changelog', 'news', 'todo',
    })

    def get_text_editors(self):
        """Retourne les éditeurs de texte installés triés alphabétiquement (insensible à la casse)."""
        editors = []
        seen = set()
        try:
            apps = Gio.AppInfo.get_all_for_type("text/plain") or []
        except Exception:
            apps = []
        for app in apps:
            try:
                display_name = app.get_display_name()
                executable = app.get_executable()
                app_id = app.get_id()
            except Exception:
                continue
            if not display_name:
                continue
            key = display_name.strip().lower()
            if not key or key in seen:
                continue
            # Ignore les handlers non-lançables (pas d'exécutable ni d'id desktop)
            if not executable and not app_id:
                continue
            seen.add(key)
            editors.append(app)
        editors.sort(key=lambda a: (a.get_display_name() or "").lower())
        if editors:
            return editors
        # Fallback : binaires connus présents dans le PATH
        return self._fallback_editors()

    def _fallback_editors(self):
        found = []
        seen = set()
        for binary, label in self.FALLBACK_EDITORS:
            if binary in seen:
                continue
            if shutil.which(binary):
                seen.add(binary)
                found.append((label, binary))
        found.sort(key=lambda item: item[0].lower())
        return found

    def _is_editable(self, file):
        if file.get_uri_scheme() != 'file':
            return False
        if file.is_directory():
            return False
        filename = (file.get_name() or "").lower()
        if not filename:
            return False
        if filename.endswith(self.EDITABLE_EXTENSIONS):
            return True
        # Dockerfile, Makefile, README, LICENSE, scripts sans extension...
        base = filename.rsplit('/', 1)[-1]
        name_no_ext = base.rsplit('.', 1)[0] if '.' in base and not base.startswith('.') else base
        if '.' not in base.lstrip('.') or base in self.EDITABLE_BASENAMES or name_no_ext in self.EDITABLE_BASENAMES:
            # Fichier sans extension : on l'accepte (scripts, README, LICENSE...)
            if '.' not in base.lstrip('.'):
                return True
            return True
        return False

    def _sanitize_id(self, app_id):
        return "".join(c if (c.isalnum() or c in "-_") else "_" for c in (app_id or "editor"))

    def get_file_items(self, files):
        """Construit le menu 'Edit With' avec un sous-menu par éditeur (ordre alphabétique)."""
        if not files:
            return []

        for file in files:
            if not self._is_editable(file):
                return []

        editors = self.get_text_editors()
        if not editors:
            return []

        top_item = Nautilus.MenuItem(
            name="EditFileExtension::EditWith",
            label="Edit With",
            tip="Open selection with a text editor",
        )
        submenu = Nautilus.Menu()
        top_item.set_submenu(submenu)

        uris = [f.get_uri() for f in files]
        filepaths = []
        for f in files:
            try:
                filepaths.append(f.get_location().get_path())
            except Exception:
                pass

        for entry in editors:
            if isinstance(entry, tuple):
                # Fallback : (label, binary)
                label, binary = entry
                item = Nautilus.MenuItem(
                    name=f"EditFileExtension::EditWith::{self._sanitize_id(binary)}",
                    label=label,
                    tip=f"Open selection with {label}",
                )
                item.connect("activate", self._open_with_binary_cb, filepaths, binary)
            else:
                # Gio.AppInfo
                try:
                    label = entry.get_display_name()
                    app_id = entry.get_id() or label
                except Exception:
                    continue
                item = Nautilus.MenuItem(
                    name=f"EditFileExtension::EditWith::{self._sanitize_id(app_id)}",
                    label=label,
                    tip=f"Open selection with {label}",
                )
                item.connect("activate", self._open_with_app_cb, uris, filepaths, entry)
            submenu.append_item(item)

        return [top_item]

    def _open_with_app_cb(self, menu, uris, filepaths, app):
        """Ouvre les fichiers via le .desktop (respecte Exec, Terminal, etc.), fallback subprocess."""
        try:
            app.launch_uris(uris, None)
            return
        except Exception as e:
            print(f"launch_uris failed ({e}), falling back to executable")
        try:
            executable = app.get_executable()
            if executable:
                subprocess.Popen([executable] + filepaths)
            else:
                print("No executable found for text editor")
        except Exception as e:
            print(f"Erreur lors de l'ouverture des fichiers: {e}")

    def _open_with_binary_cb(self, menu, filepaths, binary):
        """Fallback quand la base MIME est vide : lance le binaire directement."""
        try:
            subprocess.Popen([binary] + filepaths)
        except Exception as e:
            print(f"Erreur lors de l'ouverture des fichiers: {e}")
