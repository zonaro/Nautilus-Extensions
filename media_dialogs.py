#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Media Dialogs — shared GTK UI for media conversion
# DESC: Quick + Advanced progress dialogs used by Video/Audio/Image Tools.
#       GTK lives ONLY here. Conversion logic lives in media_core.
# AUTHOR: Nautilus-Extensions
# LICENSE: GNU General Public License v3.0
# SPDX-License-Identifier: GPL-3.0-or-later
#
# INSTALL:
#   (shipped with media-converter / video-tools / audio-tools / image-tools)
#   cp media_dialogs.py media_core -r ~/.local/share/nautilus-python/extensions/
#   nautilus -q

import locale
import os
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except Exception:
    pass
from gi.repository import Gtk, Adw, GLib, Pango

_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "convert": "Convertir",
        "cancel": "Annuler",
        "close": "Fermer",
        "choose": "Choisir…",
        "dest": "Destination",
        "format": "Format",
        "quality": "Qualité",
        "q_high": "Haute",
        "q_medium": "Moyenne",
        "q_low": "Basse",
        "ready": "Prêt",
        "converting": "Conversion en cours… ({done}/{total})",
        "done": "Terminé — {ok}/{total} réussi(s).",
        "cancelled": "Conversion annulée.",
        "error": "Erreur : {err}",
        "advanced": "Conversion avancée",
        "quick_title": "Convertir en {fmt}",
    }
elif _lang.startswith("de"):
    T = {
        "convert": "Konvertieren",
        "cancel": "Abbrechen",
        "close": "Schließen",
        "choose": "Wählen…",
        "dest": "Ziel",
        "format": "Format",
        "quality": "Qualität",
        "q_high": "Hoch",
        "q_medium": "Mittel",
        "q_low": "Niedrig",
        "ready": "Bereit",
        "converting": "Konvertiere… ({done}/{total})",
        "done": "Fertig — {ok}/{total} erfolgreich.",
        "cancelled": "Konvertierung abgebrochen.",
        "error": "Fehler: {err}",
        "advanced": "Erweiterte Konvertierung",
        "quick_title": "In {fmt} konvertieren",
    }
elif _lang.startswith("es"):
    T = {
        "convert": "Convertir",
        "cancel": "Cancelar",
        "close": "Cerrar",
        "choose": "Elegir…",
        "dest": "Destino",
        "format": "Formato",
        "quality": "Calidad",
        "q_high": "Alta",
        "q_medium": "Media",
        "q_low": "Baja",
        "ready": "Listo",
        "converting": "Convirtiendo… ({done}/{total})",
        "done": "Terminado — {ok}/{total} correctas.",
        "cancelled": "Conversión cancelada.",
        "error": "Error: {err}",
        "advanced": "Conversión avanzada",
        "quick_title": "Convertir a {fmt}",
    }
elif _lang.startswith("pt"):
    T = {
        "convert": "Converter",
        "cancel": "Cancelar",
        "close": "Fechar",
        "choose": "Escolher…",
        "dest": "Destino",
        "format": "Formato",
        "quality": "Qualidade",
        "q_high": "Alta",
        "q_medium": "Média",
        "q_low": "Baixa",
        "ready": "Pronto",
        "converting": "Convertendo… ({done}/{total})",
        "done": "Concluído — {ok}/{total} com sucesso.",
        "cancelled": "Conversão cancelada.",
        "error": "Erro: {err}",
        "advanced": "Conversão avançada",
        "quick_title": "Converter para {fmt}",
    }
else:
    T = {
        "convert": "Convert",
        "cancel": "Cancel",
        "close": "Close",
        "choose": "Choose…",
        "dest": "Destination",
        "format": "Format",
        "quality": "Quality",
        "q_high": "High",
        "q_medium": "Medium",
        "q_low": "Low",
        "ready": "Ready",
        "converting": "Converting… ({done}/{total})",
        "done": "Done — {ok}/{total} succeeded.",
        "cancelled": "Conversion cancelled.",
        "error": "Error: {err}",
        "advanced": "Advanced conversion",
        "quick_title": "Convert to {fmt}",
    }


def _default_dest(paths):
    try:
        if paths:
            d = os.path.dirname(os.path.abspath(paths[0]))
            if os.path.isdir(d):
                return d
    except Exception:
        pass
    return os.path.expanduser("~")


def _friendly_ffmpeg_error(exc):
    """Shorten verbose ffmpeg stderr into one user-friendly line."""
    msg = str(exc) if exc else ""
    if not msg:
        return "ffmpeg failed"
    # Keep only first meaningful line, cap length.
    for line in msg.splitlines():
        s = line.strip()
        if s and "ffmpeg version" not in s.lower():
            return s[:220]
    return msg[:220]


def convert_one(path, target_fmt, category, dest_dir, quality="medium",
                progress_cb=None, is_cancelled=None):
    """Convert a single file via media_core. Returns output Path.

    category: a MediaCategory value. progress_cb(fraction: float).
    Raises on failure; returns Path on success.
    """
    from media_core.models import MediaCategory, MediaItem

    src = Path(path)
    dest = Path(dest_dir)
    fmt = str(target_fmt).lower().strip().lstrip(".")

    if category == MediaCategory.IMAGE:
        # Prefer Pillow for static images; fall back to FFmpeg.
        try:
            from media_core.backends.pillow import PillowBackend
            if PillowBackend.can_register():
                be = PillowBackend()
                q = {"high": 95, "medium": 92, "low": 80}.get(quality, 92)
                return be.convert_image(
                    src, dest, fmt, quality=q, overwrite=False,
                    progress_callback=progress_cb,
                )
        except Exception:
            pass  # fall through to FFmpeg
        from media_core.backends.ffmpeg import FFmpegBackend
        be = FFmpegBackend()
        if not be.binary:
            raise RuntimeError("ffmpeg not found")
        item = MediaItem(path=src, category=MediaCategory.IMAGE, target_format=fmt)

        def _cb(frac, _item=None):
            if progress_cb:
                progress_cb(frac)

        return be.convert_item(item, dest, progress_callback=_cb,
                               overwrite=False)
    else:
        from media_core.backends.ffmpeg import FFmpegBackend
        be = FFmpegBackend()
        if not be.binary:
            raise RuntimeError("ffmpeg not found")
        item = MediaItem(path=src, category=category, target_format=fmt)

        def _cb(frac, _item=None):
            if is_cancelled and is_cancelled():
                be.abort()
                return
            if progress_cb:
                progress_cb(frac)

        out = be.convert_item(item, dest, progress_callback=_cb,
                              overwrite=False)
        return out, be


def nautilus_window():
    app = Gtk.Application.get_default()
    if app is None:
        return None
    try:
        win = app.get_active_window()
        if win is not None:
            return win
        wins = app.get_windows()
        return wins[0] if wins else None
    except Exception:
        return None


class _BaseDialog(Gtk.Dialog):
    def _dest_row(self, box, initial):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_title = Gtk.Label(label=T["dest"])
        lbl_title.set_halign(Gtk.Align.START)
        lbl_title.set_size_request(90, -1)
        row.append(lbl_title)
        self._dest_label = Gtk.Label(label=initial)
        self._dest_label.set_hexpand(True)
        self._dest_label.set_xalign(0)
        self._dest_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        row.append(self._dest_label)
        btn = Gtk.Button(label=T["choose"])
        btn.connect("clicked", self._on_choose_dest)
        row.append(btn)
        box.append(row)

    def _on_choose_dest(self, _btn):
        try:
            from gi.repository import Gio
            dlg = Gtk.FileDialog.new()
            dlg.set_title(T["dest"])
            try:
                cur = self._dest_label.get_label()
                if cur and os.path.isdir(cur):
                    dlg.set_initial_folder(Gio.File.new_for_path(cur))
            except Exception:
                pass
            dlg.select_folder(self, None, self._on_dest_done)
        except Exception:
            pass

    def _on_dest_done(self, dlg, res):
        try:
            folder = dlg.select_folder_finish(res)
            if folder:
                p = folder.get_path()
                if p:
                    self._dest_label.set_label(p)
        except Exception:
            pass


class QuickConvertDialog(_BaseDialog):
    """Destino + progresso + batch. Usado pelo fluxo 'botão direito → formato'."""

    def __init__(self, parent, paths, target_fmt, category, quality="medium"):
        super().__init__(title=T["quick_title"].format(fmt=str(target_fmt).upper()),
                         transient_for=parent, modal=True)
        self.paths = [str(p) for p in (paths or [])]
        self.target_fmt = str(target_fmt).lower()
        self.category = category
        self.quality = quality
        self._cancelled = False
        self._backend = None
        self._running = False

        self.set_default_size(480, 240)
        box = self.get_content_area()
        for m in ("margin_top", "margin_bottom", "margin_start", "margin_end"):
            try:
                getattr(box, "set_" + m)(16)
            except Exception:
                pass
        box.set_spacing(12)

        self._dest_row(box, _default_dest(self.paths))

        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(True)
        self._progress.set_fraction(0.0)
        self._progress.set_text("0 %")
        box.append(self._progress)

        self._status = Gtk.Label(label=T["ready"])
        self._status.set_halign(Gtk.Align.START)
        self._status.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(self._status)

        self._btn_cancel = self.add_button(T["cancel"], Gtk.ResponseType.CANCEL)
        self._btn_convert = self.add_button(T["convert"], Gtk.ResponseType.OK)
        self._btn_convert.add_css_class("suggested-action")
        self.connect("response", self._on_response)
        # Wayland-safe present is done by callers via GLib.idle_add.

    def present(self):  # noqa: D102 - Wayland-safe
        GLib.idle_add(super().present)

    # -- response / run -----------------------------------------------------
    def _on_response(self, _dlg, response):
        if response == Gtk.ResponseType.CANCEL:
            self._cancel()
            return
        if response == Gtk.ResponseType.OK:
            if not self._running:
                self._start()
            return
        self._cancel()

    def _cancel(self):
        self._cancelled = True
        try:
            if self._backend is not None and hasattr(self._backend, "abort"):
                self._backend.abort()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass

    def _start(self):
        self._running = True
        try:
            self._btn_convert.set_sensitive(False)
        except Exception:
            pass
        dest = self._dest_label.get_label()
        threading.Thread(target=self._worker, args=(dest,), daemon=True).start()

    def _set_progress(self, frac, text=None):
        self._progress.set_fraction(max(0.0, min(1.0, frac)))
        try:
            self._progress.set_text(text if text is not None else f"{int(frac * 100)} %")
        except Exception:
            pass
        return False

    def _set_status(self, msg):
        self._status.set_label(msg)
        return False

    def _worker(self, dest):
        from media_core.models import MediaCategory, MediaItem

        total = len(self.paths)
        ok = 0
        GLib.idle_add(self._set_status,
                      T["converting"].format(done=0, total=total))
        for i, src in enumerate(self.paths):
            if self._cancelled:
                break
            GLib.idle_add(self._set_status,
                          T["converting"].format(done=i, total=total)
                          + f" — {os.path.basename(src)}")
            try:
                if self.category == MediaCategory.IMAGE:
                    from media_core.backends.pillow import PillowBackend
                    from media_core.backends.ffmpeg import FFmpegBackend
                    done_evt = {"be": None}
                    use_pillow = PillowBackend.can_register()
                    if use_pillow:
                        try:
                            be = PillowBackend()
                            self._backend = be
                            q = {"high": 95, "medium": 92, "low": 80}.get(
                                self.quality, 92)

                            def _pcb(f, _i=i, _t=total):
                                GLib.idle_add(self._set_progress, (_i + f) / _t)
                            be.convert_image(Path(src), Path(dest),
                                             self.target_fmt, quality=q,
                                             overwrite=False,
                                             progress_callback=_pcb)
                            ok += 1
                            GLib.idle_add(self._set_progress, (i + 1) / total)
                            continue
                        except Exception as e:
                            # Fall back to FFmpeg only if Pillow genuinely
                            # cannot handle it; otherwise report error.
                            if "not available" not in str(e).lower():
                                raise
                    be = FFmpegBackend()
                    self._backend = be
                    if not be.binary:
                        raise RuntimeError("ffmpeg not found")
                    item = MediaItem(path=Path(src),
                                     category=MediaCategory.IMAGE,
                                     target_format=self.target_fmt)

                    def _fcb(f, _it=None, _i=i, _t=total):
                        if self._cancelled:
                            try:
                                be.abort()
                            except Exception:
                                pass
                            return
                        GLib.idle_add(self._set_progress, (_i + f) / _t)
                    be.convert_item(item, Path(dest), progress_callback=_fcb,
                                    overwrite=False)
                    ok += 1
                    GLib.idle_add(self._set_progress, (i + 1) / total)
                else:
                    from media_core.backends.ffmpeg import FFmpegBackend
                    be = FFmpegBackend()
                    self._backend = be
                    if not be.binary:
                        raise RuntimeError("ffmpeg not found")
                    item = MediaItem(path=Path(src), category=self.category,
                                     target_format=self.target_fmt)

                    def _fcb2(f, _it=None, _i=i, _t=total):
                        if self._cancelled:
                            try:
                                be.abort()
                            except Exception:
                                pass
                            return
                        GLib.idle_add(self._set_progress, (_i + f) / _t)
                    be.convert_item(item, Path(dest), progress_callback=_fcb2,
                                    overwrite=False)
                    ok += 1
                    GLib.idle_add(self._set_progress, (i + 1) / total)
            except Exception as e:  # noqa: BLE001 - report per-file, continue
                from media_core.backends.ffmpeg import FFmpegAborted
                if isinstance(e, FFmpegAborted) or self._cancelled:
                    break
                GLib.idle_add(self._set_status, T["error"].format(
                    err=_friendly_ffmpeg_error(e)))
                continue

        def _finish():
            self._running = False
            if self._cancelled:
                self._status.set_label(T["cancelled"])
            else:
                self._status.set_label(T["done"].format(ok=ok, total=total))
            try:
                self._btn_cancel.set_visible(False)
            except Exception:
                pass
            try:
                self._btn_convert.set_visible(False)
            except Exception:
                pass
            close_btn = self.add_button(T["close"], Gtk.ResponseType.CLOSE)
            close_btn.connect("clicked", lambda *_: self.close())
            return False

        GLib.idle_add(_finish)


class AdvancedDialog(_BaseDialog):
    """Formato + qualidade + destino, depois delega ao QuickConvertDialog."""

    def __init__(self, parent, paths, category, formats):
        super().__init__(title=T["advanced"], transient_for=parent, modal=True)
        self.paths = [str(p) for p in (paths or [])]
        self.category = category
        self.formats = [str(f).lower() for f in (formats or [])]

        self.set_default_size(480, 260)
        box = self.get_content_area()
        for m in ("margin_top", "margin_bottom", "margin_start", "margin_end"):
            try:
                getattr(box, "set_" + m)(16)
            except Exception:
                pass
        box.set_spacing(12)

        # Format
        frow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        flbl = Gtk.Label(label=T["format"])
        flbl.set_halign(Gtk.Align.START)
        flbl.set_size_request(90, -1)
        frow.append(flbl)
        self._fmt = Gtk.DropDown.new_from_strings(
            [f.upper() for f in self.formats] or ["MP4"])
        self._fmt.set_hexpand(True)
        self._fmt.set_selected(0)
        frow.append(self._fmt)
        box.append(frow)

        # Quality
        qrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        qlbl = Gtk.Label(label=T["quality"])
        qlbl.set_halign(Gtk.Align.START)
        qlbl.set_size_request(90, -1)
        qrow.append(qlbl)
        self._quality = Gtk.DropDown.new_from_strings(
            [T["q_high"], T["q_medium"], T["q_low"]])
        self._quality.set_hexpand(True)
        self._quality.set_selected(1)
        qrow.append(self._quality)
        box.append(qrow)

        self._dest_row(box, _default_dest(self.paths))

        self.add_button(T["cancel"], Gtk.ResponseType.CANCEL)
        self._btn_go = self.add_button(T["convert"], Gtk.ResponseType.OK)
        self._btn_go.add_css_class("suggested-action")
        self.connect("response", self._on_response)

    def present(self):  # noqa: D102 - Wayland-safe
        GLib.idle_add(super().present)

    def _on_response(self, _dlg, response):
        if response != Gtk.ResponseType.OK:
            try:
                self.close()
            except Exception:
                pass
            return
        try:
            fmt = self.formats[self._fmt.get_selected()]
        except Exception:
            fmt = self.formats[0] if self.formats else "mp4"
        quality = ["high", "medium", "low"][self._quality.get_selected()]
        dest = self._dest_label.get_label()
        parent = self.get_transient_for()
        try:
            self.close()
        except Exception:
            pass
        dlg = QuickConvertDialog(parent, self.paths, fmt, self.category,
                                 quality=quality)
        # Preselect the destination chosen in Advanced.
        try:
            dlg._dest_label.set_label(dest)
        except Exception:
            pass
        dlg.present()
