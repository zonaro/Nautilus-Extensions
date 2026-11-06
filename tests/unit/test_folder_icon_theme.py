"""Unit tests for ``folder_icon_theme`` (global folder icon scope, #21).

No display is needed: every helper tested here works on a temporary HOME,
so the tests never touch the real ``~/.icons`` or the user's GSettings.
"""
import io
import json
import os

import pytest

import folder_icon_theme as fit


def _png(size=256):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), (53, 132, 228, 255)).save(
        buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Isolate HOME and XDG_DATA_DIRS for one test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "system-share"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".local" / "share" / "icons").mkdir(parents=True)
    (tmp_path / "system-share" / "icons").mkdir(parents=True)
    return tmp_path


def _make_theme(root, name, with_folder=True, label=None):
    theme = root / name
    places = theme / "scalable" / "places"
    places.mkdir(parents=True)
    (theme / "index.theme").write_text(
        "[Icon Theme]\nName=%s\n" % (label or name), encoding="utf-8")
    if with_folder:
        (places / "folder.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><rect width="8" '
            'height="8" fill="#3584e4"/></svg>', encoding="utf-8")
    return theme


# ---------------------------------------------------------------------------
# Accent colour
# ---------------------------------------------------------------------------

def test_every_gnome_accent_name_has_a_hex():
    assert fit.ACCENT_COLORS == {
        "blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a",
        "yellow": "#c88800", "orange": "#ed5b00", "red": "#e62d42",
        "pink": "#d56199", "purple": "#9141ac", "slate": "#6f8396",
    }


def test_normalize_accent_falls_back_to_blue():
    assert fit.normalize_accent("purple") == "purple"
    assert fit.normalize_accent(" Purple ") == "purple"
    assert fit.normalize_accent("") == "blue"
    assert fit.normalize_accent(None) == "blue"
    assert fit.normalize_accent("banana") == "blue"


def test_accent_hex_uses_the_palette():
    assert fit.accent_hex("purple") == "#9141ac"
    assert fit.accent_hex("") == "#3584e4"


def test_accent_hex_prefers_a_valid_fallback_over_the_default():
    # A future GNOME accent name must not be painted blue by accident.
    assert fit.accent_hex("neon", fallback="#123456") == "#123456"
    assert fit.accent_hex("neon", fallback="not-a-colour") == "#3584e4"


# ---------------------------------------------------------------------------
# Theme discovery
# ---------------------------------------------------------------------------

def test_theme_name_traversal_is_rejected():
    for bad in ("", "../etc", "/usr/share/icons", ".hidden", "a b", None):
        assert fit.safe_theme_name(bad) is False, bad
    assert fit.safe_theme_name("Papirus-Dark") is True


def test_discover_lists_only_themes_with_a_folder_icon(home):
    _make_theme(home / "system-share" / "icons", "Adwaita", label="Adwaita")
    _make_theme(home / ".local" / "share" / "icons", "Papirus")
    # No folder icon -> not offered: the selector would produce a colour icon.
    _make_theme(home / "system-share" / "icons", "Cursors", with_folder=False)

    themes = fit.discover_folder_themes()
    assert [item["name"] for item in themes] == ["Adwaita", "Papirus"]
    assert themes[0]["label"] == "Adwaita"
    assert themes[0]["path"].endswith("Adwaita")


def test_discover_skips_derived_themes(home):
    _make_theme(home / ".local" / "share" / "icons", "Adwaita")
    _make_theme(home / ".local" / "share" / "icons",
                fit.DERIVED_PREFIX + "abc123")
    names = [item["name"] for item in fit.discover_folder_themes()]
    assert names == ["Adwaita"]
    names = [item["name"]
             for item in fit.discover_folder_themes(exclude_derived=False)]
    assert sorted(names) == sorted(["Adwaita", fit.DERIVED_PREFIX + "abc123"])


def test_theme_folder_icon_prefers_svg_then_bigger_png(home):
    theme = _make_theme(home / ".local" / "share" / "icons", "Mixed")
    png = theme / "places" / "48x48" / "places"
    png.mkdir(parents=True)
    (png / "folder.png").write_bytes(_png(48))
    assert fit.theme_folder_icon("Mixed").endswith("folder.svg")

    (theme / "scalable" / "places" / "folder.svg").unlink()
    assert fit.theme_folder_icon("Mixed").endswith("folder.png")
    assert fit.theme_folder_icon("nope") == ""


# ---------------------------------------------------------------------------
# Derived theme
# ---------------------------------------------------------------------------

def test_derived_theme_name_is_deterministic_and_prefixed():
    name = fit.derived_theme_name("Adwaita", "3584e4", [{"type": "text"}])
    assert name.startswith(fit.DERIVED_PREFIX)
    assert name == fit.derived_theme_name("Adwaita", "3584e4",
                                          [{"type": "text"}])
    assert name != fit.derived_theme_name("Adwaita", "e62d42",
                                          [{"type": "text"}])


def test_write_derived_theme_creates_sizes_and_inherits(home, tmp_path):
    root = tmp_path / "icons"
    name = fit.derived_theme_name("Adwaita", "3584e4")
    target = fit.write_derived_theme(name, "Adwaita", _png(), root=str(root))
    assert target == str(root / name)

    index = fit.read_index_theme(target)
    assert index["Name"] == name
    assert index["Inherits"] == "Adwaita"
    for size in fit.ICON_SIZES:
        path = root / name / f"{size}x{size}" / "places" / "folder.png"
        assert path.is_file(), path
        assert path.stat().st_size > 0

    from PIL import Image
    with Image.open(root / name / "32x32" / "places" / "folder.png") as img:
        assert img.size == (32, 32)


def test_write_derived_theme_rejects_foreign_names(home, tmp_path):
    root = tmp_path / "icons"
    assert fit.write_derived_theme("Adwaita", "Adwaita", _png(),
                                   root=str(root)) == ""
    assert fit.write_derived_theme("../evil", "Adwaita", _png(),
                                   root=str(root)) == ""
    assert fit.write_derived_theme(fit.DERIVED_PREFIX + "x", "Adwaita", b"",
                                   root=str(root)) == ""


def test_prune_removes_only_stale_derived_themes(home, tmp_path):
    root = tmp_path / "icons"
    keep = fit.derived_theme_name("Adwaita", "3584e4")
    old = fit.derived_theme_name("Adwaita", "e62d42")
    fit.write_derived_theme(keep, "Adwaita", _png(), root=str(root))
    fit.write_derived_theme(old, "Adwaita", _png(), root=str(root))
    foreign = root / "Adwaita"
    foreign.mkdir(parents=True)

    removed = fit.prune_derived_themes(keep=keep, root=str(root))
    assert removed == [old]
    assert (root / keep).is_dir()
    assert foreign.is_dir()

    assert fit.remove_derived_themes(root=str(root)) == [keep]
    assert not (root / keep).exists()
    assert foreign.is_dir()


# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------

def test_state_round_trip(home):
    state = {
        "spec": "#3584E4;E62D42",
        "layers": [{"type": "text", "text": "Hi"}],
        "theme": "Adwaita",
        "base_theme": "AdwaitaLegacy",
        "base_image": "/home/u/Pictures/base.png",
        "follow_accent": True,
        "derived_theme": fit.DERIVED_PREFIX + "abc123",
        "row_count": 2,
    }
    assert fit.save_state(state) is True
    loaded = fit.load_state()
    assert loaded["version"] == fit.STATE_VERSION
    assert loaded["spec"] == "3584e4;e62d42"
    assert loaded["layers"] == [{"type": "text", "text": "Hi"}]
    assert loaded["theme"] == "Adwaita"
    assert loaded["base_theme"] == "AdwaitaLegacy"
    assert loaded["base_image"] == "/home/u/Pictures/base.png"
    assert loaded["follow_accent"] is True
    assert loaded["derived_theme"] == fit.DERIVED_PREFIX + "abc123"
    assert loaded["row_count"] == 2


def test_state_defaults_when_the_file_is_missing(home):
    state = fit.load_state()
    assert state["version"] == fit.STATE_VERSION
    assert state["spec"] == ""
    assert state["layers"] == []
    assert state["follow_accent"] is False
    assert state["row_count"] == 1


def test_state_survives_a_broken_or_foreign_file(home):
    os.makedirs(fit.state_dir(), exist_ok=True)
    with open(fit.state_path(), "w", encoding="utf-8") as handle:
        handle.write("{not json")
    assert fit.load_state()["layers"] == []

    with open(fit.state_path(), "w", encoding="utf-8") as handle:
        json.dump(["a", "list"], handle)
    assert fit.load_state()["theme"] == ""


def test_state_drops_unsafe_and_invalid_values():
    state = fit.normalize_state({
        "spec": "zzzzzz", "theme": "../../evil", "base_theme": "/abs",
        "derived_theme": "Adwaita", "row_count": "99", "layers": "nope",
    })
    assert state["spec"] == ""
    assert state["theme"] == ""
    assert state["base_theme"] == ""
    assert state["derived_theme"] == ""
    assert state["row_count"] == 8
    assert state["layers"] == []


def test_clear_state_removes_the_file(home):
    fit.save_state({"spec": "3584e4"})
    assert os.path.isfile(fit.state_path())
    assert fit.clear_state() is True
    assert not os.path.exists(fit.state_path())
    assert fit.clear_state() is False


def test_state_dir_honours_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert fit.state_dir() == str(tmp_path / "cfg" / "nautilus-extensions")
