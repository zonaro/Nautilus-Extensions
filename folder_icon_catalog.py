"""Offline monochrome symbol catalogue for the folder icon editor.

The artwork is the official Lucide set (ISC), vendored by
``scripts/generate_folder_icons.py`` into ``assets/folder-icons/catalog.json``
next to this module. There is no network access, no third-party dependency and
no registration side effect: importing this module reads nothing until the
first catalogue call.

Public API used by ``folder_icon_editor``:

    list_icons(query="", limit=120, offset=0) -> [{"id": str, "label": str}]
    icon_svg(icon_id, color="#ffffff") -> bytes
    materialize_icon(icon_id, color="#ffffff", cache_dir=None) -> absolute path

Symbols are inserted as a recolourable layer, not applied to a folder.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

__all__ = [
    "CatalogError",
    "catalog_info",
    "icon_ids",
    "icon_svg",
    "list_icons",
    "materialize_icon",
]

MAX_LIMIT = 500
DEFAULT_LIMIT = 120
VIEWBOX = "0 0 24 24"
# Fixed geometry; the artwork itself is validated at vendor time.
_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="{viewbox}" fill="none" stroke="{color}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)
_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\Z")
_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "folder-icons"
_CATALOG = None


class CatalogError(RuntimeError):
    """The vendored catalogue is missing, unreadable or inconsistent."""


def _load():
    """Parse ``catalog.json`` once; raise :class:`CatalogError` when unusable."""
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    path = _ASSET_DIR / "catalog.json"
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CatalogError(f"symbol catalogue unavailable: {error}") from error
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise CatalogError(f"symbol catalogue is not valid JSON: {error}") from error
    icons = data.get("icons")
    if not isinstance(icons, list) or not icons:
        raise CatalogError("symbol catalogue has no icons")
    by_id = {}
    alias_of = {}
    for entry in icons:
        if not isinstance(entry, dict):
            continue
        icon_id = entry.get("id")
        body = entry.get("body")
        if not isinstance(icon_id, str) or not _ID_RE.match(icon_id):
            raise CatalogError(f"invalid symbol id {icon_id!r}")
        if not isinstance(body, str) or not body.startswith("<") or "</" in body \
                or "<script" in body.lower():
            raise CatalogError(f"invalid artwork for symbol {icon_id!r}")
        record = {
            "id": icon_id,
            "label": str(entry.get("label") or icon_id.replace("-", " ").title()),
            "aliases": tuple(a for a in entry.get("aliases") or ()
                             if isinstance(a, str) and _ID_RE.match(a)),
            "tags": tuple(t for t in entry.get("tags") or () if isinstance(t, str)),
            "body": body,
        }
        by_id[icon_id] = record
        for alias in record["aliases"]:
            alias_of.setdefault(alias, icon_id)
    if not by_id:
        raise CatalogError("symbol catalogue has no valid icons")
    _CATALOG = {
        "path": path,
        "meta": {
            "library": str(data.get("library") or "Lucide Icons"),
            "version": str(data.get("version") or ""),
            "license": str(data.get("license") or "ISC"),
            "source": str(data.get("source") or ""),
        },
        "icons": by_id,
        "aliases": alias_of,
        "order": sorted(by_id),
    }
    return _CATALOG


def catalog_info():
    """Return the vendored library metadata (version, license, source)."""
    catalog = _load()
    return {
        **catalog["meta"],
        "count": len(catalog["icons"]),
        "alias_count": len(catalog["aliases"]),
        "path": str(catalog["path"]),
    }


def icon_ids():
    """Every canonical symbol id, sorted."""
    return list(_load()["order"])


def _score(record, terms, query):
    icon_id = record["id"]
    if icon_id == query:
        return 0
    if icon_id.startswith(query):
        return 1
    haystack = " ".join((icon_id, record["label"].lower(),
                         " ".join(record["aliases"]), " ".join(record["tags"])))
    if query in icon_id or query in record["label"].lower():
        rank = 2
    elif all(term in haystack for term in terms):
        rank = 3 if all(term in icon_id for term in terms) else 4
    else:
        return None
    return rank


def list_icons(query="", limit=DEFAULT_LIMIT, offset=0):
    """Search the catalogue; deterministic ranking, stable pagination.

    A query is matched against the id, label, aliases and tags. All whitespace
    separated terms must match (AND) so "arrow down" narrows rather than
    widens. Returns at most ``limit`` entries as ``{"id", "label"}``.
    """
    catalog = _load()
    text = str(query or "").strip().lower()
    terms = [term for term in re.split(r"\s+", text) if term]
    ranked = []
    for icon_id in catalog["order"]:
        record = catalog["icons"][icon_id]
        rank = 0 if not terms else _score(record, terms, text)
        if rank is None:
            continue
        ranked.append((rank, icon_id, record["label"]))
    ranked.sort()
    try:
        start = max(0, int(offset))
        count = max(0, min(MAX_LIMIT, int(limit)))
    except (TypeError, ValueError):
        raise ValueError("limit and offset must be integers")
    window = ranked[start:start + count]
    return [{"id": icon_id, "label": label} for _rank, icon_id, label in window]


def _record(icon_id):
    catalog = _load()
    key = str(icon_id or "").strip()
    if key in catalog["icons"]:
        return catalog["icons"][key]
    alias = catalog["aliases"].get(key)
    if alias:
        return catalog["icons"][alias]
    raise KeyError(f"unknown symbol {icon_id!r}")


def _color(value):
    color = str(value or "").strip()
    if not _COLOR_RE.match(color):
        raise ValueError(f"invalid colour {value!r}; expected #rgb/#rrggbb/#rrggbbaa")
    return color.lower()


def icon_svg(icon_id, color="#ffffff"):
    """Return one symbol as a self-contained, recoloured SVG document."""
    record = _record(icon_id)
    paint = _color(color)
    body = record["body"].replace('fill="currentColor"', f'fill="{paint}"') \
                          .replace('stroke="currentColor"', f'stroke="{paint}"')
    return _SVG_TEMPLATE.format(viewbox=VIEWBOX, color=paint, body=body).encode("utf-8")


def _cache_root(cache_dir):
    if cache_dir:
        return Path(cache_dir).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return Path(base) / "nautilus-extensions" / "folder-icons" / "symbols"


def materialize_icon(icon_id, color="#ffffff", cache_dir=None):
    """Write the recoloured symbol to the cache and return its absolute path.

    The filename derives from the canonical id and the colour, so repeated
    calls reuse one file. Writes are atomic and never touch folder metadata.
    """
    record = _record(icon_id)
    paint = _color(color)
    svg = icon_svg(record["id"], paint)
    digest = hashlib.sha256(svg).hexdigest()[:12]
    root = _cache_root(cache_dir)
    target = root / f"{record['id']}-{paint.lstrip('#')}-{digest}.svg"
    if target.is_file() and target.stat().st_size == len(svg):
        return str(target.resolve())
    root.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{record['id']}-", suffix=".svg.tmp", dir=str(root))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(svg)
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return str(target.resolve())
