#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Audio Tools — Nautilus Python Extension
# DESC: "Ferramentas de Áudio" submenu: convert audio files (FFmpeg).
# AUTHOR: Nautilus-Extensions
# LICENSE: GNU General Public License v3.0
# SPDX-License-Identifier: GPL-3.0-or-later
#
# REQUIRES: ffmpeg
# INSTALL:
#   cp audio-tools.py media_dialogs.py ~/.local/share/nautilus-python/extensions/
#   cp -r media_core ~/.local/share/nautilus-python/extensions/
#   nautilus -q

import locale
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python
from gi.repository import GObject, Nautilus

_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label": "Outils audio",
        "menu_tip": "Convertir des fichiers audio (FFmpeg)",
        "convert_to": "Convertir en",
        "advanced": "Avancé…",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label": "Audio-Werkzeuge",
        "menu_tip": "Audiodateien konvertieren (FFmpeg)",
        "convert_to": "Konvertieren nach",
        "advanced": "Erweitert…",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label": "Herramientas de audio",
        "menu_tip": "Convertir archivos de audio (FFmpeg)",
        "convert_to": "Convertir a",
        "advanced": "Avanzado…",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label": "Ferramentas de áudio",
        "menu_tip": "Converter arquivos de áudio (FFmpeg)",
        "convert_to": "Converter para",
        "advanced": "Avançado…",
    }
else:
    T = {
        "menu_label": "Audio Tools",
        "menu_tip": "Convert audio files (FFmpeg)",
        "convert_to": "Convert to",
        "advanced": "Advanced…",
    }

AUDIO_QUICK = ["mp3", "m4a", "opus", "ogg", "flac", "wav"]
AUDIO_ALL = ["mp3", "m4a", "aac", "opus", "ogg", "flac", "wav", "aiff", "ac3"]


def _paths_from_files(files):
    out = []
    for f in files:
        try:
            if f.get_uri_scheme() != "file":
                return []
            if f.is_directory():
                return []
            p = f.get_location().get_path()
        except Exception:
            return []
        if not p or not os.path.isfile(p):
            return []
        out.append(p)
    return out


def _all_audio(paths):
    if not paths:
        return False
    try:
        from media_core.detection import detect_category
        from media_core.models import MediaCategory
        return all(detect_category(p) == MediaCategory.AUDIO for p in paths)
    except Exception:
        return False


def _ffmpeg_available():
    try:
        from media_core.backends.ffmpeg import FFmpegBackend
        return FFmpegBackend.can_register()
    except Exception:
        return False


class AudioToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "AudioToolsExtension"

    def _cb_quick(self, _item, paths, fmt):
        from media_core.models import MediaCategory
        from media_dialogs import QuickConvertDialog, nautilus_window
        QuickConvertDialog(nautilus_window(), paths, fmt,
                           MediaCategory.AUDIO, autostart=True).present()

    def _cb_advanced(self, _item, paths):
        from media_core.models import MediaCategory
        from media_dialogs import AdvancedDialog, nautilus_window
        AdvancedDialog(nautilus_window(), paths, MediaCategory.AUDIO,
                       AUDIO_ALL).present()

    def _menu_for(self, paths):
        if not _all_audio(paths):
            return []
        if not _ffmpeg_available():
            return []

        top = Nautilus.MenuItem(
            name="AudioTools::Top",
            label=T["menu_label"],
            tip=T["menu_tip"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)

        for fmt in AUDIO_QUICK:
            sub = Nautilus.MenuItem(
                name="AudioTools::To{0}".format(fmt.upper()),
                label=fmt.upper(),
                tip=T["menu_tip"],
            )
            sub.connect("activate", self._cb_quick, paths, fmt)
            submenu.append_item(sub)

        adv = Nautilus.MenuItem(
            name="AudioTools::Advanced",
            label=T["advanced"],
            tip=T["menu_tip"],
        )
        adv.connect("activate", self._cb_advanced, paths)
        submenu.append_item(adv)
        return [top]

    def get_file_items(self, files):
        try:
            return self._menu_for(_paths_from_files(files))
        except Exception:
            return []

    def get_background_items(self, _folder):
        return []
