"""Portable, layered SVG folder-icon projects (no GTK or theme imports).

``save_svg_project(base_png, layer_pngs, state, source_pngs=None)`` returns
an actual SVG icon: a base image followed by one full-canvas image per layer.
The caller renders transforms, masks and alpha *once*. ``state['layers']``
is top-first, but ``layer_pngs`` is painted bottom-to-top. Optional
``source_pngs`` are pre-transform content snapshots in top-first order; these
keep text usable without the original font, without distributing font files.

Editable state and content-addressed original images live in SVG metadata.
Import never applies an icon or changes folder metadata. It only writes to a
managed asset cache. Its additional ``_svg_project`` entry contains paths to
the frozen base/layers/sources and the remapped ``layer_states`` baseline.
An editor must not transform the full-canvas snapshots a second time.

Only explicitly known image fields are read/remapped, never arbitrary JSON
paths. Named emblems must first be resolved by the caller to ``emblem_uri``.
PNG metadata compatibility remains the editor's separate legacy loader.
"""

import base64
import binascii
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import unquote, urlsplit
import warnings
import xml.etree.ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
PROJECT_NS = "urn:nautilus-extensions:folder-icon-project:1"
PROJECT_FORMAT = "nautilus-folder-icon"
PROJECT_VERSION = 1
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 48 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_IMAGE_SIDE = 12000
MAX_IMAGE_PIXELS = 16_000_000
MAX_TOTAL_PIXELS = 64_000_000
MAX_ASSETS = 1024
MAX_LAYERS = 128
MAX_XML_NODES = 20000
MAX_XML_DEPTH = 64
MAX_JSON_DEPTH = 32

_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_REF_PREFIX = "asset:sha256:"
_FRAGMENT_RE = re.compile(r"#[\w.:-]+\Z", re.UNICODE)
_MIMES = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
    "GIF": ("image/gif", ".gif"),
    "BMP": ("image/bmp", ".bmp"),
    "TIFF": ("image/tiff", ".tiff"),
    "SVG": ("image/svg+xml", ".svg"),
}
_SUFFIXES = {mime: suffix for mime, suffix in _MIMES.values()}
_STATIC_TAGS = set("""svg g defs title desc metadata path rect circle ellipse
    line polyline polygon text tspan textPath a image use symbol switch
    linearGradient radialGradient stop clipPath mask pattern marker filter
    feBlend feColorMatrix feComponentTransfer feComposite feConvolveMatrix
    feDiffuseLighting feDisplacementMap feDistantLight feDropShadow feFlood
    feFuncA feFuncB feFuncG feFuncR feGaussianBlur feImage feMerge feMergeNode
    feMorphology feOffset fePointLight feSpecularLighting feSpotLight feTile
    feTurbulence style""".split())
_ACTIVE_TAGS = {"script", "foreignobject", "iframe", "object", "embed",
                "audio", "video", "set", "discard"}


class ProjectError(ValueError):
    """Malformed, unsafe, incomplete or oversized project/asset."""


class UnsupportedProjectError(ProjectError):
    """Project data exists but uses an unsupported format version."""


def _require(condition, message):
    if not condition:
        raise ProjectError(message)


def _json_bytes(value):
    try:
        data = json.dumps(value, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ProjectError("Project state must be finite UTF-8 JSON") from exc
    _require(len(data) <= MAX_METADATA_BYTES, "Project metadata is too large")
    _require(not any(char in data.decode("utf-8") for char in ("\ufffe", "\uffff")),
             "Metadata contains invalid XML characters")
    _check_json(value)
    return data


def _check_json(value, depth=0):
    _require(depth <= MAX_JSON_DEPTH, "Project metadata is too deeply nested")
    if isinstance(value, dict):
        for key, child in value.items():
            _require(isinstance(key, str), "Metadata object keys must be strings")
            _check_json(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_json(child, depth + 1)
    elif isinstance(value, float):
        _require(math.isfinite(value), "Non-finite metadata number")
    else:
        _require(value is None or isinstance(value, (str, bool, int)),
                 "Unsupported metadata value")


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate metadata key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ProjectError("Non-finite metadata number")


def _read_file(path, limit):
    """Bound reads, including FIFOs/devices and files changed after stat()."""
    try:
        fd = os.open(os.fspath(path), os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            _require(stat.S_ISREG(info.st_mode), "Only regular image files are allowed")
            _require(info.st_size <= limit, "File exceeds the byte limit")
            data = stream.read(limit + 1)
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, ProjectError):
            raise
        raise ProjectError("Cannot read project/image file") from exc
    _require(len(data) <= limit, "File exceeds the byte limit")
    return data


class _BoundedTree(ET.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = self.count = 0

    def start(self, tag, attrs):
        self.depth += 1
        self.count += 1
        _require(self.depth <= MAX_XML_DEPTH, "SVG is too deeply nested")
        _require(self.count <= MAX_XML_NODES, "SVG contains too many elements")
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)


def _parse_svg(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ProjectError("SVG must use UTF-8") from exc
    _require(not re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I),
             "SVG document types and entities are forbidden")
    _require(not re.search(r"<\?(?!xml(?:\s|\?>))", text, re.I),
             "SVG processing instructions are forbidden")
    declaration = re.match(r"\s*<\?xml\s+([^?]*)\?>", text)
    if declaration:
        encoding = re.search(r"encoding\s*=\s*['\"]([^'\"]+)", declaration[1])
        _require(not encoding or encoding[1].lower() in ("utf-8", "utf8"),
                 "SVG must declare UTF-8 encoding")
    try:
        root = ET.fromstring(text, parser=ET.XMLParser(target=_BoundedTree()))
    except (ET.ParseError, ValueError, RecursionError) as exc:
        if isinstance(exc, ProjectError):
            raise
        raise ProjectError("Malformed SVG") from exc
    _require(root.tag in ("svg", f"{{{SVG_NS}}}svg"), "Image is not an SVG")
    return root


def _local_name(name):
    return name.rsplit("}", 1)[-1]


def _dimensions(width, height):
    _require(all(math.isfinite(v) and 0 < v <= MAX_IMAGE_SIDE
                 for v in (width, height)), "Image dimensions exceed the limit")
    _require(width * height <= MAX_IMAGE_PIXELS, "Image pixel count exceeds the limit")
    return width, height


def _svg_size(root):
    viewbox = root.get("viewBox")
    if viewbox:
        try:
            parts = [float(v) for v in re.split(r"[\s,]+", viewbox.strip())]
        except ValueError as exc:
            raise ProjectError("Invalid SVG viewBox") from exc
        _require(len(parts) == 4 and all(math.isfinite(v) for v in parts),
                 "Invalid SVG viewBox")
        _dimensions(parts[2], parts[3])
    else:
        parts = [0, 0, 300, 150]
    factors = {"": 1, "px": 1, "pt": 96 / 72, "pc": 16,
               "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96,
               "em": 16, "ex": 8, "%": 0.01}
    size = []
    for key, fallback in zip(("width", "height"), parts[2:]):
        value = root.get(key)
        if value is None:
            size.append(fallback)
            continue
        match = re.fullmatch(r"\s*(\d+(?:\.\d*)?|\.\d+)\s*([a-z%]*)\s*", value)
        _require(match and match[2] in factors, "Unsupported SVG dimensions")
        number = float(match[1]) * factors[match[2]]
        size.append(number * fallback if match[2] == "%" else number)
    return _dimensions(*size)


def _safe_css(text):
    """Allow local paint references, not imports, escapes, fonts or URLs."""
    _require(not any(token in text for token in ("@", "\\", "/*", "*/")),
             "Unsafe SVG CSS")
    _require(not re.search(r"expression|javascript|vbscript|behavior|-moz-binding", text, re.I),
             "Unsafe SVG CSS")
    without_urls = re.sub(r"url\(\s*(['\"]?)(#[\w.:-]+)\1\s*\)", "", text, flags=re.I)
    _require(not re.search(r"url\s*\(|(?:https?|file|ftp|data):|//", without_urls, re.I),
             "External SVG CSS reference")


def _decode64(text, limit=MAX_ASSET_BYTES):
    _require(isinstance(text, str) and len(text) <= ((limit + 2) // 3) * 4,
             "Encoded asset exceeds the byte limit")
    try:
        data = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ProjectError("Invalid base64 image data") from exc
    _require(len(data) <= limit, "Asset exceeds the byte limit")
    return data


def _data_uri(uri):
    match = re.fullmatch(r"data:(image/[a-z+]+);base64,([A-Za-z0-9+/=]*)", uri)
    _require(match is not None, "Only embedded base64 image URLs are allowed")
    _require(match[1] in _SUFFIXES and match[1] != "image/svg+xml",
             "Nested SVG data URLs are forbidden")
    return match[1], _decode64(match[2], MAX_ASSET_BYTES)


def _validate_svg(root, pool):
    ids, references = {}, []
    for node in root.iter():
        name = _local_name(node.tag)
        lower = name.lower()
        _require(lower not in _ACTIVE_TAGS and not lower.startswith("animate"),
                 "Active SVG content is forbidden")
        if node.tag.startswith(f"{{{SVG_NS}}}") or "}" not in node.tag:
            _require(name in _STATIC_TAGS, "Unsupported SVG element")
        if name == "style":
            _safe_css("".join(node.itertext()))
        if node.get("id") is not None:
            _require(node.get("id") not in ids, "Duplicate SVG id")
            ids[node.get("id")] = node
        for attr, value in node.attrib.items():
            key = _local_name(attr).lower()
            _require(not key.startswith("on") and key not in ("base", "absref", "export-filename"),
                     "SVG events and base/path references are forbidden")
            if key in ("href", "src"):
                if _FRAGMENT_RE.fullmatch(value):
                    references.append((node, value[1:]))
                else:
                    mime, data = _data_uri(value)
                    pool.add(data, mime)
            if key == "style" or re.search(r"url\s*\(|[\\@]", value, re.I):
                _safe_css(value)
                references.extend((node, match[1]) for match in re.finditer(
                    r"url\(\s*['\"]?#([\w.:-]+)", value, re.I))
            _require("\\" not in value or key not in ("href", "src"),
                     "SVG path references are forbidden")
    # A small source SVG can otherwise expand into millions of <use> nodes.
    targets = {}
    for node, target in references:
        if target in ids:
            targets.setdefault(id(node), []).append(ids[target])
    visiting, costs = set(), {}

    def cost(node):
        ident = id(node)
        _require(len(visiting) < MAX_XML_DEPTH and ident not in visiting,
                 "Recursive SVG references are forbidden")
        if ident in costs:
            return costs[ident]
        visiting.add(ident)
        total, height = 1, 1
        for child in [*node, *targets.get(ident, [])]:
            child_cost, child_height = cost(child)
            total += child_cost
            height = max(height, child_height + 1)
            _require(total <= MAX_XML_NODES, "Expanded SVG exceeds the element limit")
        _require(total <= MAX_XML_NODES, "Expanded SVG exceeds the element limit")
        _require(height <= MAX_XML_DEPTH, "Expanded SVG exceeds the depth limit")
        visiting.remove(ident)
        costs[ident] = total, height
        return total, height

    cost(root)


def _raster_kind(data):
    """Classify real bytes, never delegate unknown input to another decoder.

    In particular, do not inflate SVGZ/gzip or let a renderer auto-detect
    UTF-16/32 XML after the UTF-8 SVG safety checks have been bypassed.
    """
    if data.startswith(b"\x1f\x8b"):
        raise UnsupportedProjectError("Compressed gzip/SVGZ images are not supported")
    for signature, kind in ((b"\x89PNG\r\n\x1a\n", "PNG"), (b"\xff\xd8\xff", "JPEG"),
                            (b"GIF87a", "GIF"), (b"GIF89a", "GIF"), (b"BM", "BMP"),
                            (b"II*\x00", "TIFF"), (b"MM\x00*", "TIFF")):
        if data.startswith(signature):
            return kind
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "WEBP"
    if data.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")) or b"\x00" in data:
        raise UnsupportedProjectError("Unsupported binary or non-UTF-8 image format")
    if data.removeprefix(b"\xef\xbb\xbf").lstrip(b" \t\r\n").startswith(b"<"):
        return "SVG"
    raise UnsupportedProjectError("Unsupported or unrecognized image format")


class _Assets:
    """One bounded, MIME-verified, content-addressed asset registry."""

    def __init__(self):
        self.items = {}
        self.sizes = {}
        self.bytes = self.pixels = 0

    def add(self, data, mime=None):
        _require(isinstance(data, bytes) and 0 < len(data) <= MAX_ASSET_BYTES,
                 "Invalid or oversized image asset")
        digest = hashlib.sha256(data).hexdigest()
        if digest in self.items:
            _require(mime is None or mime == self.items[digest][0], "Asset MIME mismatch")
            return digest
        _require(len(self.items) < MAX_ASSETS, "Too many embedded assets")
        kind = _raster_kind(data)
        actual_mime = _MIMES[kind][0]
        _require(mime is None or mime == actual_mime, "Asset MIME mismatch")
        self.bytes += len(data)
        _require(self.bytes <= MAX_TOTAL_ASSET_BYTES, "Total asset bytes exceed the limit")
        if kind == "SVG":
            root = _parse_svg(data)
            width, height = _svg_size(root)
            _validate_svg(root, self)
        else:
            try:
                from PIL import Image
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(data), formats=[kind]) as image:
                        width, height = _dimensions(*image.size)
                        _require(getattr(image, "n_frames", 1) == 1,
                                 "Animated/multipage images are not supported")
                        image.verify()
                    with Image.open(io.BytesIO(data), formats=[kind]) as image:
                        image.load()
            except ProjectError:
                raise
            except Exception as exc:
                raise ProjectError("Invalid or undecodable image asset") from exc
        self.pixels += width * height
        _require(self.pixels <= MAX_TOTAL_PIXELS, "Total asset pixels exceed the limit")
        _require(len(self.items) < MAX_ASSETS, "Too many embedded assets")
        self.items[digest] = (actual_mime, data)
        self.sizes[digest] = (width, height)
        return digest


def _state_blocks(state):
    _require(isinstance(state, dict), "Project state must be an object")
    yield state
    scopes = state.get("scopes", {})
    _require(isinstance(scopes, dict), "Project scopes must be an object")
    _require(set(scopes) <= {"folder", "global"}, "Unknown project scope")
    for scope in scopes.values():
        _require(isinstance(scope, dict), "Invalid scope state")
        yield scope


def _asset_fields(state):
    """The sole allowlist of file-bearing fields; no JSON-path interpreter."""
    for block in _state_blocks(state):
        for key in ("base_image", "base_image_path"):
            if key in block:
                yield block, key
        layers = block.get("layers", [])
        _require(isinstance(layers, list) and len(layers) <= MAX_LAYERS,
                 "Invalid or oversized layer list")
        for layer in layers:
            _require(isinstance(layer, dict), "Layer state must be an object")
            for key in ("path", "mask_path", "emblem_uri"):
                if key in layer:
                    yield layer, key
            emblem = layer.get("emblem", "")
            _require(isinstance(emblem, str), "Emblem name must be text")
            if emblem.startswith((_REF_PREFIX, "/", "./", "../", "file:")):
                yield layer, "emblem"
            else:
                _require(not any(char in emblem for char in ("/", "\\", ":")),
                         "External emblem references are forbidden")
                if layer.get("type") == "emblem" and emblem:
                    _require(bool(layer.get("emblem_uri")), "Resolve named emblems to emblem_uri before saving")


def _asset_path(value):
    _require(isinstance(value, str) and "\x00" not in value, "Invalid image path")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ProjectError("Invalid image path") from exc
    if parsed.scheme:
        _require(parsed.scheme == "file" and parsed.netloc in ("", "localhost")
                 and not parsed.query and not parsed.fragment, "Only local image paths are allowed")
        return unquote(parsed.path)
    _require(not parsed.netloc, "Remote image paths are forbidden")
    return value


def _snapshot_ids(pool, snapshots, count, size, *, optional=False):
    if snapshots is None and optional:
        return [None] * count
    _require(isinstance(snapshots, (list, tuple)) and len(snapshots) == count,
             "Snapshot count must match the top-first state layer count")
    result = []
    for png in snapshots:
        if png is None and optional:
            result.append(None)
            continue
        digest = pool.add(png, "image/png")
        _require(optional or pool.sizes[digest] == size, "Layer snapshots must use the full canvas")
        result.append(digest)
    return result


def save_svg_project(base_png, layer_pngs, state, *, source_pngs=None):
    """Return a self-contained layered SVG icon, or raise ``ProjectError``.

    State is JSON-compatible and already normalized by the caller. Every
    field is retained, except the transient import-only ``_svg_project``.
    Original asset bytes are never resized or re-encoded on round trips.
    """
    _json_bytes(state)
    clean = copy.deepcopy(state)
    for block in _state_blocks(clean):
        block.pop("_svg_project", None)
    fields = list(_asset_fields(clean))
    pool = _Assets()
    base = pool.add(base_png, "image/png")
    size = pool.sizes[base]
    count = len(clean.get("layers", []))
    _require(count <= MAX_LAYERS, "Too many layers")
    layers = _snapshot_ids(pool, layer_pngs, count, size)
    sources = _snapshot_ids(pool, source_pngs, count, size, optional=True)
    for container, key in fields:
        value = container[key]
        _require(isinstance(value, str), "Image paths must be strings")
        if value:
            data = _read_file(_asset_path(value), MAX_ASSET_BYTES)
            container[key] = _REF_PREFIX + pool.add(data)
    payload = {"format": PROJECT_FORMAT, "version": PROJECT_VERSION, "state": clean,
               "render": {"base": base, "layers": layers, "sources": sources}}
    meta = _json_bytes(payload).decode("utf-8")
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    ET.register_namespace("fcr", PROJECT_NS)
    width, height = (str(int(v)) for v in size)
    root = ET.Element(f"{{{SVG_NS}}}svg", {"width": width, "height": height,
                      "viewBox": f"0 0 {width} {height}", "version": "1.1"})
    metadata = ET.SubElement(root, f"{{{SVG_NS}}}metadata")
    project = ET.SubElement(metadata, f"{{{PROJECT_NS}}}project",
                            {"version": str(PROJECT_VERSION)})
    project.text = meta
    assets = ET.SubElement(metadata, f"{{{PROJECT_NS}}}assets")
    visible = {base, *layers}
    for digest, (mime, data) in sorted(pool.items.items()):
        if digest not in visible:
            node = ET.SubElement(assets, f"{{{PROJECT_NS}}}asset",
                                 {"sha256": digest, "mime": mime})
            node.text = base64.b64encode(data).decode("ascii")
    stack = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": "folder-icon-layers"})
    for index, digest in enumerate([base, *layers]):
        mime, data = pool.items[digest]
        attrs = {"id": "base" if index == 0 else f"layer-{index - 1}",
                 "x": "0", "y": "0", "width": width, "height": height,
                 "preserveAspectRatio": "none", f"{{{PROJECT_NS}}}sha256": digest,
                 f"{{{XLINK_NS}}}href": f"data:{mime};base64," + base64.b64encode(data).decode("ascii")}
        ET.SubElement(stack, f"{{{SVG_NS}}}image", attrs)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _require(len(data) <= MAX_FILE_BYTES, "SVG project exceeds the file byte limit")
    return data


def _digest(value):
    _require(isinstance(value, str) and _HASH_RE.fullmatch(value), "Invalid asset hash")
    return value


def _project_payload(project):
    _require(not list(project) and isinstance(project.text, str), "Invalid project metadata")
    encoded = project.text.encode("utf-8")
    _require(len(encoded) <= MAX_METADATA_BYTES, "Project metadata is too large")
    try:
        payload = json.loads(project.text, object_pairs_hook=_json_object,
                             parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ProjectError):
            raise
        raise ProjectError("Malformed project metadata JSON") from exc
    _json_bytes(payload)
    _require(isinstance(payload, dict) and payload.get("format") == PROJECT_FORMAT,
             "Invalid project format")
    if project.get("version") != str(PROJECT_VERSION) or type(payload.get("version")) is not int or payload["version"] != PROJECT_VERSION:
        raise UnsupportedProjectError("Unsupported SVG project version")
    return payload


def _project_assets(root, payload, pool):
    """Validate the complete project grammar, not just the metadata payload."""
    _require(set(root.attrib) == {"width", "height", "viewBox", "version"}, "Unexpected SVG project attributes")
    _require(len(root) == 2, "Unexpected SVG project content")
    metadata, stack = list(root)
    _require(metadata.tag == f"{{{SVG_NS}}}metadata" and not metadata.attrib,
             "Invalid SVG metadata container")
    _require(len(metadata) == 2, "Invalid SVG metadata contents")
    project, assets = list(metadata)
    _require(project.tag == f"{{{PROJECT_NS}}}project" and set(project.attrib) == {"version"}, "Invalid project metadata element")
    _require(assets.tag == f"{{{PROJECT_NS}}}assets" and not assets.attrib, "Invalid embedded asset table")
    declared = set()
    for node in assets:
        _require(node.tag == f"{{{PROJECT_NS}}}asset" and not list(node)
                 and set(node.attrib) == {"sha256", "mime"}, "Invalid asset entry")
        digest = _digest(node.get("sha256"))
        _require(digest not in declared, "Duplicate embedded asset")
        declared.add(digest)
        _require(pool.add(_decode64(node.text or "", MAX_ASSET_BYTES), node.get("mime")) == digest, "Embedded asset hash mismatch")
    render = payload.get("render")
    _require(isinstance(render, dict) and set(render) == {"base", "layers", "sources"}, "Invalid render manifest")
    _digest(render["base"])
    count = len(payload.get("state", {}).get("layers", [])) if isinstance(payload.get("state"), dict) else -1
    _require(0 <= count <= MAX_LAYERS, "Invalid project layer count")
    _require(all(isinstance(render[key], list) and len(render[key]) == count for key in ("layers", "sources")), "Render manifest layer count mismatch")
    for digest in render["layers"] + [value for value in render["sources"] if value is not None]:
        _digest(digest)
    expected = [render["base"], *render["layers"]]
    _require(stack.tag == f"{{{SVG_NS}}}g" and stack.attrib == {"id": "folder-icon-layers"}
             and len(stack) == len(expected), "Invalid rendered SVG layer stack")
    for index, (node, digest) in enumerate(zip(stack, expected)):
        attrs = {"id": "base" if index == 0 else f"layer-{index - 1}",
                 "x": "0", "y": "0", "width": root.get("width"), "height": root.get("height"),
                 "preserveAspectRatio": "none", f"{{{PROJECT_NS}}}sha256": digest}
        _require(node.tag == f"{{{SVG_NS}}}image" and not list(node)
                 and set(node.attrib) == {*attrs, f"{{{XLINK_NS}}}href"}
                 and all(node.get(key) == value for key, value in attrs.items()), "Invalid rendered SVG image")
        mime, data = _data_uri(node.get(f"{{{XLINK_NS}}}href"))
        _require(mime == "image/png" and pool.add(data, mime) == digest, "Rendered image hash/MIME mismatch")
    size = pool.sizes[render["base"]]
    width, height = (str(int(v)) for v in size)
    _require(root.get("width") == width and root.get("height") == height
             and root.get("viewBox") == f"0 0 {width} {height}", "SVG canvas differs from snapshots")
    for digest in expected:
        _require(pool.sizes[digest] == size, "Snapshot canvas mismatch")
    for digest in render["sources"]:
        if digest is not None:
            _require(digest in pool.items and pool.items[digest][0] == "image/png", "Missing or invalid source snapshot")
    return render


def _cache_root(asset_dir):
    if asset_dir is None:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        asset_dir = Path(base) / "nautilus-extensions" / "folder-icon-projects"
    root = Path(asset_dir).expanduser().absolute()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _require(not root.is_symlink() and root.is_dir(), "Asset cache must be a real directory")
    return root


def _atomic_write(path, data):
    """Replace one explicit destination; never follow the destination link."""
    path = Path(path)
    _require(not path.is_symlink(), "Refusing to replace a symlink")
    fd, temporary = tempfile.mkstemp(prefix=".folder-icon-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_svg_project(path, svg_bytes):
    """Atomically write bytes produced by ``save_svg_project``.

    Overwrite confirmation belongs to the caller. This writer never creates
    destination directories, changes folder metadata, or installs icons.
    """
    _require(isinstance(svg_bytes, bytes) and len(svg_bytes) <= MAX_FILE_BYTES,
             "Invalid or oversized SVG output")
    _atomic_write(path, svg_bytes)


def load_svg_project(path, asset_dir=None):
    """Return editable state plus frozen-render paths, or ``None``.

    ``None`` means a validated safe plain SVG or supported static raster
    image (legacy PNG metadata is handled by the caller). Unknown formats,
    compressed SVGZ/gzip, non-UTF-8 XML and malformed/unsafe images raise
    ``ProjectError`` and must *not* be retried as plain image imports.
    The entire document and every asset are validated before cache writes.
    """
    data = _read_file(path, MAX_FILE_BYTES)
    kind = _raster_kind(data)
    if kind != "SVG":
        _Assets().add(data, _MIMES[kind][0])
        return None
    root = _parse_svg(data)
    projects = [node for node in root.iter() if node.tag == f"{{{PROJECT_NS}}}project"]
    foreign_projects = [node for node in root.iter() if _local_name(node.tag) == "project" and "folder-icon-project" in node.tag]
    if not projects:
        if foreign_projects:
            raise UnsupportedProjectError("Unsupported SVG project namespace")
        _validate_svg(root, _Assets())
        _svg_size(root)
        return None
    _require(len(projects) == 1 and len(foreign_projects) == 1, "Duplicate project metadata")
    payload = _project_payload(projects[0])
    state = payload.get("state")
    # Validate the state shape and every path reference before writing assets.
    fields = list(_asset_fields(state))
    for block in _state_blocks(state):
        _require("_svg_project" not in block, "Transient snapshot paths cannot be embedded in state")
    pool = _Assets()
    render = _project_assets(root, payload, pool)
    refs = []
    for container, key in fields:
        value = container[key]
        _require(isinstance(value, str), "Invalid project image reference")
        if value:
            _require(value.startswith(_REF_PREFIX), "External project image path")
            digest = _digest(value[len(_REF_PREFIX):])
            _require(digest in pool.items, "Missing embedded source asset")
            refs.append((container, key, digest))
    root_dir = _cache_root(asset_dir)
    paths = {}
    for digest, (mime, blob) in pool.items.items():
        destination = root_dir / (digest + _SUFFIXES[mime])
        _require(not destination.is_symlink(), "Asset cache entry is a symlink")
        if not destination.exists() or _read_file(destination, MAX_ASSET_BYTES) != blob:
            _atomic_write(destination, blob)
        paths[digest] = str(destination)
    for container, key, digest in refs:
        container[key] = paths[digest]
    state["_svg_project"] = {
        "version": PROJECT_VERSION,
        "base_png": paths[render["base"]],
        "layer_pngs": [paths[digest] for digest in render["layers"]],
        "source_pngs": [paths[digest] if digest else None for digest in render["sources"]],
        "layer_states": copy.deepcopy(state.get("layers", [])),
    }
    return state
