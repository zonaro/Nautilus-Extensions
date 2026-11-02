"""Unit tests for the editor's image import helpers (#30, no display needed).

Dragging an image from Nautilus or pasting one from a browser both end up in
``parse_image_uris``: it has to accept the payloads GTK really hands over
(``Gdk.FileList``, a ``text/uri-list`` string, a list of URIs) and reject
everything that is not a local, genuinely decodable image without ever
fetching a remote URL.
"""
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import folder_icon_editor as fie


def _png(path, size=32):
    Image.new("RGBA", (size, size), (255, 0, 0, 255)).save(path, "PNG")
    return str(path)


def _svg(path):
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="8" '
                    'height="8"><rect width="8" height="8"/></svg>',
                    encoding="utf-8")
    return str(path)


class _FakeFileList:
    """Stand-in for Gdk.FileList (only get_files() is used)."""

    def __init__(self, paths):
        self._files = [_FakeFile(path) for path in paths]

    def get_files(self):
        return list(self._files)


class _FakeFile:
    def __init__(self, path):
        self._path = path

    def get_uri(self):
        return "file://" + str(self._path)


def test_parses_a_uri_list_string(tmp_path):
    image = _png(tmp_path / "a.png")
    other = _png(tmp_path / "b.png")
    payload = "file://%s\nfile://%s\n" % (image, other)
    assert fie.parse_image_uris(payload) == [image, other]


def test_parses_paths_lists_and_file_lists(tmp_path):
    image = _png(tmp_path / "a.png")
    assert fie.parse_image_uris(image) == [image]
    assert fie.parse_image_uris([image]) == [image]
    assert fie.parse_image_uris(_FakeFileList([image])) == [image]


def test_accepts_svg_and_webp_containers(tmp_path):
    svg = _svg(tmp_path / "icon.svg")
    assert fie.parse_image_uris(svg) == [svg]

    webp = tmp_path / "pic.webp"
    Image.new("RGBA", (16, 16), (0, 0, 255, 255)).save(webp, "WEBP")
    assert fie.parse_image_uris(str(webp)) == [str(webp)]


def test_deduplicates_and_ignores_comment_lines(tmp_path):
    image = _png(tmp_path / "a.png")
    payload = "# a comment\nfile://%s\nfile://%s\n" % (image, image)
    assert fie.parse_image_uris(payload) == [image]


def test_remote_urls_and_directories_are_never_used(tmp_path):
    folder = tmp_path / "dir"
    folder.mkdir()
    payload = "\n".join([
        "https://example.com/image.png",
        "http://example.com/image.png",
        "file://" + str(folder),
        "file://" + str(tmp_path / "missing.png"),
    ])
    assert fie.parse_image_uris(payload) == []


def test_a_renamed_non_image_is_rejected(tmp_path):
    fake = tmp_path / "actually-a-script.png"
    fake.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    assert fie.image_problem(str(fake)) == "unsupported"
    assert fie.parse_image_uris(str(fake)) == []


def test_empty_and_oversized_files_are_rejected(tmp_path, monkeypatch):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    assert fie.image_problem(str(empty)) == "empty"

    big = tmp_path / "big.png"
    big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048)
    monkeypatch.setattr(fie, "MAX_IMAGE_BYTES", 1024)
    assert fie.image_problem(str(big)) == "too-large"


def test_missing_path_is_reported():
    assert fie.image_problem("/definitely/not/here.png") == "missing"


def test_drop_value_types_offer_a_string_target():
    # Gdk.FileList is registered by the GTK typelib, but a partial install
    # must still have the text/uri-list target.
    assert fie.GObject.TYPE_STRING in fie._drop_value_types()


def test_pasted_bytes_are_cached_once(tmp_path, monkeypatch):
    monkeypatch.setattr(fie.GLib, "get_user_cache_dir", lambda: str(tmp_path))
    data = b"\x89PNG\r\n\x1a\nfake"
    first = fie._cache_image_bytes(data)
    second = fie._cache_image_bytes(data)
    assert first and first == second
    assert os.path.isfile(first)
    assert first.startswith(str(tmp_path))
    assert fie._cache_image_bytes(b"") == ""


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
