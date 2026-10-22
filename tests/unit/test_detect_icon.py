"""Unit tests for the icon detection of the folder icon editor.

``folder_icon_editor.py`` can look for an icon that already lives inside the
folder being customised: the images whose file name looks like an icon name
-- in any language -- are ranked and the user picks one of them.

Only the pure scanning logic is exercised here, so the whole file runs
without a display (no GTK widget is created).  The GUI entry point
``detect_icon_for_folder`` is tested with the GTK parts monkeypatched.
"""
import base64
import os
import sys
import types

import pytest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import folder_icon_editor as fie
except Exception as exc:  # pragma: no cover - depends on the local typelibs
    pytest.skip("folder_icon_editor.py is not importable here: %s" % exc,
                allow_module_level=True)

# A real 1x1 PNG, so the files are genuine images and not empty stubs.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg==")

TINY_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">'
            b'</svg>')


def _write(path, data=TINY_PNG):
    """Write a file, creating the parent folders."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def _build_tree(root):
    """Create the sample folder used by most of the tests.

    It holds a few icon-like images plus a couple of decoys that must never
    show up in the results.
    """
    _write(os.path.join(root, "favicon.png"))
    _write(os.path.join(root, "logo.svg"), TINY_SVG)
    _write(os.path.join(root, "brasao.png"))
    _write(os.path.join(root, "ícone-da-pasta.png"))
    _write(os.path.join(root, "MEU_ICONE.PNG"))
    _write(os.path.join(root, "logo_dark.svg"), TINY_SVG)
    # Decoys: a picture that does not look like an icon, a text file, a
    # hidden file and a hidden folder.
    _write(os.path.join(root, "photo.jpg"))
    _write(os.path.join(root, "notes.txt"), b"not an image")
    _write(os.path.join(root, ".hidden-icon.png"))
    _write(os.path.join(root, ".hidden-folder", "icon.png"))
    # A nested icon (two levels down) and a skipped vendor folder.
    _write(os.path.join(root, "assets", "sub", "icon.png"))
    _write(os.path.join(root, "node_modules", "pkg", "logo.png"))
    return root


@pytest.fixture
def tree(tmp_path):
    """The sample folder with the icon-like files."""
    return _build_tree(str(tmp_path))


def _names(paths, root):
    """The file names of ``paths``, relative to ``root``."""
    return [os.path.relpath(path, root) for path in paths]


# ---------------------------------------------------------------------------
# A. detect_icon_candidates -- the pure scan
# ---------------------------------------------------------------------------

def test_the_favicon_is_the_best_candidate(tree):
    """'favicon' is the strongest hint, so it wins the ranking."""
    candidates = fie.detect_icon_candidates(tree)
    assert candidates, "the sample folder must yield candidates"
    assert os.path.basename(candidates[0]) == "favicon.png"
    assert candidates[0] == os.path.join(str(tree), "favicon.png")


def test_the_icon_like_files_are_all_detected(tree):
    """Every icon-like name is found, whatever the language."""
    candidates = fie.detect_icon_candidates(tree)
    found = _names(candidates, str(tree))
    assert "favicon.png" in found
    assert "logo.svg" in found
    assert "brasao.png" in found
    assert os.path.join("assets", "sub", "icon.png") in found


def test_the_decoys_are_not_detected(tree):
    """Pictures that are not icons, hidden files and vendor folders are out."""
    candidates = fie.detect_icon_candidates(tree)
    found = _names(candidates, str(tree))
    assert "photo.jpg" not in found
    assert "notes.txt" not in found
    assert ".hidden-icon.png" not in found
    assert not any("node_modules" in name for name in found)
    assert not any(".hidden-folder" in name for name in found)


def test_a_nested_icon_is_detected(tree):
    """The scan goes two levels down into the sub-folders."""
    candidates = fie.detect_icon_candidates(tree)
    assert os.path.join(str(tree), "assets", "sub", "icon.png") in candidates


def test_the_accents_and_the_case_are_ignored(tree):
    """'icone-da-pasta' and 'MEU_ICONE' are recognised as icons."""
    candidates = fie.detect_icon_candidates(tree)
    found = _names(candidates, str(tree))
    assert "ícone-da-pasta.png" in found
    assert "MEU_ICONE.PNG" in found


def test_the_candidates_are_absolute_paths(tree):
    """The caller receives ready-to-use absolute paths."""
    candidates = fie.detect_icon_candidates(tree)
    assert candidates
    for path in candidates:
        assert os.path.isabs(path), path
        assert os.path.isfile(path), path


def test_a_missing_folder_yields_no_candidate(tmp_path):
    """A folder that does not exist is not an error."""
    missing = str(tmp_path / "does-not-exist")
    assert fie.detect_icon_candidates(missing) == []


def test_an_empty_path_yields_no_candidate():
    """An empty path is not an error either."""
    assert fie.detect_icon_candidates("") == []
    assert fie.detect_icon_candidates(None) == []


def test_a_file_is_not_scanned(tmp_path):
    """Scanning a plain file yields nothing."""
    path = _write(str(tmp_path / "favicon.png"))
    assert fie.detect_icon_candidates(path) == []


def test_the_limit_is_honoured(tree):
    """``limit`` caps the number of returned candidates."""
    assert len(fie.detect_icon_candidates(tree, limit=2)) == 2
    assert len(fie.detect_icon_candidates(tree, limit=1)) == 1
    assert fie.detect_icon_candidates(tree, limit=0) == []
    # The limit never changes the order of the candidates.
    everything = fie.detect_icon_candidates(tree)
    assert fie.detect_icon_candidates(tree, limit=2) == everything[:2]


def test_an_exact_name_wins_over_a_prefix_and_a_substring(tmp_path):
    """The ranking is: the name IS the hint, then it starts with it, then it
    only contains it."""
    _write(os.path.join(str(tmp_path), "icon-dark.png"))
    _write(os.path.join(str(tmp_path), "my-icon.png"))
    _write(os.path.join(str(tmp_path), "icon.png"))
    candidates = fie.detect_icon_candidates(str(tmp_path))
    assert _names(candidates, str(tmp_path)) == [
        "icon.png", "icon-dark.png", "my-icon.png"]


def test_the_svg_wins_over_the_png(tmp_path):
    """With the same name, the vector format comes first."""
    _write(os.path.join(str(tmp_path), "a", "logo.svg"), TINY_SVG)
    _write(os.path.join(str(tmp_path), "b", "logo.png"))
    candidates = fie.detect_icon_candidates(str(tmp_path))
    assert _names(candidates, str(tmp_path)) == [
        os.path.join("a", "logo.svg"),
        os.path.join("b", "logo.png"),
    ]


def test_the_raster_formats_are_detected_too(tmp_path):
    """The PNG/SVG request also accepts JPG, JPEG and WebP.

    The user asked for PNG and SVG, but the extra raster formats are an
    accepted extra: they are found and ranked behind the vector format.
    """
    for name in ("icon.png", "icon.webp", "icon.jpeg", "icon.jpg"):
        _write(os.path.join(str(tmp_path), name))
    candidates = fie.detect_icon_candidates(str(tmp_path))
    assert _names(candidates, str(tmp_path)) == [
        "icon.png", "icon.webp", "icon.jpeg", "icon.jpg"]


def test_a_single_candidate_is_still_a_candidate(tmp_path):
    """A folder with one icon-like file returns exactly that file."""
    _write(os.path.join(str(tmp_path), "favicon.png"))
    candidates = fie.detect_icon_candidates(str(tmp_path))
    assert candidates == [os.path.join(str(tmp_path), "favicon.png")]


# ---------------------------------------------------------------------------
# B. detect_icon_for_folder -- the flow, without a display
# ---------------------------------------------------------------------------

class _FakeAlertDialog:
    """Stand-in for ``Gtk.AlertDialog``: it never touches the display."""

    def __init__(self, message=None, **kwargs):
        self.message = message
        self.shown_with = None

    def show(self, parent=None):
        self.shown_with = parent
        return self


@pytest.fixture
def alerts(monkeypatch):
    """Replace the GTK alert of the "nothing found" path with a recorder."""
    created = []

    def factory(message=None, **kwargs):
        alert = _FakeAlertDialog(message)
        created.append(alert)
        return alert

    monkeypatch.setattr(fie, "Gtk",
                        types.SimpleNamespace(AlertDialog=factory))
    return created


def test_a_single_candidate_is_chosen_without_a_dialog(tmp_path, monkeypatch):
    """One candidate is used right away: no chooser, no display needed."""
    only = _write(os.path.join(str(tmp_path), "favicon.png"))

    def _fail(*args, **kwargs):
        raise AssertionError("the chooser must not be opened")

    monkeypatch.setattr(fie, "choose_detected_icon", _fail)
    chosen = []
    fie.detect_icon_for_folder(str(tmp_path), on_chosen=chosen.append)
    assert chosen == [only]


def test_nothing_found_ends_with_an_empty_path(tmp_path, alerts):
    """Without any candidate the callback gets an empty path."""
    chosen = []
    fie.detect_icon_for_folder(str(tmp_path), on_chosen=chosen.append)
    assert chosen == [""]
    # The user is told about it, in the language of the caller.
    assert len(alerts) == 1
    assert alerts[0].message == "No icon found"


def test_the_alert_is_translated(tmp_path, alerts):
    """The alert goes through the ``tr`` callable of the caller."""
    chosen = []
    fie.detect_icon_for_folder(str(tmp_path), tr=lambda text: "TR:" + text,
                               on_chosen=chosen.append)
    assert chosen == [""]
    assert alerts[0].message == "TR:No icon found"
    assert alerts[0].shown_with is None


def test_several_candidates_open_the_chooser(tree, monkeypatch):
    """More than one candidate: the chooser decides."""
    calls = []

    def fake_chooser(candidates, tr=None, on_chosen=None, parent=None):
        calls.append(list(candidates))
        if callable(on_chosen):
            on_chosen(candidates[0])

    monkeypatch.setattr(fie, "choose_detected_icon", fake_chooser)
    chosen = []
    fie.detect_icon_for_folder(str(tree), on_chosen=chosen.append)
    assert len(calls) == 1
    assert len(calls[0]) > 1
    assert os.path.basename(calls[0][0]) == "favicon.png"
    assert chosen == [calls[0][0]]


def test_a_callback_error_never_escapes(tmp_path):
    """A broken callback must not reach Nautilus."""
    _write(os.path.join(str(tmp_path), "favicon.png"))

    def boom(_path):
        raise RuntimeError("boom")

    # The single-candidate path calls the callback itself: the error has to
    # be swallowed by the module.
    fie.detect_icon_for_folder(str(tmp_path), on_chosen=boom)


def test_a_callback_error_never_escapes_from_the_chooser(tree, monkeypatch):
    """The chooser path swallows the callback error too."""
    def fake_chooser(candidates, tr=None, on_chosen=None, parent=None):
        # The real chooser reports the choice through the same helper.
        fie._notify_chosen(on_chosen, candidates[0])

    monkeypatch.setattr(fie, "choose_detected_icon", fake_chooser)

    def boom(_path):
        raise RuntimeError("boom")

    fie.detect_icon_for_folder(str(tree), on_chosen=boom)


# ---------------------------------------------------------------------------
# Characters NFKD cannot decompose (Danish/Norwegian ø, Polish ł, German ß):
# an icon named "logø.png" must still match the hint "logo".
# ---------------------------------------------------------------------------

def test_characters_that_nfkd_cannot_decompose_are_folded(tmp_path):
    """ø / ł / ß fold to o / l / ss so the hints still match."""
    _write(os.path.join(str(tmp_path), "logø.png"))
    _write(os.path.join(str(tmp_path), "Łogo.svg"), TINY_SVG)
    _write(os.path.join(str(tmp_path), "ßchild.png"))

    names = _names(fie.detect_icon_candidates(str(tmp_path)), str(tmp_path))
    assert "logø.png" in names, "NFKD cannot decompose ø — it needs a fold"
    assert "Łogo.svg" in names, "NFKD cannot decompose ł — it needs a fold"
    assert "ßchild.png" in names, "ß folds to ss so schild still matches"


def test_an_unfoldable_letter_stays_excluded(tmp_path):
    """The fold does not turn unrelated files into icon candidates."""
    _write(os.path.join(str(tmp_path), "ølaf-photo.png"), TINY_PNG)
    _write(os.path.join(str(tmp_path), "fulano.png"))

    names = _names(fie.detect_icon_candidates(str(tmp_path)), str(tmp_path))
    assert "fulano.png" not in names
    assert "ølaf-photo.png" not in names


# ---------------------------------------------------------------------------
# Several folders at once (a multi-selection in Nautilus).
# ---------------------------------------------------------------------------

def test_several_folders_are_scanned_and_merged(tmp_path):
    """A list of folders yields one ranked list of absolute paths."""
    first = os.path.join(str(tmp_path), "one")
    second = os.path.join(str(tmp_path), "two")
    _write(os.path.join(first, "favicon.png"))
    _write(os.path.join(second, "logo.svg"), TINY_SVG)
    _write(os.path.join(second, "photo.jpg"))  # not an icon name

    found = fie.detect_icon_candidates([first, second])
    names = sorted(os.path.basename(path) for path in found)
    assert names == ["favicon.png", "logo.svg"]
    for path in found:
        assert os.path.isabs(path)


def test_a_folder_scanned_twice_is_not_duplicated(tmp_path):
    """The same folder listed twice appears once in the result."""
    first = str(tmp_path)
    _write(os.path.join(first, "favicon.png"))
    assert fie.detect_icon_candidates([first, first, first]) == \
        fie.detect_icon_candidates(first)


def test_a_pathlib_path_is_accepted(tmp_path):
    """A pathlib.Path behaves exactly like its string form."""
    folder = tmp_path  # pathlib.Path
    _write(os.path.join(str(folder), "favicon.png"))
    assert fie.detect_icon_candidates(folder) == \
        fie.detect_icon_candidates(str(folder))


def test_the_flow_accepts_a_list_of_folders(tmp_path, monkeypatch):
    """detect_icon_for_folder works with several folders too."""
    first = os.path.join(str(tmp_path), "one")
    second = os.path.join(str(tmp_path), "two")
    _write(os.path.join(first, "favicon.png"))
    _write(os.path.join(second, "logo.svg"), TINY_SVG)

    def fake_chooser(candidates, tr=None, on_chosen=None, parent=None):
        fie._notify_chosen(on_chosen, candidates[0])

    monkeypatch.setattr(fie, "choose_detected_icon", fake_chooser)

    chosen = []
    fie.detect_icon_for_folder([first, second], on_chosen=chosen.append)

    assert len(chosen) == 1
    assert os.path.isabs(chosen[0])
    assert chosen[0] in fie.detect_icon_candidates([first, second])
