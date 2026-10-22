#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Terminal Tools — Nautilus Python Extension
# AUTHOR: Kaizonaro
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
# NAME: Terminal Tools
# DESC: Adds context menu entries to run scripts in the default terminal —
#       one plain and one with sudo — and to open a terminal inside any
#       folder, both from the folder entry and from the folder background.
# INSTALL:
#   cp terminal-tools.py ~/.local/share/nautilus-python/extensions/
#   nautilus -q

import locale
import os
import re
import shlex
import shutil
import subprocess

import gi

gi.require_version("Gtk", "4.0")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gio, Nautilus

try:
    from nautilus_i18n import resolve_locale
except ImportError:  # nautilus_i18n.py not installed next to this file
    def resolve_locale():
        return locale.getlocale()[0] or ""

_lang = resolve_locale()
if _lang.startswith("fr"):
    T = {
        "app_title":        "Outils de terminal",
        "run_label":        "Exécuter dans le terminal",
        "run_label_many":   "Exécuter {n} scripts dans le terminal",
        "run_sudo_label":   "Exécuter dans le terminal avec sudo",
        "run_sudo_label_many": "Exécuter {n} scripts dans le terminal avec sudo",
        "open_here_label":  "Ouvrir un terminal ici",
        "tip_run":          "Exécuter ce script dans le terminal par défaut",
        "tip_run_many":     "Exécuter {n} scripts dans le terminal par défaut",
        "tip_run_sudo":     "Exécuter ce script en root (sudo) dans le terminal par défaut",
        "tip_run_sudo_many": "Exécuter {n} scripts en root (sudo) dans le terminal par défaut",
        "tip_open_here":    "Ouvrir un terminal dans ce dossier",
        "err_no_terminal":  "Aucun émulateur de terminal n'a été trouvé sur ce système.",
        "err_launch":       "Impossible d'ouvrir le terminal : {error}",
        "err_no_sudo":      "sudo n'est pas disponible sur ce système.",
        "press_enter":      "Appuyez sur Entrée pour fermer cette fenêtre",
        "exit_code":        "Code de sortie",
    }
elif _lang.startswith("es"):
    T = {
        "app_title":        "Herramientas de terminal",
        "run_label":        "Ejecutar en la terminal",
        "run_label_many":   "Ejecutar {n} scripts en la terminal",
        "run_sudo_label":   "Ejecutar en la terminal con sudo",
        "run_sudo_label_many": "Ejecutar {n} scripts en la terminal con sudo",
        "open_here_label":  "Abrir terminal aquí",
        "tip_run":          "Ejecutar este script en la terminal predeterminada",
        "tip_run_many":     "Ejecutar {n} scripts en la terminal predeterminada",
        "tip_run_sudo":     "Ejecutar este script como root (sudo) en la terminal predeterminada",
        "tip_run_sudo_many": "Ejecutar {n} scripts como root (sudo) en la terminal predeterminada",
        "tip_open_here":    "Abrir una terminal en esta carpeta",
        "err_no_terminal":  "No se encontró ningún emulador de terminal en este sistema.",
        "err_launch":       "No se pudo abrir la terminal: {error}",
        "err_no_sudo":      "sudo no está disponible en este sistema.",
        "press_enter":      "Pulsa Enter para cerrar esta ventana",
        "exit_code":        "Código de salida",
    }
elif _lang.startswith("pt"):
    T = {
        "app_title":        "Ferramentas de terminal",
        "run_label":        "Executar no terminal",
        "run_label_many":   "Executar {n} scripts no terminal",
        "run_sudo_label":   "Executar no terminal com sudo",
        "run_sudo_label_many": "Executar {n} scripts no terminal com sudo",
        "open_here_label":  "Abrir terminal aqui",
        "tip_run":          "Executar este script no terminal padrão",
        "tip_run_many":     "Executar {n} scripts no terminal padrão",
        "tip_run_sudo":     "Executar este script como root (sudo) no terminal padrão",
        "tip_run_sudo_many": "Executar {n} scripts como root (sudo) no terminal padrão",
        "tip_open_here":    "Abrir um terminal nesta pasta",
        "err_no_terminal":  "Nenhum emulador de terminal foi encontrado neste sistema.",
        "err_launch":       "Não foi possível abrir o terminal: {error}",
        "err_no_sudo":      "O sudo não está disponível neste sistema.",
        "press_enter":      "Pressione Enter para fechar esta janela",
        "exit_code":        "Código de saída",
    }
elif _lang.startswith("de"):
    T = {
        "app_title":        "Terminal-Werkzeuge",
        "run_label":        "Im Terminal ausführen",
        "run_label_many":   "{n} Skripte im Terminal ausführen",
        "run_sudo_label":   "Im Terminal mit sudo ausführen",
        "run_sudo_label_many": "{n} Skripte im Terminal mit sudo ausführen",
        "open_here_label":  "Terminal hier öffnen",
        "tip_run":          "Dieses Skript im Standard-Terminal ausführen",
        "tip_run_many":     "{n} Skripte im Standard-Terminal ausführen",
        "tip_run_sudo":     "Dieses Skript als root (sudo) im Standard-Terminal ausführen",
        "tip_run_sudo_many": "{n} Skripte als root (sudo) im Standard-Terminal ausführen",
        "tip_open_here":    "Ein Terminal in diesem Ordner öffnen",
        "err_no_terminal":  "Auf diesem System wurde kein Terminal-Emulator gefunden.",
        "err_launch":       "Terminal konnte nicht geöffnet werden: {error}",
        "err_no_sudo":      "sudo ist auf diesem System nicht verfügbar.",
        "press_enter":      "Eingabetaste drücken, um dieses Fenster zu schließen",
        "exit_code":        "Exit-Code",
    }
else:  # English fallback
    T = {
        "app_title":        "Terminal Tools",
        "run_label":        "Run in Terminal",
        "run_label_many":   "Run {n} Scripts in Terminal",
        "run_sudo_label":   "Run in Terminal with sudo",
        "run_sudo_label_many": "Run {n} Scripts in Terminal with sudo",
        "open_here_label":  "Open Terminal Here",
        "tip_run":          "Run this script in the default terminal",
        "tip_run_many":     "Run {n} scripts in the default terminal",
        "tip_run_sudo":     "Run this script as root (sudo) in the default terminal",
        "tip_run_sudo_many": "Run {n} scripts as root (sudo) in the default terminal",
        "tip_open_here":    "Open a terminal in this folder",
        "err_no_terminal":  "No terminal emulator was found on this system.",
        "err_launch":       "Could not open the terminal: {error}",
        "err_no_sudo":      "sudo is not available on this system.",
        "press_enter":      "Press Enter to close this window",
        "exit_code":        "Exit code",
    }

# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------

# Interpreter used to run a script that has no shebang. The value is split on
# whitespace, so "awk -f" works as well as a plain interpreter name.
SCRIPT_INTERPRETERS = {
    ".sh":   "bash",
    ".bash": "bash",
    ".zsh":  "zsh",
    ".fish": "fish",
    ".ksh":  "ksh",
    ".py":   "python3",
    ".pl":   "perl",
    ".rb":   "ruby",
    ".php":  "php",
    ".lua":  "lua",
    ".tcl":  "tclsh",
    ".awk":  "awk -f",
    ".r":    "Rscript",
}


def _read_shebang(path):
    """Return the interpreter line of a script, without the leading '#!'.

    Returns an empty string when the file has no shebang or cannot be read.
    """
    try:
        with open(path, "rb") as handle:
            first = handle.readline(512)
    except OSError:
        return ""
    if not first.startswith(b"#!"):
        return ""
    return first[2:].decode("utf-8", "replace").strip()


def _script_argv(path):
    """Return the argument vector that runs *path*.

    A shebang wins over the file extension: it is what the author asked for.
    Without a shebang the extension decides the interpreter.
    """
    shebang = _read_shebang(path)
    if shebang:
        try:
            parts = shlex.split(shebang)
        except ValueError:
            parts = []
        if parts:
            return parts + [path]
    interpreter = SCRIPT_INTERPRETERS.get(os.path.splitext(path)[1].lower())
    if interpreter:
        return interpreter.split() + [path]
    return [path]


def _is_script(path):
    """True when *path* looks like a script we know how to run."""
    if os.path.splitext(path)[1].lower() in SCRIPT_INTERPRETERS:
        return True
    return bool(_read_shebang(path))


# ---------------------------------------------------------------------------
# Terminal detection
# ---------------------------------------------------------------------------

# Flags that separate a terminal binary from the command line. The table is
# keyed by the terminal name and used for both the PATH probe and the desktop
# entry scan, so a terminal only needs to be described once.
EXEC_FLAGS = {
    "kgx":             ("--",),
    "gnome-terminal":  ("--",),
    "ptyxis":          ("--",),
    "konsole":         ("-e",),
    "xfce4-terminal":  ("-x",),
    "alacritty":       ("-e",),
    "kitty":           (),
    "wezterm":         ("start", "--"),
    "foot":            (),
    "tilix":           ("-e",),
    "terminator":      ("-x",),
    "mate-terminal":   ("-x",),
    "urxvt":           ("-e",),
    "qterminal":       ("-e",),
    "lxterminal":      ("-e",),
    "sakura":          ("-e",),
    "deepin-terminal": ("-e",),
    "st":              ("-e",),
    "xterm":           ("-e",),
    "x-terminal-emulator": ("-e",),
    "onyxsh":          ("--execute",),
}

# Terminals we know how to drive, in preference order.
KNOWN_TERMINALS = (
    "kgx",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "alacritty",
    "kitty",
    "wezterm",
    "foot",
    "tilix",
    "terminator",
    "mate-terminal",
    "urxvt",
    "qterminal",
    "lxterminal",
    "sakura",
    "deepin-terminal",
    "st",
    "xterm",
    "x-terminal-emulator",
)

# Desktop directories scanned for terminal emulators. The flatpak and snap
# exports matter: those terminals are not on PATH.
DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    "~/.local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    "~/.local/share/flatpak/exports/share/applications",
    "/var/lib/snapd/desktop/applications",
)

_FIELD_CODE = re.compile(r"%[fFuUdDnNickvmVM]")
_FLATPAK_MARKERS = re.compile(r"@@.*?@@")
_EXEC_FLAG_HINTS = ("--execute", "--exec", "--command")


def _gsettings_string(schema, key):
    """Read a string key from GSettings, or "" when the schema is missing."""
    try:
        if Gio.SettingsSchemaSource.get_default() is None:
            return ""
        if Gio.SettingsSchemaSource.get_default().lookup(schema, True) is None:
            return ""
        return Gio.Settings.new(schema).get_string(key) or ""
    except Exception:
        return ""


def _parse_desktop_entry(path):
    """Return the keys of the [Desktop Entry] group of a desktop file."""
    fields = {}
    in_group = False
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("["):
                    if in_group:
                        break  # the next group starts here
                    in_group = line == "[Desktop Entry]"
                    continue
                if not in_group or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                fields.setdefault(key, value)
    except OSError:
        return {}
    return fields


def _exec_tokens(exec_line):
    """Split a desktop Exec line into argv, dropping the field codes."""
    cleaned = _FLATPAK_MARKERS.sub(" ", exec_line)
    cleaned = _FIELD_CODE.sub(" ", cleaned)
    try:
        return shlex.split(cleaned)
    except ValueError:
        return []


def _terminal_name(tokens, path):
    """Guess the terminal name from its desktop entry and Exec line."""
    candidates = []
    for token in tokens:
        if token.startswith("--command="):
            candidates.append(token.split("=", 1)[1])
    candidates.append(tokens[0])
    app_id = os.path.basename(path)
    if app_id.endswith(".desktop"):
        app_id = app_id[: -len(".desktop")]
        if "." in app_id:
            candidates.append(app_id.rsplit(".", 1)[1])
    for candidate in candidates:
        name = os.path.basename(candidate).lower()
        if name in EXEC_FLAGS:
            return name
    return ""


def _probe_exec_flags(tokens):
    """Ask a terminal for its help text and look for an execute flag."""
    try:
        proc = subprocess.run(
            tokens + ["--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    text = proc.stdout.decode("utf-8", "replace") if proc.stdout else ""
    for flag in _EXEC_FLAG_HINTS:
        if re.search(r"(?m)^\s*%s\b" % re.escape(flag), text):
            return (flag,)
    return ()


def _desktop_terminal_candidates():
    """Return the argv prefixes of the terminals registered on the desktop."""
    candidates = []
    for directory in DESKTOP_DIRS:
        path = os.path.expanduser(directory)
        if not os.path.isdir(path):
            continue
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            continue
        for entry in entries:
            if not entry.endswith(".desktop"):
                continue
            full = os.path.join(path, entry)
            fields = _parse_desktop_entry(full)
            if "TerminalEmulator" not in fields.get("Categories", "").split(";"):
                continue
            tokens = _exec_tokens(fields.get("Exec", ""))
            if not tokens:
                continue
            resolved = _resolve_binary(tokens[0])
            if not resolved:
                continue
            name = _terminal_name(tokens, full)
            if name:
                flags = EXEC_FLAGS[name]
            elif fields.get("TerminalExecArg"):
                flags = (fields["TerminalExecArg"],)
            else:
                flags = _probe_exec_flags(tokens)
            candidates.append([resolved] + tokens[1:] + list(flags))
    return candidates


def _resolve_terminal_candidates():
    """Return the ordered argv prefixes that may launch a terminal.

    The desktop's own idea of the default terminal comes first, then the
    freedesktop launcher, then the terminals we know, and finally the ones
    that are only registered as desktop applications (flatpak, snap).
    """
    candidates = []

    # 1. The terminal application the desktop declares as the default.
    exec_path = _gsettings_string(
        "org.gnome.desktop.default-applications.terminal", "exec")
    exec_arg = _gsettings_string(
        "org.gnome.desktop.default-applications.terminal", "exec-arg")
    prefix = _resolve_exec(exec_path)
    if prefix:
        if exec_arg:
            prefix.append(exec_arg)
        candidates.append(prefix)

    # 2. The classic GNOME default-terminal key.
    name = _gsettings_string("org.gnome.desktop.preferences", "default-terminal")
    resolved = _resolve_binary(name)
    if resolved:
        flags = EXEC_FLAGS.get(os.path.basename(name).lower(), ("--",))
        candidates.append([resolved] + list(flags))

    # 3. The freedesktop launcher, which honours the user's default.
    resolved = _resolve_binary("xdg-terminal-exec")
    if resolved:
        candidates.append([resolved, "--"])

    # 4. Terminal emulators installed on PATH.
    for terminal in KNOWN_TERMINALS:
        resolved = _resolve_binary(terminal)
        if resolved:
            candidates.append([resolved] + list(EXEC_FLAGS[terminal]))

    # 5. Terminal emulators known only to the desktop.
    candidates.extend(_desktop_terminal_candidates())

    return candidates


def _resolve_binary(name):
    """Return an executable path for *name*, or "" when there is none."""
    if not name:
        return ""
    found = shutil.which(name)
    if found:
        return found
    if os.path.isabs(name) and os.path.isfile(name) and os.access(name, os.X_OK):
        return name
    return ""


def _resolve_exec(command):
    """Resolve an Exec-style command into argv, or None when it is unusable.

    The command may carry arguments ("flatpak run --command=onyxsh app.id").
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts:
        return None
    resolved = _resolve_binary(parts[0])
    if not resolved:
        return None
    return [resolved] + parts[1:]


_TERMINAL_CACHE = []


def _terminal_candidates():
    """Return the cached terminal candidates.

    An empty result is not cached, so installing a terminal emulator does
    not require a Nautilus restart.
    """
    global _TERMINAL_CACHE
    if _TERMINAL_CACHE:
        return _TERMINAL_CACHE
    candidates = _resolve_terminal_candidates()
    if candidates:
        _TERMINAL_CACHE = candidates
    return candidates


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------

def _shell():
    """Return the shell used to run the commands inside the terminal."""
    return shutil.which("bash") or shutil.which("sh") or "/bin/sh"


def _build_run_script(commands):
    """Build the shell snippet that runs *commands* and keeps the window open."""
    lines = list(commands)
    lines.append("rc=$?")
    lines.append("printf '\\n'")
    lines.append("echo %s \"$rc\"" % shlex.quote(T["exit_code"] + ": "))
    lines.append("printf %s " % shlex.quote(T["press_enter"] + " "))
    lines.append("read -r _ || true")
    lines.append("exit \"$rc\"")
    return "\n".join(lines)


def _build_open_script(workdir):
    """Build the shell snippet that opens a shell inside *workdir*."""
    return "cd %s || exit 1\nexec \"${SHELL:-/bin/bash}\"" % shlex.quote(workdir)


def _launch(script):
    """Run a shell script inside the user's terminal.

    Returns True when a terminal accepted the command.
    """
    shell = _shell()
    for prefix in _terminal_candidates():
        argv = list(prefix) + [shell, "-c", script]
        try:
            subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            continue
        return True
    return False


def _notify(body):
    """Show a desktop notification, when the host supports it."""
    try:
        app = Gio.Application.get_default()
        if app is None:
            return
        notification = Gio.Notification.new(T["app_title"])
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new("utilities-terminal"))
        app.send_notification(None, notification)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------

class TerminalToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    """Context menu entries to run scripts and to open a terminal."""

    __gtype_name__ = "TerminalToolsExtension"

    # -- menu ---------------------------------------------------------------

    def get_file_items(self, files):
        scripts = []
        folders = []
        for entry in files:
            if entry.get_uri_scheme() != "file":
                continue
            location = entry.get_location()
            if location is None:
                continue
            path = location.get_path()
            if not path:
                continue
            if entry.is_directory():
                folders.append(path)
            elif _is_script(path):
                scripts.append(path)

        items = []
        if scripts:
            items.append(self._make_run_item(scripts, sudo=False))
            items.append(self._make_run_item(scripts, sudo=True))
        if folders:
            items.append(self._make_open_item(folders))
        return items

    def get_background_items(self, folder):
        if folder is None:
            return []
        path = folder.get_location().get_path()
        if not path:
            return []
        return [self._make_open_item([path])]

    # -- item builders ------------------------------------------------------

    def _make_run_item(self, scripts, sudo):
        many = len(scripts) > 1
        if sudo:
            name = "TerminalTools::RunSudo"
            label = T["run_sudo_label_many"] if many else T["run_sudo_label"]
            tip = T["tip_run_sudo_many"] if many else T["tip_run_sudo"]
            icon = "system-run"
        else:
            name = "TerminalTools::Run"
            label = T["run_label_many"] if many else T["run_label"]
            tip = T["tip_run_many"] if many else T["tip_run"]
            icon = "utilities-terminal"
        if many:
            label = label.format(n=len(scripts))
            tip = tip.format(n=len(scripts))

        item = Nautilus.MenuItem(name=name, label=label, tip=tip, icon=icon)
        item.connect("activate", self._on_run, scripts, sudo)
        return item

    def _make_open_item(self, folders):
        item = Nautilus.MenuItem(
            name="TerminalTools::OpenHere",
            label=T["open_here_label"],
            tip=T["tip_open_here"],
            icon="utilities-terminal",
        )
        item.connect("activate", self._on_open, folders)
        return item

    # -- actions ------------------------------------------------------------

    def _on_run(self, _item, scripts, sudo):
        if sudo and not shutil.which("sudo"):
            _notify(T["err_no_sudo"])
            return

        commands = []
        for script in scripts:
            argv = _script_argv(script)
            if sudo:
                argv = ["sudo"] + argv
            command = " ".join(shlex.quote(part) for part in argv)
            directory = os.path.dirname(script)
            commands.append("cd %s && %s" % (shlex.quote(directory), command))

        if not _launch(_build_run_script(commands)):
            _notify(T["err_no_terminal"])

    def _on_open(self, _item, folders):
        for folder in folders:
            if not _launch(_build_open_script(folder)):
                _notify(T["err_no_terminal"])
                return
