#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Dev Tools Minify – Nautilus Python Extension
# DESC: Regex-based JS/CSS minifier from the Nautilus context menu
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
# NAME: Dev Tools Minify – Nautilus Python Extension
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-adw-1
# INSTALL:
#   cp dev-tools-minify.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

import os
import re
import locale

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Nautilus

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label":     "Minifier JS/CSS",
        "menu_tip":       "Minifier les fichiers JavaScript/CSS sélectionnés",
        "report_summary": "{n} fichier(s) minifié(s) — économie totale {pct}%",
        "report_line":    "{name} : {before} → {after} o (économie {save}%)",
        "err_none":       "Aucun fichier JS/CSS n'a pu être traité.",
        "err_file":       "Impossible de traiter {name} : {err}",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":     "Minificar JS/CSS",
        "menu_tip":       "Minificar los archivos JavaScript/CSS seleccionados",
        "report_summary": "{n} archivo(s) minificado(s) — ahorro total {pct}%",
        "report_line":    "{name}: {before} → {after} B (ahorro {save}%)",
        "err_none":       "Ningún archivo JS/CSS pudo procesarse.",
        "err_file":       "No se pudo procesar {name}: {err}",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":     "Minificar JS/CSS",
        "menu_tip":       "Minificar os arquivos JavaScript/CSS selecionados",
        "report_summary": "{n} arquivo(s) minificado(s) — economia total de {pct}%",
        "report_line":    "{name}: {before} → {after} B (economia de {save}%)",
        "err_none":       "Nenhum arquivo JS/CSS pôde ser processado.",
        "err_file":       "Não foi possível processar {name}: {err}",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":     "JS/CSS minifizieren",
        "menu_tip":       "Ausgewählte JavaScript/CSS-Dateien minifizieren",
        "report_summary": "{n} Datei(en) minifiziert — Einsparung gesamt {pct}%",
        "report_line":    "{name}: {before} → {after} B (Einsparung {save}%)",
        "err_none":       "Keine JS/CSS-Datei konnte verarbeitet werden.",
        "err_file":       "{name} konnte nicht verarbeitet werden: {err}",
    }
else:
    T = {
        "menu_label":     "Minify JS/CSS",
        "menu_tip":       "Minify the selected JavaScript/CSS file(s)",
        "report_summary": "{n} file(s) minified — total saving {pct}%",
        "report_line":    "{name}: {before} → {after} B (saving {save}%)",
        "err_none":       "No JS/CSS file could be processed.",
        "err_file":       "Could not process {name}: {err}",
    }

MINIFIABLE_EXTS = (".js", ".css", ".mjs", ".cjs")
_MIN_SUFFIX_RE  = re.compile(r"\.min\.(?:js|css|mjs|cjs)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Minifiers (regex only, no external libs)
# ---------------------------------------------------------------------------

def minify_js(text: str) -> str:
    # Bloc /* ... */ puis lignes // ... (le lookbehind protège les URL contenant ://)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"(?<!:)//[^\n]*", "", text)
    # Collapse des espaces / sauts de ligne
    return re.sub(r"\s+", " ", text).strip()


_ZERO_UNIT_RE = re.compile(
    r"(?<![\w.])0(?:px|rem|em|ex|ch|vw|vh|vmin|vmax|cm|mm|in|pt|pc|fr|%)"
)


def minify_css(text: str) -> str:
    # Commentaires
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Collapse des espaces global
    text = re.sub(r"\s+", " ", text)
    # Suppression des espaces autour de : ; , { }
    text = re.sub(r"\s*([:;{},])\s*", r"\1", text)
    # Point-virgule superflu en fin de règle
    text = re.sub(r";\}", "}", text)
    # Unités nulles redondantes (0px -> 0, 0% -> 0, …)
    text = _ZERO_UNIT_RE.sub("0", text)
    return text.strip()


def _minify_text(path: str, text: str) -> str:
    if os.path.splitext(path)[1].lower() in (".js", ".mjs", ".cjs"):
        return minify_js(text)
    return minify_css(text)


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


def _suggest_output(path: str) -> str:
    base, ext = os.path.splitext(path)
    return f"{base}.min{ext}"


def _savings_pct(before: int, after: int) -> float:
    if before <= 0:
        return 0.0
    return 100.0 * (1.0 - after / before)


# ---------------------------------------------------------------------------
# Extension Nautilus 4.0 / GTK4
# ---------------------------------------------------------------------------

class MinifyExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "MinifyJSonlyExtension"

    def get_file_items(self, files):
        targets = [
            f for f in files
            if f.get_uri_scheme() == "file"
            and f.get_name().lower().endswith(MINIFIABLE_EXTS)
            and not _MIN_SUFFIX_RE.search(f.get_name())
        ]
        if not targets:
            return []

        item = Nautilus.MenuItem(
            name="MinifyJS::Minify",
            label=T["menu_label"],
            tip=T["menu_tip"],
        )
        item.connect("activate", self._on_activate, targets)
        return [item]

    def get_background_items(self, folder):
        return []

    def _on_activate(self, _item, targets):
        lines, errors, n_ok = [], [], 0
        total_before = total_after = 0

        for fi in targets:
            src = fi.get_location().get_path()
            dst = _suggest_output(src)
            try:
                with open(src, "rb") as fh:
                    raw = fh.read()
            except OSError as exc:
                errors.append(T["err_file"].format(name=os.path.basename(src), err=exc))
                continue

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")

            out_text = _minify_text(src, text)

            try:
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write(out_text)
            except OSError as exc:
                errors.append(T["err_file"].format(name=os.path.basename(dst), err=exc))
                continue

            after = len(out_text.encode("utf-8"))
            total_before += len(raw)
            total_after += after
            n_ok += 1
            lines.append(T["report_line"].format(
                name=os.path.basename(dst),
                before=len(raw),
                after=after,
                save=_savings_pct(len(raw), after),
            ))

        if n_ok == 0:
            _show_message(errors[0] if errors else T["err_none"])
            return

        lines.append(T["report_summary"].format(
            n=n_ok,
            pct=_savings_pct(total_before, total_after),
        ))
        _show_message("\n".join(lines + errors))