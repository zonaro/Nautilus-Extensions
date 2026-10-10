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
        "vcodec": "Codec vidéo",
        "acodec": "Codec audio",
        "abitrate": "Débit audio",
        "crf": "Qualité (CRF)",
        "speed": "Preset vitesse",
        "resolution": "Résolution",
        "fps": "Images/s",
        "hw": "Accélération",
        "sample_rate": "Fréq. échant.",
        "channels": "Canaux",
        "max_side": "Grand côté (px)",
        "orig": "Original",
        "mono": "Mono",
        "stereo": "Stéréo",
        "auto_preset": "Auto (preset)",
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
        "vcodec": "Video-Codec",
        "acodec": "Audio-Codec",
        "abitrate": "Audio-Bitrate",
        "crf": "Qualität (CRF)",
        "speed": "Geschwindigkeits-Preset",
        "resolution": "Auflösung",
        "fps": "Bildrate",
        "hw": "Beschleunigung",
        "sample_rate": "Abtastrate",
        "channels": "Kanäle",
        "max_side": "Lange Seite (px)",
        "orig": "Original",
        "mono": "Mono",
        "stereo": "Stereo",
        "auto_preset": "Auto (Preset)",
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
        "vcodec": "Códec de vídeo",
        "acodec": "Códec de audio",
        "abitrate": "Bitrate de audio",
        "crf": "Calidad (CRF)",
        "speed": "Preajuste velocidad",
        "resolution": "Resolución",
        "fps": "Fotogramas/s",
        "hw": "Aceleración",
        "sample_rate": "Frec. muestreo",
        "channels": "Canales",
        "max_side": "Lado mayor (px)",
        "orig": "Original",
        "mono": "Mono",
        "stereo": "Estéreo",
        "auto_preset": "Auto (preset)",
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
        "vcodec": "Codec de vídeo",
        "acodec": "Codec de áudio",
        "abitrate": "Bitrate de áudio",
        "crf": "Qualidade (CRF)",
        "speed": "Preset de velocidade",
        "resolution": "Resolução",
        "fps": "Quadros/s",
        "hw": "Aceleração",
        "sample_rate": "Taxa de amostragem",
        "channels": "Canais",
        "max_side": "Lado maior (px)",
        "orig": "Original",
        "mono": "Mono",
        "stereo": "Estéreo",
        "auto_preset": "Auto (preset)",
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
        "vcodec": "Video codec",
        "acodec": "Audio codec",
        "abitrate": "Audio bitrate",
        "crf": "Quality (CRF)",
        "speed": "Speed preset",
        "resolution": "Resolution",
        "fps": "Frame rate",
        "hw": "Acceleration",
        "sample_rate": "Sample rate",
        "channels": "Channels",
        "max_side": "Long side (px)",
        "orig": "Original",
        "mono": "Mono",
        "stereo": "Stereo",
        "auto_preset": "Auto (preset)",
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

    def __init__(self, parent, paths, target_fmt, category, quality="medium",
                 autostart=False, opts=None, hwaccel="cpu"):
        super().__init__(title=T["quick_title"].format(fmt=str(target_fmt).upper()),
                         transient_for=parent, modal=True)
        self.paths = [str(p) for p in (paths or [])]
        self.target_fmt = str(target_fmt).lower()
        self.category = category
        self.quality = quality
        self.opts = dict(opts) if opts else {}
        self.hwaccel = hwaccel or "cpu"
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
        if autostart:
            GLib.idle_add(self._autostart)

    def _autostart(self):
        if not self._running and not self._cancelled:
            self._start()
        return False

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
                    use_pillow = PillowBackend.can_register()
                    if use_pillow:
                        try:
                            be = PillowBackend()
                            self._backend = be
                            q = self.opts.get("quality")
                            if q is None:
                                q = {"high": 95, "medium": 92,
                                     "low": 80}.get(self.quality, 92)

                            def _pcb(f, _i=i, _t=total):
                                GLib.idle_add(self._set_progress, (_i + f) / _t)
                            be.convert_image(Path(src), Path(dest),
                                             self.target_fmt, quality=int(q),
                                             overwrite=False,
                                             progress_callback=_pcb,
                                             max_side=self.opts.get("max_side"))
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
                                    overwrite=False, hwaccel=self.hwaccel,
                                    opts=self.opts or None)
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
                                    overwrite=False, hwaccel=self.hwaccel,
                                    opts=self.opts or None)
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
    """All conversion settings per media type, then hands off to Quick."""

    _SPEEDS = ("ultrafast", "superfast", "veryfast", "faster", "fast",
               "medium", "slow", "slower", "veryslow")
    _ABITRATES = ("64k", "96k", "128k", "192k", "256k", "320k")

    def __init__(self, parent, paths, category, formats):
        super().__init__(title=T["advanced"], transient_for=parent, modal=True)
        from media_core.models import MediaCategory
        self.paths = [str(p) for p in (paths or [])]
        self.category = category
        self.formats = [str(f).lower() for f in (formats or [])]
        self._ctl = {}

        self.set_default_size(540, 620)
        outer = self.get_content_area()
        for m in ("margin_top", "margin_bottom", "margin_start", "margin_end"):
            try:
                getattr(outer, "set_" + m)(16)
            except Exception:
                pass
        outer.set_spacing(12)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.append(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll.set_child(box)

        def _row(label):
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lab = Gtk.Label(label=label)
            lab.set_halign(Gtk.Align.START)
            lab.set_size_request(150, -1)
            lab.set_wrap(True)
            r.append(lab)
            box.append(r)
            return r

        def _drop(items, active=0):
            d = Gtk.DropDown.new_from_strings(list(items))
            d.set_hexpand(True)
            try:
                d.set_selected(active)
            except Exception:
                pass
            return d

        def _spin(value, lo, hi, step=1):
            s = Gtk.SpinButton.new_with_range(lo, hi, step)
            s.set_value(value)
            s.set_hexpand(True)
            return s

        # Format (all categories)
        r = _row(T["format"])
        self._fmt = _drop([f.upper() for f in self.formats] or ["MP4"])
        r.append(self._fmt)

        if category == MediaCategory.VIDEO:
            try:
                from media_core.capabilities import (
                    available_video_codecs, available_audio_codecs,
                    available_hw)
                vcs = available_video_codecs()
                acs = available_audio_codecs()
                hws = available_hw()
            except Exception:
                vcs, acs, hws = [], [], ["Auto", "CPU"]
            self._vcodecs = [None] + [e for e, _ in vcs]
            r = _row(T["vcodec"])
            self._ctl["vcodec"] = _drop(
                [T["auto_preset"]] + [f"{lbl} ({e})" for e, lbl in vcs])
            r.append(self._ctl["vcodec"])
            r = _row(T["crf"])
            self._ctl["crf"] = _spin(23, 0, 51)
            r.append(self._ctl["crf"])
            r = _row(T["speed"])
            self._ctl["speed"] = _drop(["Auto"] + list(self._SPEEDS), 3)
            r.append(self._ctl["speed"])
            r = _row(T["resolution"])
            self._resolutions = [None, "480p", "720p", "1080p", "2160p"]
            self._ctl["resolution"] = _drop([T["orig"]] + self._resolutions[1:])
            r.append(self._ctl["resolution"])
            r = _row(T["fps"])
            self._fps = [None, 24, 25, 30, 50, 60]
            self._ctl["fps"] = _drop(
                [T["orig"]] + [str(f) for f in self._fps[1:]])
            r.append(self._ctl["fps"])
            self._acodecs = [None] + [e for e, _ in acs]
            r = _row(T["acodec"])
            self._ctl["acodec"] = _drop(
                [T["auto_preset"]] + [f"{lbl} ({e})" for e, lbl in acs])
            r.append(self._ctl["acodec"])
            r = _row(T["abitrate"])
            self._ctl["abitrate"] = _drop(["Auto"] + list(self._ABITRATES), 4)
            r.append(self._ctl["abitrate"])
            self._hws = hws if hws else ["Auto", "CPU"]
            r = _row(T["hw"])
            self._ctl["hw"] = _drop(self._hws)
            r.append(self._ctl["hw"])
        elif category == MediaCategory.AUDIO:
            r = _row(T["quality"])
            self._quality = _drop([T["q_high"], T["q_medium"], T["q_low"]], 1)
            r.append(self._quality)
            r = _row(T["sample_rate"])
            self._srates = [None, 44100, 48000]
            self._ctl["sample_rate"] = _drop(
                [T["orig"], "44100 Hz", "48000 Hz"])
            r.append(self._ctl["sample_rate"])
            r = _row(T["channels"])
            self._chan = [None, 1, 2]
            self._ctl["channels"] = _drop([T["orig"], T["mono"], T["stereo"]])
            r.append(self._ctl["channels"])
        else:
            r = _row(T["quality"])
            self._ctl["quality"] = _spin(92, 1, 100)
            r.append(self._ctl["quality"])
            r = _row(T["max_side"])
            self._ctl["max_side"] = _spin(0, 0, 8000, 100)
            r.append(self._ctl["max_side"])

        self._dest_row(box, _default_dest(self.paths))

        self.add_button(T["cancel"], Gtk.ResponseType.CANCEL)
        self._btn_go = self.add_button(T["convert"], Gtk.ResponseType.OK)
        self._btn_go.add_css_class("suggested-action")
        self.connect("response", self._on_response)

    def present(self):  # noqa: D102 - Wayland-safe
        GLib.idle_add(super().present)

    def _sel(self, name, default=0):
        try:
            return self._ctl[name].get_selected()
        except Exception:
            return default

    def _on_response(self, _dlg, response):
        if response != Gtk.ResponseType.OK:
            try:
                self.close()
            except Exception:
                pass
            return
        from media_core.models import MediaCategory
        try:
            fmt = self.formats[self._fmt.get_selected()]
        except Exception:
            fmt = self.formats[0] if self.formats else "mp4"
        opts: dict = {}
        hwaccel = "cpu"
        quality = "medium"
        if self.category == MediaCategory.VIDEO:
            vc = self._vcodecs[self._sel("vcodec")]
            if vc:
                opts["vcodec"] = vc
            try:
                opts["crf"] = str(int(self._ctl["crf"].get_value()))
            except Exception:
                pass
            sp = self._sel("speed")
            if sp > 0:
                opts["speed"] = self._SPEEDS[sp - 1]
            rs = self._sel("resolution")
            if rs > 0:
                opts["resolution"] = self._resolutions[rs]
            fp = self._sel("fps")
            if fp > 0:
                opts["fps"] = self._fps[fp]
            ac = self._acodecs[self._sel("acodec")]
            if ac:
                opts["acodec"] = ac
            ab = self._sel("abitrate")
            if ab > 0:
                opts["abitrate"] = self._ABITRATES[ab - 1]
            try:
                hw = self._hws[self._ctl["hw"].get_selected()]
            except Exception:
                hw = "Auto"
            if hw == "CPU":
                hwaccel = "cpu"
            elif hw in ("VAAPI", "NVENC", "QSV"):
                hwaccel = hw.lower()
            else:
                hwaccel = "cpu"
                for cand in self._hws[2:]:
                    hwaccel = cand.lower()
                    break
        elif self.category == MediaCategory.AUDIO:
            try:
                quality = ["high", "medium", "low"][
                    self._quality.get_selected()]
            except Exception:
                quality = "medium"
            opts["abitrate"] = {"high": "256k", "medium": "192k",
                                "low": "128k"}[quality]
            sr = self._srates[self._sel("sample_rate")]
            if sr:
                opts["sample_rate"] = sr
            ch = self._chan[self._sel("channels")]
            if ch:
                opts["channels"] = ch
        else:
            try:
                q = int(self._ctl["quality"].get_value())
            except Exception:
                q = 92
            try:
                ms = int(self._ctl["max_side"].get_value())
            except Exception:
                ms = 0
            opts["quality"] = q
            if ms > 0:
                opts["max_side"] = ms
        dest = self._dest_label.get_label()
        parent = self.get_transient_for()
        try:
            self.close()
        except Exception:
            pass
        dlg = QuickConvertDialog(parent, self.paths, fmt, self.category,
                                 quality=quality, autostart=True,
                                 opts=opts or None, hwaccel=hwaccel)
        try:
            dlg._dest_label.set_label(dest)
        except Exception:
            pass
        dlg.present()
