"""Unit tests for the follow-shell relay and its sender mode.

The module is a standalone script, so it is loaded by path. The tests cover
the pure contract (registry paths, wire protocol, marker scanning, injection
policy, shell integration and command quoting) plus one real end-to-end run
of relay mode over a pair of ptys with a fake shell.
"""

import importlib.util
import json
import os
import pathlib
import pty
import select
import shlex
import socket
import stat
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FS_PATH = os.path.join(REPO_ROOT, "follow-shell.py")

VALID_TOKEN = "0123456789ab"


def _load_module():
    """Import ``follow-shell.py`` under the name ``fs``."""
    spec = importlib.util.spec_from_file_location("follow_shell", FS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fs = _load_module()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_dir_prefers_the_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NAUTILUS_FOLLOW_DIR", str(tmp_path / "custom"))
    assert fs.registry_dir() == str(tmp_path / "custom")
    assert fs.registry_dir(str(tmp_path / "other")) == str(tmp_path / "other")


def test_registry_dir_falls_back_to_the_runtime_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("NAUTILUS_FOLLOW_DIR", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    assert fs.registry_dir() == str(tmp_path / "run" / "nautilus-follow")


def test_registry_dir_falls_back_to_tmp_with_the_uid(monkeypatch):
    monkeypatch.delenv("NAUTILUS_FOLLOW_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert fs.registry_dir() == "/tmp/nautilus-follow-%d" % os.getuid()
    # A relative runtime directory is invalid, as in terminal-tools.py.
    monkeypatch.setenv("XDG_RUNTIME_DIR", "relative/run")
    assert fs.registry_dir() == "/tmp/nautilus-follow-%d" % os.getuid()


def test_ensure_registry_creates_a_private_directory(tmp_path):
    root = fs.ensure_registry(str(tmp_path / "registry"))
    assert os.path.isdir(root)
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700


def test_registry_paths_are_built_from_the_token(tmp_path):
    root = str(tmp_path / "registry")
    assert fs.socket_path(VALID_TOKEN, root) == os.path.join(
        root, "s-%s.sock" % VALID_TOKEN)
    assert fs.meta_path(VALID_TOKEN, root) == os.path.join(
        root, "s-%s.meta.json" % VALID_TOKEN)
    assert fs.current_path(root) == os.path.join(root, "current")
    assert fs.rc_dir(VALID_TOKEN, root) == os.path.join(
        root, "rc", VALID_TOKEN)
    assert fs.relay_log_path(VALID_TOKEN, root) == os.path.join(
        root, "%s.relay.log" % VALID_TOKEN)
    assert fs.extension_log_path(root) == os.path.join(
        root, "follow-nautilus.log")


def test_tokens_are_12_lowercase_hex_characters():
    assert fs.valid_token("0123456789ab") is True
    for bad in ("", "0123456789AB", "0123456789abc", "0123456789a",
                "../etc/passwd", "0123456789ag", None):
        assert fs.valid_token(bad) is False


def test_meta_record_has_the_agreed_fields():
    record = fs.meta_record(
        VALID_TOKEN, 1234, "/tmp", "/bin/bash", "marker", nautilus_pid=99)
    assert record == {
        "token": VALID_TOKEN,
        "pid": 1234,
        "started": record["started"],
        "cwd": "/tmp",
        "shell": "/bin/bash",
        "mode": "marker",
        "nautilus_pid": 99,
    }
    assert isinstance(record["started"], str) and record["started"]


# ---------------------------------------------------------------------------
# Wire protocol
# ---------------------------------------------------------------------------

def test_encode_message_is_one_utf8_line():
    payload = fs.encode_message({"op": "cd", "path": "/tmp/ação"})
    assert isinstance(payload, bytes)
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert "/tmp/ação".encode("utf-8") in payload


def test_decode_message_round_trips_requests():
    request = {"op": "run", "argv": ["bash", "/tmp/a b.sh"],
               "cwd": "/tmp/a b"}
    assert fs.decode_message(fs.encode_message(request)) == request
    assert fs.decode_message(fs.encode_message(request).decode()) == request


@pytest.mark.parametrize("line", [
    b"",
    b"   ",
    b"not json",
    b"[]",
    b'"text"',
    b"\xff\xfe",
])
def test_decode_message_rejects_malformed_lines(line):
    with pytest.raises(fs.ProtocolError):
        fs.decode_message(line)


def test_line_buffer_reassembles_requests_across_reads():
    buffer = fs.LineBuffer()
    encoded = fs.encode_message({"op": "status"})
    assert buffer.feed(encoded[:5]) == []
    assert buffer.feed(encoded[5:]) == [encoded[:-1]]
    assert buffer.feed(b"\n\n") == [b"", b""]


# ---------------------------------------------------------------------------
# Prompt marker scanning
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("split", range(1, len(fs.PROMPT_MARKER)))
def test_marker_is_found_across_every_chunk_boundary(split):
    scanner = fs.MarkerScanner()
    assert scanner.feed(fs.PROMPT_MARKER[:split]) is False
    assert scanner.feed(fs.PROMPT_MARKER[split:]) is True


def test_marker_is_found_byte_by_byte():
    scanner = fs.MarkerScanner()
    results = [scanner.feed(bytes([byte])) for byte in fs.PROMPT_MARKER]
    assert results == [False] * (len(fs.PROMPT_MARKER) - 1) + [True]


def test_marker_is_found_inside_a_larger_chunk():
    scanner = fs.MarkerScanner()
    assert scanner.feed(b"user@host:~$ ") is False
    assert scanner.feed(b"before" + fs.PROMPT_MARKER + b"after") is True
    # The following chunk is ordinary output, not another prompt event.
    assert scanner.feed(b"command output") is False
    assert scanner.feed(fs.PROMPT_MARKER) is True


def test_other_osc_sequences_are_not_prompts():
    scanner = fs.MarkerScanner()
    assert scanner.feed(b"\x1b]777;nautilus-follow;other\x07") is False
    assert scanner.feed(b"\x1b]0;title\x07") is False
    # A marker split by that noise still completes on the next read.
    assert scanner.feed(fs.PROMPT_MARKER) is True


# ---------------------------------------------------------------------------
# Injection policy truth table
# ---------------------------------------------------------------------------

def _expected_blocker(state, dirty, foreground, alive, mode):
    if mode != "marker":
        return "no-markers"
    if not alive:
        return "dead"
    if not foreground:
        return "not-foreground"
    if dirty:
        return "typing"
    if state == "prompt":
        return ""
    return "starting" if state == "starting" else "busy"


POLICY_CASES = [
    (state, dirty, foreground, alive)
    for state in ("starting", "busy", "prompt")
    for dirty in (False, True)
    for foreground in (False, True)
    for alive in (False, True)
]


@pytest.mark.parametrize("state,dirty,foreground,alive", POLICY_CASES)
def test_injection_policy_truth_table(state, dirty, foreground, alive):
    expected = _expected_blocker(
        state, dirty, foreground, alive, "marker")
    assert fs.injection_blocker(
        state, dirty, foreground, alive, "marker") == expected
    assert fs.can_inject(
        state, dirty, foreground, alive, "marker") is (expected == "")
    assert fs.injection_blocker(
        state, dirty, foreground, alive, "unsupported") == "no-markers"
    assert fs.can_inject(
        state, dirty, foreground, alive, "unsupported") is False


def test_injection_is_only_allowed_for_a_clean_prompt_with_the_foreground():
    assert fs.can_inject("prompt", False, True, True) is True
    assert fs.can_inject("prompt", True, True, True) is False
    assert fs.can_inject("prompt", False, False, True) is False
    assert fs.can_inject("prompt", False, True, False) is False
    assert fs.can_inject("busy", False, True, True) is False


# ---------------------------------------------------------------------------
# Injection bytes and quoting
# ---------------------------------------------------------------------------

def test_cd_command_quotes_spaces_quotes_and_dollars():
    path = "/tmp/a b/it's \"quoted\" $HOME;rm -rf ~"
    command = fs.cd_command(path)
    assert isinstance(command, bytes)
    assert command.endswith(b"\n")
    assert shlex.split(command.decode("utf-8")) == ["cd", "--", path]


def test_run_command_adds_the_directory_and_quotes_every_argument():
    argv = ["bash", "/tmp/a b/run's $script.sh"]
    cwd = "/tmp/a b/$work"
    line = fs.run_command(argv, cwd).decode("utf-8")
    assert line.endswith("\n")
    assert shlex.split(line) == ["cd", "--", cwd, "&&", "bash", argv[1]]


def test_run_command_without_a_directory_does_not_cd():
    line = fs.run_command(["echo", "hello world"]).decode("utf-8")
    assert shlex.split(line) == ["echo", "hello world"]


def test_generated_command_lines_are_valid_bash():
    lines = [
        fs.cd_command("/tmp/a b/$x"),
        fs.run_command(["bash", "/tmp/a b/x.sh"], "/tmp/a b"),
        fs.run_command(["echo", "it's"]),
    ]
    for line in lines:
        proc = subprocess.run(
            ["bash", "-n"], input=line, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


@pytest.mark.parametrize("argv", [[], None, [""], ["ok", 3]])
def test_run_command_rejects_bad_arguments(argv):
    with pytest.raises(ValueError):
        fs.run_command(argv)


@pytest.mark.parametrize("path", ["", None, 3])
def test_cd_command_rejects_bad_paths(path):
    with pytest.raises(ValueError):
        fs.cd_command(path)


# ---------------------------------------------------------------------------
# Shell integration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("/bin/bash", "bash"),
    ("/usr/bin/bash", "bash"),
    ("-bash", "bash"),
    ("/usr/bin/rbash", "bash"),
    ("/usr/bin/zsh", "zsh"),
    ("/usr/local/bin/fish", "fish"),
    ("/bin/sh", ""),
    ("/usr/bin/dash", ""),
])
def test_shell_kind(path, expected):
    assert fs.shell_kind(path) == expected


def test_bash_rc_sources_the_user_file_and_installs_the_marker():
    content = fs.bash_rc_content()
    assert 'source "$HOME/.bashrc"' in content
    assert "__nf_prompt" in content
    assert "PROMPT_COMMAND" in content
    assert "PROMPT_COMMAND+=(__nf_prompt)" in content
    assert "\\033]777;nautilus-follow;prompt\\007" in content


def test_zsh_rc_sources_the_user_file_and_appends_precmd():
    content = fs.zsh_rc_content()
    assert 'source "$HOME/.zshrc"' in content
    assert "precmd_functions+=(__nf_prompt)" in content
    assert "\\033]777;nautilus-follow;prompt\\007" in content


def test_fish_init_wraps_the_existing_prompt():
    command = fs.fish_init_command()
    assert "functions --copy fish_prompt __nf_prompt_original" in command
    assert "__nf_prompt_original" in command
    assert "\\033]777;nautilus-follow;prompt\\007" in command


def test_shell_invocation_writes_the_bash_rc_file(tmp_path):
    root = str(tmp_path / "registry")
    argv, env = fs.shell_invocation("/bin/bash", "bash", VALID_TOKEN, root)
    assert argv[0] == "/bin/bash"
    assert argv[1] == "--rcfile"
    assert argv[3] == "-i"
    assert env == {}
    rc = pathlib.Path(argv[2])
    assert rc.name == "bashrc"
    assert rc.parent == pathlib.Path(fs.rc_dir(VALID_TOKEN, root))
    assert fs.bash_rc_content() == rc.read_text(encoding="utf-8")
    assert stat.S_IMODE(rc.stat().st_mode) == 0o600


def test_shell_invocation_points_zsh_at_the_generated_zdotdir(tmp_path):
    root = str(tmp_path / "registry")
    argv, env = fs.shell_invocation("/usr/bin/zsh", "zsh", VALID_TOKEN, root)
    assert argv == ["/usr/bin/zsh", "-i"]
    directory = pathlib.Path(fs.rc_dir(VALID_TOKEN, root))
    assert env == {"ZDOTDIR": str(directory)}
    assert (directory / ".zshrc").read_text(encoding="utf-8") == fs.zsh_rc_content()


def test_shell_invocation_for_fish_uses_init_command(tmp_path):
    root = str(tmp_path / "registry")
    argv, env = fs.shell_invocation("/usr/bin/fish", "fish", VALID_TOKEN, root)
    assert argv[:2] == ["/usr/bin/fish", "--init-command"]
    assert argv[2] == fs.fish_init_command()
    assert argv[3] == "-i"
    assert env == {}


def test_an_unknown_shell_starts_without_integration(tmp_path):
    root = str(tmp_path / "registry")
    assert fs.shell_invocation("/bin/dash", "", VALID_TOKEN, root) == (
        ["/bin/dash", "-i"], {})
    assert not os.path.exists(fs.rc_dir(VALID_TOKEN, root))
    assert fs.rc_content("") == ""


# ---------------------------------------------------------------------------
# Script detection and run requests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("script.sh", ["bash", "script.sh"]),
    ("script.zsh", ["zsh", "script.zsh"]),
    ("script.fish", ["fish", "script.fish"]),
    ("script.py", ["python3", "script.py"]),
    ("script.awk", ["awk", "-f", "script.awk"]),
    ("SCRIPT.SH", ["bash", "SCRIPT.SH"]),
])
def test_script_argv_uses_the_extension_table(name, expected):
    assert fs.script_argv(name) == expected


def test_script_argv_prefers_the_shebang(tmp_path):
    script = tmp_path / "runner.sh"
    script.write_text("#!/usr/bin/env python3\nprint('hi')\n")
    assert fs.script_argv(str(script)) == [
        "/usr/bin/env", "python3", str(script)]


def test_script_argv_without_a_shebang_uses_the_extension(tmp_path):
    script = tmp_path / "runner.sh"
    script.write_text("echo hi\n")
    assert fs.script_argv(str(script)) == ["bash", str(script)]


def test_run_request_runs_one_script_in_its_own_directory(tmp_path):
    script = tmp_path / "a b" / "run.sh"
    script.parent.mkdir()
    script.write_text("echo hi\n")
    request = fs.build_run_request([str(script)])
    assert request == {
        "op": "run",
        "argv": ["bash", str(script)],
        "cwd": str(script.parent),
    }


def test_run_request_with_sudo_and_an_explicit_directory(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("#!/usr/bin/python3\n")
    request = fs.build_run_request(
        [str(script)], cwd=str(tmp_path), sudo=True)
    assert request["argv"] == ["sudo", "/usr/bin/python3", str(script)]
    assert request["cwd"] == str(tmp_path)


def test_run_request_joins_many_scripts_into_one_shell_command(tmp_path):
    first = tmp_path / "a b" / "one.sh"
    second = tmp_path / "two.py"
    first.parent.mkdir()
    first.write_text("echo one\n")
    second.write_text("print('two')\n")
    request = fs.build_run_request([str(first), str(second)], sudo=True)
    assert request["op"] == "run"
    assert request["argv"][:2] == ["bash", "-c"]
    line = request["argv"][2]
    assert "cd -- %s" % shlex.quote(str(first.parent)) in line
    assert "sudo bash %s" % shlex.quote(str(first)) in line
    assert "cd -- %s" % shlex.quote(str(tmp_path)) in line
    assert "sudo python3 %s" % shlex.quote(str(second)) in line
    proc = subprocess.run(
        ["bash", "-n"], input=line, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout


def test_run_request_needs_a_file():
    with pytest.raises(ValueError):
        fs.build_run_request([])


# ---------------------------------------------------------------------------
# Sender mode
# ---------------------------------------------------------------------------

def test_resolve_socket_prefers_the_explicit_path(tmp_path):
    assert fs._resolve_socket("/tmp/x.sock", str(tmp_path)) == "/tmp/x.sock"


def test_resolve_socket_reads_current(tmp_path):
    root = fs.ensure_registry(str(tmp_path / "registry"))
    with open(fs.current_path(root), "w", encoding="utf-8") as handle:
        handle.write("/tmp/current.sock\n")
    assert fs._resolve_socket("", root) == "/tmp/current.sock"


def test_resolve_socket_returns_empty_without_a_relay(tmp_path):
    assert fs._resolve_socket("", str(tmp_path / "missing")) == ""


def test_describe_reply_summarises_applied_queued_and_status():
    assert fs.describe_reply(
        {"op": "cd"}, {"ok": True, "applied": True}) == (
            "cd applied in the synced terminal")
    assert fs.describe_reply(
        {"op": "cd"},
        {"ok": True, "applied": False, "reason": "typing"}) == (
            "cd queued until the next prompt (typing)")
    assert fs.describe_reply(
        {"op": "status"},
        {"ok": True, "pid": 7, "cwd": "/tmp", "mode": "marker",
         "prompt_ready": True}) == (
            "pid 7, cwd /tmp, mode marker, prompt ready")
    assert fs.describe_reply(
        {"op": "run"}, {"ok": False, "error": "no-markers"}) == (
            "run failed: no-markers")


def test_sender_mode_fails_when_no_relay_is_reachable(tmp_path, capsys):
    assert fs.sender_main([
        "--send", "status", "--socket", str(tmp_path / "missing.sock")]) == 1
    assert "cannot reach" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# End to end relay over a real pty
# ---------------------------------------------------------------------------

FAKE_SHELL = '''#!%(python)s
import os
import signal
import sys
import time

MARKER = %(marker)r
RECLAIM = %(reclaim)r


def emit():
    os.write(1, MARKER)


signal.signal(signal.SIGTTIN, signal.SIG_IGN)
signal.signal(signal.SIGTTOU, signal.SIG_IGN)
emit()
while True:
    line = sys.stdin.buffer.readline()
    if not line:
        break
    text = line.decode("utf-8", "replace").rstrip("\\r\\n")
    if text.startswith("detach"):
        helper = os.fork()
        if helper == 0:
            os.setpgid(0, 0)
            time.sleep(30)
            os._exit(0)
        for _ in range(500):
            try:
                if os.getpgid(helper) == helper:
                    break
            except OSError:
                pass
            time.sleep(0.01)
        os.write(1, b"DETACHED\\n")
        os.tcsetpgrp(0, helper)
        emit()
        while not os.path.exists(RECLAIM):
            time.sleep(0.02)
        os.tcsetpgrp(0, os.getpgrp())
        emit()
        try:
            os.kill(helper, signal.SIGTERM)
        except OSError:
            pass
        try:
            os.waitpid(helper, 0)
        except OSError:
            pass
        continue
    os.write(1, ("PWD:" + text + "\\n").encode("utf-8"))
    emit()
'''


class _PtyReader:
    """Keep the relay output flowing across several read_until calls."""

    def __init__(self, fd):
        self.fd = fd
        self.buffer = b""

    def read_until(self, needle, timeout=8.0):
        deadline = time.time() + timeout
        while needle not in self.buffer:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise AssertionError(
                    "timed out waiting for %r, got %r"
                    % (needle, self.buffer[-2000:]))
            readable, _writable, _errors = select.select(
                [self.fd], [], [], remaining)
            if not readable:
                continue
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                raise AssertionError(
                    "relay output ended while waiting for %r, got %r"
                    % (needle, self.buffer[-2000:]))
            self.buffer += chunk
        index = self.buffer.index(needle) + len(needle)
        head, self.buffer = self.buffer[:index], self.buffer[index:]
        return head


class _Client:
    """One persistent socket connection speaking the line protocol."""

    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(2.0)
        deadline = time.time() + 5.0
        while True:
            try:
                self.sock.connect(path)
                break
            except (ConnectionRefusedError, FileNotFoundError):
                if time.time() >= deadline:
                    raise
                time.sleep(0.02)
        self.buffer = b""

    def request(self, request):
        self.sock.sendall(fs.encode_message(request))
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise AssertionError("relay closed the socket")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return fs.decode_message(line)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _wait_ready(client, timeout=8.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.request({"op": "status"})
        if last.get("prompt_ready"):
            return last
        time.sleep(0.05)
    raise AssertionError("the relay never reported a ready prompt: %r" % last)


def _wait_exit(pid, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        waited, status = os.waitpid(pid, os.WNOHANG)
        if waited:
            return status
        time.sleep(0.05)
    raise AssertionError("the relay did not exit")


@pytest.mark.skipif(not os.path.exists("/dev/ptmx"),
                    reason="/dev/ptmx is unavailable")
@pytest.mark.filterwarnings(
    "ignore:.*multi-threaded.*:DeprecationWarning")
def test_relay_end_to_end_with_a_fake_shell(tmp_path):
    token = "00112233aabb"
    root = tmp_path / "registry"
    work = tmp_path / "work"
    target_a = tmp_path / "target one"
    target_b = tmp_path / "target's $two"
    target_c = tmp_path / "target three"
    reclaim = tmp_path / "reclaim"
    for directory in (work, target_a, target_b, target_c):
        directory.mkdir()

    shell_dir = tmp_path / "bin"
    shell_dir.mkdir()
    fake_shell = shell_dir / "bash"
    fake_shell.write_text(FAKE_SHELL % {
        "python": sys.executable,
        "marker": fs.PROMPT_MARKER,
        "reclaim": str(reclaim),
    })
    fake_shell.chmod(0o755)

    try:
        pid, master = pty.fork()
    except OSError as exc:
        pytest.skip("pty.fork is unavailable: %s" % exc)
    if pid == 0:  # pragma: no cover - runs in the relay child
        try:
            os.execv(sys.executable, [
                sys.executable, FS_PATH,
                "--dir", str(root),
                "--token", token,
                "--cwd", str(work),
                "--shell", str(fake_shell),
            ])
        finally:
            os._exit(127)

    reader = _PtyReader(master)
    client = None
    relay_status = None
    try:
        sock_path = fs.socket_path(token, str(root))
        deadline = time.time() + 8.0
        while time.time() < deadline and not os.path.exists(sock_path):
            time.sleep(0.02)
        assert os.path.exists(sock_path), "the relay never bound its socket"
        assert stat.S_IMODE(os.stat(sock_path).st_mode) == 0o600
        with open(fs.current_path(str(root)), encoding="utf-8") as handle:
            assert handle.read().strip() == sock_path
        with open(fs.meta_path(token, str(root)), encoding="utf-8") as handle:
            meta = json.load(handle)
        assert meta["token"] == token
        assert meta["pid"] == pid
        assert meta["cwd"] == str(work)
        assert meta["shell"] == str(fake_shell)
        assert meta["mode"] == "marker"
        assert meta["started"]
        assert os.path.isfile(
            os.path.join(fs.rc_dir(token, str(root)), "bashrc"))

        reader.read_until(fs.PROMPT_MARKER, 8.0)
        client = _Client(sock_path)
        status = _wait_ready(client)
        assert status["mode"] == "marker"
        assert status["cwd"] == str(work)
        assert status["pid"] > 0

        # 1. A cd sent through sender mode is injected at the prompt.
        sent = subprocess.run(
            [sys.executable, FS_PATH, "--send", "cd",
             "--path", str(target_a), "--dir", str(root)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=8)
        assert sent.returncode == 0, sent.stderr
        assert "applied" in sent.stdout
        reader.read_until(
            b"PWD:cd -- " + shlex.quote(str(target_a)).encode("utf-8"), 8.0)

        reader.read_until(fs.PROMPT_MARKER, 8.0)
        assert _wait_ready(client)["cwd"] == str(target_a)

        # 2. Typing at the prompt keeps the request queued until the next one.
        os.write(master, b"typed text")
        reader.read_until(b"typed text", 8.0)
        reply = client.request({"op": "cd", "path": str(target_b)})
        assert reply == {
            "ok": True, "applied": False, "reason": "typing"}
        os.write(master, b"\n")
        reader.read_until(b"PWD:typed text", 8.0)
        reader.read_until(
            b"PWD:cd -- " + shlex.quote(str(target_b)).encode("utf-8"), 8.0)

        # 3. While another process group owns the terminal, nothing is written.
        reader.read_until(fs.PROMPT_MARKER, 8.0)
        _wait_ready(client)
        os.write(master, b"detach\n")
        reader.read_until(b"DETACHED", 8.0)
        reader.read_until(fs.PROMPT_MARKER, 8.0)
        time.sleep(0.15)
        status = client.request({"op": "status"})
        assert status["mode"] == "marker"
        assert status["prompt_ready"] is False
        reply = client.request({"op": "cd", "path": str(target_c)})
        assert reply == {
            "ok": True, "applied": False, "reason": "not-foreground"}
        # Ask the fake shell to take the terminal back; the queued cd is
        # applied at the prompt marker it emits right after doing so.
        reclaim.write_text("go\n")
        reader.read_until(
            b"PWD:cd -- " + shlex.quote(str(target_c)).encode("utf-8"), 10.0)

        # The relay keeps the terminal usable and quits cleanly.
        assert client.request({"op": "unknown"}) == {
            "ok": False, "error": "unknown-op"}
        assert client.request({"op": "quit"}) == {"ok": True}
        relay_status = _wait_exit(pid)
        assert os.WIFEXITED(relay_status)
        assert os.WEXITSTATUS(relay_status) == 0
        assert not os.path.exists(sock_path)
        assert not os.path.exists(fs.meta_path(token, str(root)))
        assert not os.path.exists(fs.rc_dir(token, str(root)))
    finally:
        if client is not None:
            client.close()
        if relay_status is None:
            try:
                os.kill(pid, 9)
            except OSError:
                pass
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass
        try:
            os.close(master)
        except OSError:
            pass
