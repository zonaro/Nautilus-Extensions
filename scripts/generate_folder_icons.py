"""Vendor the Lucide monochrome symbol set into ``assets/folder-icons``.

Run by hand, offline afterwards, standard library only:

    python3 scripts/generate_folder_icons.py [--archive PATH]

The archive is the official ``lucide-static`` npm tarball, checked against the
pinned SRI digest below before a single byte is read from it. Output is
deterministic: ``catalog.json``, ``manifest.json`` and ``LICENSE``.

Nothing here ships at runtime: ``folder_icon_catalog.py`` only reads the
generated ``catalog.json``.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

VERSION = "1.69.0"
PACKAGE = "lucide-static"
LICENSE = "ISC"
SOURCE = "https://github.com/lucide-icons/lucide"
TARBALL_URL = f"https://registry.npmjs.org/{PACKAGE}/-/{PACKAGE}-{VERSION}.tgz"
TARBALL_SHA512 = (
    "n51UItv/qDzvu/UQixn0eSkp3hXppIJg0sRvtltb+rEO0XH2tyqFmtLsaUWu3SiAD0/"
    "7NHj/LH0eJlJJL5F4Ew=="
)
TARBALL_SHA256 = (
    "fc9981e0cac51a0baeaaacf669b6faaa0fbd2427df1b46609a858b6a75df6617"
)
TARBALL_SHASUM = "8dd7fb512b566495b79af1f735a18b05ef2ecd8a"

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "assets" / "folder-icons"

LICENSE_TEXT = """\
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

# Lucide artwork uses only these shapes. Anything else aborts the build rather
# than silently entering the vendored catalogue.
ALLOWED_TAGS = {"path", "circle", "rect", "line", "ellipse", "polyline", "polygon"}
ALLOWED_ATTRS = {"d", "cx", "cy", "r", "x", "y", "width", "height", "rx", "ry",
                 "x1", "x2", "y1", "y2", "points", "transform", "fill", "stroke"}
ALLOWED_PAINTS = {"none", "currentColor"}
_PAINT_RE = re.compile(r"#[0-9a-fA-F]{3,8}\Z")
_TAG_RE = re.compile(r"<([a-zA-Z][\w:-]*)((?:\s[^<>]*?)?)\s*/?>")
_ATTR_RE = re.compile(r"([a-zA-Z:_-][\w:.-]*)\s*=\s*\"([^\"]*)\"")
_FORBIDDEN = re.compile(r"<!|<\?|javascript:|url\(|href|on[a-z]+\s*=", re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)


class BuildError(RuntimeError):
    """The pinned archive does not match its expected shape or digest."""


def verify_archive(data):
    """Reject anything that is not the exact pinned npm tarball."""
    digest512 = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if digest512 != TARBALL_SHA512:
        raise BuildError("tarball sha512 mismatch; refusing to vendor unknown art")
    if hashlib.sha256(data).hexdigest() != TARBALL_SHA256:
        raise BuildError("tarball sha256 mismatch")
    if hashlib.sha1(data).hexdigest() != TARBALL_SHASUM:
        raise BuildError("tarball sha1 mismatch")


def sanitize_body(icon_id, inner):
    """Validate and normalise one icon's inner markup."""
    if _FORBIDDEN.search(inner):
        raise BuildError(f"{icon_id}: active or external markup")
    body = " ".join(inner.split())
    position = 0
    out = []
    for match in _TAG_RE.finditer(body):
        if match.start() != position:
            leftover = body[position:match.start()].strip()
            if leftover:
                raise BuildError(f"{icon_id}: unexpected markup {leftover[:40]!r}")
        tag = match.group(1)
        if tag not in ALLOWED_TAGS:
            raise BuildError(f"{icon_id}: unsupported element <{tag}>")
        attrs = dict(_ATTR_RE.findall(match.group(2) or ""))
        unexpected = set(attrs) - ALLOWED_ATTRS
        if unexpected:
            raise BuildError(f"{icon_id}: unsupported attributes {sorted(unexpected)}")
        for name in ("fill", "stroke"):
            if name in attrs and attrs[name] not in ALLOWED_PAINTS \
                    and not _PAINT_RE.match(attrs[name]):
                raise BuildError(f"{icon_id}: unsupported {name} paint")
        out.append("<%s%s/>" % (tag, "".join(
            f' {name}="{value}"' for name, value in sorted(attrs.items()))))
        position = match.end()
    if body[position:].strip():
        raise BuildError(f"{icon_id}: trailing markup")
    if not out:
        raise BuildError(f"{icon_id}: empty artwork")
    return "".join(out)


def build(archive):
    data = Path(archive).read_bytes()
    verify_archive(data)
    tags = {}
    bodies = {}      # sha256(body) -> body
    canonical = {}   # sha256(body) -> first icon id
    aliases = {}     # canonical id -> alias ids
    order = []
    with tarfile.open(fileobj=__import__("io").BytesIO(data)) as tar:
        try:
            tags = json.loads(tar.extractfile("package/tags.json").read())
        except KeyError:
            tags = {}
        for member in sorted(tar.getmembers(), key=lambda m: m.name):
            name = member.name
            if not (name.startswith("package/icons/") and name.endswith(".svg")):
                continue
            icon_id = name[len("package/icons/"):-len(".svg")]
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", icon_id):
                raise BuildError(f"unexpected icon filename {name!r}")
            raw = tar.extractfile(member).read().decode("utf-8")
            match = re.search(r"<svg\b[^>]*>(.*)</svg>", _COMMENT.sub("", raw), re.S)
            if not match:
                raise BuildError(f"{icon_id}: no svg root")
            body = sanitize_body(icon_id, match.group(1))
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if digest in bodies:
                aliases.setdefault(canonical[digest], []).append(icon_id)
                continue
            bodies[digest] = body
            canonical[digest] = icon_id
            order.append(icon_id)

    digest_of = {icon_id: digest for digest, icon_id in canonical.items()}
    icons = []
    for icon_id in order:
        entry_tags = [str(t) for t in tags.get(icon_id, []) if isinstance(t, str)][:24]
        alias_list = sorted(aliases.get(icon_id, []))
        for alias in alias_list:
            entry_tags.extend(str(t) for t in tags.get(alias, []) if isinstance(t, str))
        icons.append({
            "id": icon_id,
            "label": " ".join(part.capitalize() for part in icon_id.split("-")),
            "aliases": alias_list,
            "tags": sorted(dict.fromkeys(entry_tags))[:32],
            "body": bodies[digest_of[icon_id]],
        })
    icons.sort(key=lambda entry: entry["id"])

    catalog = {
        "schema": 1,
        "library": "Lucide Icons",
        "package": PACKAGE,
        "version": VERSION,
        "license": LICENSE,
        "source": SOURCE,
        "tarball": TARBALL_URL,
        "icons": icons,
    }
    manifest = {
        "library": "Lucide Icons",
        "package": PACKAGE,
        "version": VERSION,
        "license": LICENSE,
        "source": SOURCE,
        "tarball_url": TARBALL_URL,
        "tarball_sha512": TARBALL_SHA512,
        "tarball_sha256": TARBALL_SHA256,
        "tarball_shasum": TARBALL_SHASUM,
        "icon_count": len(icons),
        "alias_count": sum(len(entry["aliases"]) for entry in icons),
        "notice_text": LICENSE_TEXT,
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "catalog.json").write_text(
        json.dumps(catalog, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8")
    (ARTIFACTS / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ARTIFACTS / "LICENSE").write_text(LICENSE_TEXT, encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default="/tmp/opencode/lucide-static-1.69.0.tgz")
    args = parser.parse_args()
    try:
        result = build(args.archive)
    except BuildError as error:
        sys.exit(f"build failed: {error}")
    print("wrote %d icons (%d aliases) from %s %s"
          % (result["icon_count"], result["alias_count"], PACKAGE, VERSION))
