#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Media Converter — Nautilus Python Extension
# DESC: Convert media files (video/audio/image) using FFmpeg and Pillow
# AUTHOR: Adapted for Nautilus-Extensions
# LICENSE: GNU General Public License v3.0
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import threading
import locale
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except (ValueError, Exception):
    pass
from gi.repository import GObject, Gtk, Adw, GLib, Pango, Nautilus

from media_core.registry import ConversionRegistry
from media_core.models import MediaCategory
from media_core.presets_manager import Presets

# i18n
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label": "Convertir média",
        "convert_video": "Convertir vidéo",
        "convert_audio": "Convertir audio",
        "convert_image": "Convertir image",
        "extract_audio": "Extraire l'audio",
        "advanced": "Avancé…",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label": "Medien konvertieren",
        "convert_video": "Video konvertieren",
        "convert_audio": "Audio konvertieren",
        "convert_image": "Bild konvertieren",
        "extract_audio": "Audio extrahieren",
        "advanced": "Erweitert…",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label": "Convertir medios",
        "convert_video": "Convertir vídeo",
        "convert_audio": "Convertir audio",
        "convert_image": "Convertir imagen",
        "extract_audio": "Extraer audio",
        "advanced": "Avanzado…",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label": "Converter mídia",
        "convert_video": "Converter vídeo",
        "convert_audio": "Converter áudio",
        "convert_image": "Converter imagem",
        "extract_audio": "Extrair áudio",
        "advanced": "Avançado…",
    }
else:
    T = {
        "menu_label": "Convert Media",
        "convert_video": "Convert Video",
        "convert_audio": "Convert Audio",
        "convert_image": "Convert Image",
        "extract_audio": "Extract Audio",
        "advanced": "Advanced…",
    }

VIDEO_FORMATS = Presets.VIDEO
AUDIO_EXTRACT_FORMATS = Presets.AUDIO_EXTRACT
AUDIO_FORMATS = Presets.AUDIO
IMAGE_FORMATS = Presets.IMAGE


class MediaConverterExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "MediaConverterExtension"

    def __init__(self):
        super().__init__()
        self._registry = ConversionRegistry()

    def _get_paths_from_files(self, files):
        paths = []
        for f in files:
            try:
                if f.get_uri_scheme() != "file":
                    return None
                if f.is_directory():
                    continue
                p = f.get_location().get_path()
                if p:
                    paths.append(p)
            except Exception:
                continue
        return paths

    def get_file_items(self, files):
        paths = self._get_paths_from_files(files)
        if not paths:
            return []

        if len(paths) == 0:
            return []

        # Classify files
        categories = set()
        for p in paths:
            cat = self._registry.get_media_type(p)
            categories.add(cat)

        if MediaCategory.UNKNOWN in categories and len(categories) > 1:
            categories.discard(MediaCategory.UNKNOWN)

        if len(categories) != 1:
            # Mixed or all unknown - don't show if no valid media
            if categories == {MediaCategory.UNKNOWN}:
                return []
            # Mixed types - could be handled more intelligently, but keep simple
            # For now, if mixed and includes valid, show generic?
            # But requirement says "If multiple files are selected, only show option if applicable to all"
            return []

        cat = categories.pop()

        if cat == MediaCategory.VIDEO:
            menu = Nautilus.Menu()
            item_main = Nautilus.MenuItem(
                name="MediaConverter::ConvertVideo",
                label=T["menu_label"],
                icon="video-x-generic-symbolic",
            )
            item_main.set_submenu(menu)

            # Quick convert subitems
            for fmt in VIDEO_FORMATS:
                sub = Nautilus.MenuItem(
                    name=f"MediaConverter::VideoTo{fmt.upper()}",
                    label=f"{fmt.upper()}",
                )
                sub.connect("activate", self._quick_convert_video, paths, fmt)
                menu.append_item(sub)

            menu.append_item(Nautilus.MenuItem(name="sep1", label="────────────"))

            # Extract audio submenu
            audio_menu = Nautilus.Menu()
            for fmt in AUDIO_EXTRACT_FORMATS:
                sub = Nautilus.MenuItem(
                    name=f"MediaConverter::Extract{fmt.upper()}",
                    label=f"{fmt.upper()}",
                )
                sub.connect("activate", self._extract_audio, paths, fmt)
                audio_menu.append_item(sub)

            extract_item = Nautilus.MenuItem(
                name="MediaConverter::ExtractAudio",
                label=T["extract_audio"],
            )
            extract_item.set_submenu(audio_menu)
            menu.append_item(extract_item)

            menu.append_item(Nautilus.MenuItem(name="sep2", label="────────────"))
            adv = Nautilus.MenuItem(
                name="MediaConverter::Advanced",
                label=T["advanced"],
            )
            adv.connect("activate", self._advanced, paths, cat)
            menu.append_item(adv)

            return [item_main]

        elif cat == MediaCategory.AUDIO:
            menu = Nautilus.Menu()
            item_main = Nautilus.MenuItem(
                name="MediaConverter::ConvertAudio",
                label=T["convert_audio"],
                icon="audio-x-generic-symbolic",
            )
            item_main.set_submenu(menu)

            for fmt in AUDIO_FORMATS:
                sub = Nautilus.MenuItem(
                    name=f"MediaConverter::AudioTo{fmt.upper()}",
                    label=f"{fmt.upper()}",
                )
                sub.connect("activate", self._quick_convert_audio, paths, fmt)
                menu.append_item(sub)

            menu.append_item(Nautilus.MenuItem(name="sep", label="────────────"))
            adv = Nautilus.MenuItem(
                name="MediaConverter::Advanced",
                label=T["advanced"],
            )
            adv.connect("activate", self._advanced, paths, cat)
            menu.append_item(adv)

            return [item_main]

        elif cat == MediaCategory.IMAGE:
            menu = Nautilus.Menu()
            item_main = Nautilus.MenuItem(
                name="MediaConverter::ConvertImage",
                label=T["convert_image"],
                icon="image-x-generic-symbolic",
            )
            item_main.set_submenu(menu)

            for fmt in IMAGE_FORMATS:
                sub = Nautilus.MenuItem(
                    name=f"MediaConverter::ImageTo{fmt.upper()}",
                    label=f"{fmt.upper()}",
                )
                sub.connect("activate", self._quick_convert_image, paths, fmt)
                menu.append_item(sub)

            menu.append_item(Nautilus.MenuItem(name="sep", label="────────────"))
            adv = Nautilus.MenuItem(
                name="MediaConverter::Advanced",
                label=T["advanced"],
            )
            adv.connect("activate", self._advanced, paths, cat)
            menu.append_item(adv)

            return [item_main]

        return []

    def get_background_items(self, folder):
        return []

    def _quick_convert_video(self, menu_item, paths, target_fmt):
        # Quick conversion stub - will implement proper dialog
        pass

    def _extract_audio(self, menu_item, paths, target_fmt):
        pass

    def _quick_convert_audio(self, menu_item, paths, target_fmt):
        pass

    def _quick_convert_image(self, menu_item, paths, target_fmt):
        pass

    def _advanced(self, menu_item, paths, cat):
        pass


class ProgressDialog(Gtk.Dialog):
    def __init__(self, parent, title="Converting..."):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(400, 200)
        self.set_resizable(False)

        box = self.get_content_area()
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_spacing(12)

        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(True)
        box.append(self._progress)

        self._status = Gtk.Label(label="Preparing...")
        self._status.set_halign(Gtk.Align.START)
        box.append(self._status)


if __name__ == "__main__":
    pass


class QuickConvertDialog(Gtk.Dialog):
    def __init__(self, parent, paths, target_fmt, cat):
        super().__init__(title="Convert", transient_for=parent, modal=True)
        self.paths = paths
        self.target_fmt = target_fmt
        self.cat = cat
        self._registry = ConversionRegistry()
        self._cancelled = False
        self._worker = None

        self.set_default_size(450, 220)
        box = self.get_content_area()
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_spacing(12)

        # Destination folder
        dest_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._dest_label = Gtk.Label(label=os.path.dirname(paths[0]) if paths else os.path.expanduser("~"))
        self._dest_label.set_hexpand(True)
        self._dest_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._dest_label.set_xalign(0)
        dest_btn = Gtk.Button(label=T.get("choose", "Choose..."))
        dest_btn.connect("clicked", self._choose_dest)
        dest_box.append(self._dest_label)
        dest_box.append(dest_btn)
        box.append(dest_box)

        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(True)
        box.append(self._progress)

        self._status = Gtk.Label(label="Ready")
        self._status.set_halign(Gtk.Align.START)
        self._status.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(self._status)

        self.add_button(T.get("cancel", "Cancel"), Gtk.ResponseType.CANCEL)
        self._convert_btn = self.add_button(T.get("convert", "Convert"), Gtk.ResponseType.OK)
        self._convert_btn.set_sensitive(True)

        self.connect("response", self._on_response)
    def _choose_dest(self, btn):
        dlg = Gtk.FileDialog.new()
        dlg.set_title("Select destination folder")
        try:
            dlg.select_folder(self, None, self._on_dest_selected)
        except Exception:
            pass

    def _on_dest_selected(self, dlg, res):
        try:
            folder = dlg.select_folder_finish(res)
            if folder:
                path = folder.get_path()
                if path:
                    self._dest_label.set_label(path)
        except Exception:
            pass
    def _on_response(self, dlg, response):
        if response == Gtk.ResponseType.CANCEL:
            self._cancelled = True
            if self._worker:
                backend = self._registry.get_backend()
                if hasattr(backend, 'abort'):
                    backend.abort()
            self.close()
            return
        if response == Gtk.ResponseType.OK:
            self._start()

    def _start(self):
        self._convert_btn.set_sensitive(False)
        dest = Path(self._dest_label.get_label())
        total = len(self.paths)
        backend = self._registry.get_backend()

        def worker():
            ok = 0
            for i, p in enumerate(self.paths):
                if self._cancelled:
                    break
                try:
                    GLib.idle_add(lambda i=i: self._update_status(f"Processing {Path(self.paths[i]).name} ({i+1}/{total})"))
                    from media_core.models import MediaItem
                    from media_core.models import MediaCategory
                    cat = MediaCategory.VIDEO if self.cat == MediaCategory.VIDEO else (
                        MediaCategory.AUDIO if self.cat == MediaCategory.AUDIO else MediaCategory.IMAGE)
                    if self.cat == MediaCategory.VIDEO and self.target_fmt in AUDIO_EXTRACT_FORMATS:
                        cat = MediaCategory.VIDEO  # but target audio - handled by FFmpeg
                        item = MediaItem(path=Path(p), category=MediaCategory.VIDEO, target_format=self.target_fmt)
                    else:
                        item = MediaItem(path=Path(p), category=cat, target_format=self.target_fmt)
                    if isinstance(backend, type(self._registry.backends[0])) is False or True:  # just run
                        pass
                    # Run conversion
                    if hasattr(backend, 'convert_item'):
                        def prog(fraction, item_=None):
                            GLib.idle_add(lambda f=fraction: self._progress.set_fraction(f))
                            return False
                        out = backend.convert_item(item, dest, progress_callback=prog)
                    ok += 1
                    GLib.idle_add(lambda: self._progress.set_fraction((i + 1) / total if total > 0 else 1.0))
                except Exception as e:
                    GLib.idle_add(lambda e=e: self._update_status(f"Error: {e}"))
            GLib.idle_add(lambda ok=ok, total=total: self._on_done(ok, total))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _update_status(self, msg):
        self._status.set_label(msg)
        return False

    def _on_done(self, ok, total):
        self._status.set_label(f"Done: {ok}/{total}")
        self.add_button("Close", Gtk.ResponseType.CLOSE)
        return False
    def _quick_convert_video(self, menu_item, paths, target_fmt):
        dlg = QuickConvertDialog(_nautilus_window(), paths, target_fmt, MediaCategory.VIDEO)
        dlg.present()

    def _extract_audio(self, menu_item, paths, target_fmt):
        dlg = QuickConvertDialog(_nautilus_window(), paths, target_fmt, MediaCategory.VIDEO)
        dlg.present()

    def _quick_convert_audio(self, menu_item, paths, target_fmt):
        dlg = QuickConvertDialog(_nautilus_window(), paths, target_fmt, MediaCategory.AUDIO)
        dlg.present()

    def _quick_convert_image(self, menu_item, paths, target_fmt):
        dlg = QuickConvertDialog(_nautilus_window(), paths, target_fmt, MediaCategory.IMAGE)
        dlg.present()

    def _advanced(self, menu_item, paths, cat):
        dlg = AdvancedDialog(_nautilus_window(), paths, cat)
        dlg.present()


def _nautilus_window():
    app = Gtk.Application.get_default()
    if app is None:
        return None
    win = app.get_active_window()
    if win is not None:
        return win
    windows = app.get_windows()
    return windows[0] if windows else None


class AdvancedDialog(Gtk.Dialog):
    def __init__(self, parent, paths, cat):
        super().__init__(title=T["advanced"], transient_for=parent, modal=True)
        self.paths = paths
        self.cat = cat
        self._registry = ConversionRegistry()

        self.set_default_size(550, 400)
        box = self.get_content_area()
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_spacing(12)

        # Format selector
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(Gtk.Label(label="Format"))
        self._format = Gtk.ComboBoxText()
        if cat == MediaCategory.VIDEO:
            for f in VIDEO_FORMATS + AUDIO_EXTRACT_FORMATS:
                self._format.append_text(f.upper())
        elif cat == MediaCategory.AUDIO:
            for f in AUDIO_FORMATS:
                self._format.append_text(f.upper())
        elif cat == MediaCategory.IMAGE:
            for f in IMAGE_FORMATS:
                self._format.append_text(f.upper())
        self._format.set_active(0)
        self._format.set_hexpand(True)
        row.append(self._format)
        box.append(row)

        # Destination
        dest_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._dest_label = Gtk.Label(label=os.path.dirname(paths[0]) if paths else os.path.expanduser("~"))
        self._dest_label.set_hexpand(True)
        self._dest_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._dest_label.set_xalign(0)
        dest_btn = Gtk.Button(label=T.get("choose", "Choose..."))
        dest_btn.connect("clicked", self._choose_dest)
        dest_box.append(self._dest_label)
        dest_box.append(dest_btn)
        box.append(dest_box)

        self.add_button(T.get("cancel", "Cancel"), Gtk.ResponseType.CANCEL)
        self._convert_btn = self.add_button(T.get("convert", "Convert"), Gtk.ResponseType.OK)

        self.connect("response", self._on_response)

    def _choose_dest(self, btn):
        dlg = Gtk.FileDialog.new()
        dlg.set_title("Select destination folder")
        try:
            dlg.select_folder(self, None, self._on_dest_selected)
        except Exception:
            pass

    def _on_dest_selected(self, dlg, res):
        try:
            folder = dlg.select_folder_finish(res)
            if folder:
                path = folder.get_path()
                if path:
                    self._dest_label.set_label(path)
        except Exception:
            pass

    def _on_response(self, dlg, response):
        if response == Gtk.ResponseType.CANCEL:
            self.close()
            return
        if response == Gtk.ResponseType.OK:
            fmt = self._format.get_active_text().lower()
            prog = QuickConvertDialog(self.get_transient_for(), self.paths, fmt, self.cat)
            self.close()
            prog.present()
