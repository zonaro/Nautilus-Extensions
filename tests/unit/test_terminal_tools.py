"""Unit tests for the Terminal Tools Nautilus extension.

The extension needs GTK/Nautilus at import time, so the whole module is
skipped when those are unavailable. The tests only cover the pure helpers:
script detection, shell snippet building, desktop entry parsing, the follow
registry / launch argv / debounce helpers and the i18n coverage contract.
"""

import ast
import importlib.util
import json
import os
import pathlib
import re
import shlex
import socket
import subprocess
import threading
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXT_PATH = os.path.join(REPO_ROOT, "terminal-tools.py")


def _load_module():
    """Import ``terminal-tools.py`` under the name ``tt``."""
    spec = importlib.util.spec_from_file_location("tt", EXT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    tt = _load_module()
except Exception as exc:  # pragma: no cover - depends on the host
    pytest.skip("terminal-tools.py is not importable here: %s" % exc, allow_module_level=True)


# ---------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("script.sh", ["bash", "script.sh"]),
    ("script.bash", ["bash", "script.bash"]),
    ("script.zsh", ["zsh", "script.zsh"]),
    ("script.fish", ["fish", "script.fish"]),
    ("script.py", ["python3", "script.py"]),
    ("script.pl", ["perl", "script.pl"]),
    ("script.rb", ["ruby", "script.rb"]),
    ("script.php", ["php", "script.php"]),
    ("script.lua", ["lua", "script.lua"]),
    ("script.awk", ["awk", "-f", "script.awk"]),
    ("SCRIPT.SH", ["bash", "SCRIPT.SH"]),
])
def test_script_argv_uses_the_extension(name, expected):
    assert tt._script_argv(name) == expected


def test_script_argv_prefers_the_shebang(tmp_path):
    script = tmp_path / "runner.sh"
    script.write_text("#!/usr/bin/env python3\nprint('hi')\n")
    assert tt._script_argv(str(script)) == ["/usr/bin/env", "python3", str(script)]


def test_script_argv_falls_back_to_the_extension_without_shebang(tmp_path):
    script = tmp_path / "runner.sh"
    script.write_text("echo hi\n")
    assert tt._script_argv(str(script)) == ["bash", str(script)]


def test_read_shebang_ignores_regular_files(tmp_path):
    plain = tmp_path / "notes.txt"
    plain.write_text("just text\n")
    assert tt._read_shebang(str(plain)) == ""


def test_is_script(tmp_path):
    shell = tmp_path / "run.sh"
    shell.write_text("#!/bin/bash\necho hi\n")
    python = tmp_path / "run.py"
    python.write_text("print('hi')\n")
    plain = tmp_path / "notes.txt"
    plain.write_text("nothing to run\n")
    assert tt._is_script(str(shell)) is True
    assert tt._is_script(str(python)) is True
    assert tt._is_script(str(plain)) is False


# ---------------------------------------------------------------------------
# Shell snippets
# ---------------------------------------------------------------------------

def test_run_script_keeps_the_window_open_and_reports_the_exit_code():
    script = tt._build_run_script(["cd '/tmp' && bash '/tmp/demo.sh'"])
    assert "cd '/tmp' && bash '/tmp/demo.sh'" in script
    assert "rc=$?" in script
    assert "read -r _" in script
    assert 'exit "$rc"' in script
    assert tt.T["press_enter"] in script
    assert tt.T["exit_code"] in script


def test_option_args_handles_both_option_shapes():
    assert tt._option_args("--working-directory=", "/tmp") == ["--working-directory=/tmp"]
    assert tt._option_args("--working-directory", "/tmp") == ["--working-directory", "/tmp"]
    assert tt._option_args(None, "/tmp") == []


# ---------------------------------------------------------------------------
# Terminal descriptors
# ---------------------------------------------------------------------------

def test_terminal_specs_are_well_formed():
    for name, spec in tt.TERMINAL_SPECS.items():
        workdir, exec_option, style = spec
        assert style in ("argv", "line"), name
        assert workdir is None or isinstance(workdir, str), name
        assert exec_option is None or isinstance(exec_option, str), name


def test_onyxsh_uses_its_native_workdir_option_and_the_line_style():
    # OnyxSH joins the --execute arguments into a single shell line, so the
    # command has to be a ready to type line and the working directory has
    # to be given by the terminal itself.
    workdir, exec_option, style = tt.TERMINAL_SPECS["onyxsh"]
    assert workdir == "--working-directory"
    assert exec_option == "--execute"
    assert style == "line"


# ---------------------------------------------------------------------------
# Opening a terminal
# ---------------------------------------------------------------------------

def test_open_argv_uses_the_terminal_workdir_and_types_no_command():
    descriptor = tt._descriptor(["gnome-terminal"], "--working-directory=", "--", "argv")
    argv = tt._open_argv(descriptor, "/home/user/My Folder")
    assert argv == ["gnome-terminal", "--working-directory=/home/user/My Folder"]
    # No command is typed into the terminal: the shell comes up clean.
    assert "--" not in argv


def test_open_argv_falls_back_to_a_shell_wrapper_without_a_workdir_option():
    descriptor = tt._descriptor(["xterm"], None, "-e", "argv")
    argv = tt._open_argv(descriptor, "/home/user/My Folder")
    assert argv[:2] == ["xterm", "-e"]
    script = argv[-1]
    assert script.startswith("cd '/home/user/My Folder' || exit 1")
    assert 'exec "${SHELL:-/bin/bash}"' in script


def test_open_argv_for_a_line_terminal_types_nothing_when_it_can_set_the_folder():
    descriptor = tt._descriptor(["onyxsh"], "--working-directory", "--execute", "line")
    argv = tt._open_argv(descriptor, "/tmp")
    assert argv == ["onyxsh", "--working-directory", "/tmp"]


def test_open_argv_for_a_line_terminal_without_a_workdir_option():
    descriptor = tt._descriptor(["onyxsh"], None, "--execute", "line")
    argv = tt._open_argv(descriptor, "/tmp/a b")
    assert argv[:2] == ["onyxsh", "--execute"]
    assert argv[2] == "cd '/tmp/a b' && exec \"${SHELL:-/bin/bash}\""


# ---------------------------------------------------------------------------
# Running scripts
# ---------------------------------------------------------------------------

def test_run_argv_for_a_line_terminal_keeps_the_quoting():
    descriptor = tt._descriptor(["onyxsh"], "--working-directory", "--execute", "line")
    argv = tt._run_argv(descriptor, ["/tmp/a b/run.sh"])
    assert argv[:4] == ["onyxsh", "--working-directory", "/tmp/a b", "--execute"]
    line = argv[4]
    assert line.startswith("bash '/tmp/a b/run.sh'")
    assert "$?" in line


def test_run_argv_for_a_line_terminal_prefixes_sudo():
    descriptor = tt._descriptor(["onyxsh"], "--working-directory", "--execute", "line")
    line = tt._run_argv(descriptor, ["/tmp/a b/run.sh"], sudo=True)[-1]
    assert line.startswith("sudo bash '/tmp/a b/run.sh'")


def test_run_argv_for_an_argv_terminal_uses_a_shell_script():
    descriptor = tt._descriptor(["gnome-terminal"], None, "--", "argv")
    argv = tt._run_argv(descriptor, ["/tmp/run.sh"])
    assert argv[0] == "gnome-terminal"
    assert argv[1] == "--"
    assert argv[2] == tt._shell()
    assert argv[3] == "-c"
    script = argv[4]
    assert "cd /tmp && bash /tmp/run.sh" in script
    # The window has to survive the script, so the shell waits for Enter.
    assert "read -r _" in script


def test_run_argv_for_an_argv_terminal_with_a_workdir_option():
    descriptor = tt._descriptor(["gnome-terminal"], "--working-directory=", "--", "argv")
    argv = tt._run_argv(descriptor, ["/tmp/run.sh"])
    assert argv[1] == "--working-directory=/tmp"


def test_run_argv_runs_every_script_of_the_selection():
    descriptor = tt._descriptor(["onyxsh"], "--working-directory", "--execute", "line")
    line = tt._run_argv(descriptor, ["/a/one.sh", "/b/two.sh"])[-1]
    assert "bash /a/one.sh" in line
    assert "cd /b && bash /b/two.sh" in line


def test_generated_commands_are_valid_shell():
    line_descriptor = tt._descriptor(["onyxsh"], None, "--execute", "line")
    argv_descriptor = tt._descriptor(["xterm"], None, "-e", "argv")
    snippets = [
        tt._open_argv(line_descriptor, "/tmp")[2],
        tt._run_argv(line_descriptor, ["/tmp/a b/run.sh"])[2],
        tt._open_argv(argv_descriptor, "/tmp")[-1],
        tt._run_argv(argv_descriptor, ["/tmp/run.sh"])[-1],
    ]
    for snippet in snippets:
        proc = subprocess.run(["bash", "-n"], input=snippet, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert proc.returncode == 0, proc.stdout


def test_paths_with_spaces_are_quoted():
    descriptor = tt._descriptor(["xterm"], None, "-e", "argv")
    script = tt._open_argv(descriptor, "/tmp/a b/c")[-1]
    assert "'/tmp/a b/c'" in script


# ---------------------------------------------------------------------------
# Desktop entries
# ---------------------------------------------------------------------------

def test_exec_tokens_drops_field_codes():
    tokens = tt._exec_tokens("flatpak run --command=onyxsh app.id @@ %F @@")
    assert tokens == ["flatpak", "run", "--command=onyxsh", "app.id"]


def test_parse_desktop_entry_reads_the_main_group(tmp_path):
    entry = tmp_path / "term.desktop"
    entry.write_text(
        "[Desktop Entry]\n"
        "Name=Terminal\n"
        "Name[pt]=Terminal\n"
        "Exec=kgx --\n"
        "Categories=System;TerminalEmulator;\n"
        "\n"
        "[Desktop Action New]\n"
        "Exec=kgx --new-window\n"
    )
    fields = tt._parse_desktop_entry(str(entry))
    assert fields["Name"] == "Terminal"
    assert fields["Exec"] == "kgx --"
    assert "TerminalEmulator" in fields["Categories"].split(";")
    # The Exec of the action group must not override the main one.
    assert "--new-window" not in fields["Exec"]


def test_terminal_name_is_guessed_from_the_exec_line(tmp_path):
    entry = tmp_path / "io.github.vagnarok.OnyxSH.desktop"
    entry.write_text("[Desktop Entry]\nExec=onyxsh\n")
    tokens = tt._exec_tokens("onyxsh")
    assert tt._terminal_name(tokens, str(entry)) == "onyxsh"


# ---------------------------------------------------------------------------
# Terminal discovery
# ---------------------------------------------------------------------------

def test_terminal_candidates_are_resolvable_descriptors():
    candidates = tt._terminal_candidates()
    assert isinstance(candidates, list)
    for descriptor in candidates:
        assert descriptor["argv"]
        assert all(isinstance(part, str) for part in descriptor["argv"])
        assert descriptor["style"] in ("argv", "line")
        assert descriptor["workdir"] is None or isinstance(descriptor["workdir"], str)
        assert descriptor["exec"] is None or isinstance(descriptor["exec"], str)


def test_gsettings_string_survives_a_missing_schema():
    assert tt._gsettings_string("org.gnome.this.schema.does.not.exist", "exec") == ""


def test_resolve_binary_rejects_nothing_installed():
    assert tt._resolve_binary("definitely-not-a-real-binary-xyz") == ""
    assert tt._resolve_binary("") == ""


# ---------------------------------------------------------------------------
# Following the browsed folder
# ---------------------------------------------------------------------------

FOLLOW_KEYS = (
    "open_follow_label",
    "tip_open_follow",
    "run_follow_label",
    "run_follow_label_many",
    "tip_run_follow",
    "tip_run_follow_many",
    "err_follow_unsupported",
    "err_follow_shell",
    "err_follow_detached",
)

FOLLOW_TOKEN = "0123456789ab"
FOLLOW_SCRIPT = "/opt/nautilus extensions/follow-shell.py"
FOLLOW_PYTHON = "/usr/bin/python3"


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Point the follow registry at a throwaway directory."""
    path = tmp_path / "registry"
    monkeypatch.setenv("NAUTILUS_FOLLOW_DIR", str(path))
    monkeypatch.delenv("NAUTILUS_FOLLOW_DEBUG", raising=False)
    return path


class FakeLocation:
    """The tiny part of a Gio.File the slot helpers use."""

    def __init__(self, path):
        self._path = path

    def get_path(self):
        return self._path


class FakeWidget:
    """Minimal GTK4 widget node, enough for the slot walker."""

    def __init__(self, type_name, children=(), props=None):
        self.__gtype__ = type("FakeGType", (), {"name": type_name})()
        self._children = list(children)
        self._sibling = None
        self.props = dict(props or {})
        for previous, following in zip(self._children, self._children[1:]):
            previous._sibling = following

    def get_first_child(self):
        return self._children[0] if self._children else None

    def get_next_sibling(self):
        return self._sibling

    def get_property(self, name):
        return self.props[name]


class FakeScheduler:
    """Stand-in for GLib.timeout_add / GLib.source_remove."""

    def __init__(self):
        self.sources = {}
        self.cancelled = []
        self._next = 1

    def schedule(self, delay, callback):
        source = self._next
        self._next += 1
        self.sources[source] = (delay, callback)
        return source

    def cancel(self, source):
        self.cancelled.append(source)
        self.sources.pop(source, None)


def _fake_script(directory, name="follow-shell.py"):
    path = pathlib.Path(directory) / name
    path.write_text("#!/usr/bin/env python3\n")
    return str(path)


# -- registry ---------------------------------------------------------------

def test_follow_registry_honours_the_override(tmp_path, monkeypatch):
    target = tmp_path / "a" / "registry"
    monkeypatch.setenv("NAUTILUS_FOLLOW_DIR", str(target))
    assert tt._follow_registry() == str(target)
    assert target.is_dir()
    assert target.stat().st_mode & 0o777 == 0o700


def test_follow_registry_uses_the_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("NAUTILUS_FOLLOW_DIR", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert tt._follow_registry() == str(tmp_path / "nautilus-follow")


def test_follow_registry_falls_back_to_tmp_without_a_runtime_dir(monkeypatch):
    monkeypatch.delenv("NAUTILUS_FOLLOW_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    expected = "/tmp/nautilus-follow-%d" % os.getuid()
    assert tt._follow_registry() == expected
    assert os.path.isdir(expected)


def test_follow_socket_path_lives_in_the_registry(registry):
    assert tt._follow_socket_path(FOLLOW_TOKEN) == str(
        registry / ("s-%s.sock" % FOLLOW_TOKEN))


def test_follow_token_is_twelve_hex_characters():
    token = tt._follow_token()
    assert re.fullmatch(r"[0-9a-f]{12}", token)
    assert tt._follow_token() != token


# -- script and interpreter resolution --------------------------------------

def test_follow_script_resolves_next_to_the_extension(tmp_path):
    script = _fake_script(tmp_path)
    assert tt._follow_script([str(tmp_path)]) == script


def test_follow_script_prefers_the_first_directory(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    _fake_script(second)
    assert tt._follow_script([str(first), str(second)]) == str(second / "follow-shell.py")
    _fake_script(first)
    assert tt._follow_script([str(first), str(second)]) == str(first / "follow-shell.py")


def test_follow_script_is_empty_when_it_is_not_installed(tmp_path):
    assert tt._follow_script([str(tmp_path), ""]) == ""


def test_follow_script_search_order_starts_next_to_the_extension():
    dirs = tt._follow_script_dirs()
    assert dirs[0] == os.path.dirname(os.path.abspath(EXT_PATH))
    assert len(dirs) == 3


def test_follow_python_is_an_existing_interpreter():
    python = tt._follow_python()
    assert os.path.isabs(python)
    assert os.access(python, os.X_OK)


# -- launch argv ------------------------------------------------------------

def test_follow_argv_for_an_argv_terminal():
    descriptor = tt._descriptor(["gnome-terminal"], "--working-directory=", "--", "argv")
    argv = tt._follow_argv(descriptor, "/home/user/My Folder", FOLLOW_TOKEN,
                           FOLLOW_SCRIPT, FOLLOW_PYTHON, debug=False)
    assert argv == [
        "gnome-terminal",
        "--working-directory=/home/user/My Folder",
        "--",
        FOLLOW_PYTHON,
        FOLLOW_SCRIPT,
        "--token", FOLLOW_TOKEN,
        "--cwd", "/home/user/My Folder",
    ]


def test_follow_argv_for_an_argv_terminal_without_a_workdir_option():
    descriptor = tt._descriptor(["xterm"], None, "-e", "argv")
    argv = tt._follow_argv(descriptor, "/tmp", FOLLOW_TOKEN, FOLLOW_SCRIPT,
                           FOLLOW_PYTHON, debug=False)
    assert argv == ["xterm", "-e", FOLLOW_PYTHON, FOLLOW_SCRIPT,
                    "--token", FOLLOW_TOKEN, "--cwd", "/tmp"]


def test_follow_argv_for_a_line_terminal_is_one_quoted_line():
    descriptor = tt._descriptor(["onyxsh"], "--working-directory", "--execute", "line")
    argv = tt._follow_argv(descriptor, "/home/user/My Folder", FOLLOW_TOKEN,
                           FOLLOW_SCRIPT, FOLLOW_PYTHON, debug=False)
    assert argv[:3] == ["onyxsh", "--working-directory", "/home/user/My Folder"]
    assert argv[3] == "--execute"
    line = argv[4]
    assert line.startswith("%s '%s'" % (FOLLOW_PYTHON, FOLLOW_SCRIPT))
    assert "--token %s" % FOLLOW_TOKEN in line
    assert "--cwd '/home/user/My Folder'" in line
    # The terminal types this line into a shell: the quoting must survive.
    assert shlex.split(line) == [FOLLOW_PYTHON, FOLLOW_SCRIPT, "--token",
                                 FOLLOW_TOKEN, "--cwd", "/home/user/My Folder"]


def test_follow_argv_line_style_can_be_run_by_bash():
    descriptor = tt._descriptor(["onyxsh"], None, "--execute", "line")
    line = tt._follow_argv(descriptor, "/tmp/a b", FOLLOW_TOKEN, FOLLOW_SCRIPT,
                           FOLLOW_PYTHON, debug=False)[-1]
    proc = subprocess.run(["bash", "-n"], input=line, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout


def test_follow_argv_adds_the_debug_flag_explicitly():
    descriptor = tt._descriptor(["xterm"], None, "-e", "argv")
    argv = tt._follow_argv(descriptor, "/tmp", FOLLOW_TOKEN, FOLLOW_SCRIPT,
                           FOLLOW_PYTHON, debug=True)
    assert argv[-1] == "--debug"


def test_follow_argv_reads_the_debug_environment(registry, monkeypatch):
    descriptor = tt._descriptor(["xterm"], None, "-e", "argv")
    monkeypatch.setenv("NAUTILUS_FOLLOW_DEBUG", "1")
    argv = tt._follow_argv(descriptor, "/tmp", FOLLOW_TOKEN, FOLLOW_SCRIPT,
                           FOLLOW_PYTHON)
    assert argv[-1] == "--debug"
    monkeypatch.delenv("NAUTILUS_FOLLOW_DEBUG")
    argv = tt._follow_argv(descriptor, "/tmp", FOLLOW_TOKEN, FOLLOW_SCRIPT,
                           FOLLOW_PYTHON)
    assert "--debug" not in argv


# -- debounce ---------------------------------------------------------------

def test_follow_debounce_keeps_one_timer_per_key():
    scheduler = FakeScheduler()
    pending = {}
    calls = []
    first = tt._follow_debounce(
        pending, "win", lambda: calls.append("first"),
        schedule=scheduler.schedule, cancel=scheduler.cancel)
    second = tt._follow_debounce(
        pending, "win", lambda: calls.append("second"),
        schedule=scheduler.schedule, cancel=scheduler.cancel)
    assert (first, second) == (1, 2)
    assert scheduler.cancelled == [1]
    assert pending == {"win": 2}
    delay, fire = scheduler.sources[2]
    assert delay == tt.FOLLOW_DEBOUNCE_MS
    assert fire() is False
    assert calls == ["second"]
    assert pending == {}


def test_follow_debounce_separates_windows():
    scheduler = FakeScheduler()
    pending = {}
    calls = []
    tt._follow_debounce(pending, "one", lambda: calls.append("one"),
                        schedule=scheduler.schedule, cancel=scheduler.cancel)
    tt._follow_debounce(pending, "two", lambda: calls.append("two"),
                        schedule=scheduler.schedule, cancel=scheduler.cancel)
    assert scheduler.cancelled == []
    assert set(pending) == {"one", "two"}
    for _delay, fire in list(scheduler.sources.values()):
        fire()
    assert calls == ["one", "two"]


def test_follow_debounce_swallows_a_failing_callback(registry, monkeypatch):
    scheduler = FakeScheduler()
    pending = {}

    def explode():
        raise RuntimeError("boom")

    tt._follow_debounce(pending, "win", explode,
                        schedule=scheduler.schedule, cancel=scheduler.cancel)
    _delay, fire = scheduler.sources[pending["win"]]
    assert fire() is False  # the exception never leaves the GTK callback
    assert pending == {}


# -- socket delivery --------------------------------------------------------

def test_follow_send_writes_one_json_line_and_reads_the_reply(tmp_path):
    socket_path = str(tmp_path / "s.sock")
    received = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)

    def serve():
        try:
            connection, _address = server.accept()
            with connection:
                data = b""
                while b"\n" not in data:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                received.append(data)
                connection.sendall(b'{"ok":true,"applied":true}\n')
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    payload = {"op": "cd", "path": "/tmp/a b"}
    reply = tt._follow_send(socket_path, payload, timeout=2.0)
    thread.join(3)
    assert reply == {"ok": True, "applied": True}
    assert received
    assert json.loads(received[0].decode("utf-8")) == payload


def test_follow_send_returns_none_for_an_unreachable_relay(tmp_path):
    missing = str(tmp_path / "nope.sock")
    assert tt._follow_send(missing, {"op": "cd", "path": "/tmp"}, timeout=0.2) is None


# -- watcher ----------------------------------------------------------------

class FakeSignalWidget(FakeWidget):
    """FakeWidget with just enough of the GObject signal API."""

    def __init__(self, type_name, children=(), props=None):
        super().__init__(type_name, children, props)
        self._handlers = {}
        self._next_handler = 1

    def connect(self, signal, callback):
        handler = self._next_handler
        self._next_handler += 1
        self._handlers.setdefault(signal, {})[handler] = callback
        return handler

    def disconnect(self, handler):
        for handlers in self._handlers.values():
            handlers.pop(handler, None)

    def emit(self, signal):
        result = None
        for callback in list(self._handlers.get(signal, {}).values()):
            result = callback(self, None)
        return result

    def get_visible(self):
        return True

    def is_active(self):
        return True


class FakeWindowSlot(FakeSignalWidget):
    def __init__(self, path):
        super().__init__("NautilusWindowSlot",
                         props={"active": True, "location": FakeLocation(path)})


class FakeNautilusWindow(FakeSignalWidget):
    def __init__(self, children):
        super().__init__("GtkApplicationWindow", children=children,
                         props={"active-slot": children[0] if children else None})


def _pump(predicate, timeout=5.0):
    """Run the GLib main context until *predicate* is true."""
    context = tt.GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)


def _stop_watcher(watcher):
    for key in list(watcher._windows):
        watcher._detach(key)
    if watcher._rescan_source is not None:
        tt.GLib.source_remove(watcher._rescan_source)
        watcher._rescan_source = None


def _listening_relay(socket_path, received):
    """Accept connections on *socket_path* and collect their JSON lines."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(4)

    def serve():
        try:
            for _attempt in range(4):
                connection, _address = server.accept()
                with connection:
                    data = b""
                    while b"\n" not in data:
                        chunk = connection.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    received.append(data)
        except OSError:
            pass
        finally:
            server.close()

    threading.Thread(target=serve, daemon=True).start()
    return server


def test_watcher_sends_the_new_folder_to_the_relay(registry):
    token = "abcdefabcdef"
    socket_path = tt._follow_socket_path(token)
    received = []
    server = _listening_relay(socket_path, received)
    slot = FakeWindowSlot("/tmp/first")
    window = FakeNautilusWindow([slot])
    watcher = tt._FollowWatcher()
    try:
        assert watcher.attach(window, token) is True
        slot.props["location"] = FakeLocation("/tmp/second")
        slot.emit("notify::location")
        _pump(lambda: bool(received))
    finally:
        _stop_watcher(watcher)
        server.close()
    assert received, "the relay never received a request"
    assert json.loads(received[-1].decode("utf-8")) == {
        "op": "cd", "path": "/tmp/second"}


def test_watcher_detaches_when_the_window_closes(registry):
    slot = FakeWindowSlot("/tmp/first")
    window = FakeNautilusWindow([slot])
    watcher = tt._FollowWatcher()
    try:
        assert watcher.attach(window, "aaaaaaaaaaaa") is True
        assert watcher._windows
        assert window.emit("close-request") is False  # let the window close
        assert watcher._windows == {}
    finally:
        _stop_watcher(watcher)


def test_watcher_detaches_a_refused_relay_and_notifies_once(registry, monkeypatch):
    token = "0123456789ab"
    socket_path = tt._follow_socket_path(token)
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(socket_path)  # the file stays behind, but nobody listens
    dead.close()
    notices = []
    monkeypatch.setattr(tt, "_notify", notices.append)
    slot = FakeWindowSlot("/tmp/first")
    window = FakeNautilusWindow([slot])
    watcher = tt._FollowWatcher()
    try:
        assert watcher.attach(window, token) is True
        slot.props["location"] = FakeLocation("/tmp/second")
        slot.emit("notify::location")
        _pump(lambda: not watcher._windows)
    finally:
        _stop_watcher(watcher)
    assert notices == [tt.T["err_follow_detached"]]
    assert watcher._windows == {}


# -- window slots -----------------------------------------------------------

def test_iter_slots_finds_slots_at_every_depth():
    deep_slot = FakeWidget("NautilusWindowSlot", props={"location": None})
    shallow_slot = FakeWidget("NautilusWindowSlot", props={"location": None})
    box = FakeWidget("GtkBox", children=[deep_slot, FakeWidget("GtkLabel")])
    window = FakeWidget("GtkApplicationWindow", children=[box, shallow_slot])
    assert tt._iter_slots(window) == [shallow_slot, deep_slot]
    assert tt._iter_slots(None) == []


def test_slot_path_returns_only_local_folders():
    assert tt._slot_path(FakeWidget("NautilusWindowSlot",
                                    props={"location": FakeLocation("/home/u/x")})) \
        == "/home/u/x"
    assert tt._slot_path(FakeWidget("NautilusWindowSlot",
                                    props={"location": FakeLocation(None)})) == ""
    assert tt._slot_path(FakeWidget("NautilusWindowSlot",
                                    props={"location": FakeLocation("smb://host/share")})) == ""
    assert tt._slot_path(FakeWidget("NautilusWindowSlot",
                                    props={"location": None})) == ""
    # A slot without the property at all must not raise.
    assert tt._slot_path(FakeWidget("NautilusWindowSlot")) == ""


def test_slot_has_location_detects_the_property():
    assert tt._slot_has_location(FakeWidget("NautilusWindowSlot",
                                            props={"location": None})) is True
    assert tt._slot_has_location(FakeWidget("NautilusWindowSlot")) is False


def test_active_slot_prefers_the_marked_slot():
    first = FakeWidget("NautilusWindowSlot", props={"active": False, "location": None})
    second = FakeWidget("NautilusWindowSlot", props={"active": True, "location": None})
    window = FakeWidget("GtkApplicationWindow", props={"active-slot": first})
    assert tt._active_slot(window, [first, second]) is second


def test_active_slot_falls_back_to_the_window_property():
    first = FakeWidget("NautilusWindowSlot", props={"active": False, "location": None})
    window = FakeWidget("GtkApplicationWindow", props={"active-slot": first})
    assert tt._active_slot(window, [first]) is first
    window.props["active-slot"] = None
    assert tt._active_slot(window, [first]) is None


def test_active_path_reads_the_active_slot():
    slot = FakeWidget("NautilusWindowSlot",
                      props={"active": True,
                             "location": FakeLocation("/home/u/Project")})
    window = FakeWidget("GtkApplicationWindow", children=[slot])
    assert tt._active_path(window) == "/home/u/Project"
    assert tt._active_path(None) == ""


def test_follow_supported_accepts_a_slot_with_a_location_property(registry, monkeypatch):
    monkeypatch.setattr(tt, "_FOLLOW_SUPPORTED", True)
    slot = FakeWidget("NautilusWindowSlot", props={"location": None})
    window = FakeWidget("GtkApplicationWindow", children=[slot])
    assert tt._follow_supported(window) is True
    assert tt._FOLLOW_SUPPORTED is True


def test_follow_supported_does_not_cache_an_unanswered_probe(registry, monkeypatch):
    """No window, or a window still being built, proves nothing about the host.

    Caching that answer would switch following off until the next Nautilus
    restart because of a single awkward click, so the verdict must stay open.
    """
    monkeypatch.setattr(tt, "_FOLLOW_SUPPORTED", True)
    monkeypatch.setenv("NAUTILUS_FOLLOW_DEBUG", "1")
    assert tt._follow_supported(None) is False
    assert tt._FOLLOW_SUPPORTED is True
    assert tt._follow_supported(FakeWidget("GtkApplicationWindow")) is False
    assert tt._FOLLOW_SUPPORTED is True
    log = registry / "follow-nautilus.log"
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "following disabled" not in text


def test_follow_supported_disables_itself_once_and_logs(registry, monkeypatch):
    monkeypatch.setattr(tt, "_FOLLOW_SUPPORTED", True)
    monkeypatch.setenv("NAUTILUS_FOLLOW_DEBUG", "1")
    # A slot we can see but cannot read is a real answer: the host stopped
    # exposing the browsed folder, and only then does the verdict stick.
    window = FakeWidget(
        "GtkApplicationWindow",
        children=[FakeWidget("NautilusWindowSlot", props={"label": "nautilus"})],
    )
    assert tt._follow_supported(window) is False
    assert tt._FOLLOW_SUPPORTED is False
    log = registry / "follow-nautilus.log"
    assert "following disabled" in log.read_text(encoding="utf-8")
    # A later window is not probed again, and nothing raises.
    readable = FakeWidget("GtkApplicationWindow",
                          children=[FakeWidget("NautilusWindowSlot", props={"location": None})])
    assert tt._follow_supported(readable) is False


# -- running a script inside the synced terminal -----------------------------

class _RoutingWatcher:
    """Watcher stand-in: answers from a queue and records every request."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.sent = []

    def send(self, window, payload, reply=True, timeout=None):
        self.sent.append((payload, reply))
        return self.answers.pop(0) if self.answers else None


def test_follow_run_payload_carries_the_script_and_its_folder(tmp_path):
    script = tmp_path / "job.sh"
    script.write_text("echo hi\n")          # no shebang: the extension rules
    assert tt._follow_run_payload([str(script)]) == [{
        "op": "run",
        "argv": ["bash", str(script)],
        "cwd": str(tmp_path),
    }]


def test_follow_run_payload_keeps_the_shebang_authority(tmp_path):
    script = tmp_path / "job.sh"
    script.write_text("#!/usr/bin/env python3\nprint('hi')\n")
    payload = tt._follow_run_payload([str(script)])[0]
    assert payload["argv"] == ["/usr/bin/env", "python3", str(script)]


def test_follow_run_payload_prefixes_sudo(tmp_path):
    script = tmp_path / "job.sh"
    script.write_text("echo hi\n")
    payload = tt._follow_run_payload([str(script)], sudo=True)[0]
    # sudo + interpreter + path, exactly what the menu used to type.
    assert payload["argv"] == ["sudo", "bash", str(script)]


def test_follow_run_without_a_watcher_falls_back():
    assert tt._follow_run(None, None, ["/tmp/x.sh"]) is False


def test_follow_run_falls_back_when_nobody_answers(registry):
    assert tt._follow_run(_RoutingWatcher(), None, ["/tmp/x.sh"]) is False


def test_follow_run_falls_back_when_the_relay_refuses(registry):
    watcher = _RoutingWatcher({"ok": False, "applied": False, "error": "busy"})
    assert tt._follow_run(watcher, None, ["/tmp/x.sh"]) is False


def test_follow_run_uses_the_synced_terminal(registry):
    watcher = _RoutingWatcher({"ok": True, "applied": True})
    assert tt._follow_run(watcher, None, ["/tmp/x.sh"]) is True
    payload, reply = watcher.sent[0]
    assert payload == {"op": "run", "argv": ["bash", "/tmp/x.sh"], "cwd": "/tmp"}
    assert reply is True


def test_follow_run_tells_the_user_when_the_shell_hides_its_prompt(registry, monkeypatch):
    notices = []
    monkeypatch.setattr(tt, "_notify", notices.append)
    watcher = _RoutingWatcher({"ok": False, "applied": False, "reason": "no-markers"})
    # A usable session: the user is told why nothing happened, and the menu
    # must not open a second terminal that would hide that reason.
    assert tt._follow_run(watcher, None, ["/tmp/x.sh"]) is True
    assert notices == [tt.T["err_follow_shell"]]


def test_follow_run_hands_the_rest_of_the_selection_over(registry):
    watcher = _RoutingWatcher({"ok": True, "applied": True},
                              {"ok": True, "applied": True})
    assert tt._follow_run(watcher, None, ["/tmp/a.sh", "/tmp/b.sh"]) is True
    assert len(watcher.sent) == 2
    assert watcher.sent[0][1] is True    # the route is decided on the first
    assert watcher.sent[1][1] is False   # the rest is best effort
    assert watcher.sent[1][0]["argv"] == ["bash", "/tmp/b.sh"]


def test_run_in_terminal_survives_a_broken_router(registry, monkeypatch):
    """Routing may never break the action it is supposed to improve."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("router down")

    opened = []
    monkeypatch.setattr(tt, "_follow_run", boom)
    monkeypatch.setattr(tt, "_launch_run",
                        lambda scripts, sudo=False: opened.append((scripts, sudo)) or True)
    extension = tt.TerminalToolsExtension()
    extension._on_run(None, ["/tmp/x.sh"], sudo=False)
    assert opened == [(["/tmp/x.sh"], False)]


def test_watcher_send_prefers_the_attached_relay(registry, monkeypatch):
    seen = []

    def record(path, payload, timeout=None, reply=True):
        seen.append(path)
        return {"ok": True}

    monkeypatch.setattr(tt, "_follow_send", record)
    window = FakeNautilusWindow([FakeWindowSlot("/tmp/here")])
    watcher = tt._FollowWatcher()
    try:
        assert watcher.attach(window, "abcdefabcdef") is True
        assert watcher.send(window, {"op": "status"}) == {"ok": True}
    finally:
        _stop_watcher(watcher)
    assert seen == [tt._follow_socket_path("abcdefabcdef")]


def test_watcher_send_falls_back_to_the_current_session(registry, monkeypatch):
    registry.mkdir(parents=True, exist_ok=True)
    stale = "/run/user/0/nautilus-follow/s-stale.sock"
    (registry / "current").write_text(stale + "\n", encoding="utf-8")
    seen = []

    def record(path, payload, timeout=None, reply=True):
        seen.append(path)
        return {"ok": True}

    monkeypatch.setattr(tt, "_follow_send", record)
    watcher = tt._FollowWatcher()
    try:
        assert watcher.send(None, {"op": "status"}) == {"ok": True}
    finally:
        _stop_watcher(watcher)
    assert seen == [stale]


# -- menu wiring and i18n ---------------------------------------------------

def test_follow_menu_item_is_added_to_both_menus():
    source = pathlib.Path(EXT_PATH).read_text(encoding="utf-8")
    assert source.count('name="TerminalTools::OpenFollow"') == 1
    assert source.count('label=T["open_follow_label"]') == 1
    assert source.count('tip=T["tip_open_follow"]') == 1
    assert source.count("self._make_open_follow_item(") == 2


def test_follow_translation_keys_exist_in_every_locale():
    tables = _locale_tables(EXT_PATH)
    for locale, keys in tables.items():
        assert set(FOLLOW_KEYS) <= keys, "locale %s misses %s" % (
            locale, sorted(set(FOLLOW_KEYS) - keys))


def test_follow_plural_labels_keep_the_counter_in_every_locale():
    tree = ast.parse(pathlib.Path(EXT_PATH).read_text(encoding="utf-8"))
    found = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(target, "id", None) == "T" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        values = {key.value: value.value
                  for key, value in zip(node.value.keys, node.value.values)}
        assert "{n}" in values["run_follow_label_many"]
        assert "{n}" in values["tip_run_follow_many"]
        found += 1
    assert found == 5


# ---------------------------------------------------------------------------
# i18n contract
# ---------------------------------------------------------------------------

def _branch_label(test):
    """Return the locale of an ``_lang.startswith("xx")`` branch."""
    if isinstance(test, ast.Call):
        for argument in test.args:
            if isinstance(argument, ast.Constant):
                return argument.value
    if isinstance(test, ast.Compare):
        for comparator in test.comparators:
            if isinstance(comparator, ast.Constant):
                return comparator.value
    return ""


def _locale_tables(path):
    """Return {locale: set(keys)} for every translation table in the file."""
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    tables = {}
    node = None
    for statement in tree.body:
        if isinstance(statement, ast.If) and _branch_label(statement.test):
            node = statement
            break
    if node is None:
        return tables

    def collect(body, label):
        for inner in body:
            if not isinstance(inner, ast.Assign):
                continue
            if not any(getattr(target, "id", None) == "T" for target in inner.targets):
                continue
            if isinstance(inner.value, ast.Dict):
                tables[label] = {key.value for key in inner.value.keys}

    label = _branch_label(node.test)
    while True:
        collect(node.body, label)
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            node = node.orelse[0]
            label = _branch_label(node.test)
            continue
        collect(node.orelse, "en")
        break
    return tables


def test_every_locale_has_the_same_translation_keys():
    tables = _locale_tables(EXT_PATH)
    assert set(tables) == {"fr", "es", "pt", "de", "en"}
    reference = tables["en"]
    assert reference
    for locale, keys in tables.items():
        assert keys == reference, "locale %s is missing %s" % (
            locale, sorted(reference ^ keys))


def test_every_translation_key_used_in_the_code_exists():
    source = pathlib.Path(EXT_PATH).read_text(encoding="utf-8")
    used = set(re.findall(r'T\["([^"]+)"\]', source))
    assert used
    tables = _locale_tables(EXT_PATH)
    for locale, keys in tables.items():
        assert used <= keys, "locale %s misses %s" % (locale, sorted(used - keys))


def test_labels_are_not_empty_in_any_locale():
    tables = _locale_tables(EXT_PATH)
    for locale, keys in tables.items():
        assert keys, locale
    tree = ast.parse(pathlib.Path(EXT_PATH).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(target, "id", None) == "T" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            assert isinstance(value, ast.Constant), key.value
            assert isinstance(value.value, str) and value.value.strip(), key.value
