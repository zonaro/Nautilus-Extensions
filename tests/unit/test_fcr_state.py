"""Unit tests for folder-color-revival host state and accent behavior.

Covers the corrections requested in the audit:

* named GNOME accent colour resolution (not just raw hex)
* missing accent schema is nonfatal
* Global tab opt-in when folder_icon_theme is absent
* actual changed spec/state is applied and saved
* follow_accent survives no-op transitions
* AccentWatcher callback uses a single (3-arg) arity and re-tints
* partial write errors are reported (not saved as bogus state)
* restore preserves foreign emblems/icon metadata
* Unicode state paths
* multi-scope cancellation fails closed
"""
import gi.repository
import importlib.util
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

HOST_PATH = os.path.join(REPO_ROOT, "folder-color-revival.py")


def _load_host_module():
    spec = importlib.util.spec_from_file_location("fcr_state", HOST_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    fcr = _load_host_module()
except Exception as exc:  # pragma: no cover - depends on local typelibs
    pytest.skip("folder-color-revival.py is not importable here: %s" % exc,
                allow_module_level=True)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeFolderColor:
    """Records what the host asked it to apply."""

    def __init__(self, overlay_ok=True, color_ok=True):
        self.overlay_calls = []
        self.color_calls = []
        self.restore_calls = []
        self.overlay_ok = overlay_ok
        self.color_ok = color_ok

    def set_custom_overlay_color(self, path, spec, state):
        self.overlay_calls.append((path, spec, state))
        return self.overlay_ok

    def set_custom_color(self, path, spec):
        self.color_calls.append((path, spec))
        return self.color_ok

    def set_restore(self, path):
        self.restore_calls.append(path)
        return True


def _patch_apply(monkeypatch, state=None, attrs=("", "")):
    saved = []
    monkeypatch.setattr(fcr, "_load_overlay_state",
                        lambda *a, **k: state)
    monkeypatch.setattr(fcr, "_folder_custom_attrs",
                        lambda *a, **k: attrs)
    monkeypatch.setattr(fcr, "_save_overlay_state",
                        lambda path, st: saved.append((path, st)) or True)
    monkeypatch.setattr(fcr, "_clear_overlay_state", lambda *a, **k: None)
    return saved


class _GioSettingsFactory:
    """Stand-in for Gio.Settings whose .new() returns a fixed-value settings."""

    def __init__(self, value):
        self.value = value

    def new(self, _schema):
        return _FixedSettings(self.value)


class _FixedSettings:
    def __init__(self, value):
        self.value = value

    def get_string(self, _key):
        return self.value


# ---------------------------------------------------------------------------
# Accent colour: named GNOME palette (not raw hex only)
# ---------------------------------------------------------------------------

def test_resolve_accent_hex_maps_a_gnome_name(monkeypatch):
    """'purple' -> palette hex, not a raw-hex parse failure."""
    if not fcr._ICON_THEME_AVAILABLE:
        pytest.skip("folder_icon_theme unavailable in this environment")

    monkeypatch.setattr(gi.repository.Gio, "Settings",
                        _GioSettingsFactory("purple"))
    assert fcr._resolve_accent_hex() == fcr.icon_theme.ACCENT_COLORS["purple"]


def test_resolve_accent_hex_raw_hex_still_works(monkeypatch):
    """A raw '#rrggbb' setting value passes through unchanged."""
    if not fcr._ICON_THEME_AVAILABLE:
        pytest.skip("folder_icon_theme unavailable in this environment")

    monkeypatch.setattr(gi.repository.Gio, "Settings",
                        _GioSettingsFactory("#123456"))
    assert fcr._resolve_accent_hex() == "#123456"


def test_resolve_accent_hex_missing_schema_is_nonfatal(monkeypatch):
    """GSettings failing entirely degrades to the default blue, no crash."""

    def _boom(_schema):
        raise Exception("no session bus / schema missing")

    monkeypatch.setattr(gi.repository.Gio, "Settings", type("X", (), {
        "new": staticmethod(_boom)}))
    assert fcr._resolve_accent_hex() == "#3584e4"


# ---------------------------------------------------------------------------
# Global tab opt-in
# ---------------------------------------------------------------------------

def test_global_host_opt_in_when_theme_module_missing(monkeypatch):
    """Without folder_icon_theme the Global host is a safe no-op."""
    monkeypatch.setattr(fcr, "_ICON_THEME_AVAILABLE", False)
    monkeypatch.setattr(fcr, "icon_theme", None)
    host = fcr.GlobalIconHost(tr=lambda text: text)
    assert host.themes() == []
    assert host.state() == {}
    assert host.is_active() is False
    assert host.accent_hex() == "#3584e4"
    assert host.apply(spec="3366ff", layers=[], theme="") is False
    assert host.restore() is False


# ---------------------------------------------------------------------------
# _apply_icon_state: actual changed spec/state, no-op, follow_accent survival
# ---------------------------------------------------------------------------

def test_apply_icon_state_applies_changed_colour_and_saves(monkeypatch):
    """A real colour change is written and the spec is persisted."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#ff0000"], [], ["#3366ff"])
    assert result is True
    assert foldercolor.color_calls == [("/tmp/folder", "ff0000")]
    assert len(saved) == 1
    assert saved[0][1].get("spec") == "ff0000"


def test_apply_icon_state_no_op_when_nothing_changed(monkeypatch):
    """Unchanged colour, no overlay: folder left untouched."""
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
    assert saved == []


def test_apply_icon_state_follow_accent_survives_a_no_op(monkeypatch):
    """follow_accent must be recorded even when no repaint is needed."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    monkeypatch.setattr(fcr, "_resolve_accent_hex", lambda: "#3366ff")
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/unicode-fólder"],
                                   ["#3366ff"], [], ["#3366ff"],
                                   follow_accent=True)
    assert result is True
    assert foldercolor.color_calls == []
    assert foldercolor.overlay_calls == []
    # The state file must still carry follow_accent so the watcher re-tints later.
    assert len(saved) == 1
    assert saved[0][1].get("follow_accent") is True


def test_apply_icon_state_reports_a_partial_write_failure(monkeypatch):
    """A failing metadata write must be reported as failure, not silent."""
    saved = _patch_apply(monkeypatch, state=None, attrs=("", ""))
    monkeypatch.setattr(fcr, "_save_overlay_state",
                        lambda path, st: False)
    foldercolor = FakeFolderColor()
    result = fcr._apply_icon_state(foldercolor, ["/tmp/folder"],
                                   ["#ff0000"], [], ["#3366ff"])
    assert result is False


# ---------------------------------------------------------------------------
# AccentWatcher: single callback arity + actual re-tint + missing schema
# ---------------------------------------------------------------------------

def test_accent_watcher_callback_has_one_arity(monkeypatch):
    """The watcher notifies with (accent, count, applied) — exactly 3 args."""
    calls = []
    watcher = fcr.AccentWatcher(None,
                                on_accent_changed=lambda *a: calls.append(a))
    watcher.stop()
    # Force a known accent so the result is deterministic.
    monkeypatch.setattr(fcr, "_resolve_accent_hex",
                        lambda: "#2190a4")
    watcher._debounced_regenerate()
    assert calls == [("#2190a4", 0, 0)]


def test_accent_watcher_re_tints_follow_accent_folders(tmp_path, monkeypatch):
    """regenerate_all re-applies the current accent, not the stored spec."""
    applied = []

    class _FolderColor:
        def set_custom_overlay_color(self, path, spec, state):
            applied.append((path, spec, state))
            return True

    monkeypatch.setattr(fcr, "_resolve_accent_hex", lambda: "#2190a4")
    monkeypatch.setattr(fcr, "_custom_cache_dir", lambda: str(tmp_path))

    # Write one follow-accent folder state into the cache dir.
    state_path = os.path.join(tmp_path, "state-x.json")
    state = {"follow_accent": True, "_path": "/tmp/carpeta",
             "spec": "3366ff;f5c211", "layers": [], "theme": "",
             "base_image": ""}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)

    watcher = fcr.AccentWatcher(_FolderColor())
    watcher.stop()
    count, applied_n = watcher.regenerate_all(_FolderColor())
    assert count == 1
    assert applied_n == 1
    # Every shape re-tinted to teal, not the stored 3366ff;f5c211.
    assert applied[0][1] == "2190a4;2190a4"


def test_accent_watcher_missing_schema_stays_idle(monkeypatch):
    """No session bus / schema: the watcher never crashes."""

    def _boom(_schema):
        raise Exception("no schema")

    monkeypatch.setattr(gi.repository.Gio, "Settings", type("X", (), {
        "new": staticmethod(_boom)}))
    watcher = fcr.AccentWatcher(None)
    watcher.stop()
    # regenerate_all with no foldercolor should not raise.
    assert watcher.regenerate_all(None) == (0, 0)


# ---------------------------------------------------------------------------
# Restore: preserve foreign emblems / icon metadata
# ---------------------------------------------------------------------------

def test_is_our_custom_icon_only_owns_our_cache(tmp_path, monkeypatch):
    """_is_our_custom_icon is True only for our cached URIs."""
    fcr._custom_cache_dir = lambda: str(tmp_path / "cache")
    assert fcr._is_our_custom_icon(str(tmp_path / "cache" / "folder-x.svg"))
    assert not fcr._is_our_custom_icon("file:///other/theme/icon.svg")
    assert not fcr._is_our_custom_icon("")


def test_read_emblems_degrades_nonfatal(monkeypatch):
    """_read_emblems returns [] when Gio cannot be queried."""

    def _boom(*a, **k):
        raise Exception("Gio unavailable")

    monkeypatch.setattr(gi.repository.Gio, "File", _boom)
    assert fcr._read_emblems("/tmp/folder") == []


# ---------------------------------------------------------------------------
# Unicode state paths
# ---------------------------------------------------------------------------

def test_overlay_state_path_handles_unicode(tmp_path, monkeypatch):
    """Unicode folder paths produce a valid, readable state file."""
    fcr._custom_cache_dir = lambda: str(tmp_path)
    path = "/tmp/carpetà-ções/üniçodé"
    state = {"spec": "ff0000", "follow_accent": True, "_path": path}
    assert fcr._save_overlay_state(path, state) is True
    loaded = fcr._load_overlay_state(path)
    assert isinstance(loaded, dict)
    assert loaded["spec"] == "ff0000"
    assert loaded["follow_accent"] is True


# ---------------------------------------------------------------------------
# Multi-scope cancellation fails closed
# ---------------------------------------------------------------------------

def test_confirm_multi_scope_dialog_failure_fails_closed(monkeypatch):
    """A broken GTK dialog must not silently apply to all folders."""
    called = []

    def _action(paths):
        called.append(list(paths))

    class _BadDialog:
        def __init__(self, *a, **k):
            raise Exception("GTK broken")

    monkeypatch.setattr(fcr.Gtk, "AlertDialog", _BadDialog)
    monkeypatch.setattr(fcr, "_nautilus_window", lambda: None)
    fcr._confirm_multi_scope(["/a", "/b"], _action)
    assert called == [], "cancel/failure must fail closed, never apply all"


# ---------------------------------------------------------------------------
# RegenJob / GlobalIconHost.regenerate_folders (#35/#38)
# ---------------------------------------------------------------------------

class _RegenFolderColor:
    def __init__(self, fail_on=None, ok=True):
        self.calls = []
        self.fail_on = fail_on
        self.ok = ok

    def set_custom_overlay_color(self, path, spec, state):
        self.calls.append((path, spec))
        if self.fail_on == path:
            return False
        return self.ok


def _write_state(cache_dir, name, state):
    import json as _json
    path = os.path.join(cache_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(state, f)
    return path


def test_global_host_regenerate_folders_returns_job(tmp_path, monkeypatch):
    """regenerate_folders returns a cancellable RegenJob when wired."""
    if not fcr._ICON_THEME_AVAILABLE:
        pytest.skip("folder_icon_theme unavailable in this environment")
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir, exist_ok=True)
    fcr._custom_cache_dir = lambda: cache_dir
    monkeypatch.setattr(fcr, "_resolve_accent_hex", lambda: "#2190a4")
    monkeypatch.setattr(fcr.GLib, "idle_add", lambda cb: 1)
    fc = _RegenFolderColor()
    host = fcr.GlobalIconHost(tr=lambda t: t, foldercolor=fc)
    job = host.regenerate_folders()
    assert job is not None
    assert hasattr(job, "cancel")
    assert job.total == 0  # no candidates yet
    job.cancel()


def test_regen_job_applies_to_follow_accent_folders(tmp_path, monkeypatch):
    """Cooperative steps re-tint each follow-accent folder to the accent."""
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir, exist_ok=True)
    fcr._custom_cache_dir = lambda: cache_dir
    monkeypatch.setattr(fcr, "_resolve_accent_hex", lambda: "#2190a4")
    monkeypatch.setattr(fcr.GLib, "idle_add", lambda cb: 1)
    _write_state(cache_dir, "state-a.json",
                 {"follow_accent": True, "_path": "/tmp/carpeta",
                  "spec": "3366ff;ff0000", "layers": [], "theme": "",
                  "base_image": ""})
    _write_state(cache_dir, "state-b.json",
                 {"follow_accent": True, "_path": "/tmp/folder-b",
                  "spec": "ff0000", "layers": [], "theme": "", "base_image": ""})
    _write_state(cache_dir, "state-c.json",
                 {"follow_accent": False, "_path": "/tmp/folder-c",
                  "spec": "ff0000", "layers": [], "theme": "", "base_image": ""})
    fc = _RegenFolderColor()
    progress = []
    done = {}
    job = fcr.RegenJob(fc,
                       on_progress=lambda *a: progress.append(a),
                       on_done=lambda applied, skipped, failed, cancelled: done.update(
                           dict(applied=applied, skipped=skipped,
                                failed=failed, cancelled=cancelled)))
    job.start()
    assert job.total == 2
    # Drive the cooperative steps manually (no main loop pumped in tests).
    for _ in range(5):
        if not job._step():
            break
    assert done == {"applied": 2, "skipped": 0, "failed": 0, "cancelled": False}
    assert len(fc.calls) == 2
    specs = [c[1] for c in fc.calls]
    assert "2190a4;2190a4" in specs
    assert all(s in ("2190a4", "2190a4;2190a4") for s in specs)
    assert progress[-1][3] == "applied"


def test_regen_job_skips_invalid_and_counts_failures(tmp_path, monkeypatch):
    """Non follow-accent and invalid states are skipped; write failures counted."""
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir, exist_ok=True)
    fcr._custom_cache_dir = lambda: cache_dir
    monkeypatch.setattr(fcr, "_resolve_accent_hex", lambda: "#2190a4")
    monkeypatch.setattr(fcr.GLib, "idle_add", lambda cb: 1)
    _write_state(cache_dir, "state-a.json",
                 {"follow_accent": True, "_path": "/tmp/fail-me",
                  "spec": "3366ff", "layers": [], "theme": "", "base_image": ""})
    _write_state(cache_dir, "state-b.json",
                 {"follow_accent": True, "_path": "/tmp/no-spec",
                  "spec": "", "layers": [], "theme": "", "base_image": ""})
    _write_state(cache_dir, "state-c.json",
                 {"follow_accent": False, "_path": "/tmp/nope",
                  "spec": "3366ff", "layers": [], "theme": "", "base_image": ""})
    fc = _RegenFolderColor(fail_on="/tmp/fail-me")
    done = {}
    job = fcr.RegenJob(fc, on_progress=lambda *a: None,
                       on_done=lambda applied, skipped, failed, cancelled: done.update(
                           dict(applied=applied, skipped=skipped,
                                failed=failed, cancelled=cancelled)))
    job.start()
    assert job.total == 2
    for _ in range(3):
        if not job._step():
            break
    assert done == {"applied": 0, "skipped": 1, "failed": 1, "cancelled": False}


def test_regen_job_cancel_stops_clean(tmp_path, monkeypatch):
    """cancel() stops further steps and on_done reports cancelled=True."""
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir, exist_ok=True)
    fcr._custom_cache_dir = lambda: cache_dir
    monkeypatch.setattr(fcr, "_resolve_accent_hex", lambda: "#2190a4")
    monkeypatch.setattr(fcr.GLib, "idle_add", lambda cb: 1)
    _write_state(cache_dir, "state-a.json",
                 {"follow_accent": True, "_path": "/tmp/one",
                  "spec": "3366ff", "layers": [], "theme": "", "base_image": ""})
    fc = _RegenFolderColor()
    done = {}
    job = fcr.RegenJob(fc, on_progress=lambda *a: None,
                       on_done=lambda applied, skipped, failed, cancelled: done.update(
                           dict(applied=applied, skipped=skipped,
                                failed=failed, cancelled=cancelled)))
    job.start()
    job.cancel()
    assert job._step() is False  # finishes immediately
    assert done == {"applied": 0, "skipped": 0, "failed": 0, "cancelled": True}
    assert fc.calls == []  # nothing applied


def test_global_host_regenerate_folders_none_without_foldercolor(tmp_path, monkeypatch):
    """No foldercolor -> None (safe no-op, no watcher created)."""
    if not fcr._ICON_THEME_AVAILABLE:
        pytest.skip("folder_icon_theme unavailable in this environment")
    host = fcr.GlobalIconHost(tr=lambda t: t, foldercolor=None)
    assert host.regenerate_folders() is None


# ---------------------------------------------------------------------------
# #36 gallery history: corrupt/missing entries and safe unmark
# ---------------------------------------------------------------------------

def test_gallery_get_ignores_corrupt_entries(tmp_path, monkeypatch):
    """_gallery_get returns None for a corrupt/non-dict entry."""
    monkeypatch.setattr(fcr, "_gallery_dir", lambda: str(tmp_path / "gallery"))
    monkeypatch.setattr(fcr, "_gallery_index_path",
                        lambda: str(tmp_path / "gallery" / "index.json"))
    os.makedirs(fcr._gallery_dir(), exist_ok=True)
    index_path = fcr._gallery_index_path()
    with open(index_path, "w") as fh:
        json.dump({"abc": "not-a-dict", "def": {"hash": "def"}}, fh)
    assert fcr._gallery_get("abc") is None
    assert fcr._gallery_get("def")["hash"] == "def"
    assert fcr._gallery_get("missing") is None


def test_gallery_remove_works_after_unmark_refs(tmp_path, monkeypatch):
    """An entry whose used_by was unmarked becomes removable (#36/#37)."""
    monkeypatch.setattr(fcr, "_gallery_dir", lambda: str(tmp_path / "gallery"))
    monkeypatch.setattr(fcr, "_gallery_index_path",
                        lambda: str(tmp_path / "gallery" / "index.json"))
    os.makedirs(fcr._gallery_dir(), exist_ok=True)
    png = os.path.join(fcr._gallery_dir(), "abc.png")
    open(png, "wb").write(b"PNG")
    index_path = fcr._gallery_index_path()
    with open(index_path, "w") as fh:
        json.dump({"abc": {"hash": "abc", "png": png, "used_by": ["/x/a"]}}, fh)
    # Still in use -> not removable.
    assert fcr._gallery_remove("abc") is False
    # Unmark the ref (as restore/reapply does) -> removable.
    fcr._gallery_unmark_used("abc", "/x/a")
    assert fcr._gallery_remove("abc") is True
    assert not os.path.exists(png)


def test_gallery_remove_tolerates_missing_png_and_corrupt(tmp_path, monkeypatch):
    """Corrupt entry and missing png don't crash removal."""
    monkeypatch.setattr(fcr, "_gallery_dir", lambda: str(tmp_path / "gallery"))
    monkeypatch.setattr(fcr, "_gallery_index_path",
                        lambda: str(tmp_path / "gallery" / "index.json"))
    os.makedirs(fcr._gallery_dir(), exist_ok=True)
    index_path = fcr._gallery_index_path()
    with open(index_path, "w") as fh:
        json.dump({"abc": {"hash": "abc", "used_by": []},
                   "def": {"hash": "def", "png": "/no/such.png", "used_by": []}},
                  fh)
    assert fcr._gallery_remove("abc") is True
    assert fcr._gallery_remove("def") is True
    assert fcr._gallery_remove("missing") is False
