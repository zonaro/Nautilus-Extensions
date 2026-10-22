"""Unit tests for the folder-color-revival host helpers (no display needed).

The host module (``folder-color-revival.py``) has a dash in its name, so it
cannot be imported with a plain ``import`` statement -- it is loaded through
``importlib.util.spec_from_file_location`` instead.

These tests cover the helpers that keep the layered icon editor from
destroying colours that were applied through the regular colour menu:

* ``_spec_from_custom_icon``  -- read the colour spec back from a cached icon
* ``_current_color_specs``     -- current spec/hexes of a folder
* ``_apply_icon_state``        -- apply the editor result without data loss

plus the contract between the host and ``folder_icon_editor.py``
(``open_editor`` signature and i18n key coverage).
"""
import ast
import importlib.util
import inspect
import os
import pathlib
import sys

import pytest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

HOST_PATH = os.path.join(REPO_ROOT, "folder-color-revival.py")
EDITOR_PATH = os.path.join(REPO_ROOT, "folder_icon_editor.py")


def _load_host_module():
    """Import ``folder-color-revival.py`` under the name ``fcr``."""
    spec = importlib.util.spec_from_file_location("fcr", HOST_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    fcr = _load_host_module()
except Exception as exc:  # pragma: no cover - depends on the local typelibs
    pytest.skip("folder-color-revival.py is not importable here: %s" % exc,
                allow_module_level=True)


class FakeFolderColor:
    """Stand-in for ``FolderColor`` that only records what was applied."""

    def __init__(self, overlay_ok=True):
        self.overlay_calls = []
        self.color_calls = []
        self.overlay_ok = overlay_ok

    def set_custom_overlay_color(self, path, spec, state):
        self.overlay_calls.append((path, spec, state))
        return self.overlay_ok

    def set_custom_color(self, path, spec):
        self.color_calls.append((path, spec))


def _patch_sources(monkeypatch, state, attrs):
    """Replace the two state sources of the host with fixed values.

    ``state`` is what ``_load_overlay_state`` returns, ``attrs`` is the
    ``(custom_icon_uri, custom_icon_name)`` pair of ``_folder_custom_attrs``.
    """
    monkeypatch.setattr(fcr, "_load_overlay_state",
                        lambda *a, **k: state)
    monkeypatch.setattr(fcr, "_folder_custom_attrs",
                        lambda *a, **k: attrs)


def _patch_apply(monkeypatch, state=None, attrs=("", "")):
    """Patch everything ``_apply_icon_state`` may touch.

    Returns the list that records the ``_save_overlay_state`` calls.
    """
    saved = []
    _patch_sources(monkeypatch, state, attrs)
    monkeypatch.setattr(fcr, "_save_overlay_state",
                        lambda path, st: saved.append((path, st)))
    monkeypatch.setattr(fcr, "_clear_overlay_state", lambda *a, **k: None)
    return saved


# ---------------------------------------------------------------------------
# A. _spec_from_custom_icon
# ---------------------------------------------------------------------------

def test_spec_from_custom_icon_with_a_single_colour():
    """'folder-adwaita-3366ff.svg' -> '3366ff'."""
    uri = "file:///home/u/.cache/folder-color/folder-adwaita-3366ff.svg"
    assert fcr._spec_from_custom_icon(uri) == "3366ff"


def test_spec_from_custom_icon_with_two_colours():
    """'folder-adwaita-3366ff-f5c211.svg' -> '3366ff;f5c211'."""
    uri = "file:///home/u/.cache/folder-color/folder-adwaita-3366ff-f5c211.svg"
    assert fcr._spec_from_custom_icon(uri) == "3366ff;f5c211"


def test_spec_from_custom_icon_ignores_the_cache_digest():
    """The cache digest is not a colour and must not leak into the spec."""
    uri = ("file:///home/u/.cache/folder-color/"
           "folder-adwaita-3366ff-f5c211-1a2b3c4d5e.png")
    assert fcr._spec_from_custom_icon(uri) == "3366ff;f5c211"


def test_spec_from_custom_icon_without_any_colour():
    """An unrelated icon name has no colour spec."""
    assert fcr._spec_from_custom_icon("file:///tmp/foo.svg") == ""


def test_spec_from_custom_icon_with_an_empty_uri():
    """An empty or missing URI is simply unknown."""
    assert fcr._spec_from_custom_icon("") == ""
    assert fcr._spec_from_custom_icon(None) == ""


def test_folder_custom_attrs_of_a_plain_folder(tmp_path):
    """A folder without any customisation has no custom icon."""
    assert fcr._folder_custom_attrs(str(tmp_path)) == ("", "")


def test_folder_custom_attrs_of_a_missing_folder(tmp_path):
    """A failure yields an empty pair instead of an exception."""
    missing = str(tmp_path / "does-not-exist")
    assert fcr._folder_custom_attrs(missing) == ("", "")


# ---------------------------------------------------------------------------
# B. _current_color_specs
# ---------------------------------------------------------------------------

def test_current_color_specs_reads_the_state_file(monkeypatch):
    """The saved state is the source of truth when it exists."""
    _patch_sources(monkeypatch, {"spec": "3366ff;f5c211"}, ("", ""))
    spec, hexes = fcr._current_color_specs("/tmp/folder")
    assert spec == "3366ff;f5c211"
    assert hexes == ["#3366ff", "#f5c211"]


def test_current_color_specs_falls_back_to_the_custom_icon(monkeypatch):
    """Without a state file the custom icon URI still carries the colours."""
    uri = "file:///home/u/.cache/folder-color/folder-adwaita-3366ff.svg"
    _patch_sources(monkeypatch, None, (uri, ""))
    spec, hexes = fcr._current_color_specs("/tmp/folder")
    assert spec == "3366ff"
    assert hexes == ["#3366ff"]


def test_current_color_specs_when_nothing_is_known(monkeypatch):
    """No state and no custom icon -> unknown."""
    _patch_sources(monkeypatch, None, ("", ""))
    assert fcr._current_color_specs("/tmp/folder") == ("", [])


def test_current_color_specs_survives_a_broken_state_file(monkeypatch):
    """A state file that is not a dict must not raise."""
    _patch_sources(monkeypatch, [1, 2], ("", ""))
    assert fcr._current_color_specs("/tmp/folder") == ("", [])


# ---------------------------------------------------------------------------
# C. _apply_icon_state -- the data-loss regression
# ---------------------------------------------------------------------------

def test_apply_icon_state_does_nothing_when_nothing_changed(monkeypatch):
    """The bug: applying an untouched editor repainted the folder grey.

    With no layers and unchanged colours the folder must be left alone.
    """
    saved = _patch_apply(
        monkeypatch,
        state=None,
        attrs=("file:///home/u/.cache/folder-color/folder-adwaita-3366ff.svg",
               ""))
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#3366ff"], [], ["#3366ff"])
    assert result is True
    assert foldercolor.color_calls == []
    assert foldercolor.overlay_calls == []


def test_apply_icon_state_does_nothing_with_a_matching_state_file(monkeypatch):
    """Same as above, but the colours come from the state file."""
    saved = _patch_apply(monkeypatch, state={"spec": "3366ff"},
                         attrs=("", ""))
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#3366ff"], [], ["#3366ff"])
    assert result is True
    assert foldercolor.color_calls == []
    assert foldercolor.overlay_calls == []


def test_apply_icon_state_writes_the_new_colour(monkeypatch):
    """Changed colours without layers -> plain custom colour + saved spec."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#ff0000"], [], ["#3366ff"])
    assert result is True
    assert foldercolor.color_calls == [("/tmp/folder", "ff0000")]
    assert foldercolor.overlay_calls == []
    assert len(saved) == 1
    saved_path, saved_state = saved[0]
    assert saved_path == "/tmp/folder"
    assert saved_state.get("spec") == "ff0000"
    assert not saved_state.get("layers")


def test_apply_icon_state_uses_the_overlay_when_there_are_layers(monkeypatch):
    """With layers the overlay icon is painted and the state keeps them."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    layers = [{"type": "text", "text": "hi"}]
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#3366ff"], layers, ["#3366ff"])
    assert result is True
    assert foldercolor.color_calls == []
    assert len(foldercolor.overlay_calls) == 1
    path, spec, state = foldercolor.overlay_calls[0]
    assert path == "/tmp/folder"
    assert spec == "3366ff"
    # The layers are forwarded to set_custom_overlay_color; they may be
    # normalised, so only the payload itself is checked.
    forwarded = state["layers"] if isinstance(state, dict) else state
    assert forwarded
    assert forwarded[0]["type"] == "text"
    assert forwarded[0]["text"] == "hi"
    assert len(saved) == 1
    saved_path, saved_state = saved[0]
    assert saved_path == "/tmp/folder"
    assert saved_state.get("spec") == "3366ff"
    saved_layers = saved_state.get("layers")
    assert saved_layers
    assert saved_layers[0]["type"] == "text"
    assert saved_layers[0]["text"] == "hi"


def test_apply_icon_state_applies_when_existing_layers_were_removed(monkeypatch):
    """Removing the layers of a folder that had some is a real change."""
    saved = _patch_apply(
        monkeypatch,
        state={"spec": "3366ff", "layers": [{"type": "text", "text": "x"}]},
        attrs=("", ""))
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#3366ff"], [], ["#3366ff"])
    assert result is True
    assert len(foldercolor.color_calls) == 1
    assert foldercolor.color_calls[0][0] == "/tmp/folder"
    assert foldercolor.color_calls[0][1] == "3366ff"


def test_apply_icon_state_reports_a_failed_overlay(monkeypatch):
    """A failing set_custom_overlay_color must be reported to the caller."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    layers = [{"type": "text", "text": "hi"}]
    foldercolor = FakeFolderColor(overlay_ok=False)
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#3366ff"], layers, ["#3366ff"])
    assert result is False


def test_apply_icon_state_normalises_the_spec(monkeypatch):
    """'#3366FF' becomes the lower-case, hash-less '3366ff'."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    foldercolor = FakeFolderColor()
    fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                          ["#3366FF"], [], ["#000000"])
    assert len(foldercolor.color_calls) == 1
    assert foldercolor.color_calls[0][1] == "3366ff"


def test_apply_icon_state_joins_several_colours(monkeypatch):
    """Two colours become the 'rrggbb;rrggbb' spec."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    foldercolor = FakeFolderColor()
    fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                          ["#3366FF", "#F5C211"], [], ["#000000", "#000000"])
    assert len(foldercolor.color_calls) == 1
    assert foldercolor.color_calls[0][1] == "3366ff;f5c211"


# ---------------------------------------------------------------------------
# D. Contract between the host and folder_icon_editor.py
# ---------------------------------------------------------------------------

def test_open_editor_signature_matches_the_contract():
    """The host imports open_editor from the editor module."""
    editor = pytest.importorskip("folder_icon_editor")
    assert hasattr(fcr, "open_editor"), (
        "the host must import open_editor from folder_icon_editor "
        "at module level")
    assert fcr.open_editor is editor.open_editor

    signature = inspect.signature(fcr.open_editor)
    parameters = list(signature.parameters.values())
    assert [p.name for p in parameters] == [
        "title", "row_count", "hexes", "layers", "base_builder", "on_apply",
        "emblem_icons", "tr", "scan_dir"]
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in parameters)
    assert signature.parameters["emblem_icons"].default is None
    assert signature.parameters["tr"].default is None
    # The scanned folder is optional: without it the editor simply does not
    # offer the "Detect icon..." action.
    assert signature.parameters["scan_dir"].default is None


def _tr_keys(path):
    """Every literal key passed to ``self.tr(...)`` in the given file."""
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "tr":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            keys.add(first.value)
    return keys


def _branch_label(test):
    """The locale name of a ``_lang.startswith("xx")`` branch."""
    if isinstance(test, ast.Call) and test.args:
        first = test.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _locale_tables(path):
    """The ``_T`` translation tables of the host, per locale."""
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    tables = {}
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        branch = node
        while True:
            label = _branch_label(branch.test)
            for statement in branch.body:
                if not isinstance(statement, ast.Assign):
                    continue
                targets = [t.id for t in statement.targets
                           if isinstance(t, ast.Name)]
                if "_T" not in targets:
                    continue
                table = statement.value
                if isinstance(table, ast.Dict):
                    tables[label] = {k.value for k in table.keys
                                     if isinstance(k, ast.Constant)}
            if (len(branch.orelse) == 1
                    and isinstance(branch.orelse[0], ast.If)):
                branch = branch.orelse[0]
            else:
                break
    return tables


def test_the_host_defines_the_four_locale_tables():
    """fr, de, es and pt must each have their own _T table."""
    tables = _locale_tables(HOST_PATH)
    assert set(tables) == {"fr", "de", "es", "pt"}
    for locale, keys in tables.items():
        assert keys, "the %s translation table is empty" % locale


def test_every_editor_translation_key_exists_in_every_locale():
    """No self.tr() key of the editor may be missing from a locale table."""
    tables = _locale_tables(HOST_PATH)
    assert set(tables) == {"fr", "de", "es", "pt"}, (
        "the host must define the fr, de, es and pt translation tables")

    editor_keys = _tr_keys(EDITOR_PATH)
    assert editor_keys, "no self.tr() call found in folder_icon_editor.py"

    # The icon detection action is part of the contract: the editor offers it
    # through self.tr("Detect icon..."), so every locale must know the key.
    assert "Detect icon…" in editor_keys, (
        "the editor must offer the icon detection action")
    missing_detect = sorted(locale for locale, keys in tables.items()
                            if "Detect icon…" not in keys)
    assert not missing_detect, (
        "the 'Detect icon…' key is missing from the locale tables: "
        + ", ".join(missing_detect))

    problems = []
    for locale in sorted(tables):
        missing = sorted(editor_keys - tables[locale])
        if missing:
            problems.append("%s -> %s" % (locale, missing))
    assert not problems, (
        "translation keys missing from the host locale tables: "
        + "; ".join(problems))
