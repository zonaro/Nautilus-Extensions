"""Unit tests for the Move and Symlink Nautilus extension.

The extension needs GTK/Nautilus at import time, so the whole module is
skipped when those are unavailable. Every behaviour that matters for a move
is implemented as a pure module-level function (``_plan_move``,
``_apply_move``, ``_run_move``, ``_unique_path``, ``_relative_link``), so the
tests here exercise the real logic against ``tmp_path`` without a display.
The i18n coverage contract is checked from the source with ``ast``.
"""

import ast
import importlib.util
import os
import pathlib
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXT_PATH = os.path.join(REPO_ROOT, "move-and-symlink.py")


def _load_module():
    """Import ``move-and-symlink.py`` under the name ``ms``."""
    spec = importlib.util.spec_from_file_location("move_and_symlink", EXT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    ms = _load_module()
except Exception as exc:  # pragma: no cover - depends on the host
    pytest.skip("move-and-symlink.py is not importable here: %s" % exc, allow_module_level=True)


# ---------------------------------------------------------------------------
# _unique_path
# ---------------------------------------------------------------------------

def test_unique_path_keeps_a_free_name(tmp_path):
    assert ms._unique_path(str(tmp_path / "free.txt")) == str(tmp_path / "free.txt")


def test_unique_path_skips_files_and_directories(tmp_path):
    target = tmp_path / "report.txt"
    target.write_text("a", encoding="utf-8")
    (tmp_path / "report-1.txt").write_text("b", encoding="utf-8")

    assert ms._unique_path(str(target)) == str(tmp_path / "report-2.txt")


def test_unique_path_skips_broken_symlink(tmp_path):
    target = tmp_path / "link.txt"
    os.symlink(str(tmp_path / "nowhere"), target)

    assert ms._unique_path(str(target)) == str(tmp_path / "link-1.txt")


# ---------------------------------------------------------------------------
# _relative_link
# ---------------------------------------------------------------------------

def test_relative_link_is_relative_to_the_original_folder(tmp_path):
    link_path = str(tmp_path / "origin" / "file.txt")
    target = str(tmp_path / "store" / "file.txt")

    assert ms._relative_link(target, link_path) == os.path.join("..", "store", "file.txt")


def test_relative_link_of_a_sibling_folder(tmp_path):
    link_path = str(tmp_path / "origin" / "sub" / "file.txt")
    target = str(tmp_path / "origin" / "store" / "file.txt")

    assert ms._relative_link(target, link_path) == os.path.join("..", "store", "file.txt")


# ---------------------------------------------------------------------------
# _same_or_inside and _plan_move guards
# ---------------------------------------------------------------------------

def test_same_or_inside_compares_real_paths(tmp_path):
    parent = tmp_path / "parent"
    (parent / "child" / "deep").mkdir(parents=True)

    assert ms._same_or_inside(str(parent), str(parent)) is True
    assert ms._same_or_inside(str(parent / "child"), str(parent)) is True
    assert ms._same_or_inside(str(parent / "child" / "deep"), str(parent)) is True
    assert ms._same_or_inside(str(tmp_path / "parent2"), str(parent)) is False
    assert ms._same_or_inside(str(parent / "childish"), str(parent / "child")) is False


def test_plan_move_skips_an_existing_symlink_source(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    os.symlink(str(real), link)

    with pytest.raises(ms.PlanError) as excinfo:
        ms._plan_move(str(link), str(dest))

    assert excinfo.value.reason == "re_symlink"
    assert excinfo.value.message() == ms.T["re_symlink"]


def test_plan_move_skips_the_folder_it_already_lives_in(tmp_path):
    src = tmp_path / "file.txt"
    src.write_text("x", encoding="utf-8")

    with pytest.raises(ms.PlanError) as excinfo:
        ms._plan_move(str(src), str(tmp_path))

    assert excinfo.value.reason == "re_same_dir"


def test_plan_move_rejects_a_destination_inside_the_source(tmp_path):
    src = tmp_path / "folder"
    nested = src / "nested"
    nested.mkdir(parents=True)

    with pytest.raises(ms.PlanError) as excinfo:
        ms._plan_move(str(src), str(nested))

    assert excinfo.value.reason == "re_inside"


def test_plan_move_rejects_a_destination_inside_a_nested_source(tmp_path):
    src = tmp_path / "folder"
    (src / "a" / "b").mkdir(parents=True)

    with pytest.raises(ms.PlanError) as excinfo:
        ms._plan_move(str(src), str(src / "a" / "b"))

    assert excinfo.value.reason == "re_inside"


def test_plan_move_rejects_a_missing_source(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(ms.PlanError) as excinfo:
        ms._plan_move(str(tmp_path / "gone.txt"), str(dest))

    assert excinfo.value.reason == "re_missing"


def test_plan_move_returns_an_absolute_target_and_link(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    src = tmp_path / "file.txt"
    src.write_text("x", encoding="utf-8")

    target, link_target = ms._plan_move(str(src), str(dest))

    assert target == str(dest / "file.txt")
    assert link_target == target


def test_plan_move_can_build_a_relative_link(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "file.txt"
    src.write_text("x", encoding="utf-8")

    target, link_target = ms._plan_move(str(src), str(dest), relative=True)

    assert target == str(dest / "file.txt")
    assert link_target == os.path.join("..", "dest", "file.txt")


def test_plan_move_applies_the_unique_suffix_at_the_destination(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "file.txt").write_text("old", encoding="utf-8")
    src = tmp_path / "file.txt"
    src.write_text("new", encoding="utf-8")

    target, _link = ms._plan_move(str(src), str(dest))

    assert target == str(dest / "file-1.txt")


# ---------------------------------------------------------------------------
# _apply_move / _run_move
# ---------------------------------------------------------------------------

def test_apply_move_moves_the_item_and_links_the_original_path(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    src = tmp_path / "file.txt"
    src.write_text("payload", encoding="utf-8")

    assert ms._apply_move(str(src), str(dest)) is None

    moved = dest / "file.txt"
    assert moved.read_text(encoding="utf-8") == "payload"
    assert os.path.islink(src)
    assert os.path.realpath(src) == os.path.realpath(moved)


def test_apply_move_never_overwrites_an_existing_name(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "file.txt").write_text("old", encoding="utf-8")
    src = tmp_path / "file.txt"
    src.write_text("new", encoding="utf-8")

    assert ms._apply_move(str(src), str(dest)) is None

    assert (dest / "file.txt").read_text(encoding="utf-8") == "old"
    assert (dest / "file-1.txt").read_text(encoding="utf-8") == "new"
    assert os.path.realpath(src) == os.path.realpath(dest / "file-1.txt")


def test_apply_move_creates_a_relative_link_when_asked(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "file.txt"
    src.write_text("x", encoding="utf-8")

    assert ms._apply_move(str(src), str(dest), relative=True) is None

    assert os.path.islink(src)
    assert os.readlink(src) == os.path.join("..", "dest", "file.txt")


def test_apply_move_reports_a_symlink_source_without_touching_it(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    os.symlink(str(real), link)

    reason = ms._apply_move(str(link), str(dest))

    assert reason == ms.T["re_symlink"]
    assert os.path.islink(link)
    assert real.exists()
    assert not (dest / "link.txt").exists()


def test_run_move_keeps_going_after_one_item_fails(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    os.symlink(str(real), link)
    other = tmp_path / "other.txt"
    other.write_text("y", encoding="utf-8")

    moved, failures = ms._run_move([str(link), str(other)], str(dest))

    assert moved == 1
    assert len(failures) == 1
    assert failures[0].startswith("link.txt — ")
    assert ms.T["re_symlink"] in failures[0]
    assert os.path.realpath(other) == os.path.realpath(dest / "other.txt")


def test_run_move_reports_every_failed_item_in_a_single_list(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    first = tmp_path / "first.txt"
    first.write_text("x", encoding="utf-8")
    second = tmp_path / "second.txt"
    second.write_text("y", encoding="utf-8")
    os.symlink(str(first), tmp_path / "first-link.txt")
    os.symlink(str(second), tmp_path / "second-link.txt")

    moved, failures = ms._run_move(
        [str(tmp_path / "first-link.txt"), str(tmp_path / "second-link.txt")],
        str(dest),
    )

    assert moved == 0
    assert len(failures) == 2
    assert [line.split(" — ", 1)[0] for line in failures] == [
        "first-link.txt", "second-link.txt",
    ]


# ---------------------------------------------------------------------------
# Menu / dialog wiring
# ---------------------------------------------------------------------------

def test_menu_exposes_a_single_item_for_the_selection():
    source = pathlib.Path(EXT_PATH).read_text(encoding="utf-8")

    assert source.count('name="MoveAndSymlink::MoveSymlink"') == 1
    assert source.count('label=T["menu_label"]') == 1
    assert source.count('tip=T["menu_label"]') == 1
    assert "item.connect(\"activate\", self._cb_move, paths)" in source
    assert "if not paths:\n            return []" in source


def test_dialog_uses_the_folder_picker_and_a_suggested_action():
    source = pathlib.Path(EXT_PATH).read_text(encoding="utf-8")

    assert "Gtk.FileDialog" in source
    assert "dlg.select_folder(" in source
    assert "dlg.select_folder_finish(result)" in source
    assert 'add_css_class("suggested-action")' in source
    assert "GLib.idle_add(super().present)" in source
    assert "set_active(False)" in source


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

    assert set(tables) == {"fr", "de", "es", "pt", "en"}
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


def test_translations_are_non_empty_strings():
    tree = ast.parse(pathlib.Path(EXT_PATH).read_text(encoding="utf-8"))
    tables = 0
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
        tables += 1
    assert tables == 5


def test_reason_keys_cover_every_plan_error_raised():
    source = pathlib.Path(EXT_PATH).read_text(encoding="utf-8")
    reasons = set(re.findall(r'PlanError\("([^"]+)"', source))
    assert reasons
    reference = _locale_tables(EXT_PATH)["en"]
    assert reasons <= reference
