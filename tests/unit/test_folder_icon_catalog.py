"""Offline symbol catalogue: no network, no GTK, no folder writes."""

import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import folder_icon_catalog as catalog


SVG_NS = "http://www.w3.org/2000/svg"


def test_catalogue_is_vendored_and_labelled():
    info = catalog.catalog_info()
    assert info["library"] == "Lucide Icons"
    assert info["license"] == "ISC"
    assert info["version"] == "1.69.0"
    assert info["source"].startswith("https://github.com/lucide-icons/lucide")
    assert info["count"] >= 2000
    assert Path(info["path"]).is_file()
    assert (Path(info["path"]).parent / "LICENSE").is_file()


def test_module_imports_no_network_or_gtk_modules():
    source = Path(catalog.__file__).read_text(encoding="utf-8")
    for forbidden in ("import gi", "urllib", "requests", "socket", "subprocess"):
        assert forbidden not in source


def test_list_is_stable_paginated_and_bounded():
    first = catalog.list_icons(limit=10)
    assert len(first) == 10
    assert all(set(entry) == {"id", "label"} for entry in first)
    repeat = catalog.list_icons(limit=10)
    assert first == repeat
    assert catalog.list_icons(limit=10, offset=10) == catalog.list_icons(limit=20)[10:]
    assert len(catalog.list_icons(limit=10_000)) <= catalog.MAX_LIMIT
    assert catalog.list_icons(limit=10_000) == catalog.list_icons(limit=catalog.MAX_LIMIT)
    ids = [entry["id"] for entry in catalog.list_icons(limit=catalog.MAX_LIMIT, offset=0)]
    assert len(ids) == len(set(ids))


def test_query_narrows_and_exact_id_wins():
    broad = catalog.list_icons("arrow", limit=catalog.MAX_LIMIT)
    narrow = catalog.list_icons("arrow down", limit=catalog.MAX_LIMIT)
    assert broad and narrow
    assert len(narrow) < len(broad)
    narrow_ids = [entry["id"] for entry in narrow]
    assert "arrow-down" in narrow_ids
    assert set(narrow_ids).issubset(set(entry["id"] for entry in broad))
    assert catalog.list_icons("arrow-down")[0]["id"] == "arrow-down"
    assert "arrow-down" in [entry["id"] for entry in catalog.list_icons("Arrow Down")]
    assert catalog.list_icons("no-such-symbol-anywhere") == []


def test_tags_are_searchable():
    hits = catalog.list_icons("typography", limit=catalog.MAX_LIMIT)
    assert hits
    assert any("a-" in entry["id"] for entry in hits)


def test_alias_resolves_to_canonical_artwork():
    canonical = catalog.list_icons("alarm-check")[0]["id"]
    assert canonical == "alarm-check"
    assert catalog.icon_svg("alarm-clock-check") == catalog.icon_svg("alarm-check")
    assert catalog.materialize_icon("alarm-clock-check") == \
        catalog.materialize_icon("alarm-check")


def test_icon_svg_is_well_formed_recoloured_and_inert():
    data = catalog.icon_svg("folder", color="#1A2b3C")
    root = ET.fromstring(data)
    assert root.tag == f"{{{SVG_NS}}}svg"
    assert root.get("viewBox") == "0 0 24 24"
    assert root.get("stroke") == "#1a2b3c"
    text = data.decode("utf-8")
    assert "currentColor" not in text
    assert "script" not in text.lower()
    assert "href" not in text.lower()
    assert "url(" not in text.lower()
    assert 'fill="none"' in text
    assert 'stroke="#1a2b3c"' in text
    for child in root:
        assert child.tag.split("}")[-1] in {
            "path", "circle", "rect", "line", "ellipse", "polyline", "polygon"}
        assert child.get("fill") in (None, "none")


@pytest.mark.parametrize("colour", ["", "red", "#12", "#12345", "rgb(0,0,0)",
                                    "#fff;fill:url(#x)", "url(#paint)"])
def test_invalid_colours_rejected(colour):
    with pytest.raises(ValueError):
        catalog.icon_svg("folder", color=colour)


def test_unknown_symbol_rejected():
    with pytest.raises(KeyError):
        catalog.icon_svg("definitely-not-an-icon")
    with pytest.raises(KeyError):
        catalog.materialize_icon("../etc/passwd")


def test_materialize_is_absolute_cached_and_idempotent(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    path = catalog.materialize_icon("folder", "#ffffff", cache_dir=cache)
    assert os.path.isabs(path)
    assert Path(path).is_file()
    assert Path(path).parent == cache.resolve()
    assert Path(path).read_bytes() == catalog.icon_svg("folder", "#ffffff")
    before = Path(path).stat().st_mtime_ns
    assert catalog.materialize_icon("folder", "#ffffff", cache_dir=cache) == path
    assert Path(path).stat().st_mtime_ns == before
    assert not [name for name in os.listdir(cache) if name.endswith(".tmp")]


def test_materialize_uses_xdg_cache_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    path = Path(catalog.materialize_icon("folder", "#000000"))
    assert path.is_relative_to((tmp_path / "xdg" / "nautilus-extensions"))
    assert path.is_file()


def test_every_symbol_renders():
    ids = catalog.icon_ids()
    assert len(ids) >= 2000
    for icon_id in ids[:200] + ids[-200:]:
        root = ET.fromstring(catalog.icon_svg(icon_id))
        assert len(root), icon_id
