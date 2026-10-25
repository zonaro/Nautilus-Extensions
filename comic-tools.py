#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Comic Tools — Nautilus Python Extension
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
# NAME: Comic Tools – Nautilus Python Extension
# DESC: Open CBZ/CBR/CB7/CBT comic archives in an image viewer
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-gtk-4.0,
#           p7zip-full (CB7 and CBR fallback), unrar (CBR),
#           loupe, eog or gwenview
# INSTALL:
#   cp comic-tools.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q

"""Open comic archives from the Nautilus context menu.

Pages are unpacked, in a background thread, into a per-archive cache:

    ~/.cache/nautilus-comics/<key>/001.jpg

<key> is the first 16 hex digits of SHA-1 over the absolute path, mtime and
size of the archive, so replacing or moving a comic gets a fresh cache
instead of stale pages. Nested folders are flattened and only images are
kept. Extraction goes to <key>.part, renamed to <key> only on success, so an
interrupted run leaves nothing that looks like a valid cache.
"""

import hashlib
import locale
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50); in CLI
    # mode nothing is pre-loaded, so ask for the newer namespace explicitly.
    try:
        gi.require_version("Nautilus", "4.1")
    except ValueError:
        pass
from gi.repository import GObject, Gtk, GLib, Nautilus

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
try:
    from nautilus_i18n import resolve_locale
except ImportError:  # nautilus_i18n.py not installed next to this file
    def resolve_locale():
        return locale.getlocale()[0] or ""

_lang = resolve_locale()

if _lang.startswith("fr"):
    T = {
        "menu_label":       "Ouvrir la bande dessinée…",
        "tip_open":         "Ouvrir les pages de la bande dessinée sélectionnée",
        "notice_multi":     "{count} autre(s) bande(s) dessinée(s) sélectionnée(s) — seule la première sera ouverte.",
        "err_unsupported":  "Ce fichier n'est pas une bande dessinée prise en charge (CBZ, CBR, CB7 ou CBT).",
        "err_empty":        "Cette bande dessinée n'a aucune page : l'archive est vide ou ne contient pas d'images.",
        "err_extract":      "Impossible d'extraire la bande dessinée.\n{detail}",
        "err_missing_tool": "Outil requis absent : {tool}. Installez-le puis réessayez.",
        "err_no_viewer":    "Aucun lecteur d'images trouvé. Installez Loupe, Eye of GNOME (eog) ou Gwenview.",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":       "Abrir el cómic…",
        "tip_open":         "Abrir las páginas del cómic seleccionado",
        "notice_multi":     "{count} cómic(s) más seleccionado(s): solo se abrirá el primero.",
        "err_unsupported":  "Este archivo no es un cómic compatible (CBZ, CBR, CB7 o CBT).",
        "err_empty":        "Este cómic no tiene páginas: el archivo está vacío o no contiene imágenes.",
        "err_extract":      "No se pudo extraer el cómic.\n{detail}",
        "err_missing_tool": "Falta una herramienta necesaria: {tool}. Instálala y vuelve a intentarlo.",
        "err_no_viewer":    "No se encontró ningún visor de imágenes. Instala Loupe, Eye of GNOME (eog) o Gwenview.",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":       "Abrir quadrinho…",
        "tip_open":         "Abrir as páginas do quadrinho selecionado",
        "notice_multi":     "{count} outro(s) quadrinho(s) selecionado(s) — abrindo apenas o primeiro.",
        "err_unsupported":  "Este arquivo não é um quadrinho compatível (CBZ, CBR, CB7 ou CBT).",
        "err_empty":        "Este quadrinho não tem páginas: o arquivo está vazio ou não contém imagens.",
        "err_extract":      "Não foi possível extrair o quadrinho.\n{detail}",
        "err_missing_tool": "Ferramenta necessária ausente: {tool}. Instale e tente de novo.",
        "err_no_viewer":    "Nenhum visualizador de imagens encontrado. Instale o Loupe, o Eye of GNOME (eog) ou o Gwenview.",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":       "Comic öffnen…",
        "tip_open":         "Die Seiten des ausgewählten Comics öffnen",
        "notice_multi":     "{count} weitere Comics ausgewählt — nur der erste wird geöffnet.",
        "err_unsupported":  "Diese Datei ist kein unterstützter Comic (CBZ, CBR, CB7 oder CBT).",
        "err_empty":        "Dieser Comic hat keine Seiten: Das Archiv ist leer oder enthält keine Bilder.",
        "err_extract":      "Der Comic konnte nicht entpackt werden.\n{detail}",
        "err_missing_tool": "Benötigtes Werkzeug fehlt: {tool}. Bitte installieren und erneut versuchen.",
        "err_no_viewer":    "Kein Bildbetrachter gefunden. Bitte Loupe, Eye of GNOME (eog) oder Gwenview installieren.",
    }
else:
    T = {
        "menu_label":       "Open comic…",
        "tip_open":         "Open the pages of the selected comic archive",
        "notice_multi":     "{count} more comic(s) selected — opening only the first.",
        "err_unsupported":  "This file is not a supported comic archive (CBZ, CBR, CB7 or CBT).",
        "err_empty":        "This comic has no pages: the archive is empty or holds no images.",
        "err_extract":      "Could not extract the comic.\n{detail}",
        "err_missing_tool": "Missing required tool: {tool}. Install it and try again.",
        "err_no_viewer":    "No image viewer found. Install Loupe, Eye of GNOME (eog) or Gwenview.",
    }

COMIC_MIMES = frozenset({
    "application/vnd.comicbook+zip", "application/vnd.comicbook-rar",
    "application/x-cbz", "application/x-cbr", "application/x-cb7",
    "application/x-cbt", "application/x-ext-cbz", "application/x-ext-cbr",
    "application/x-ext-cb7", "application/x-ext-cbt",
})

COMIC_EXTS = frozenset({".cbz", ".cbr", ".cb7", ".cbt"})

IMAGE_EXTS = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".avif", ".jxl", ".bmp", ".tif", ".tiff",
})

# Extraction family per extension. Plain archive extensions are accepted so a
# mislabelled comic still opens, but only COMIC_EXTS trigger the menu entry.
_FAMILIES = {
    ".cbz": "zip", ".zip": "zip",
    ".cbr": "rar", ".rar": "rar",
    ".cb7": "7z",  ".7z":  "7z",
    ".cbt": "tar", ".tar": "tar",
}

VIEWERS = ("loupe", "eog", "gwenview")

SZ_BIN = shutil.which("7z") or shutil.which("7za")
UNRAR_BIN = shutil.which("unrar")

CACHE_ROOT = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "nautilus-comics")

_DIGITS_RE = re.compile(r"(\d+)")

# One lock per cache key, so two activations of the same comic cannot extract
# into the same ".part" directory at the same time.
_CACHE_LOCKS = {}
_CACHE_LOCKS_GUARD = threading.Lock()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class _ComicError(Exception):
    """Failure carrying a translated message key and an optional detail."""

    def __init__(self, key, detail=""):
        super().__init__(detail or key)
        self.key = key
        self.detail = detail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nautilus_window():
    app = Gtk.Application.get_default()
    if app is None:
        return None
    win = app.get_active_window()
    return win or (app.get_windows()[0] if app.get_windows() else None)


def _show_message(msg: str):
    """Show a message through Gtk.AlertDialog (GTK 4.10+)."""
    Gtk.AlertDialog(message=msg).show(_nautilus_window())


def _is_image(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in IMAGE_EXTS


def _family(path: str) -> str:
    """Return "zip", "rar", "7z", "tar" or "" for this archive."""
    return _FAMILIES.get(os.path.splitext(path)[1].lower(), "")


def _is_comic(info) -> bool:
    """True for a local file whose MIME type or extension says "comic"."""
    try:
        if info.get_uri_scheme() != "file":
            return False
        if (info.get_mime_type() or "") in COMIC_MIMES:
            return True
        path = info.get_location().get_path()
        return bool(path) and os.path.splitext(path)[1].lower() in COMIC_EXTS
    except Exception:
        return False


def _natural_key(name: str):
    """Sort key that compares digit runs as numbers: page-9 < page-10.

    Text runs are compared case-insensitively and digit runs by value, so
    leading zeros ("007") do not change the page order. Ties fall back to the
    raw name to keep the order deterministic ("P2" before "p2").
    """
    chunks = tuple(
        (0, int(chunk), "") if index % 2 else (1, 0, chunk.casefold())
        for index, chunk in enumerate(_DIGITS_RE.split(name)) if chunk)
    return (chunks, name)


def _cache_key(path: str) -> str:
    """SHA-1 of absolute path + mtime + size, truncated to 16 hex digits."""
    info = os.stat(path)
    raw = "{}\0{}\0{}".format(
        os.path.abspath(path), info.st_mtime_ns, info.st_size)
    return hashlib.sha1(
        raw.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def _collect_images(directory: str):
    """Images below *directory*, ordered naturally by relative path."""
    if not os.path.isdir(directory):
        return []
    pages = [os.path.join(root, name)
             for root, _dirs, names in os.walk(directory)
             for name in names if _is_image(name)]
    pages.sort(key=lambda p: _natural_key(os.path.relpath(p, directory)))
    return pages


def _unique_name(name: str, used: set) -> str:
    """Return *name*, or "stem-2.ext" and so on when it is already taken."""
    if name.casefold() not in used:
        used.add(name.casefold())
        return name
    stem, ext = os.path.splitext(name)
    counter = 2
    while True:
        candidate = "{}-{}{}".format(stem, counter, ext)
        if candidate.casefold() not in used:
            used.add(candidate.casefold())
            return candidate
        counter += 1


def _target_path(root: str, member: str):
    """Safe extraction target for *member*, or None when it escapes *root*."""
    root = os.path.abspath(root)
    target = os.path.abspath(os.path.join(root, member))
    return target if target.startswith(root + os.sep) else None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _run(cmd, check=True):
    """Run *cmd* without a shell; return (returncode, stderr text)."""
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise _ComicError("err_extract", str(exc)) from exc
    detail = proc.stderr.decode("utf-8", errors="replace")
    if check and proc.returncode != 0:
        lines = [line.strip() for line in detail.splitlines() if line.strip()]
        raise _ComicError(
            "err_extract",
            (lines[-1][:300] if lines else "")
            or "exit code {}".format(proc.returncode))
    return proc.returncode, detail


def _extract_zip(archive: str, dest: str):
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if _is_image(info.filename) and _target_path(dest, info.filename):
                    zf.extract(info, dest)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise _ComicError("err_extract", str(exc)) from exc


def _extract_tar(archive: str, dest: str):
    try:
        with tarfile.open(archive, "r:*") as tar:
            for member in tar.getmembers():
                if not (member.isfile() and _is_image(member.name)
                        and _target_path(dest, member.name)):
                    continue
                try:
                    tar.extract(member, dest, filter="data")
                except TypeError:  # Python < 3.12 has no filter argument
                    tar.extract(member, dest)
    except (tarfile.TarError, OSError) as exc:
        raise _ComicError("err_extract", str(exc)) from exc


def _extract_7z(archive: str, dest: str):
    binary = SZ_BIN or shutil.which("7z") or shutil.which("7za")
    if not binary:
        raise _ComicError("err_missing_tool", "p7zip")
    _run([binary, "x", "-y", "-bd", "-o{}".format(dest), archive])


def _extract_rar(archive: str, dest: str):
    # unrar reads every RAR generation; 7z still handles most RAR4/RAR5
    # archives, so a missing or failing unrar is not fatal.
    binary = UNRAR_BIN or shutil.which("unrar")
    if binary:
        if _run([binary, "x", "-o+", "-idq", archive, dest + os.sep],
                check=False)[0] == 0:
            return
    _extract_7z(archive, dest)


def _extract(archive: str, dest: str):
    family = _family(archive)
    if not family:
        raise _ComicError("err_unsupported")
    if not os.path.isfile(archive):
        raise _ComicError("err_extract", os.path.basename(archive))
    os.makedirs(dest, exist_ok=True)
    {
        "zip": _extract_zip,
        "tar": _extract_tar,
        "7z": _extract_7z,
        "rar": _extract_rar,
    }[family](archive, dest)


def _flatten(raw_dir: str, dest: str):
    """Move every image below *raw_dir* into the flat *dest* directory."""
    used = set()
    pages = []
    for source in _collect_images(raw_dir):
        target = os.path.join(
            dest, _unique_name(os.path.basename(source), used))
        shutil.move(source, target)
        pages.append(target)
    return pages


def _prepare_pages(archive: str):
    """Return the cached page images, extracting the archive when needed."""
    cache_dir = os.path.join(CACHE_ROOT, _cache_key(archive))
    with _CACHE_LOCKS_GUARD:
        lock = _CACHE_LOCKS.setdefault(cache_dir, threading.Lock())
    with lock:
        pages = _collect_images(cache_dir)
        if pages:
            return pages

        part_dir = cache_dir + ".part"
        shutil.rmtree(part_dir, ignore_errors=True)
        os.makedirs(part_dir)
        raw_dir = os.path.join(part_dir, "raw")
        try:
            _extract(archive, raw_dir)
            pages = _flatten(raw_dir, part_dir)
            shutil.rmtree(raw_dir, ignore_errors=True)
            if not pages:
                raise _ComicError("err_empty")
            # cache_dir held no images, so it is a leftover from an
            # interrupted run and can be replaced by the fresh extraction.
            shutil.rmtree(cache_dir, ignore_errors=True)
            os.replace(part_dir, cache_dir)
        except BaseException:
            shutil.rmtree(part_dir, ignore_errors=True)
            raise
    return _collect_images(cache_dir)


# ---------------------------------------------------------------------------
# Viewer
# ---------------------------------------------------------------------------

def _spawn(argv):
    subprocess.Popen(
        argv,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _launch(pages):
    """Open the ordered pages in the first viewer that is installed."""
    if not pages:
        raise _ComicError("err_empty")
    for name in VIEWERS:
        binary = shutil.which(name)
        if binary:
            _spawn([binary] + pages)
            return
    gio = shutil.which("gio")
    if gio:
        _spawn([gio, "open", pages[0]])
        return
    raise _ComicError("err_no_viewer")


# ---------------------------------------------------------------------------
# Nautilus extension
# ---------------------------------------------------------------------------

class ComicToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "ComicToolsExtension"

    def get_file_items(self, files):
        comics = [f for f in files if _is_comic(f)]
        if not comics:
            return []

        item = Nautilus.MenuItem(
            name="ComicTools::OpenComic",
            label=T["menu_label"],
            tip=T["tip_open"],
            icon="image-x-generic",
        )
        item.connect("activate", self._on_activate, comics)
        return [item]

    def get_background_items(self, folder):
        return []

    def _on_activate(self, _item, comics):
        try:
            self._open(comics)
        except Exception as exc:
            # Never let a menu handler traceback escape into Nautilus.
            _show_message(T["err_extract"].format(detail=str(exc)))

    def _open(self, comics):
        paths = []
        for info in comics:
            location = info.get_location()
            path = location.get_path() if location else None
            if path:
                paths.append(path)
        if not paths:
            _show_message(T["err_unsupported"])
            return

        archive = paths[0]
        if len(paths) > 1:
            _show_message(T["notice_multi"].format(count=len(paths) - 1))
        if not os.path.isfile(archive) or not _family(archive):
            _show_message(T["err_unsupported"])
            return

        threading.Thread(
            target=self._extract_and_open,
            args=(archive,),
            daemon=True,
        ).start()

    def _extract_and_open(self, archive):
        try:
            _launch(_prepare_pages(archive))
        except _ComicError as exc:
            GLib.idle_add(_show_message, T[exc.key].format(
                detail=exc.detail, tool=exc.detail))
        except Exception as exc:
            GLib.idle_add(
                _show_message, T["err_extract"].format(detail=str(exc)))


# ---------------------------------------------------------------------------
# CLI mode — used by comic-reader.desktop so that double-clicking a comic
# archive opens it, not only the context-menu action.
# ---------------------------------------------------------------------------

def _cli(argv):
    """Open every comic named on the command line; return a shell exit code."""
    paths = [a for a in argv if not a.startswith("-")]
    if not paths:
        print("usage: comic-tools.py --open FILE...", file=sys.stderr)
        return 2

    status = 0
    for path in paths:
        try:
            _launch(_prepare_pages(path))
        except _ComicError as exc:
            message = T[exc.key].format(detail=exc.detail, tool=exc.detail)
            print("{0}: {1}".format(os.path.basename(path), message),
                  file=sys.stderr)
            status = 1
        except Exception as exc:  # never traceback into a desktop launcher
            message = T["err_extract"].format(detail=exc)
            print("{0}: {1}".format(os.path.basename(path), message),
                  file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
