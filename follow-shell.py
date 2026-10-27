#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Follow Shell — Synced Terminal Relay
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
# NAME: Follow Shell
# DESC: Keeps one terminal attached to the Nautilus window it was opened
#       from. Relay mode owns a pty, spawns the user's shell with invisible
#       prompt markers, relays bytes verbatim and injects cd/run requests
#       only at a clean prompt. Send mode talks to that relay over a Unix
#       socket (cd, run, status).
# INSTALL:
#   cp follow-shell.py ~/.local/share/nautilus-python/extensions/
#   chmod 755 ~/.local/share/nautilus-python/extensions/follow-shell.py
#   nautilus -q

import argparse
import json
import os
import pty
import re
import select
import selectors
import shlex
import shutil
import signal
import socket
import sys
import termios
import time
import tty

# ---------------------------------------------------------------------------
# Registry (shared with terminal-tools.py)
# ---------------------------------------------------------------------------

PROMPT_MARKER = b"\x1b]777;nautilus-follow;prompt\x07"
REGISTRY_ENV = "NAUTILUS_FOLLOW_DIR"
DEFAULT_SHELL = "/bin/bash"
MARKER_TIMEOUT = 5.0
SOCKET_TIMEOUT = 2.0

_TOKEN_RE = re.compile(r"^[0-9a-f]{12}$")


def valid_token(token):
    """True when *token* is the 12 lowercase hex chars the registry expects."""
    return bool(token) and bool(_TOKEN_RE.match(token))


def registry_dir(root=None):
    """Return the registry root, without creating it.

    An explicit *root* or ``$NAUTILUS_FOLLOW_DIR`` wins, then
    ``$XDG_RUNTIME_DIR/nautilus-follow``, then ``/tmp/nautilus-follow-<uid>``.
    """
    explicit = root or os.environ.get(REGISTRY_ENV)
    if explicit:
        return explicit
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isabs(runtime):
        return os.path.join(runtime, "nautilus-follow")
    return "/tmp/nautilus-follow-%d" % os.getuid()


def ensure_registry(root=None):
    """Create the registry root with mode 0700 and return its path."""
    path = registry_dir(root)
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def socket_path(token, root=None):
    """Return the Unix socket path of *token*."""
    return os.path.join(registry_dir(root), "s-%s.sock" % token)


def meta_path(token, root=None):
    """Return the metadata path of *token*."""
    return os.path.join(registry_dir(root), "s-%s.meta.json" % token)


def current_path(root=None):
    """Return the file that names the most recently started relay."""
    return os.path.join(registry_dir(root), "current")


def rc_root(root=None):
    """Return the directory that holds the generated rc directories."""
    return os.path.join(registry_dir(root), "rc")


def rc_dir(token, root=None):
    """Return the generated rc directory of *token*."""
    return os.path.join(rc_root(root), token)


def relay_log_path(token, root=None):
    """Return the debug log path of a relay started with ``--debug``."""
    return os.path.join(registry_dir(root), "%s.relay.log" % token)


def extension_log_path(root=None):
    """Return the debug log path used by the Nautilus extension."""
    return os.path.join(registry_dir(root), "follow-nautilus.log")


def meta_record(token, pid, cwd, shell, mode, started=None, nautilus_pid=None):
    """Build the metadata object written next to the socket."""
    return {
        "token": token,
        "pid": pid,
        "started": started or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cwd": cwd,
        "shell": shell,
        "mode": mode,
        "nautilus_pid": nautilus_pid,
    }


def _write_text_file(path, text, mode=0o600):
    """Write *text* to *path* atomically, with *mode*."""
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


# ---------------------------------------------------------------------------
# Wire protocol
# ---------------------------------------------------------------------------

class ProtocolError(ValueError):
    """Raised when a line of the wire protocol cannot be decoded."""


def encode_message(message):
    """Encode one protocol object as a newline terminated UTF-8 line."""
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    return (payload + "\n").encode("utf-8")


def decode_message(line):
    """Decode one protocol line into a dict, raising ProtocolError."""
    if isinstance(line, bytes):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("message is not valid UTF-8: %s" % exc) from exc
    else:
        text = line
    text = text.strip()
    if not text:
        raise ProtocolError("empty message")
    try:
        message = json.loads(text)
    except ValueError as exc:
        raise ProtocolError("message is not JSON: %s" % exc) from exc
    if not isinstance(message, dict):
        raise ProtocolError("message is not a JSON object")
    return message


class LineBuffer:
    """Split decoded bytes into newline terminated lines across reads."""

    def __init__(self, limit=4 * 1024 * 1024):
        self.limit = limit
        self._buffer = b""

    def feed(self, data):
        """Add *data* and return every complete line it completed."""
        self._buffer += data
        lines = self._buffer.split(b"\n")
        self._buffer = lines.pop()
        if len(self._buffer) > self.limit:
            self._buffer = b""
        return lines


class MarkerScanner:
    """Find the prompt marker in a byte stream split into arbitrary chunks.

    The marker is emitted by the shell just before the prompt, so the prompt
    text itself follows it in the same chunk. Detection therefore means "the
    marker has been seen", not "the marker is the last byte of the chunk".
    """

    def __init__(self, marker=PROMPT_MARKER):
        self.marker = marker
        self._tail = b""

    def feed(self, data):
        """Return True when *data* completes an occurrence of the marker."""
        combined = self._tail + data
        if self.marker in combined:
            self._tail = b""
            return True
        keep = len(self.marker) - 1
        self._tail = combined[-keep:] if keep > 0 else b""
        return False


# ---------------------------------------------------------------------------
# Injection policy
# ---------------------------------------------------------------------------

def injection_blocker(state, input_dirty, foreground, alive, mode="marker"):
    """Return why injection must wait, or "" when it is safe.

    Injection is safe only when the shell is alive, owns the pty foreground
    process group, is sitting at a marked prompt and nothing was typed into
    the input buffer.
    """
    if mode != "marker":
        return "no-markers"
    if not alive:
        return "dead"
    if not foreground:
        return "not-foreground"
    if input_dirty:
        return "typing"
    if state != "prompt":
        return "starting" if state == "starting" else "busy"
    return ""


def can_inject(state, input_dirty, foreground, alive, mode="marker"):
    """True when the injection policy allows writing to the pty."""
    return injection_blocker(
        state, input_dirty, foreground, alive, mode) == ""


def cd_command(path):
    """Return the bytes that change the shell directory to *path*."""
    if not isinstance(path, str) or not path:
        raise ValueError("cd needs a non-empty path")
    return ("cd -- %s\n" % shlex.quote(path)).encode("utf-8")


def run_command(argv, cwd=None):
    """Return the bytes that run *argv*, optionally after changing to *cwd*."""
    if not argv or not all(isinstance(part, str) and part for part in argv):
        raise ValueError("run needs a non-empty argument vector")
    line = " ".join(shlex.quote(part) for part in argv)
    if cwd:
        line = "cd -- %s && %s" % (shlex.quote(cwd), line)
    return (line + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Shell integration
# ---------------------------------------------------------------------------

def shell_kind(path):
    """Return ``bash``, ``zsh``, ``fish`` or "" for an unsupported shell."""
    name = os.path.basename(path or "").lstrip("-").lower()
    if name in ("bash", "rbash") or name.startswith("bash"):
        return "bash"
    for kind in ("zsh", "fish"):
        if name == kind or name.startswith(kind):
            return kind
    return ""


def bash_rc_content():
    """Return the generated bashrc that installs ``__nf_prompt``."""
    return (
        "# Generated by follow-shell.py - do not edit.\n"
        "if [ -f \"$HOME/.bashrc\" ]; then\n"
        "    source \"$HOME/.bashrc\"\n"
        "fi\n"
        "__nf_prompt() {\n"
        "    printf '\\033]777;nautilus-follow;prompt\\007'\n"
        "}\n"
        "if declare -p PROMPT_COMMAND 2>/dev/null | grep -q 'declare -a'; then\n"
        "    PROMPT_COMMAND+=(__nf_prompt)\n"
        "elif [ -n \"${PROMPT_COMMAND:-}\" ]; then\n"
        "    PROMPT_COMMAND=\"${PROMPT_COMMAND};__nf_prompt\"\n"
        "else\n"
        "    PROMPT_COMMAND=\"__nf_prompt\"\n"
        "fi\n"
    )


def zsh_rc_content():
    """Return the generated zshrc that appends ``__nf_prompt`` to precmd."""
    return (
        "# Generated by follow-shell.py - do not edit.\n"
        "if [ -f \"$HOME/.zshrc\" ]; then\n"
        "    source \"$HOME/.zshrc\"\n"
        "fi\n"
        "__nf_prompt() {\n"
        "    printf '\\033]777;nautilus-follow;prompt\\007'\n"
        "}\n"
        "typeset -ga precmd_functions\n"
        "precmd_functions+=(__nf_prompt)\n"
    )


def fish_init_command():
    """Return the fish ``--init-command`` that wraps ``fish_prompt``."""
    return (
        "functions --copy fish_prompt __nf_prompt_original; "
        "function fish_prompt; "
        "__nf_prompt_original; "
        "printf '\\033]777;nautilus-follow;prompt\\007'; "
        "end"
    )


def rc_content(kind):
    """Return the generated integration snippet for *kind* ("" otherwise)."""
    if kind == "bash":
        return bash_rc_content()
    if kind == "zsh":
        return zsh_rc_content()
    if kind == "fish":
        return fish_init_command()
    return ""


def write_rc(token, kind, root=None):
    """Write the generated rc file for *kind*, returning its path or ""."""
    if kind == "bash":
        name = "bashrc"
    elif kind == "zsh":
        name = ".zshrc"
    else:
        return ""
    directory = rc_dir(token, root)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    path = os.path.join(directory, name)
    _write_text_file(path, rc_content(kind))
    return path


def shell_invocation(shell, kind, token, root=None):
    """Return ``(argv, env_updates)`` that start *shell* with markers."""
    if kind == "bash":
        path = write_rc(token, kind, root)
        return [shell, "--rcfile", path, "-i"], {}
    if kind == "zsh":
        path = write_rc(token, kind, root)
        return [shell, "-i"], {"ZDOTDIR": os.path.dirname(path)}
    if kind == "fish":
        return [shell, "--init-command", fish_init_command(), "-i"], {}
    return [shell, "-i"], {}


# ---------------------------------------------------------------------------
# Script detection (mirrors terminal-tools._script_argv without importing it)
# ---------------------------------------------------------------------------

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


def read_shebang(path):
    """Return the interpreter line of a script, or "" when it has none."""
    try:
        with open(path, "rb") as handle:
            first = handle.readline(512)
    except OSError:
        return ""
    if not first.startswith(b"#!"):
        return ""
    return first[2:].decode("utf-8", "replace").strip()


def script_argv(path):
    """Return the argument vector that runs *path*.

    The shebang wins over the extension; without one the extension table
    decides. This is the same rule terminal-tools.py uses for its menu.
    """
    shebang = read_shebang(path)
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


def build_run_request(files, cwd=None, sudo=False):
    """Build the wire request that runs *files* in the synced terminal."""
    if not files:
        raise ValueError("run needs at least one file")
    paths = [os.path.abspath(path) for path in files]
    if len(paths) == 1:
        argv = script_argv(paths[0])
        if sudo:
            argv = ["sudo"] + argv
        return {
            "op": "run",
            "argv": argv,
            "cwd": os.path.abspath(cwd) if cwd else os.path.dirname(paths[0]),
        }

    parts = []
    for path in paths:
        command = script_argv(path)
        if sudo:
            command = ["sudo"] + command
        directory = os.path.abspath(cwd) if cwd else os.path.dirname(path)
        parts.append("cd -- %s && %s" % (
            shlex.quote(directory),
            " ".join(shlex.quote(part) for part in command)))
    request = {"op": "run", "argv": ["bash", "-c", "; ".join(parts)]}
    if cwd:
        request["cwd"] = os.path.abspath(cwd)
    return request


# ---------------------------------------------------------------------------
# Relay (default mode)
# ---------------------------------------------------------------------------

class _Relay:
    """Own a pty, relay it to the outer terminal and serve the socket."""

    def __init__(self, token, root, cwd, shell, debug=False, nautilus_pid=None):
        self.token = token
        self.root = ensure_registry(root)
        self.cwd = os.path.abspath(cwd or os.getcwd())
        self.shell = shell
        self.kind = shell_kind(shell)
        self.mode = "marker" if self.kind else "unsupported"
        self.nautilus_pid = nautilus_pid
        self.debug = debug
        self.started = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        self.sock_path = socket_path(token, self.root)
        self.server = None
        self.socket_identity = None
        self.master = None
        self.child_pid = None
        self.child_status = None
        self.scanner = MarkerScanner()
        self.state = "starting"
        self.input_dirty = False
        self.pending = None
        self.first_output_at = None
        self.saw_marker = False
        self.winch = False
        self.stop = False
        self.quit_requested = False
        self.clients = {}
        self.buffers = {}
        self.selector = None
        self._term_attrs = None
        self._term_restored = False
        self._log_handle = None
        if debug:
            try:
                self._log_handle = open(
                    relay_log_path(token, self.root), "a", encoding="utf-8")
            except OSError:
                self._log_handle = None

    # -- logging ------------------------------------------------------------

    def _log(self, message):
        if self._log_handle is None:
            return
        try:
            self._log_handle.write("%s %s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"), message))
            self._log_handle.flush()
        except OSError:
            pass

    # -- setup --------------------------------------------------------------

    def _bind(self):
        if os.path.lexists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.sock_path)
        try:
            stat = os.stat(self.sock_path)
            self.socket_identity = (stat.st_dev, stat.st_ino)
        except OSError:
            self.socket_identity = None
        os.chmod(self.sock_path, 0o600)
        self.server.listen(8)
        self.server.setblocking(False)
        self._write_meta()
        _write_text_file(current_path(self.root), self.sock_path + "\n")
        self._log("listening on %s" % self.sock_path)

    def _write_meta(self):
        record = meta_record(
            self.token, os.getpid(), self.cwd, self.shell, self.mode,
            started=self.started, nautilus_pid=self.nautilus_pid)
        _write_text_file(
            meta_path(self.token, self.root),
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _spawn(self):
        argv, env_updates = shell_invocation(
            self.shell, self.kind, self.token, self.root)
        environment = os.environ.copy()
        environment.update(env_updates)
        try:
            os.chdir(self.cwd)
        except OSError as exc:
            raise OSError("cannot enter %s: %s" % (self.cwd, exc))
        self.child_pid, self.master = pty.fork()
        if self.child_pid == 0:  # pragma: no cover - runs in the child
            try:
                os.execvpe(argv[0], argv, environment)
            except OSError as exc:
                try:
                    os.write(2, ("follow-shell: cannot start %s: %s\n" % (
                        argv[0], exc)).encode("utf-8", "replace"))
                except OSError:
                    pass
                os._exit(127)
        os.set_blocking(self.master, False)
        self._copy_winsize()

    def _save_terminal(self):
        try:
            self._term_attrs = termios.tcgetattr(0)
            tty.setraw(0)
        except (OSError, termios.error):
            self._term_attrs = None

    def _restore_terminal(self):
        if self._term_restored or self._term_attrs is None:
            return
        self._term_restored = True
        try:
            termios.tcsetattr(0, termios.TCSADRAIN, self._term_attrs)
        except (OSError, termios.error):
            pass

    def _copy_winsize(self):
        if self.master is None:
            return
        try:
            import fcntl
            import struct
            size = fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8)
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack(
                "HHHH", *struct.unpack("HHHH", size)))
        except (OSError, ImportError, termios.error):
            pass

    # -- signals ------------------------------------------------------------

    def _install_signals(self):
        def on_stop(_signum, _frame):
            self.stop = True
            self._restore_terminal()

        def on_winch(_signum, _frame):
            self.winch = True

        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(signum, on_stop)
            except (OSError, ValueError):
                pass
        try:
            signal.signal(signal.SIGWINCH, on_winch)
        except (OSError, ValueError):
            pass

    # -- event loop ---------------------------------------------------------

    def run(self):
        self._bind()
        self._save_terminal()
        self._install_signals()
        try:
            self._spawn()
            self._log("shell %s started as %d (mode %s)" % (
                self.shell, self.child_pid, self.mode))
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.server, selectors.EVENT_READ, "server")
            self.selector.register(self.master, selectors.EVENT_READ, "master")
            try:
                self.selector.register(sys.stdin.fileno(),
                                       selectors.EVENT_READ, "stdin")
            except (KeyError, ValueError, OSError):
                pass
            self._loop()
        finally:
            self._restore_terminal()
            self._terminate_child()
            self._cleanup()
        return self._exit_code()

    def _loop(self):
        while not self.stop:
            if not self._child_alive():
                self._drain_master()
                break
            if self._marker_deadline_passed():
                self._set_unsupported()
            try:
                events = self.selector.select(0.1)
            except OSError:
                break
            for key, _mask in events:
                tag = key.data
                if tag == "server":
                    self._accept()
                elif tag == "master":
                    self._read_master()
                elif tag == "stdin":
                    self._read_stdin()
                elif isinstance(tag, tuple) and tag[0] == "client":
                    self._read_client(tag[1])
            if self.winch:
                self.winch = False
                self._copy_winsize()

    def _marker_deadline_passed(self):
        return (self.mode == "marker" and not self.saw_marker
                and self.first_output_at is not None
                and time.time() - self.first_output_at >= MARKER_TIMEOUT)

    def _set_unsupported(self):
        self.mode = "unsupported"
        self.pending = None
        self.state = "busy"
        self._write_meta()
        self._log("no prompt marker within %.0f s, injection disabled"
                  % MARKER_TIMEOUT)

    # -- descriptors --------------------------------------------------------

    def _accept(self):
        try:
            connection, _address = self.server.accept()
        except (BlockingIOError, OSError):
            return
        connection.setblocking(True)
        connection.settimeout(1.0)
        self.clients[connection] = True
        self.buffers[connection] = LineBuffer()
        try:
            self.selector.register(connection, selectors.EVENT_READ,
                                   ("client", connection))
        except (KeyError, ValueError):
            self._drop_client(connection)

    def _drop_client(self, connection):
        self.clients.pop(connection, None)
        self.buffers.pop(connection, None)
        try:
            self.selector.unregister(connection)
        except (KeyError, ValueError):
            pass
        try:
            connection.close()
        except OSError:
            pass

    def _read_client(self, connection):
        try:
            data = connection.recv(65536)
        except (OSError, socket.timeout):
            self._drop_client(connection)
            return
        if not data:
            self._drop_client(connection)
            return
        buffer = self.buffers.get(connection)
        if buffer is None:
            self._drop_client(connection)
            return
        for line in buffer.feed(data):
            if not line.strip():
                continue
            try:
                request = decode_message(line)
            except ProtocolError:
                self._send(connection, {
                    "ok": False, "error": "bad-request"})
                continue
            self._send(connection, self._dispatch(request))

    def _send(self, connection, message):
        try:
            connection.sendall(encode_message(message))
        except OSError:
            self._drop_client(connection)

    def _read_stdin(self):
        try:
            data = os.read(0, 65536)
        except (OSError, BlockingIOError):
            self.stop = True
            return
        if not data:
            self.stop = True
            return
        self.input_dirty = True
        try:
            _write_all(self.master, data)
        except OSError:
            self.stop = True

    def _read_master(self):
        try:
            data = os.read(self.master, 65536)
        except BlockingIOError:
            return
        except OSError:
            # EIO means the slave side is gone; the next waitpid reaps it.
            return
        if not data:
            return
        if self.first_output_at is None:
            self.first_output_at = time.time()
        try:
            _write_all(1, data)
        except OSError:
            self.stop = True
            return
        if self.scanner.feed(data):
            self.saw_marker = True
            if self.mode == "marker":
                self.state = "prompt"
            self.input_dirty = False
            self._try_inject()
        elif self.state == "starting":
            self.state = "busy"

    def _drain_master(self):
        if self.master is None:
            return
        while True:
            try:
                data = os.read(self.master, 65536)
            except (BlockingIOError, OSError):
                return
            if not data:
                return
            try:
                _write_all(1, data)
            except OSError:
                return

    def _child_alive(self):
        if self.child_status is not None:
            return False
        try:
            pid, status = os.waitpid(self.child_pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            self.child_status = 0
            return False
        if pid == 0:
            return True
        self.child_status = status
        return False

    def _alive(self):
        return self.child_status is None and not self.stop

    def _foreground(self):
        if self.master is None:
            return False
        try:
            return os.tcgetpgrp(self.master) == self.child_pid
        except OSError:
            return False

    # -- requests -----------------------------------------------------------

    def _dispatch(self, request):
        op = request.get("op")
        if op == "status":
            return self._status_reply()
        if op == "quit":
            self.quit_requested = True
            self.stop = True
            return {"ok": True}
        if op in ("cd", "run"):
            return self._queue(op, request)
        return {"ok": False, "error": "unknown-op"}

    def _status_reply(self):
        return {
            "ok": True,
            "pid": self.child_pid,
            "cwd": self.cwd,
            "mode": self.mode,
            "prompt_ready": can_inject(
                self.state, self.input_dirty, self._foreground(),
                self._alive(), self.mode),
        }

    def _queue(self, op, request):
        if op == "cd":
            path = request.get("path")
            if not isinstance(path, str) or not path:
                return {"ok": False, "error": "missing-path"}
            if not os.path.isabs(path):
                path = os.path.abspath(path)
            target = {
                "op": "cd",
                "payload": cd_command(path),
                "cwd": path,
            }
        else:
            argv = request.get("argv")
            if (not isinstance(argv, list) or not argv
                    or not all(isinstance(part, str) and part
                               for part in argv)):
                return {"ok": False, "error": "bad-argv"}
            cwd = request.get("cwd")
            if cwd is not None:
                if not isinstance(cwd, str) or not cwd:
                    return {"ok": False, "error": "bad-cwd"}
                if not os.path.isabs(cwd):
                    cwd = os.path.abspath(cwd)
            target = {
                "op": "run",
                "payload": run_command(argv, cwd),
                "cwd": cwd if cwd is not None else self.cwd,
            }

        if self.mode != "marker":
            return {"ok": False, "error": "no-markers", "applied": False,
                    "reason": "no-markers"}

        blocker = injection_blocker(
            self.state, self.input_dirty, self._foreground(),
            self._alive(), self.mode)
        self.pending = target
        if blocker:
            self._log("%s queued: %s" % (op, blocker))
            return {"ok": True, "applied": False, "reason": blocker}
        if not self._inject(target):
            return {"ok": False, "error": "write-failed", "applied": False,
                    "reason": "write-failed"}
        return {"ok": True, "applied": True}

    def _inject(self, target):
        try:
            _write_all(self.master, target["payload"])
        except OSError as exc:
            self._log("injection failed: %s" % exc)
            return False
        self.pending = None
        self.cwd = target.get("cwd") or self.cwd
        self.state = "busy"
        self.input_dirty = False
        self._log("%s injected" % target["op"])
        return True

    def _try_inject(self):
        if self.pending is None or self.mode != "marker":
            return
        if not can_inject(self.state, self.input_dirty, self._foreground(),
                          self._alive(), self.mode):
            return
        self._inject(self.pending)

    # -- teardown -----------------------------------------------------------

    def _exit_code(self):
        if self.quit_requested or self.child_status is None:
            return 0
        if os.WIFEXITED(self.child_status):
            return os.WEXITSTATUS(self.child_status)
        if os.WIFSIGNALED(self.child_status):
            return 128 + os.WTERMSIG(self.child_status)
        return 0

    def _terminate_child(self):
        if self.child_pid is None or self.child_status is not None:
            return
        for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.child_pid, signum)
            except OSError:
                try:
                    os.kill(self.child_pid, signum)
                except OSError:
                    pass
            deadline = time.time() + 0.4
            while time.time() < deadline:
                try:
                    pid, status = os.waitpid(self.child_pid, os.WNOHANG)
                except (ChildProcessError, OSError):
                    self.child_status = 0
                    return
                if pid:
                    self.child_status = status
                    return
                time.sleep(0.02)

    def _cleanup(self):
        for connection in list(self.clients):
            self._drop_client(connection)
        if self.selector is not None:
            try:
                self.selector.close()
            except OSError:
                pass
            self.selector = None
        if self.server is not None:
            try:
                self.server.close()
            except OSError:
                pass
            self.server = None
        if self.master is not None:
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = None
        self._unlink_if_ours(self.sock_path, self.socket_identity)
        try:
            os.unlink(meta_path(self.token, self.root))
        except OSError:
            pass
        try:
            current = current_path(self.root)
            with open(current, encoding="utf-8") as handle:
                if handle.read().strip() == self.sock_path:
                    os.unlink(current)
        except OSError:
            pass
        try:
            shutil.rmtree(rc_dir(self.token, self.root), ignore_errors=True)
        except OSError:
            pass
        self._log("relay stopped")
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None

    def _unlink_if_ours(self, path, identity):
        if identity is None:
            return
        try:
            stat = os.stat(path)
        except OSError:
            return
        if (stat.st_dev, stat.st_ino) == identity:
            try:
                os.unlink(path)
            except OSError:
                pass


def _write_all(fd, data):
    """Write all of *data* to *fd*, waiting for writability when needed."""
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except BlockingIOError:
            try:
                select.select([], [fd], [], 0.2)
            except OSError:
                raise
            continue
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _env_pid(name):
    try:
        value = int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return None
    return value or None


def relay_main(argv):
    """Parse relay arguments, run the relay and return its exit code."""
    parser = argparse.ArgumentParser(
        prog="follow-shell.py",
        description="Relay a shell on a pty and follow a Nautilus window.")
    parser.add_argument("--dir", help="registry directory override")
    parser.add_argument("--token", required=True,
                        help="12 hex chars identifying this relay")
    parser.add_argument("--cwd", help="directory the shell starts in")
    parser.add_argument("--shell", help="shell to run (default $SHELL)")
    parser.add_argument("--debug", action="store_true",
                        help="write <token>.relay.log in the registry")
    args = parser.parse_args(argv)

    if not valid_token(args.token):
        parser.error("--token must be 12 lowercase hex characters")
    if args.cwd and not os.path.isdir(args.cwd):
        parser.error("--cwd is not a directory: %s" % args.cwd)

    shell = args.shell or os.environ.get("SHELL") or DEFAULT_SHELL
    relay = None
    try:
        relay = _Relay(
            args.token, args.dir, args.cwd or os.getcwd(), shell,
            debug=args.debug,
            nautilus_pid=_env_pid("NAUTILUS_FOLLOW_NAUTILUS_PID"))
        return relay.run()
    except OSError as exc:
        try:
            os.write(2, ("follow-shell: %s\n" % exc).encode(
                "utf-8", "replace"))
        except OSError:
            pass
        if relay is not None:
            relay._restore_terminal()
            relay._cleanup()
        return 1


# ---------------------------------------------------------------------------
# Sender mode
# ---------------------------------------------------------------------------

def _resolve_socket(explicit, root=None):
    """Return the socket path to use, or "" when there is no current relay."""
    if explicit:
        return os.path.abspath(explicit)
    try:
        with open(current_path(root), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def send_request(request, sock_path, timeout=SOCKET_TIMEOUT):
    """Send one request and return its one reply object."""
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(timeout)
    try:
        connection.connect(sock_path)
        connection.sendall(encode_message(request))
        buffer = b""
        while b"\n" not in buffer:
            chunk = connection.recv(65536)
            if not chunk:
                break
            buffer += chunk
    finally:
        try:
            connection.close()
        except OSError:
            pass
    if not buffer.strip():
        raise ProtocolError("the relay closed the connection")
    return decode_message(buffer.split(b"\n", 1)[0])


def describe_reply(request, reply):
    """Return a short human summary of *reply* for the sender mode."""
    op = request.get("op")
    if not reply.get("ok"):
        return "%s failed: %s" % (op, reply.get("error", "unknown error"))
    if op == "status":
        return "pid %s, cwd %s, mode %s, prompt %s" % (
            reply.get("pid"), reply.get("cwd"), reply.get("mode"),
            "ready" if reply.get("prompt_ready") else "not ready")
    if reply.get("applied"):
        return "%s applied in the synced terminal" % op
    return "%s queued until the next prompt (%s)" % (
        op, reply.get("reason", "busy"))


def sender_main(argv):
    """Parse sender arguments, talk to the relay and return an exit code."""
    parser = argparse.ArgumentParser(
        prog="follow-shell.py --send",
        description="Send one request to a running follow-shell relay.")
    parser.add_argument("--send", choices=("cd", "run", "status"),
                        required=True)
    parser.add_argument("--path", help="directory for --send cd")
    parser.add_argument("--file", action="append", default=[],
                        help="script to run for --send run (repeatable)")
    parser.add_argument("--cwd", help="directory to run the scripts in")
    parser.add_argument("--sudo", action="store_true",
                        help="run the scripts through sudo")
    parser.add_argument("--socket", help="explicit socket path")
    parser.add_argument("--dir", help="registry directory override")
    parser.add_argument("--timeout", type=float, default=SOCKET_TIMEOUT,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.send == "cd":
        if not args.path:
            parser.error("--send cd needs --path")
        request = {"op": "cd", "path": os.path.abspath(args.path)}
    elif args.send == "run":
        if not args.file:
            parser.error("--send run needs --file")
        try:
            request = build_run_request(args.file, args.cwd, args.sudo)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        request = {"op": "status"}

    target = _resolve_socket(args.socket, args.dir)
    if not target:
        print("follow-shell: no synced terminal is registered", file=sys.stderr)
        return 1
    try:
        reply = send_request(request, target, args.timeout)
    except (OSError, ProtocolError) as exc:
        print("follow-shell: cannot reach the synced terminal: %s" % exc,
              file=sys.stderr)
        return 1
    print("follow-shell: %s" % describe_reply(request, reply))
    return 0 if reply.get("ok") else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    """Dispatch between relay mode and ``--send`` mode."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if any(argument == "--send" or argument.startswith("--send=")
           for argument in arguments):
        return sender_main(arguments)
    return relay_main(arguments)


if __name__ == "__main__":
    sys.exit(main())
