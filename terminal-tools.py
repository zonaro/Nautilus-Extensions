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
#       Also opens a synced terminal that follows the browsed folder.
# INSTALL:
#   cp terminal-tools.py follow-shell.py ~/.local/share/nautilus-python/extensions/
#   nautilus -q

import json
import locale
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import traceback
import uuid
import weakref

import gi

gi.require_version("Gtk", "4.0")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gio, GLib, Gtk, Nautilus

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
        "open_follow_label": "Ouvrir un terminal synchronisé ici",
        "tip_open_follow":  "Ouvrir un terminal qui suit cette fenêtre pendant la navigation",
        "run_follow_label": "Exécuter dans le terminal synchronisé",
        "run_follow_label_many": "Exécuter {n} scripts dans le terminal synchronisé",
        "tip_run_follow":   "Exécuter ce script dans le terminal qui suit Nautilus",
        "tip_run_follow_many": "Exécuter {n} scripts dans le terminal qui suit Nautilus",
        "err_follow_unsupported": "Cette version de Nautilus n'expose pas le dossier courant — le suivi est désactivé.",
        "err_follow_shell": "Ce shell n'annonce pas son invite : le suivi en direct est indisponible (bash, zsh et fish sont pris en charge).",
        "err_follow_detached": "Le terminal synchronisé n'est plus joignable.",
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
        "open_follow_label": "Abrir terminal sincronizado aquí",
        "tip_open_follow":  "Abrir una terminal que sigue esta ventana mientras navegas",
        "run_follow_label": "Ejecutar en la terminal sincronizada",
        "run_follow_label_many": "Ejecutar {n} scripts en la terminal sincronizada",
        "tip_run_follow":   "Ejecutar este script en la terminal que sigue a Nautilus",
        "tip_run_follow_many": "Ejecutar {n} scripts en la terminal que sigue a Nautilus",
        "err_follow_unsupported": "Esta versión de Nautilus no expone la carpeta actual: la sincronización está desactivada.",
        "err_follow_shell": "Este shell no anuncia su prompt: el seguimiento en vivo no está disponible (se admiten bash, zsh y fish).",
        "err_follow_detached": "La terminal sincronizada ya no está accesible.",
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
        "open_follow_label": "Abrir terminal sincronizado aqui",
        "tip_open_follow":  "Abrir um terminal que acompanha esta janela enquanto você navega",
        "run_follow_label": "Executar no terminal sincronizado",
        "run_follow_label_many": "Executar {n} scripts no terminal sincronizado",
        "tip_run_follow":   "Executar este script no terminal que acompanha o Nautilus",
        "tip_run_follow_many": "Executar {n} scripts no terminal que acompanha o Nautilus",
        "err_follow_unsupported": "Esta versão do Nautilus não expõe a pasta atual — sincronização desativada.",
        "err_follow_shell": "Este shell não informa o prompt: sincronização em tempo real indisponível (bash, zsh e fish são suportados).",
        "err_follow_detached": "O terminal sincronizado não está mais acessível.",
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
        "open_follow_label": "Synchronisiertes Terminal hier öffnen",
        "tip_open_follow":  "Ein Terminal öffnen, das diesem Fenster beim Navigieren folgt",
        "run_follow_label": "Im synchronisierten Terminal ausführen",
        "run_follow_label_many": "{n} Skripte im synchronisierten Terminal ausführen",
        "tip_run_follow":   "Dieses Skript im Terminal ausführen, das Nautilus folgt",
        "tip_run_follow_many": "{n} Skripte im Terminal ausführen, das Nautilus folgt",
        "err_follow_unsupported": "Diese Nautilus-Version stellt den aktuellen Ordner nicht bereit — die Synchronisierung ist deaktiviert.",
        "err_follow_shell": "Diese Shell meldet ihren Prompt nicht: Live-Synchronisierung ist nicht verfügbar (bash, zsh und fish werden unterstützt).",
        "err_follow_detached": "Das synchronisierte Terminal ist nicht mehr erreichbar.",
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
        "open_follow_label": "Open Synced Terminal Here",
        "tip_open_follow":  "Open a terminal that follows this window as you navigate",
        "run_follow_label": "Run in Synced Terminal",
        "run_follow_label_many": "Run {n} Scripts in Synced Terminal",
        "tip_run_follow":   "Run this script in the terminal that follows Nautilus",
        "tip_run_follow_many": "Run {n} scripts in the terminal that follows Nautilus",
        "err_follow_unsupported": "This Nautilus version does not expose the current folder — following is disabled.",
        "err_follow_shell": "That shell does not report its prompt: live following is unavailable (bash, zsh and fish are supported).",
        "err_follow_detached": "The synced terminal is no longer reachable.",
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

# How to drive the terminals we know. Every entry is a tuple of
#
#   (working directory option, command option, command style)
#
# * the working directory option tells the terminal where to start; it is
#   None for terminals that cannot be told, and then the command itself
#   enters the folder;
# * the command option introduces the command ("--", "-e", "--execute") and
#   is None for terminals that take the command without any flag;
# * the command style is "argv" when the terminal receives the command as
#   separate arguments, and "line" when it joins the arguments into a single
#   shell line that it types into the terminal — OnyxSH does that, and the
#   quoting is lost on the way, so the command has to be a ready to type
#   line instead of an argument vector.
TERMINAL_SPECS = {
    "gnome-terminal":  ("--working-directory=", "--", "argv"),
    "konsole":         ("--workdir", "-e", "argv"),
    "xfce4-terminal":  ("--working-directory=", "-x", "argv"),
    "alacritty":       ("--working-directory=", "-e", "argv"),
    "kitty":           ("--directory", None, "argv"),
    "foot":            ("--working-directory=", None, "argv"),
    "tilix":           ("--working-directory=", "-e", "argv"),
    "terminator":      (None, "-x", "argv"),
    "urxvt":           ("-cd", "-e", "argv"),
    "qterminal":       ("--workdir", "-e", "argv"),
    "lxterminal":      ("--working-directory=", "-e", "argv"),
    "sakura":          ("--working-directory=", "-e", "argv"),
    "deepin-terminal": ("--workdir", "-e", "argv"),
    "xterm":           (None, "-e", "argv"),
    "st":              (None, "-e", "argv"),
    "onyxsh":          ("--working-directory", "--execute", "line"),
}

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
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup(schema, True) is None:
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


def _terminal_name(tokens, path=""):
    """Guess the terminal name from its Exec line and desktop entry."""
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
        if name in TERMINAL_SPECS:
            return name
    return ""


def _probe_exec_flag(tokens):
    """Ask a terminal for its help text and look for a command flag."""
    try:
        proc = subprocess.run(
            tokens + ["--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = proc.stdout.decode("utf-8", "replace") if proc.stdout else ""
    for flag in _EXEC_FLAG_HINTS:
        if re.search(r"(?m)^\s*%s\b" % re.escape(flag), text):
            return flag
    return ""


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


def _descriptor(argv, workdir, exec_option, style):
    """Build a terminal descriptor."""
    return {
        "argv": list(argv),
        "workdir": workdir,
        "exec": exec_option,
        "style": style,
    }


def _desktop_terminal_candidates():
    """Return the descriptors of the terminals registered on the desktop."""
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
            spec = TERMINAL_SPECS.get(name)
            if spec:
                candidates.append(
                    _descriptor([resolved] + tokens[1:], spec[0], spec[1], spec[2]))
                continue
            exec_option = fields.get("TerminalExecArg")
            if not exec_option:
                exec_option = _probe_exec_flag(tokens)
            if not exec_option:
                continue
            candidates.append(
                _descriptor([resolved] + tokens[1:], None, exec_option, "argv"))
    return candidates


def _resolve_terminal_candidates():
    """Return the ordered descriptors that may launch a terminal.

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
        spec = TERMINAL_SPECS.get(_terminal_name(prefix))
        if spec:
            candidates.append(
                _descriptor(prefix, spec[0], spec[1], spec[2]))
        elif exec_arg:
            candidates.append(_descriptor(prefix, None, exec_arg, "argv"))

    # 2. The classic GNOME default-terminal key.
    name = _gsettings_string("org.gnome.desktop.preferences", "default-terminal")
    resolved = _resolve_binary(name)
    if resolved:
        spec = TERMINAL_SPECS.get(os.path.basename(name).lower())
        if spec:
            candidates.append(_descriptor([resolved], spec[0], spec[1], spec[2]))

    # 3. The freedesktop launcher, which honours the user's default.
    resolved = _resolve_binary("xdg-terminal-exec")
    if resolved:
        candidates.append(_descriptor([resolved, "--"], None, None, "argv"))

    # 4. Terminal emulators installed on PATH.
    for name, spec in TERMINAL_SPECS.items():
        resolved = _resolve_binary(name)
        if resolved:
            candidates.append(_descriptor([resolved], spec[0], spec[1], spec[2]))

    # 5. Terminal emulators known only to the desktop.
    candidates.extend(_desktop_terminal_candidates())

    return candidates


_TERMINAL_CACHE = []


def _terminal_candidates():
    """Return the cached terminal descriptors.

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


def _option_args(option, value):
    """Return the tokens that pass *value* to *option*."""
    if option is None:
        return []
    if option.endswith("="):
        return [option + value]
    return [option, value]


def _exec_args(option, *args):
    """Return the tokens that pass the command to *option*."""
    if option is None:
        return list(args)
    return [option] + list(args)


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


def _open_argv(descriptor, folder):
    """Return the argv that opens a clean shell inside *folder*.

    When the terminal knows how to start in a folder, no command is typed
    into it at all: the shell comes up clean, on the right directory.
    """
    argv = list(descriptor["argv"])
    workdir = _option_args(descriptor["workdir"], folder)
    if workdir:
        return argv + workdir
    if descriptor["style"] == "line":
        line = 'cd %s && exec "${SHELL:-/bin/bash}"' % shlex.quote(folder)
        return argv + _exec_args(descriptor["exec"], line)
    script = 'cd %s || exit 1\nexec "${SHELL:-/bin/bash}"' % shlex.quote(folder)
    return argv + _exec_args(descriptor["exec"], _shell(), "-c", script)


def _run_argv(descriptor, scripts, sudo=False):
    """Return the argv that runs every script of *scripts* in the terminal."""
    commands = []
    for script in scripts:
        command = _script_argv(script)
        if sudo:
            command = ["sudo"] + command
        commands.append((os.path.dirname(script), command))

    argv = list(descriptor["argv"])
    workdir = _option_args(descriptor["workdir"], commands[0][0])
    start = commands[0][0] if workdir else None

    if descriptor["style"] == "line":
        parts = []
        for directory, command in commands:
            text = " ".join(shlex.quote(part) for part in command)
            if directory != start:
                text = "cd %s && %s" % (shlex.quote(directory), text)
            parts.append(text)
        line = "%s; echo %s\"$?\"" % (
            "; ".join(parts), shlex.quote(T["exit_code"] + ": "))
        return argv + workdir + _exec_args(descriptor["exec"], line)

    lines = []
    for directory, command in commands:
        text = " ".join(shlex.quote(part) for part in command)
        lines.append("cd %s && %s" % (shlex.quote(directory), text))
    script = _build_run_script(lines)
    return argv + workdir + _exec_args(descriptor["exec"], _shell(), "-c", script)


def _spawn(argv):
    """Start *argv*, returning True when the process was launched."""
    try:
        subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return True


def _launch_open(folder):
    """Open the default terminal with a clean shell in *folder*."""
    for descriptor in _terminal_candidates():
        if _spawn(_open_argv(descriptor, folder)):
            return True
    return False


def _launch_run(scripts, sudo=False):
    """Open the default terminal and run every script of *scripts*."""
    for descriptor in _terminal_candidates():
        if _spawn(_run_argv(descriptor, scripts, sudo)):
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
# Following the browsed folder
# ---------------------------------------------------------------------------

# The relay (follow-shell.py) owns one Unix socket per session in a registry
# directory shared by every process involved: the extension writes "cd"
# requests there, the relay applies them at the next shell prompt. Nothing
# here is terminal specific, so every emulator works the same way.
FOLLOW_SCRIPT_NAME = "follow-shell.py"
FOLLOW_SOCKET_TEMPLATE = "s-%s.sock"
FOLLOW_CURRENT_NAME = "current"
FOLLOW_LOG_NAME = "follow-nautilus.log"
FOLLOW_DEBUG_VAR = "NAUTILUS_FOLLOW_DEBUG"
FOLLOW_DEBOUNCE_MS = 250
FOLLOW_RESCAN_MS = 2000
FOLLOW_TIMEOUT = 1.0
FOLLOW_INSTALL_DIRS = (
    "~/.local/share/nautilus-python/extensions",
    "/usr/share/zonaro-nautilus-extensions",
)

# Cleared the first time the host shows no window slot able to report its
# location: from then on the menu entry opens a plain terminal instead.
_FOLLOW_SUPPORTED = True


def _follow_debug_enabled():
    """True when the extension should keep a debug log."""
    return bool(os.environ.get(FOLLOW_DEBUG_VAR))


def _follow_registry():
    """Return the registry directory shared with the relays, mode 0700."""
    override = os.environ.get("NAUTILUS_FOLLOW_DIR")
    if override:
        path = override
    else:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime and os.path.isabs(runtime):
            path = os.path.join(runtime, "nautilus-follow")
        else:
            uid = os.getuid() if hasattr(os, "getuid") else 0
            path = "/tmp/nautilus-follow-%d" % uid
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _follow_log(message):
    """Append a timestamped line to the debug log, when debugging is on."""
    if not _follow_debug_enabled():
        return
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(_follow_registry(), FOLLOW_LOG_NAME), "a",
                  encoding="utf-8") as handle:
            handle.write("%s %s\n" % (stamp, message))
    except Exception:
        pass


def _follow_error(where):
    """Log the exception being handled, without raising another one."""
    if not _follow_debug_enabled():
        return
    try:
        lines = traceback.format_exc().strip().splitlines()
        _follow_log("%s failed: %s" % (where, lines[-1] if lines else "?"))
    except Exception:
        pass


def _follow_token():
    """Return the 12 hex characters that name one relay session."""
    return uuid.uuid4().hex[:12]


def _follow_socket_path(token):
    """Return the socket of the relay *token*."""
    return os.path.join(_follow_registry(), FOLLOW_SOCKET_TEMPLATE % token)


def _follow_current_socket():
    """Return the socket of the most recently started relay, or "".

    The relays write their own absolute socket path to the "current" file,
    so a session opened by another Nautilus process (or before this one
    attached a window) is still reachable.
    """
    try:
        with open(os.path.join(_follow_registry(), FOLLOW_CURRENT_NAME),
                  encoding="utf-8") as handle:
            line = handle.readline().strip()
    except OSError:
        return ""
    if not line or not os.path.isabs(line):
        return ""
    return line


def _follow_script_dirs():
    """Return the directories that may hold follow-shell.py, best first."""
    here = os.path.dirname(os.path.abspath(__file__))
    return (here,) + tuple(os.path.expanduser(d) for d in FOLLOW_INSTALL_DIRS)


def _follow_script(directories=None):
    """Return the installed follow-shell.py, or "" when there is none."""
    if directories is None:
        directories = _follow_script_dirs()
    for directory in directories:
        if not directory:
            continue
        candidate = os.path.join(os.path.expanduser(directory), FOLLOW_SCRIPT_NAME)
        if os.path.isfile(candidate):
            return candidate
    return ""


def _follow_python():
    """Return the Python that runs the relay."""
    return shutil.which("python3") or sys.executable or "python3"


def _follow_command_args(folder, token, script, python, debug=False):
    """Return the relay command line as an argument vector."""
    parts = [python, script, "--token", token, "--cwd", folder]
    if debug:
        parts.append("--debug")
    return parts


def _follow_argv(descriptor, folder, token, script, python=None, debug=None):
    """Return the argv that starts a relay terminal in *folder*.

    The command follows the terminal's command style: an argument vector for
    "argv" terminals and one fully quoted shell line for "line" terminals,
    which join the arguments themselves and would lose the quoting.
    """
    if python is None:
        python = _follow_python()
    if debug is None:
        debug = _follow_debug_enabled()
    command = _follow_command_args(folder, token, script, python, debug)
    argv = list(descriptor["argv"]) + _option_args(descriptor["workdir"], folder)
    if descriptor["style"] == "line":
        line = " ".join(shlex.quote(part) for part in command)
        return argv + _exec_args(descriptor["exec"], line)
    return argv + _exec_args(descriptor["exec"], *command)


def _launch_follow(folder, token):
    """Open a relay terminal in *folder*.

    Returns (launched, following). *following* is False when follow-shell.py
    is not installed: a plain terminal is opened instead, because a terminal
    in the right folder is still what the user asked for.
    """
    script = _follow_script()
    if not script:
        _follow_log("follow-shell.py is not installed; opened a plain terminal")
        return _launch_open(folder), False
    python = _follow_python()
    for descriptor in _terminal_candidates():
        if _spawn(_follow_argv(descriptor, folder, token, script, python)):
            _follow_log("relay %s started in %s" % (token, folder))
            return True, True
    return False, False


def _follow_send(socket_path, payload, timeout=FOLLOW_TIMEOUT, reply=True):
    """Write one JSON line to a relay socket and return its reply.

    One connection per request, closed right after the answer, and a single
    deadline shared by the connect, the write and the read. ``None`` means
    the relay could not be reached or did not answer; with ``reply=False`` a
    written request returns an empty dict, so callers must compare with
    ``is None`` and not with the truthiness of the result.
    """
    try:
        message = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    except (TypeError, ValueError):
        return None
    deadline = time.monotonic() + max(0.05, timeout)
    answer = b""
    sock = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(max(0.05, deadline - time.monotonic()))
        sock.connect(socket_path)
        sock.sendall(message)
        if not reply:
            return {}
        while b"\n" not in answer and len(answer) <= 65536:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(max(0.01, remaining))
            chunk = sock.recv(65536)
            if not chunk:
                break
            answer += chunk
    except Exception:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    line = answer.split(b"\n", 1)[0].strip()
    if not line:
        return None
    try:
        parsed = json.loads(line.decode("utf-8", "replace"))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _follow_debounce(pending, key, callback, delay=FOLLOW_DEBOUNCE_MS,
                     schedule=None, cancel=None):
    """Restart the timer of *key* so only the last change is delivered.

    *pending* maps a key to its running source id; the previous source is
    removed before the new one is scheduled, which is what keeps one timer
    per window. Returns the new source id, or None when it cannot be started.
    """
    if schedule is None:
        schedule = GLib.timeout_add
    if cancel is None:
        cancel = GLib.source_remove
    previous = pending.pop(key, None)
    if previous is not None:
        try:
            cancel(previous)
        except Exception:
            pass

    def _fire():
        pending.pop(key, None)
        try:
            callback()
        except Exception:
            _follow_error("debounced follow")
        return False

    try:
        source = schedule(delay, _fire)
    except Exception:
        _follow_error("follow debounce")
        return None
    pending[key] = source
    return source


def _widget_type_name(widget):
    """Return the GTK type name of *widget*, or "" when it has none."""
    try:
        name = GObject.type_name(widget)
    except Exception:
        name = ""
    if not name:
        name = getattr(getattr(widget, "__gtype__", None), "name", "") or ""
    return name


def _widget_children(widget):
    """Yield the direct children of *widget* through the GTK4 API."""
    try:
        child = widget.get_first_child()
    except Exception:
        return
    while child is not None:
        yield child
        try:
            child = child.get_next_sibling()
        except Exception:
            return


def _iter_widgets(root):
    """Walk the widget tree of *root* breadth first."""
    if root is None:
        return
    queue = [root]
    while queue:
        node = queue.pop(0)
        yield node
        queue.extend(_widget_children(node))


def _iter_slots(window):
    """Return the Nautilus window slots found in *window*.

    The slot type is not exported in the introspection data of every
    Nautilus, so the widget tree is matched on its type name.
    """
    if window is None:
        return []
    return [widget for widget in _iter_widgets(window)
            if "NautilusWindowSlot" in _widget_type_name(widget)]


def _slot_location(slot):
    """Return the Gio.File of *slot*, or None (navigating, remote, missing)."""
    try:
        return slot.get_property("location")
    except Exception:
        return None


def _slot_has_location(slot):
    """True when the slot exposes a readable 'location' property."""
    try:
        slot.get_property("location")
    except Exception:
        return False
    return True


def _slot_path(slot):
    """Return the local folder shown by *slot*, or "" for remote locations."""
    location = _slot_location(slot)
    if location is None:
        return ""
    try:
        path = location.get_path()
    except Exception:
        return ""
    if not path or not os.path.isabs(path):
        return ""
    return path


def _active_slot(window, slots=None):
    """Return the slot the user is looking at, or None."""
    if slots is None:
        slots = _iter_slots(window)
    for slot in slots:
        try:
            if slot.get_property("active"):
                return slot
        except Exception:
            continue
    try:
        active = window.get_property("active-slot")
    except Exception:
        active = None
    return active


def _widget_visible(widget):
    """Return the visibility of *widget*, assuming True when it cannot tell."""
    try:
        return bool(widget.get_visible())
    except Exception:
        return True


def _nautilus_windows():
    """Return the Gtk windows of the running application, best effort."""
    windows = []
    try:
        app = Gtk.Application.get_default()
        if app is not None:
            windows = [w for w in app.get_windows() if isinstance(w, Gtk.Window)]
    except Exception:
        windows = []
    if not windows:
        try:
            toplevels = Gtk.Window.get_toplevels()
            for index in range(toplevels.get_n_items()):
                item = toplevels.get_item(index)
                if isinstance(item, Gtk.Window):
                    windows.append(item)
        except Exception:
            pass
    return windows


def _active_nautilus_window():
    """Return the visible window the user is working in, or None."""
    try:
        windows = [w for w in _nautilus_windows() if _widget_visible(w)]
    except Exception:
        return None
    for window in windows:
        try:
            if window.is_active():
                return window
        except Exception:
            continue
    return windows[0] if windows else None


def _active_path(window):
    """Return the folder of the active slot of *window*, or ""."""
    if window is None:
        return ""
    return _slot_path(_active_slot(window))


def _follow_supported(window=None):
    """Return True while the host lets us read the browsed folder.

    The answer is cached for the life of the process only once the host has
    actually answered: a Nautilus that does not expose its window slots will
    not start doing so, so a slot we *can* see but *cannot* read disables
    following for good. A missing window or a window that has not finished
    building proves nothing about the host, so it never caches — one awkward
    click must not turn following off until the next restart.
    """
    global _FOLLOW_SUPPORTED
    if not _FOLLOW_SUPPORTED:
        return False
    if window is None:
        return False
    slots = _iter_slots(window)
    for slot in slots:
        if _slot_has_location(slot):
            return True
    if not slots:
        return False  # transient: the window is still being built
    _FOLLOW_SUPPORTED = False
    _follow_log("no Nautilus window slot exposes 'location'; following disabled")
    return False


class _FollowWatcher:
    """Keep the relay terminals of each window in the browsed folder.

    One instance lives in the extension. A window is held weakly, its slots
    are connected once and re-scanned every two seconds, and a closed window
    detaches without keeping Nautilus alive. Every entry point swallows its
    exceptions: a raising GTK callback would take the file manager down with
    it, and following is never worth losing a window over.
    """

    def __init__(self):
        self._windows = {}
        self._rescan_source = None
        self._detach_notified = False

    # -- attach / detach ----------------------------------------------------

    def attach(self, window, token):
        """Follow *window* with *token*, watching the window when needed."""
        try:
            if window is None:
                return False
            key = id(window)
            state = self._windows.get(key)
            if state is not None and state["window"]() is not window:
                self._detach(key)
                state = None
            if state is None:
                state = {
                    "window": weakref.ref(window),
                    "tokens": [],
                    "slots": {},
                    "handlers": [],
                    "debounce": {},
                    "path": "",
                }
                self._windows[key] = state
                self._connect_window(window, key)
                self._scan(key, state)
            if token and token not in state["tokens"]:
                state["tokens"].append(token)
            self._start_rescan()
            _follow_log("window %#x follows token %s" % (key, token))
            return True
        except Exception:
            _follow_error("follow attach")
            return False

    def _detach(self, key):
        """Forget *key*, disconnecting every signal and timer it owned."""
        state = self._windows.pop(key, None)
        if state is None:
            return
        for source in list(state["debounce"].values()):
            try:
                GLib.source_remove(source)
            except Exception:
                pass
        state["debounce"].clear()
        for reference, handler in state["handlers"]:
            owner = reference()
            if owner is None:
                continue
            try:
                owner.disconnect(handler)
            except Exception:
                pass
        state["handlers"].clear()
        state["slots"].clear()
        _follow_log("detached from window %#x" % key)

    def _live(self, key):
        """Return the state of *key*, detaching it when the window is gone."""
        state = self._windows.get(key)
        if state is not None and state["window"]() is None:
            self._detach(key)
            return None
        return state

    # -- signals ------------------------------------------------------------

    def _connect(self, state, obj, signal, callback):
        """Connect *signal* without keeping *obj* alive through the list."""
        try:
            handler = obj.connect(signal, callback)
        except Exception:
            return 0
        state["handlers"].append((weakref.ref(obj), handler))
        return handler

    def _disconnect(self, state, obj=None):
        """Drop the connections of *obj*, plus the ones of dead objects."""
        remaining = []
        for reference, handler in state["handlers"]:
            owner = reference()
            if owner is None or owner is obj:
                if owner is not None:
                    try:
                        owner.disconnect(handler)
                    except Exception:
                        pass
                continue
            remaining.append((reference, handler))
        state["handlers"] = remaining

    def _connect_window(self, window, key):
        """Listen to the active tab of *window* and to its closing."""
        state = self._windows.get(key)
        if state is None:
            return
        self._connect(state, window, "notify::active-slot",
                      lambda *_args: self._on_change(key))
        self._connect(state, window, "close-request",
                      lambda *_args: self._on_close(key))

    def _on_close(self, key):
        """Stop following a window that is closing, and let it close."""
        try:
            self._detach(key)
        except Exception:
            _follow_error("follow close")
        return False

    def _scan(self, key, state=None):
        """Connect the slots that appeared since the last scan."""
        if state is None:
            state = self._live(key)
        if state is None:
            return
        window = state["window"]()
        if window is None:
            self._detach(key)
            return
        slots = _iter_slots(window)
        alive = {id(slot) for slot in slots}
        # A closed tab must not stay connected, nor stay alive through us.
        for slot_id in [value for value in state["slots"] if value not in alive]:
            self._disconnect(state, state["slots"].pop(slot_id))
        for slot in slots:
            slot_id = id(slot)
            if slot_id in state["slots"]:
                continue
            state["slots"][slot_id] = slot
            self._connect(state, slot, "notify::location",
                          lambda *_args: self._on_change(key))
            _follow_log("watching slot %#x of window %#x" % (slot_id, key))

    def _on_change(self, key):
        """Debounce a location change, then send the new folder."""
        try:
            state = self._live(key)
            if state is None:
                return
            _follow_debounce(state["debounce"], key, lambda: self._deliver(key))
        except Exception:
            _follow_error("follow change")

    def _start_rescan(self):
        """Start the two second slot scan, once per process."""
        if self._rescan_source is not None:
            return
        try:
            self._rescan_source = GLib.timeout_add(FOLLOW_RESCAN_MS, self._rescan)
        except Exception:
            self._rescan_source = None
            _follow_error("follow rescan")

    def _rescan(self):
        """Look for new tabs in every attached window."""
        try:
            for key in list(self._windows):
                self._scan(key)
        except Exception:
            _follow_error("follow rescan")
        return True

    # -- delivery -----------------------------------------------------------

    def _deliver(self, key):
        """Send the active folder of the window to its relays."""
        state = self._live(key)
        if state is None:
            return
        path = _active_path(state["window"]())
        if not path or path == state["path"]:
            return
        state["path"] = path
        payload = {"op": "cd", "path": path}
        missing = []
        refused = []
        # One deadline for the whole window: several relays must not add up
        # to several seconds inside the main loop.
        deadline = time.monotonic() + FOLLOW_TIMEOUT
        for token in list(state["tokens"]):
            remaining = deadline - time.monotonic()
            socket_path = _follow_socket_path(token)
            if remaining <= 0.05:
                missing.append(token)
                _follow_log("no time left to reach relay %s" % token)
                continue
            if _follow_send(socket_path, payload, timeout=remaining,
                            reply=False) is not None:
                continue
            if os.path.exists(socket_path):
                refused.append(token)
            else:
                missing.append(token)
                _follow_log("relay %s is not listening yet" % token)
        for token in refused:
            try:
                state["tokens"].remove(token)
            except ValueError:
                pass
        if refused:
            _follow_log("relay %s refused the connection" % ", ".join(refused))
            self._notify_detached()
        if not state["tokens"] and not missing:
            self._detach(key)
        elif state["tokens"]:
            _follow_log("cd %s (%d relay(s))" % (path, len(state["tokens"])))

    def _notify_detached(self):
        """Tell the user once that a synced terminal went away."""
        if self._detach_notified:
            return
        self._detach_notified = True
        _notify(T["err_follow_detached"])

    # -- other requests -----------------------------------------------------

    def tokens_for(self, window):
        """Return the relay tokens attached to *window*, oldest first."""
        try:
            if window is None:
                return []
            state = self._live(id(window))
            if state is None or state["window"]() is not window:
                return []
            return list(state["tokens"])
        except Exception:
            _follow_error("follow tokens")
            return []

    def send(self, window, payload, reply=True, timeout=FOLLOW_TIMEOUT):
        """Send one request to a relay of *window* and return its reply.

        The relays attached to the window are tried first; the registry
        "current" pointer is the last resort, so a session opened before
        this process saw the window still receives the request. One
        deadline covers every attempt, because this runs inside the
        Nautilus main loop. Returns None when nobody answered.
        """
        try:
            targets = [_follow_socket_path(token)
                       for token in self.tokens_for(window)]
            current = _follow_current_socket()
            if current and current not in targets:
                targets.append(current)
            deadline = time.monotonic() + max(0.05, timeout)
            for socket_path in targets:
                remaining = deadline - time.monotonic()
                if remaining <= 0.05:
                    break
                answer = _follow_send(socket_path, payload, timeout=remaining,
                                      reply=reply)
                if answer is not None:
                    return answer
        except Exception:
            _follow_error("follow send")
        return None


def _follow_run_payload(scripts, sudo=False):
    """Return the "run" requests that reproduce the menu action.

    One request per script, each carrying the folder of its file: the relay
    applies them one at a time, exactly like the terminal chain does.
    """
    requests = []
    for script in scripts:
        argv = _script_argv(script)
        if sudo:
            argv = ["sudo"] + argv
        requests.append({
            "op": "run",
            "argv": argv,
            "cwd": os.path.dirname(script) or os.getcwd(),
        })
    return requests


def _follow_run(watcher, window, scripts, sudo=False):
    """Run *scripts* in the synced terminal of *window*.

    Returns True when a relay accepted the request, False when there is no
    usable session and the caller must keep its old behaviour. A shell that
    cannot report its prompt is a usable session too: the relay refuses with
    "no-markers", the user is told why, and opening a second terminal would
    only hide the reason from them.
    """
    if watcher is None or not scripts:
        return False
    requests = _follow_run_payload(scripts, sudo)
    answer = watcher.send(window, requests[0])
    if answer is None:
        return False
    if answer.get("reason") == "no-markers":
        _notify(T["err_follow_shell"])
        return True
    if not answer.get("ok"):
        return False
    # The route is decided: hand over the rest of the selection best effort.
    for request in requests[1:]:
        watcher.send(window, request, reply=False)
    return True


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------

class TerminalToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    """Context menu entries to run scripts and to open a terminal."""

    __gtype_name__ = "TerminalToolsExtension"

    def __init__(self):
        super().__init__()
        self._follow = _FollowWatcher()

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
            items.append(self._make_open_follow_item(folders))
        return items

    def get_background_items(self, folder):
        if folder is None:
            return []
        location = folder.get_location()
        if location is None:
            return []
        path = location.get_path()
        if not path:
            return []
        return [self._make_open_item([path]),
                self._make_open_follow_item([path])]

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

    def _make_open_follow_item(self, folders):
        item = Nautilus.MenuItem(
            name="TerminalTools::OpenFollow",
            label=T["open_follow_label"],
            tip=T["tip_open_follow"],
            icon="utilities-terminal",
        )
        item.connect("activate", self._on_open_follow, folders)
        return item

    # -- actions ------------------------------------------------------------

    def _on_run(self, _item, scripts, sudo):
        if sudo and not shutil.which("sudo"):
            _notify(T["err_no_sudo"])
            return
        # A synced terminal attached to the window is the point of the follow
        # feature, so the script runs there instead of in a new window. Any
        # failure to reach it falls back to the old behaviour: routing can
        # never break "Run in Terminal".
        try:
            handled = _follow_run(self._follow, _active_nautilus_window(),
                                  scripts, sudo)
        except Exception:
            _follow_error("run in synced terminal")
            handled = False
        if handled:
            return
        if not _launch_run(scripts, sudo):
            _notify(T["err_no_terminal"])

    def _on_open(self, _item, folders):
        for folder in folders:
            if not _launch_open(folder):
                _notify(T["err_no_terminal"])
                return

    def _on_open_follow(self, _item, folders):
        """Open relay terminals for *folders* and make them follow the window."""
        window = _active_nautilus_window()
        if not _follow_supported(window):
            # The host hides its slots: a plain terminal still helps, and the
            # user deserves to know why it does not follow.
            for folder in folders:
                if not _launch_open(folder):
                    _notify(T["err_no_terminal"])
                    return
            _notify(T["err_follow_unsupported"])
            return
        for folder in folders:
            token = _follow_token()
            launched, following = _launch_follow(folder, token)
            if not launched:
                _notify(T["err_no_terminal"])
                return
            if following:
                self._follow.attach(window, token)
