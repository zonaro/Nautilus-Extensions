#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Progress Mirror – Nautilus Python Extension
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
# NAME: Progress Mirror – Nautilus Python Extension
# DESC: Pops up a small window in front of Nautilus during long copy/move
#       operations, mirroring (read-only) the progress of the native bubble
#       widgets. Short operations stay silent and the native progress circle
#       is left untouched; the mirror's cancel button relays to the native
#       cancel button, so Nautilus keeps owning its GCancellable.
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
# INSTALL:
#   cp progress-mirror.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q
#
# ASSUMPTIONS (from nautilus-progress-info-widget.c — verify with
# GTK_DEBUG=interactive nautilus, or with DEBUG = True):
#   1. One operation = one "NautilusProgressInfoWidget" widget, present in the
#      Nautilus window's widget tree (inside the popover).
#   2. Its children: a Gtk.ProgressBar, two Gtk.Labels (order: status, then
#      details) and a Gtk.Button (cancel).
#   3. Nautilus has two indicators (header bar and a bottom bar on narrow
#      windows), so the same operation appears twice. We de-duplicate on the
#      status text.

import time
import locale

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import Nautilus, GObject, Gtk, Adw, GLib, Pango

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
DEBUG       = False   # True: print the "Progress" widget types found in the terminal
TICK_MS     = 250     # how often the native widgets are polled
SHOW_DELAY  = 0.5     # seconds: only show the box if the operation outlives this
                      # (avoids flicker on NVMe)
NATIVE_TYPE = "NautilusProgressInfoWidget"

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "title":  "Opérations en cours",
        "cancel": "Annuler",
    }
elif _lang.startswith("de"):
    T = {
        "title":  "Laufende Vorgänge",
        "cancel": "Abbrechen",
    }
elif _lang.startswith("es"):
    T = {
        "title":  "Operaciones en curso",
        "cancel": "Cancelar",
    }
elif _lang.startswith("pt"):
    T = {
        "title":  "Operações em andamento",
        "cancel": "Cancelar",
    }
else:
    T = {
        "title":  "File operations",
        "cancel": "Cancel",
    }


# ---------------------------------------------------------------------------
# Reading the native widgets
# ---------------------------------------------------------------------------
def _collect_natives(widget, out):
    if type(widget).__name__ == NATIVE_TYPE:
        out.append(widget)
        return
    child = widget.get_first_child()
    while child:
        _collect_natives(child, out)
        child = child.get_next_sibling()


def _gather(widget, labels, bars, buttons):
    if isinstance(widget, Gtk.Label):
        labels.append(widget)
    elif isinstance(widget, Gtk.ProgressBar):
        bars.append(widget)
    elif isinstance(widget, Gtk.Button):
        buttons.append(widget)
    child = widget.get_first_child()
    while child:
        _gather(child, labels, bars, buttons)
        child = child.get_next_sibling()


class _Info:
    """Snapshot of one operation's state, read off the native widget."""

    def __init__(self, native):
        labels, bars, buttons = [], [], []
        _gather(native, labels, bars, buttons)
        self.status   = labels[0].get_text() if labels else ""
        self.details  = labels[1].get_text() if len(labels) > 1 else ""
        self.fraction = bars[0].get_fraction() if bars else 0.0
        self.button   = buttons[0] if buttons else None
        self.key      = self.status          # de-duplication key
        self.done     = self.fraction >= 0.999


def _debug_dump(window):
    seen = set()

    def walk(w, depth=0):
        name = type(w).__name__
        if "Progress" in name and (name, depth) not in seen:
            seen.add((name, depth))
            print(f"[progress-mirror] {'  ' * depth}{name}")
        child = w.get_first_child()
        while child:
            walk(child, depth + 1)
            child = child.get_next_sibling()

    walk(window)


# ---------------------------------------------------------------------------
# Centering over the Nautilus window (X11)
# ---------------------------------------------------------------------------
def _center_on_parent_x11(win, parent):
    """GTK4 offers no API to position a toplevel, and Mutter does not center
    those windows on their parent. Under X11 the window is therefore moved
    manually via Xlib (ctypes, separate X connection). Under Wayland (or
    whenever anything is missing): silently does nothing."""
    try:
        import ctypes
        import ctypes.util
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11

        s_win, s_par = win.get_surface(), parent.get_surface()
        if not (isinstance(s_win, GdkX11.X11Surface)
                and isinstance(s_par, GdkX11.X11Surface)):
            return
        lib = ctypes.util.find_library("X11")
        if not lib:
            return

        c = ctypes
        x11 = c.CDLL(lib)
        x11.XOpenDisplay.restype = c.c_void_p
        x11.XOpenDisplay.argtypes = [c.c_char_p]
        x11.XDefaultRootWindow.restype = c.c_ulong
        x11.XDefaultRootWindow.argtypes = [c.c_void_p]
        x11.XGetGeometry.restype = c.c_int
        x11.XGetGeometry.argtypes = [
            c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong),
            c.POINTER(c.c_int), c.POINTER(c.c_int),
            c.POINTER(c.c_uint), c.POINTER(c.c_uint),
            c.POINTER(c.c_uint), c.POINTER(c.c_uint)]
        x11.XTranslateCoordinates.restype = c.c_int
        x11.XTranslateCoordinates.argtypes = [
            c.c_void_p, c.c_ulong, c.c_ulong, c.c_int, c.c_int,
            c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_ulong)]
        x11.XMoveWindow.argtypes = [c.c_void_p, c.c_ulong, c.c_int, c.c_int]
        x11.XFlush.argtypes = [c.c_void_p]
        x11.XCloseDisplay.argtypes = [c.c_void_p]

        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return
        try:
            def size_of(xid):
                root = c.c_ulong()
                x, y = c.c_int(), c.c_int()
                w, h, bw, depth = c.c_uint(), c.c_uint(), c.c_uint(), c.c_uint()
                x11.XGetGeometry(dpy, xid, c.byref(root), c.byref(x), c.byref(y),
                                 c.byref(w), c.byref(h), c.byref(bw), c.byref(depth))
                return w.value, h.value

            xid_win, xid_par = s_win.get_xid(), s_par.get_xid()
            ox, oy = c.c_int(), c.c_int()
            child = c.c_ulong()
            x11.XTranslateCoordinates(dpy, xid_par, x11.XDefaultRootWindow(dpy),
                                      0, 0, c.byref(ox), c.byref(oy), c.byref(child))
            pw, ph = size_of(xid_par)
            ww, wh = size_of(xid_win)
            x11.XMoveWindow(dpy, xid_win,
                            ox.value + (pw - ww) // 2,
                            oy.value + (ph - wh) // 2)
            x11.XFlush(dpy)
        finally:
            x11.XCloseDisplay(dpy)
    except Exception as exc:
        if DEBUG:
            print(f"[progress-mirror] centering unavailable: {exc}")


# ---------------------------------------------------------------------------
# Mirror window
# ---------------------------------------------------------------------------
class _MirrorRow:
    def __init__(self, on_cancel):
        self.native_button = None

        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left.set_hexpand(True)

        self.status = Gtk.Label(xalign=0.0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.set_max_width_chars(45)
        left.append(self.status)

        self.bar = Gtk.ProgressBar()
        self.bar.set_hexpand(True)
        left.append(self.bar)

        self.details = Gtk.Label(xalign=0.0)
        self.details.add_css_class("dim-label")
        self.details.add_css_class("caption")
        left.append(self.details)

        self.box.append(left)

        self.cancel = Gtk.Button.new_from_icon_name("window-close-symbolic")
        self.cancel.set_tooltip_text(T["cancel"])
        self.cancel.set_valign(Gtk.Align.CENTER)
        self.cancel.add_css_class("circular")
        self.cancel.connect("clicked", lambda _b: on_cancel(self))
        self.box.append(self.cancel)

    def update(self, info):
        self.native_button = info.button
        self.status.set_text(info.status)
        self.details.set_text(info.details)
        if info.fraction <= 0.0:
            self.bar.pulse()                   # activity mode (no fraction known)
        else:
            self.bar.set_fraction(min(info.fraction, 1.0))


class _MirrorWindow(Adw.Window):
    __gtype_name__ = "ProgressMirrorWindow"

    def __init__(self, on_user_close):
        super().__init__(title=T["title"])
        self.set_default_size(420, -1)
        self.set_resizable(False)
        self._rows = {}
        self._on_user_close = on_user_close

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(self._list, f"set_margin_{side}")(16)

        # Adw.Window + ToolbarView: same rounded corners as the other tools
        # (a bare Gtk.Window does not get them from the theme).
        header = Adw.HeaderBar()
        header.set_decoration_layout(":close")
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self._list)
        self.set_content(toolbar)

        self.connect("close-request", self._on_close)

    def _on_close(self, _win):
        # The user closed the box: hide it and remember the operations still
        # running, so it is not reopened on every tick.
        self._on_user_close(set(self._rows))
        self.set_visible(False)
        return True

    def _cancel(self, row):
        # Cancel relayed to the native button: Nautilus owns the GCancellable.
        if row.native_button is not None:
            try:
                row.native_button.emit("clicked")
            except Exception:
                pass

    def sync(self, active):
        """active : dict key -> _Info. Updates, adds and drops rows."""
        for key in list(self._rows):
            if key not in active:
                self._list.remove(self._rows.pop(key).box)
        for key, info in active.items():
            row = self._rows.get(key)
            if row is None:
                row = _MirrorRow(self._cancel)
                self._rows[key] = row
                self._list.append(row.box)
            row.update(info)

    def is_empty(self):
        return not self._rows


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------
class ProgressMirror(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "ProgressMirror"

    def __init__(self):
        super().__init__()
        self._first_seen = {}     # key -> when it first appeared
        self._dismissed  = set()  # keys the user closed by hand
        self._win        = None   # strong ref, else the GC closes it
        self._debug_done = False
        GLib.timeout_add(TICK_MS, self._tick)

    def _dismiss(self, keys):
        self._dismissed |= keys

    def _tick(self):
        seen, parent = {}, None
        for win in Gtk.Window.list_toplevels():
            if "Nautilus" not in type(win).__name__:
                continue
            if DEBUG and not self._debug_done:
                _debug_dump(win)
            natives = []
            _collect_natives(win, natives)
            for native in natives:
                info = _Info(native)
                if info.key and info.key not in seen:   # de-duplication
                    seen[info.key] = info
                    parent = parent or win
        self._debug_done = True

        now = time.monotonic()
        for key in seen:
            self._first_seen.setdefault(key, now)
        for key in list(self._first_seen):
            if key not in seen:                          # operation gone
                del self._first_seen[key]
                self._dismissed.discard(key)

        active = {
            k: v for k, v in seen.items()
            if not v.done
            and k not in self._dismissed
            and now - self._first_seen[k] >= SHOW_DELAY
        }
        self._update_window(active, parent)
        return True

    def _update_window(self, active, parent):
        if not active:
            if self._win is not None and self._win.get_visible():
                self._win.sync({})
                self._win.set_visible(False)
            return
        if self._win is None:
            self._win = _MirrorWindow(self._dismiss)
        self._win.sync(active)
        if not self._win.get_visible():
            if parent is not None:
                self._win.set_transient_for(parent)   # wanted here: "dialog" feel
            # Idle turn instead of presenting straight from the tick: gives the
            # window manager a beat to map the toplevel first, which is what
            # keeps the cancel button clickable on Wayland (same rationale as
            # the settings dialogs across this repo).
            GLib.idle_add(self._present, parent)

    def _present(self, parent):
        if self._win is not None and not self._win.get_visible():
            self._win.present()
            if parent is not None:
                # Give the window a moment to be shown before moving it.
                GLib.timeout_add(120, self._center, parent)
        return False

    def _center(self, parent):
        if self._win is not None and self._win.get_visible():
            _center_on_parent_x11(self._win, parent)
        return False

    def get_file_items(self, files):
        return []

    def get_background_items(self, folder):
        return []
