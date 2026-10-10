#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Audio Tools — Nautilus Python Extension
# DESC: "Ferramentas de Áudio" submenu: convert audio (FFmpeg) + edit tags.
# AUTHOR: Nautilus-Extensions
# LICENSE: GNU General Public License v3.0
# SPDX-License-Identifier: GPL-3.0-or-later
#
# REQUIRES: ffmpeg (conversion); mutagen (tag editor, optional)
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
from gi.repository import GObject, Gtk, Gdk, GLib, Gio, Pango, Nautilus

_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label": "Outils audio",
        "menu_tip": "Convertir des fichiers audio (FFmpeg)",
        "convert_to": "Convertir en",
        "advanced": "Avancé…",
        "edit_tags": "Modifier les tags…",
        "save": "Enregistrer",
        "cancel": "Annuler",
        "close": "Fermer",
        "multi_hint": "{n} fichiers — les champs remplis s'appliquent "
                      "à tous ; les vides gardent leur valeur.",
        "done_msg": "{ok}/{total} enregistré(s).",
        "f_title": "Titre",
        "f_artist": "Artiste",
        "f_album": "Album",
        "f_albumartist": "Artiste de l'album",
        "f_genre": "Genre",
        "f_year": "Année",
        "f_track": "Piste",
        "f_tracktotal": "sur",
        "f_disc": "Disque",
        "f_composer": "Compositeur",
        "f_comment": "Commentaire",
        "cover": "Pochette",
        "cover_add": "Ajouter / remplacer…",
        "cover_remove": "Supprimer",
        "cover_export": "Exporter…",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label": "Audio-Werkzeuge",
        "menu_tip": "Audiodateien konvertieren (FFmpeg)",
        "convert_to": "Konvertieren nach",
        "advanced": "Erweitert…",
        "edit_tags": "Tags bearbeiten…",
        "save": "Speichern",
        "cancel": "Abbrechen",
        "close": "Schließen",
        "multi_hint": "{n} Dateien — ausgefüllte Felder gelten für alle; "
                      "leere behalten ihren Wert.",
        "done_msg": "{ok}/{total} gespeichert.",
        "f_title": "Titel",
        "f_artist": "Künstler",
        "f_album": "Album",
        "f_albumartist": "Albumkünstler",
        "f_genre": "Genre",
        "f_year": "Jahr",
        "f_track": "Titel-Nr.",
        "f_tracktotal": "von",
        "f_disc": "Disc",
        "f_composer": "Komponist",
        "f_comment": "Kommentar",
        "cover": "Cover",
        "cover_add": "Hinzufügen / ersetzen…",
        "cover_remove": "Entfernen",
        "cover_export": "Exportieren…",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label": "Herramientas de audio",
        "menu_tip": "Convertir archivos de audio (FFmpeg)",
        "convert_to": "Convertir a",
        "advanced": "Avanzado…",
        "edit_tags": "Editar etiquetas…",
        "save": "Guardar",
        "cancel": "Cancelar",
        "close": "Cerrar",
        "multi_hint": "{n} archivos — los campos rellenados se aplican "
                      "a todos; los vacíos conservan su valor.",
        "done_msg": "{ok}/{total} guardados.",
        "f_title": "Título",
        "f_artist": "Artista",
        "f_album": "Álbum",
        "f_albumartist": "Artista del álbum",
        "f_genre": "Género",
        "f_year": "Año",
        "f_track": "Pista",
        "f_tracktotal": "de",
        "f_disc": "Disco",
        "f_composer": "Compositor",
        "f_comment": "Comentario",
        "cover": "Portada",
        "cover_add": "Añadir / reemplazar…",
        "cover_remove": "Quitar",
        "cover_export": "Exportar…",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label": "Ferramentas de áudio",
        "menu_tip": "Converter arquivos de áudio (FFmpeg)",
        "convert_to": "Converter para",
        "advanced": "Avançado…",
        "edit_tags": "Editar tags…",
        "save": "Salvar",
        "cancel": "Cancelar",
        "close": "Fechar",
        "multi_hint": "{n} arquivos — campos preenchidos aplicam a todos; "
                      "vazios mantêm o valor de cada arquivo.",
        "done_msg": "{ok}/{total} salvos.",
        "f_title": "Título",
        "f_artist": "Artista",
        "f_album": "Álbum",
        "f_albumartist": "Artista do álbum",
        "f_genre": "Gênero",
        "f_year": "Ano",
        "f_track": "Faixa",
        "f_tracktotal": "de",
        "f_disc": "Disco",
        "f_composer": "Compositor",
        "f_comment": "Comentário",
        "cover": "Capa",
        "cover_add": "Adicionar / trocar…",
        "cover_remove": "Remover",
        "cover_export": "Exportar…",
    }
else:
    T = {
        "menu_label": "Audio Tools",
        "menu_tip": "Convert audio files (FFmpeg)",
        "convert_to": "Convert to",
        "advanced": "Advanced…",
        "edit_tags": "Edit tags…",
        "save": "Save",
        "cancel": "Cancel",
        "close": "Close",
        "multi_hint": "{n} files — filled fields apply to all; "
                      "empty fields keep each file's value.",
        "done_msg": "{ok}/{total} saved.",
        "f_title": "Title",
        "f_artist": "Artist",
        "f_album": "Album",
        "f_albumartist": "Album artist",
        "f_genre": "Genre",
        "f_year": "Year",
        "f_track": "Track",
        "f_tracktotal": "of",
        "f_disc": "Disc",
        "f_composer": "Composer",
        "f_comment": "Comment",
        "cover": "Cover",
        "cover_add": "Add / replace…",
        "cover_remove": "Remove",
        "cover_export": "Export…",
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


def _tags_editable(paths):
    if not paths:
        return False
    try:
        from media_core.audio_tags import can_edit
        return all(can_edit(p) for p in paths)
    except Exception:
        return False


class TagEditorDialog(Gtk.Dialog):
    def __init__(self, parent, paths):
        from media_core.audio_tags import read_tags, read_cover
        super().__init__(title=T["edit_tags"], transient_for=parent,
                         modal=True)
        self.paths = [str(p) for p in (paths or [])]
        self.multi = len(self.paths) > 1
        self._cover_action = ("keep",)
        self._cover_data = None
        self._saving = False

        self.set_default_size(560, 680)
        outer = self.get_content_area()
        for m in ("margin_top", "margin_bottom", "margin_start",
                  "margin_end"):
            try:
                getattr(outer, "set_" + m)(16)
            except Exception:
                pass
        outer.set_spacing(12)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.append(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        scroll.set_child(box)

        if self.multi:
            hint = Gtk.Label(label=T["multi_hint"].format(n=len(self.paths)))
            hint.set_wrap(True)
            hint.set_halign(Gtk.Align.START)
            hint.add_css_class("dim-label")
            box.append(hint)
        else:
            name = Gtk.Label(label=os.path.basename(self.paths[0]))
            name.set_halign(Gtk.Align.START)
            name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            name.add_css_class("dim-label")
            box.append(name)

        # Cover row
        crow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.append(crow)
        self._pic = Gtk.Picture()
        self._pic.set_size_request(192, 192)
        self._pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        crow.append(self._pic)
        cbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cbox.set_valign(Gtk.Align.CENTER)
        cbox.set_hexpand(True)
        crow.append(cbox)
        clab = Gtk.Label(label=T["cover"])
        clab.set_halign(Gtk.Align.START)
        cbox.append(clab)
        btn_add = Gtk.Button(label=T["cover_add"])
        btn_add.connect("clicked", self._on_cover_add)
        cbox.append(btn_add)
        btn_rm = Gtk.Button(label=T["cover_remove"])
        btn_rm.connect("clicked", self._on_cover_remove)
        cbox.append(btn_rm)
        self._btn_export = Gtk.Button(label=T["cover_export"])
        self._btn_export.connect("clicked", self._on_cover_export)
        cbox.append(self._btn_export)

        # Text fields
        self._entries = {}
        for key in ("title", "artist", "album", "albumartist", "genre",
                    "composer"):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lab = Gtk.Label(label=T["f_" + key])
            lab.set_halign(Gtk.Align.START)
            lab.set_size_request(150, -1)
            row.append(lab)
            ent = Gtk.Entry()
            ent.set_hexpand(True)
            row.append(ent)
            box.append(row)
            self._entries[key] = ent

        # Numeric fields
        self._spins = {}
        for key, label, lo, hi in (("year", T["f_year"], 0, 2100),
                                   ("track", T["f_track"], 0, 999),
                                   ("tracktotal", T["f_tracktotal"], 0, 999),
                                   ("disc", T["f_disc"], 0, 99)):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lab = Gtk.Label(label=label)
            lab.set_halign(Gtk.Align.START)
            lab.set_size_request(150, -1)
            row.append(lab)
            sp = Gtk.SpinButton.new_with_range(lo, hi, 1)
            sp.set_hexpand(True)
            row.append(sp)
            box.append(row)
            self._spins[key] = sp

        # Comment
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=T["f_comment"])
        lab.set_halign(Gtk.Align.START)
        lab.set_valign(Gtk.Align.START)
        lab.set_size_request(150, -1)
        row.append(lab)
        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.set_size_request(-1, 90)
        self._comment = Gtk.TextView()
        self._comment.set_wrap_mode(Gtk.WrapMode.WORD)
        frame.set_child(self._comment)
        row.append(frame)
        box.append(row)

        self._status = Gtk.Label(label="")
        self._status.set_halign(Gtk.Align.START)
        self._status.set_ellipsize(Pango.EllipsizeMode.END)
        outer.append(self._status)

        # Prefill from first file (single-file mode only)
        if not self.multi:
            try:
                tags = read_tags(self.paths[0])
                for key, ent in self._entries.items():
                    ent.set_text(tags.get(key, ""))
                for key, spin in self._spins.items():
                    raw = (tags.get("date") if key == "year"
                           else tags.get(key, ""))
                    try:
                        spin.set_value(int(str(raw).strip()[:4])
                                       if key == "year" else int(raw))
                    except (ValueError, TypeError):
                        pass
                buf = self._comment.get_buffer()
                buf.set_text(tags.get("comment", ""))
                cov = read_cover(self.paths[0])
                if cov:
                    self._set_cover(cov[0], cov[1])
            except Exception:
                pass
        self._refresh_export()

        self._btn_cancel = self.add_button(T["cancel"], Gtk.ResponseType.CANCEL)
        self._btn_save = self.add_button(T["save"], Gtk.ResponseType.OK)
        self._btn_save.add_css_class("suggested-action")
        self.connect("response", self._on_response)

    def present(self):
        GLib.idle_add(super().present)

    # -- cover ------------------------------------------------------------
    def _set_cover(self, mime, data):
        self._cover_data = (mime, bytes(data))
        try:
            tex = Gdk.Texture.new_from_bytes(GLib.Bytes(bytes(data)))
            self._pic.set_paintable(tex)
        except Exception:
            pass
        self._refresh_export()

    def _refresh_export(self):
        try:
            self._btn_export.set_sensitive(self._cover_data is not None)
        except Exception:
            pass
        return False

    def _on_cover_add(self, _btn):
        dlg = Gtk.FileDialog.new()
        filt = Gtk.FileFilter()
        filt.set_name("JPEG / PNG")
        filt.add_mime_type("image/jpeg")
        filt.add_mime_type("image/png")
        filt.add_pattern("*.jpg")
        filt.add_pattern("*.jpeg")
        filt.add_pattern("*.png")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dlg.set_filters(store)
        dlg.open(self, None, self._on_cover_chosen)

    def _on_cover_chosen(self, dlg, res):
        try:
            f = dlg.open_finish(res)
            p = f.get_path()
            if not p:
                return
            ext = os.path.splitext(p)[1].lower()
            mime = {"jpg": "image/jpeg", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png"}.get(ext)
            if mime is None:
                return
            with open(p, "rb") as fh:
                data = fh.read()
            if not data:
                return
            self._cover_action = ("set", mime, data)
            self._set_cover(mime, data)
        except Exception:
            pass

    def _on_cover_remove(self, _btn):
        self._cover_action = ("remove",)
        self._cover_data = None
        try:
            self._pic.set_paintable(None)
        except Exception:
            pass
        self._refresh_export()

    def _on_cover_export(self, _btn):
        if not self._cover_data:
            return
        dlg = Gtk.FileDialog.new()
        mime, _data = self._cover_data
        dlg.set_initial_name("cover.png" if mime == "image/png"
                             else "cover.jpg")
        dlg.save(self, None, self._on_cover_saved)

    def _on_cover_saved(self, dlg, res):
        try:
            dest = dlg.save_finish(res).get_path()
            if dest and self._cover_data:
                with open(dest, "wb") as fh:
                    fh.write(self._cover_data[1])
        except Exception:
            pass

    # -- save ---------------------------------------------------------------
    def _collect(self):
        tags: dict = {}
        for key, ent in self._entries.items():
            v = ent.get_text().strip()
            if v or not self.multi:
                tags[key] = v
        year = int(self._spins["year"].get_value())
        if year or not self.multi:
            tags["date"] = str(year) if year else ""
        for key in ("track", "tracktotal", "disc"):
            v = int(self._spins[key].get_value())
            if v or not self.multi:
                tags[key] = str(v) if v else ""
        buf = self._comment.get_buffer()
        c = buf.get_text(buf.get_start_iter(), buf.get_end_iter(),
                         False).strip()
        if c or not self.multi:
            tags["comment"] = c
        return tags

    def _on_response(self, _dlg, response):
        if response != Gtk.ResponseType.OK or self._saving:
            if response != Gtk.ResponseType.OK:
                try:
                    self.close()
                except Exception:
                    pass
            return
        self._saving = True
        try:
            self._btn_save.set_sensitive(False)
        except Exception:
            pass
        import threading
        threading.Thread(target=self._worker, args=(self._collect(),),
                         daemon=True).start()

    def _worker(self, tags):
        from media_core.audio_tags import write_tags
        ok = 0
        for src in self.paths:
            try:
                write_tags(src, tags, self._cover_action)
                ok += 1
            except Exception:
                continue
        total = len(self.paths)
        GLib.idle_add(self._finish, ok, total)

    def _finish(self, ok, total):
        self._status.set_text(T["done_msg"].format(ok=ok, total=total))
        try:
            self._btn_cancel.set_visible(False)
            self._btn_save.set_visible(False)
        except Exception:
            pass
        close_btn = self.add_button(T["close"], Gtk.ResponseType.CLOSE)
        close_btn.connect("clicked", lambda *_: self.close())
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

    def _cb_tags(self, _item, paths):
        from media_dialogs import nautilus_window
        TagEditorDialog(nautilus_window(), paths).present()

    def _menu_for(self, paths):
        if not _all_audio(paths):
            return []
        has_ffmpeg = _ffmpeg_available()
        has_tags = _tags_editable(paths)
        if not has_ffmpeg and not has_tags:
            return []

        top = Nautilus.MenuItem(
            name="AudioTools::Top",
            label=T["menu_label"],
            tip=T["menu_tip"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)

        if has_ffmpeg:
            for fmt in AUDIO_QUICK:
                sub = Nautilus.MenuItem(
                    name="AudioTools::To{0}".format(fmt.upper()),
                    label=fmt.upper(),
                    tip=T["menu_tip"],
                )
                sub.connect("activate", self._cb_quick, paths, fmt)
                submenu.append_item(sub)

        if has_tags:
            tags = Nautilus.MenuItem(
                name="AudioTools::EditTags",
                label=T["edit_tags"],
                tip=T["menu_tip"],
            )
            tags.connect("activate", self._cb_tags, paths)
            submenu.append_item(tags)

        if has_ffmpeg:
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
