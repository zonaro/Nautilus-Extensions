"""Unit tests for the Terminal Tools Nautilus extension.

The extension needs GTK/Nautilus at import time, so the whole module is
skipped when those are unavailable. The tests only cover the pure helpers:
script detection, shell snippet building, desktop entry parsing and the
i18n coverage contract.
"""

import ast
import importlib.util
import os
import pathlib
import re
import subprocess

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


def test_open_script_enters_the_folder_and_starts_a_shell():
    script = tt._build_open_script("/home/user/My Folder")
    assert script.startswith("cd '/home/user/My Folder' || exit 1")
    assert 'exec "${SHELL:-/bin/bash}"' in script


def test_generated_scripts_are_valid_shell():
    for script in (tt._build_run_script(["true"]), tt._build_open_script("/tmp")):
        proc = subprocess.run(["bash", "-n"], input=script, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert proc.returncode == 0, proc.stdout


def test_paths_with_spaces_are_quoted():
    script = tt._build_open_script("/tmp/a b/c")
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

def test_terminal_candidates_are_resolvable_prefixes():
    candidates = tt._terminal_candidates()
    assert isinstance(candidates, list)
    for prefix in candidates:
        assert prefix
        assert all(isinstance(part, str) for part in prefix)


def test_gsettings_string_survives_a_missing_schema():
    assert tt._gsettings_string("org.gnome.this.schema.does.not.exist", "exec") == ""


def test_resolve_binary_rejects_nothing_installed():
    assert tt._resolve_binary("definitely-not-a-real-binary-xyz") == ""
    assert tt._resolve_binary("") == ""


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
