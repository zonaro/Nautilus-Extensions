"""Portable SVG projects: no GTK, real installs, theme writes or network."""

import base64
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import folder_icon_project as project


SVG = "{" + project.SVG_NS + "}"
FCR = "{" + project.PROJECT_NS + "}"
XLINK = "{" + project.XLINK_NS + "}"
SAFE_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
            b'<defs><linearGradient id="paint"><stop stop-color="#ff00ee"/>'
            b'</linearGradient></defs><path fill="url(#paint)" d="M0 0h16v16z"/></svg>')


def png(color=(40, 80, 120, 255), size=(16, 16)):
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, format="PNG")
    return out.getvalue()


def save(tmp_path, state=None, layers=None, **kwargs):
    if state is None:
        state = {"version": 2, "spec": "3584e4", "theme": "Adwaita",
                 "base_image": "", "follow_accent": True,
                 "layers": [{"type": "text", "text": "Olá 世界", "font": "Missing Font"}]}
    if layers is None:
        layers = [png((255, 20, 50, 128)) for _ in state.get("layers", [])]
    data = project.save_svg_project(png(), layers, state, **kwargs)
    path = tmp_path / "project.svg"
    path.write_bytes(data)
    return path, data


def metadata(root):
    node = root.find("./" + SVG + "metadata/" + FCR + "project")
    return node, json.loads(node.text)


def edit_metadata(data, edit):
    root = ET.fromstring(data)
    node, payload = metadata(root)
    edit(payload)
    node.text = json.dumps(payload, ensure_ascii=False)
    return ET.tostring(root, encoding="utf-8")


def load_data(tmp_path, data):
    path = tmp_path / "changed.svg"
    path.write_bytes(data)
    return project.load_svg_project(path, tmp_path / "cache")


def test_visible_svg_has_real_bottom_to_top_layer_stack(tmp_path):
    top, bottom = png((230, 20, 20, 128)), png((20, 230, 20, 128))
    state = {"layers": [{"type": "text", "text": "top"},
                        {"type": "text", "text": "bottom"}]}
    path, data = save(tmp_path, state, [bottom, top])
    root = ET.fromstring(data)
    images = root.findall("./" + SVG + "g/" + SVG + "image")
    assert len(images) == 3
    assert [image.get("id") for image in images] == ["base", "layer-0", "layer-1"]
    decoded = [base64.b64decode(image.get(XLINK + "href").split(",", 1)[1])
               for image in images]
    assert decoded == [png(), bottom, top]
    assert all(image.get("transform") is None for image in images)
    assert all(image.get("opacity") is None for image in images)
    node, payload = metadata(root)
    assert node.get("version") == "1"
    assert payload["state"] == state
    loaded = project.load_svg_project(path, tmp_path / "cache")
    assert [Path(value).read_bytes() for value in loaded["_svg_project"]["layer_pngs"]] == [bottom, top]


def test_roundtrip_preserves_all_fields_and_embeds_originals_after_deletion(tmp_path):
    originals = tmp_path / "originals"
    originals.mkdir()
    assets = {"base.png": png((1, 2, 3, 255)), "image.png": png((4, 5, 6, 130)),
              "emblem.svg": SAFE_SVG, "mask.svg": SAFE_SVG.replace(b"ff00ee", b"ffffff")}
    for name, data in assets.items():
        (originals / name).write_bytes(data)
    image = {"type": "image", "name": "Foto açafrão", "path": str(originals / "image.png"),
             "symbol_id": "test/image", "opacity": 61, "scale": 72, "rotation": -31,
             "offset_x": -4, "offset_y": 13, "hue": 12, "saturation": -40,
             "monochrome": True, "invert": True, "threshold": 88, "mono_color": "#aabbcc",
             "mask_mode": "custom", "mask_path": str(originals / "mask.svg"),
             "future_flag": {"enabled": True}}
    text = {"type": "text", "text": "Olá 日本語 مرحبا 🐱", "font": "Uninstalled Font",
            "font_size": 37, "bold": True, "italic": True, "color": "#00ffcc"}
    emblem = {"type": "emblem", "name": "Ícone", "emblem": "emblem-important",
              "emblem_uri": (originals / "emblem.svg").as_uri(), "scale": 25}
    state = {"version": 2, "spec": "ffeedd;112233", "theme": "Theme not installed",
             "follow_accent": True, "base_image": str(originals / "base.png"),
             "layers": [image, text, emblem], "selected": 1, "scope": "folder",
             "scopes": {"folder": {"base_image_path": str(originals / "base.png"),
                                   "layers": [copy.deepcopy(image)], "theme": "Adwaita",
                                   "follow_accent": False, "hexes": ["#ffeedd"]},
                        "global": {"base_image": "", "layers": [copy.deepcopy(emblem)],
                                   "spec": "aabbcc", "theme": "Yaru", "follow_accent": True}}}
    untouched = copy.deepcopy(state)
    raw_sources = [None, png((250, 250, 250, 180), (9, 7)), None]
    snapshots = [png((10, 20, 30, 40)), png((30, 40, 50, 60)), png((60, 70, 80, 90))]
    path, exported = save(tmp_path, state, snapshots, source_pngs=raw_sources)
    assert state == untouched
    assert str(originals).encode() not in exported
    for file in originals.iterdir():
        file.unlink()
    originals.rmdir()
    restored = project.load_svg_project(path, tmp_path / "cache")
    frozen = restored.pop("_svg_project")
    expected = copy.deepcopy(untouched)
    for block in (expected, expected["scopes"]["folder"], expected["scopes"]["global"]):
        for key in ("base_image", "base_image_path"):
            if block.get(key):
                data = assets[Path(block[key]).name]
                block[key] = str(tmp_path / "cache" / (hashlib.sha256(data).hexdigest() + ".png"))
        for layer in block.get("layers", []):
            for key in ("path", "mask_path", "emblem_uri"):
                if layer.get(key):
                    name = layer[key].rsplit("/", 1)[-1]
                    data = assets[name]
                    suffix = ".svg" if name.endswith(".svg") else ".png"
                    layer[key] = str(tmp_path / "cache" / (hashlib.sha256(data).hexdigest() + suffix))
    assert restored == expected
    assert frozen["layer_states"] == expected["layers"]
    assert Path(frozen["source_pngs"][1]).read_bytes() == raw_sources[1]
    assert Path(frozen["base_png"]).read_bytes() == png()
    assert Path(restored["layers"][2]["emblem_uri"]).read_bytes() == SAFE_SVG
    reexported = project.save_svg_project(
        Path(frozen["base_png"]).read_bytes(),
        [Path(value).read_bytes() for value in frozen["layer_pngs"]],
        {**restored, "_svg_project": frozen},
        source_pngs=[Path(value).read_bytes() if value else None for value in frozen["source_pngs"]])
    assert reexported == exported


def test_sources_are_deduplicated_by_hash_and_unknown_paths_are_not_read(tmp_path):
    source = tmp_path / "source.svg"
    source.write_bytes(SAFE_SVG)
    state = {"base_image": str(source), "unknown": {"path": "/never/read/this"},
             "font": "/also/not/a/font/file", "layers": [
                 {"type": "symbol", "path": str(source), "mask_path": str(source),
                  "symbol_id": "favorite", "color": "#aabbcc"}]}
    path, data = save(tmp_path, state)
    assert len(ET.fromstring(data).findall("./" + SVG + "metadata/" + FCR + "assets/" + FCR + "asset")) == 1
    restored = project.load_svg_project(path, tmp_path / "cache")
    assert restored["base_image"] == restored["layers"][0]["path"] == restored["layers"][0]["mask_path"]
    assert restored["unknown"] == state["unknown"]
    assert restored["font"] == state["font"]


def test_plain_safe_svg_and_legacy_png_return_none_without_cache_writes(tmp_path):
    for name, data in (("plain.svg", SAFE_SVG), ("legacy.png", png())):
        path = tmp_path / name
        path.write_bytes(data)
        assert project.load_svg_project(path, tmp_path / "cache") is None
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("suffix", [".svgz", ".png", ""])
@pytest.mark.parametrize("content", ["plain", "oversized", "project", "malformed"])
def test_compressed_svg_never_falls_back_regardless_filename(tmp_path, suffix, content, monkeypatch):
    _path, exported = save(tmp_path)
    payloads = {"plain": SAFE_SVG,
                "oversized": b'<svg xmlns="http://www.w3.org/2000/svg" width="12001" height="1"/>',
                "project": exported, "malformed": b'<svg xmlns="http://www.w3.org/2000/svg"'}
    path = tmp_path / ("compressed" + suffix)
    path.write_bytes(gzip.compress(payloads[content]))

    def no_decompression(*_args, **_kwargs):
        pytest.fail("Compressed input must be rejected without decompression")

    monkeypatch.setattr(gzip, "decompress", no_decompression)
    with pytest.raises(project.UnsupportedProjectError, match="gzip|SVGZ"):
        project.load_svg_project(path, tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("suffix", [".svgz", ".png", ""])
@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be",
                                      "utf-32", "utf-32-le", "utf-32-be"])
@pytest.mark.parametrize("xml", [SAFE_SVG.decode(), '<svg xmlns="http://www.w3.org/2000/svg"'])
def test_encoded_xml_never_falls_back_regardless_filename(tmp_path, suffix, encoding, xml):
    path = tmp_path / ("encoded" + suffix)
    path.write_bytes(xml.encode(encoding))
    with pytest.raises(project.ProjectError):
        project.load_svg_project(path, tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("suffix", [".svgz", ".png", ""])
@pytest.mark.parametrize("payload", [b"", b"not an image", b"\x00\x01\x02",
                                    b"%PDF-1.7\n", b"\x1f\x8btruncated gzip"])
def test_unknown_formats_never_fall_back_to_generic_decoder(tmp_path, suffix, payload):
    path = tmp_path / ("unknown" + suffix)
    path.write_bytes(payload)
    with pytest.raises(project.ProjectError):
        project.load_svg_project(path, tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("signature", [b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff",
                                      b"GIF89a", b"BM", b"II*\x00", b"RIFF\x00\x00\x00\x00WEBP"])
@pytest.mark.parametrize("suffix", [".svgz", ".png", ""])
def test_malformed_raster_fallback_is_rejected_after_magic_match(tmp_path, signature, suffix):
    path = tmp_path / ("truncated" + suffix)
    path.write_bytes(signature)
    with pytest.raises(project.ProjectError):
        project.load_svg_project(path, tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("limit,value", [("MAX_ASSET_BYTES", 10), ("MAX_IMAGE_SIDE", 8),
                                         ("MAX_IMAGE_PIXELS", 64)])
def test_plain_raster_fallback_obeys_asset_and_pixel_limits(tmp_path, monkeypatch, limit, value):
    path = tmp_path / "ordinary.png"
    path.write_bytes(png())
    monkeypatch.setattr(project, limit, value)
    with pytest.raises(project.ProjectError):
        project.load_svg_project(path, tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("kind", ["PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP"])
def test_valid_supported_raster_fallback_is_validated_without_cache_writes(tmp_path, kind):
    out = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(out, format=kind)
    path = tmp_path / "ordinary"
    path.write_bytes(out.getvalue())
    assert project.load_svg_project(path, tmp_path / "cache") is None
    assert not (tmp_path / "cache").exists()


def test_legacy_png_project_metadata_remains_available_for_editor_loader(tmp_path):
    from PIL.PngImagePlugin import PngInfo

    legacy = {"version": 1, "spec": "3584e4", "layers": [{"type": "text", "text": "Olá"}]}
    info = PngInfo()
    info.add_text("fcRev", json.dumps(legacy, ensure_ascii=False))
    path = tmp_path / "legacy.png"
    Image.new("RGBA", (16, 16), "red").save(path, format="PNG", pnginfo=info)
    assert project.load_svg_project(path, tmp_path / "cache") is None
    with Image.open(path) as image:
        assert json.loads(image.info["fcRev"]) == legacy
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("malicious", [
    b'<!DOCTYPE svg [<!ENTITY x "boom">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.invalid/a.png"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/passwd"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><image href="../a.png"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://example.invalid/)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://example.invalid/";</style></svg>',
    br'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="u\72l(https://example.invalid/)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" xml:base="/tmp/"/>',
    b'<?xml-stylesheet href="https://example.invalid/a.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><animate attributeName="href"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><g id="loop"><use href="#loop"/></g></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><pattern id="loop"><path fill="url(#loop)"/></pattern></svg>',
])
def test_unsafe_plain_svg_and_embedded_source_svg_are_rejected(tmp_path, malicious):
    source = tmp_path / "unsafe.svg"
    source.write_bytes(malicious)
    with pytest.raises(project.ProjectError):
        project.load_svg_project(source, tmp_path / "cache")
    with pytest.raises(project.ProjectError):
        save(tmp_path, {"layers": [{"type": "image", "path": str(source)}]})
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("edit", [
    lambda p: p.update(version=999),
    lambda p: p.update(version=True),
    lambda p: p.update(format="another-format"),
    lambda p: p.update(state=[]),
    lambda p: p["render"].update(layers=[]),
    lambda p: p["render"].update(base="../escape"),
    lambda p: p["state"].update(base_image="file:///etc/passwd"),
    lambda p: p["state"]["layers"][0].update(path="../../escape.png"),
    lambda p: p["state"]["layers"][0].update(path="asset:sha256:" + "0" * 64),
    lambda p: p["state"].update(scopes={"untrusted": {"layers": []}}),
])
def test_malformed_project_metadata_rejected_before_cache_write(tmp_path, edit):
    _path, data = save(tmp_path)
    with pytest.raises(project.ProjectError):
        load_data(tmp_path, edit_metadata(data, edit))
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("change", ["json", "duplicate_json", "xml", "namespace", "version",
                                    "extra_image", "event", "mimetype", "pixel", "asset_hash"])
def test_malformed_and_unsafe_projects_do_not_fall_back_to_plain_images(tmp_path, change):
    source = tmp_path / "source.svg"
    source.write_bytes(SAFE_SVG)
    _path, data = save(tmp_path, {"layers": [{"type": "image", "path": str(source)}]})
    root = ET.fromstring(data)
    node, payload = metadata(root)
    if change == "json":
        node.text = "{bad json"
    elif change == "duplicate_json":
        node.text = '{"version":1,"version":2}'
    elif change == "xml":
        data = data[:-10]
    elif change == "namespace":
        node.tag = "{urn:nautilus-extensions:folder-icon-project:999}project"
    elif change == "version":
        node.set("version", "2")
    elif change == "extra_image":
        ET.SubElement(root, SVG + "image", {"href": "file:///etc/passwd"})
    elif change == "event":
        root.find("./" + SVG + "g/" + SVG + "image").set("onload", "boom()")
    elif change == "mimetype":
        asset = root.find("./" + SVG + "metadata/" + FCR + "assets/" + FCR + "asset")
        asset.set("mime", "image/png")
    elif change == "pixel":
        root.set("width", "17")
    elif change == "asset_hash":
        asset = root.find("./" + SVG + "metadata/" + FCR + "assets/" + FCR + "asset")
        asset.set("sha256", "0" * 64)
    if change != "xml":
        data = ET.tostring(root, encoding="utf-8")
    with pytest.raises(project.ProjectError):
        load_data(tmp_path, data)
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("limit,value", [
    ("MAX_FILE_BYTES", 50), ("MAX_METADATA_BYTES", 30), ("MAX_ASSET_BYTES", 10),
    ("MAX_TOTAL_ASSET_BYTES", 100), ("MAX_IMAGE_SIDE", 8), ("MAX_IMAGE_PIXELS", 64),
    ("MAX_TOTAL_PIXELS", 300), ("MAX_ASSETS", 1), ("MAX_LAYERS", 0),
])
def test_export_and_import_enforce_limits(tmp_path, monkeypatch, limit, value):
    path, _data = save(tmp_path)
    monkeypatch.setattr(project, limit, value)
    with pytest.raises(project.ProjectError):
        save(tmp_path)
    with pytest.raises(project.ProjectError):
        project.load_svg_project(path, tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


def test_deep_and_oversized_xml_and_json_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(project, "MAX_XML_DEPTH", 5)
    deep = b'<svg xmlns="http://www.w3.org/2000/svg">' + b"<g>" * 6 + b"</g>" * 6 + b"</svg>"
    with pytest.raises(project.ProjectError, match="deep"):
        load_data(tmp_path, deep)
    monkeypatch.setattr(project, "MAX_XML_NODES", 2)
    with pytest.raises(project.ProjectError, match="elements"):
        load_data(tmp_path, SAFE_SVG)
    monkeypatch.setattr(project, "MAX_JSON_DEPTH", 2)
    with pytest.raises(project.ProjectError, match="nested"):
        save(tmp_path, {"layers": [], "extra": {"one": {"two": {"three": 1}}}})


def test_snapshot_count_dimensions_and_mime_checked(tmp_path):
    state = {"layers": [{"type": "text", "text": "x"}]}
    for snapshots in ([], [png(size=(8, 8))], [SAFE_SVG], [b"not a PNG"]):
        with pytest.raises(project.ProjectError):
            project.save_svg_project(png(), snapshots, state)
    with pytest.raises(project.ProjectError):
        project.save_svg_project(png(), [png()], state, source_pngs=[])


def test_original_mime_is_sniffed_and_corrupt_pixels_are_rejected(tmp_path):
    misleading = tmp_path / "picture.png"
    misleading.write_bytes(SAFE_SVG)
    path, _data = save(tmp_path, {"layers": [{"path": str(misleading)}]})
    loaded = project.load_svg_project(path, tmp_path / "cache")
    assert loaded["layers"][0]["path"].endswith(".svg")
    misleading.write_bytes(png()[:45])
    with pytest.raises(project.ProjectError, match="image"):
        save(tmp_path, {"layers": [{"path": str(misleading)}]})


def test_source_svg_nested_raster_is_verified_and_nested_svg_is_rejected(tmp_path):
    def svg(mime, blob):
        return (b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><image href="data:'
                + mime + b';base64,' + base64.b64encode(blob) + b'"/></svg>')
    source = tmp_path / "embedded.svg"
    source.write_bytes(svg(b"image/png", png()))
    save(tmp_path, {"layers": [{"path": str(source)}]})
    for mime, blob in ((b"image/png", SAFE_SVG), (b"image/svg+xml", SAFE_SVG)):
        source.write_bytes(svg(mime, blob))
        with pytest.raises(project.ProjectError):
            save(tmp_path, {"layers": [{"path": str(source)}]})


def test_cache_hash_names_cannot_traverse_or_follow_symlinks(tmp_path):
    path, _data = save(tmp_path)
    outside = tmp_path / "untouched"
    outside.write_bytes(b"private")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / (hashlib.sha256(png()).hexdigest() + ".png")).symlink_to(outside)
    with pytest.raises(project.ProjectError, match="symlink"):
        project.load_svg_project(path, cache)
    assert outside.read_bytes() == b"private"
    alias = tmp_path / "alias"
    alias.symlink_to(cache, target_is_directory=True)
    with pytest.raises(project.ProjectError, match="directory"):
        project.load_svg_project(path, alias)


def test_atomic_writer_and_managed_cache_are_idempotent(tmp_path):
    _path, data = save(tmp_path)
    destination = tmp_path / "final.svg"
    destination.write_bytes(b"old content")
    project.write_svg_project(destination, data)
    assert destination.read_bytes() == data
    restored = project.load_svg_project(destination, tmp_path / "cache")
    snapshots = {path: os.stat(path).st_mtime_ns for path in (tmp_path / "cache").iterdir()}
    assert project.load_svg_project(destination, tmp_path / "cache") == restored
    assert {path: os.stat(path).st_mtime_ns for path in snapshots} == snapshots
    assert not list(tmp_path.glob(".folder-icon-*"))
    link = tmp_path / "link.svg"
    link.symlink_to(destination)
    with pytest.raises(project.ProjectError, match="symlink"):
        project.write_svg_project(link, data)


def test_atomic_replace_failure_preserves_old_file_and_removes_temporary(tmp_path, monkeypatch):
    _path, data = save(tmp_path)
    destination = tmp_path / "final.svg"
    destination.write_bytes(b"old content")

    def fail_replace(_source, _destination):
        raise OSError("simulated failure before atomic replace")

    monkeypatch.setattr(project.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        project.write_svg_project(destination, data)
    assert destination.read_bytes() == b"old content"
    assert not list(tmp_path.glob(".folder-icon-*"))


def test_import_repairs_corrupt_managed_cache_and_handles_local_emblem_paths(tmp_path):
    source = tmp_path / "ícone com espaço.svg"
    source.write_bytes(SAFE_SVG)
    state = {"layers": [{"type": "emblem", "emblem": str(source), "emblem_uri": source.as_uri()}]}
    path, _data = save(tmp_path, state)
    restored = project.load_svg_project(path, tmp_path / "cache")
    layer = restored["layers"][0]
    assert layer["emblem"] == layer["emblem_uri"]
    cached = Path(layer["emblem_uri"])
    assert cached.read_bytes() == SAFE_SVG
    cached.write_bytes(b"corrupt")
    assert project.load_svg_project(path, tmp_path / "cache") == restored
    assert cached.read_bytes() == SAFE_SVG


def test_nonfinite_numbers_and_unresolved_emblems_and_remote_sources_fail(tmp_path):
    for state in ({"layers": [], "opacity": float("nan")},
                  {"layers": [{"type": "emblem", "emblem": "emblem-important"}]},
                  {"layers": [{"path": "https://example.invalid/a.png"}]},
                  {"layers": [{"path": "file://remote.invalid/a.png"}]},
                  {"layers": [{"path": "/missing/original.png"}]}):
        with pytest.raises(project.ProjectError):
            save(tmp_path, state)


@pytest.mark.parametrize("state", [None, [], {"layers": 1}, {"layers": "text"},
                                  {"layers": [1]}, {"scopes": []},
                                  {"scopes": {"folder": None}},
                                  {"layers": [{"path": 42}]},
                                  {"layers": [{"emblem": "https://example.invalid/"}]},
                                  {"layers": [{"path": "file://[invalid"}]}])
def test_invalid_export_state_uses_clear_project_errors(state):
    with pytest.raises(project.ProjectError):
        project.save_svg_project(png(), [], state)


def test_import_rejects_reserved_snapshot_paths_in_scopes(tmp_path):
    _path, data = save(tmp_path)
    changed = edit_metadata(data, lambda payload: payload["state"].update(
        scopes={"folder": {"layers": [], "_svg_project": {"base_png": "/never/read"}}}))
    with pytest.raises(project.ProjectError, match="Transient"):
        load_data(tmp_path, changed)
    assert not (tmp_path / "cache").exists()


def test_import_rejects_traversal_asset_names(tmp_path):
    source = tmp_path / "source.svg"
    source.write_bytes(SAFE_SVG)
    _path, data = save(tmp_path, {"layers": [{"path": str(source)}]})
    root = ET.fromstring(data)
    root.find("./" + SVG + "metadata/" + FCR + "assets/" + FCR + "asset").set("sha256", "../escape")
    with pytest.raises(project.ProjectError, match="hash"):
        load_data(tmp_path, ET.tostring(root))
    assert not (tmp_path / "escape").exists()


def test_source_svg_dimensions_and_expanded_reference_graph_are_bounded(tmp_path):
    large = b'<svg xmlns="http://www.w3.org/2000/svg" width="1e20" height="1"/>'
    huge_viewbox = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 99999999 9"/>'
    # Reverse order defeats a depth check that forgets cached subtree heights.
    chain = (b'<svg xmlns="http://www.w3.org/2000/svg"><defs><g id="n0"/>'
             + b"".join(f'<g id="n{i}"><use href="#n{i - 1}"/></g>'.encode()
                        for i in range(1, 40)) + b'</defs><use href="#n39"/></svg>')
    for data in (large, huge_viewbox, chain):
        with pytest.raises(project.ProjectError):
            load_data(tmp_path, data)


def test_animation_and_utf16_or_malformed_base64_are_rejected(tmp_path):
    animation = io.BytesIO()
    Image.new("RGBA", (4, 4), "red").save(
        animation, format="PNG", save_all=True,
        append_images=[Image.new("RGBA", (4, 4), "blue")], duration=100)
    with pytest.raises(project.ProjectError, match="Animated"):
        project.save_svg_project(animation.getvalue(), [], {"layers": []})
    with pytest.raises(project.UnsupportedProjectError, match="non-UTF-8"):
        load_data(tmp_path, SAFE_SVG.decode().encode("utf-16"))
    with pytest.raises(project.ProjectError, match="UTF-8"):
        load_data(tmp_path, b'<?xml version="1.0" encoding="iso-8859-1"?>' + SAFE_SVG)
    _path, data = save(tmp_path)
    root = ET.fromstring(data)
    root.find("./" + SVG + "g/" + SVG + "image").set(XLINK + "href", "data:image/png;base64,!!bad!!")
    with pytest.raises(project.ProjectError):
        load_data(tmp_path, ET.tostring(root))


def test_regular_file_only_and_default_cache_is_isolated(tmp_path, monkeypatch):
    fifo = tmp_path / "pipe.svg"
    os.mkfifo(fifo)
    with pytest.raises(project.ProjectError, match="regular"):
        project.load_svg_project(fifo, tmp_path / "cache")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    path, _data = save(tmp_path)
    state = project.load_svg_project(path)
    assert state["_svg_project"]["base_png"].startswith(str(tmp_path / "xdg"))
    assert not (tmp_path / "cache").exists()
