#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Video Tools — Nautilus Python Extension
# DESC: "Ferramentas de Vídeo" submenu: convert video (FFmpeg) + extract
#       audio (quick via media_core, or the full extraction dialog).
# AUTHOR: Nautilus-Extensions
# LICENSE: GNU General Public License v3.0
# SPDX-License-Identifier: GPL-3.0-or-later
#
# REQUIRES: ffmpeg (ffprobe optional, for progress %)
# INSTALL:
#   cp video-tools.py media_dialogs.py ~/.local/share/nautilus-python/extensions/
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
        "menu_label": "Outils vidéo",
        "menu_tip": "Convertir des vidéos et extraire l'audio (FFmpeg)",
        "convert_to": "Convertir en",
        "extract_audio": "Extraire l'audio",
        "full_dialog": "Extraction complète…",
        "advanced": "Avancé…",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label": "Video-Werkzeuge",
        "menu_tip": "Videos konvertieren und Audio extrahieren (FFmpeg)",
        "convert_to": "Konvertieren nach",
        "extract_audio": "Audio extrahieren",
        "full_dialog": "Vollständige Extraktion…",
        "advanced": "Erweitert…",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label": "Herramientas de vídeo",
        "menu_tip": "Convertir vídeos y extraer audio (FFmpeg)",
        "convert_to": "Convertir a",
        "extract_audio": "Extraer audio",
        "full_dialog": "Extracción completa…",
        "advanced": "Avanzado…",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label": "Ferramentas de vídeo",
        "menu_tip": "Converter vídeos e extrair áudio (FFmpeg)",
        "convert_to": "Converter para",
        "extract_audio": "Extrair áudio",
        "full_dialog": "Extração completa…",
        "advanced": "Avançado…",
    }
else:
    T = {
        "menu_label": "Video Tools",
        "menu_tip": "Convert videos and extract audio (FFmpeg)",
        "convert_to": "Convert to",
        "extract_audio": "Extract audio",
        "full_dialog": "Full extraction…",
        "advanced": "Advanced…",
    }

VIDEO_QUICK = ["mp4", "mkv", "webm", "mov", "avi"]
VIDEO_ALL = ["mp4", "mkv", "webm", "mov", "avi", "mpeg", "ts", "3gp", "ogv", "gif"]
AUDIO_QUICK = ["mp3", "m4a", "opus", "flac", "wav"]


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


def _all_videos(paths):
    if not paths:
        return False
    try:
        from media_core.detection import detect_category
        from media_core.models import MediaCategory
        return all(detect_category(p) == MediaCategory.VIDEO for p in paths)
    except Exception:
        return False


def _ffmpeg_available():
    try:
        from media_core.backends.ffmpeg import FFmpegBackend
        return FFmpegBackend.can_register()
    except Exception:
        return False


class VideoToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "VideoToolsExtension"

    def _add(self, menu, name, label, cb, *args, tip=None):
        item = Nautilus.MenuItem(
            name="VideoTools::{0}".format(name),
            label=label,
            tip=tip or T["menu_tip"],
        )
        item.connect("activate", cb, *args)
        menu.append_item(item)

    # -- actions ----------------------------------------------------------
    def _cb_quick_video(self, _item, paths, fmt):
        from media_core.models import MediaCategory
        from media_dialogs import QuickConvertDialog, nautilus_window
        QuickConvertDialog(nautilus_window(), paths, fmt,
                           MediaCategory.VIDEO).present()

    def _cb_quick_audio(self, _item, paths, fmt):
        from media_core.models import MediaCategory
        from media_dialogs import QuickConvertDialog, nautilus_window
        QuickConvertDialog(nautilus_window(), paths, fmt,
                           MediaCategory.VIDEO).present()

    def _cb_full_extraction(self, _item, paths):
        # Full dialog (quality levels, per-file status) moved here from the
        # old standalone video-to-audio.py extension.
        try:
            import importlib.util
            import sys
            mod = sys.modules.get("video_to_audio")
            if mod is None:
                here = os.path.dirname(os.path.abspath(__file__))
                legacy = os.path.join(here, "video-to-audio.py")
                if not os.path.isfile(legacy):
                    legacy = os.path.join(
                        os.path.expanduser(
                            "~/.local/share/nautilus-python/extensions"),
                        "video-to-audio.py")
                spec = importlib.util.spec_from_file_location(
                    "video_to_audio", legacy)
                mod = importlib.util.module_from_spec(spec)
                sys.modules["video_to_audio"] = mod
                spec.loader.exec_module(mod)
            mod.VideoToAudioWindow(paths).present()
        except Exception:
            # Fallback: quick MP3 dialog so the entry never dead-ends.
            from media_core.models import MediaCategory
            from media_dialogs import QuickConvertDialog, nautilus_window
            QuickConvertDialog(nautilus_window(), paths, "mp3",
                               MediaCategory.VIDEO).present()

    def _cb_advanced(self, _item, paths):
        from media_core.models import MediaCategory
        from media_dialogs import AdvancedDialog, nautilus_window
        AdvancedDialog(nautilus_window(), paths, MediaCategory.VIDEO,
                       VIDEO_ALL + AUDIO_QUICK).present()

    # -- menu --------------------------------------------------------------
    def _menu_for(self, paths):
        if not _all_videos(paths):
            return []
        if not _ffmpeg_available():
            return []

        top = Nautilus.MenuItem(
            name="VideoTools::Top",
            label=T["menu_label"],
            tip=T["menu_tip"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)

        # Convert to video formats (quick presets)
        conv = Nautilus.Menu()
        for fmt in VIDEO_QUICK:
            sub = Nautilus.MenuItem(
                name="VideoTools::To{0}".format(fmt.upper()),
                label=fmt.upper(),
                tip=T["menu_tip"],
            )
            sub.connect("activate", self._cb_quick_video, paths, fmt)
            conv.append_item(sub)
        conv_item = Nautilus.MenuItem(
            name="VideoTools::ConvertTo",
            label=T["convert_to"],
            tip=T["menu_tip"],
        )
        conv_item.set_submenu(conv)
        submenu.append_item(conv_item)

        # Extract audio (moved here from the old standalone extension)
        amenu = Nautilus.Menu()
        for fmt in AUDIO_QUICK:
            sub = Nautilus.MenuItem(
                name="VideoTools::Extract{0}".format(fmt.upper()),
                label=fmt.upper(),
                tip=T["menu_tip"],
            )
            sub.connect("activate", self._cb_quick_audio, paths, fmt)
            amenu.append_item(sub)
        self._add(amenu, "FullExtraction", T["full_dialog"],
                  self._cb_full_extraction, paths)
        a_item = Nautilus.MenuItem(
            name="VideoTools::ExtractAudio",
            label=T["extract_audio"],
            tip=T["menu_tip"],
        )
        a_item.set_submenu(amenu)
        submenu.append_item(a_item)

        self._add(submenu, "Advanced", T["advanced"], self._cb_advanced,
                  paths)
        return [top]

    def get_file_items(self, files):
        try:
            return self._menu_for(_paths_from_files(files))
        except Exception:
            return []

    def get_background_items(self, _folder):
        return []
