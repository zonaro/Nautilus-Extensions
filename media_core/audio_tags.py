# -*- coding: utf-8 -*-
#
# Media Core - Audio Tag Reading/Writing (ID3, MP4, Vorbis, FLAC + covers)
#
# GTK-free. Optional dependency: mutagen (pip / python3-mutagen).
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from pathlib import Path

SUPPORTED_EXTS: frozenset[str] = frozenset(
    {".mp3", ".m4a", ".m4b", ".ogg", ".oga", ".opus", ".flac"})

FIELDS: tuple[str, ...] = (
    "title", "artist", "album", "albumartist", "genre", "date",
    "composer", "comment", "track", "tracktotal", "disc",
)

COVER_MIMES: tuple[str, str] = ("image/jpeg", "image/png")


def mutagen_available() -> bool:
    try:
        import mutagen  # noqa: F401
        return True
    except Exception:
        return False


def can_edit(path: str | Path) -> bool:
    if not mutagen_available():
        return False
    return Path(path).suffix.lower() in SUPPORTED_EXTS


def blank_tags() -> dict[str, str]:
    return {f: "" for f in FIELDS}


def read_tags(path: str | Path) -> dict[str, str]:
    """All fields as strings; missing/unsupported -> blank_tags()."""
    tags = blank_tags()
    try:
        ext = Path(path).suffix.lower()
        if ext == ".mp3":
            _read_mp3(str(path), tags)
        elif ext in (".m4a", ".m4b"):
            _read_mp4(str(path), tags)
        elif ext in (".ogg", ".oga", ".opus"):
            _read_vorbis(str(path), tags)
        elif ext == ".flac":
            _read_flac(str(path), tags)
    except Exception:
        pass
    return tags


def read_cover(path: str | Path) -> tuple[str, bytes] | None:
    """(mime, data) of the front cover, or None."""
    try:
        ext = Path(path).suffix.lower()
        if ext == ".mp3":
            return _read_mp3_cover(str(path))
        if ext in (".m4a", ".m4b"):
            return _read_mp4_cover(str(path))
        if ext in (".ogg", ".oga", ".opus"):
            return _read_vorbis_cover(str(path))
        if ext == ".flac":
            return _read_flac_cover(str(path))
    except Exception:
        pass
    return None


def write_tags(path: str | Path, tags: dict[str, str] | None = None,
               cover: tuple | None = None) -> None:
    """Write given fields (\"\" clears that field) and apply cover action.

    cover: None or ("keep",) -> untouched; ("remove",) -> delete;
    ("set", mime, data) -> replace with the given JPEG/PNG image.
    Raises ValueError for unsupported files, RuntimeError without mutagen.
    """
    from mutagen import MutagenError  # noqa: F401 (ensures importable)
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported audio type: {ext}")
    tags = tags or {}
    cover = cover or ("keep",)
    if ext == ".mp3":
        _write_mp3(str(path), tags, cover)
    elif ext in (".m4a", ".m4b"):
        _write_mp4(str(path), tags, cover)
    elif ext in (".ogg", ".oga", ".opus"):
        _write_vorbis(str(path), tags, cover)
    elif ext == ".flac":
        _write_flac(str(path), tags, cover)


# -- MP3 (ID3) ---------------------------------------------------------------
_MP3_TEXT = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "albumartist": "TPE2",
    "genre": "TCON",
    "date": "TDRC",
    "composer": "TCOM",
}


def _mp3_or_add(path: str):
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3
    try:
        audio = MP3(path, ID3=ID3)
    except Exception:
        audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    return audio


def _read_mp3(path: str, tags: dict) -> None:
    audio = _mp3_or_add(path)
    for field, frame in _MP3_TEXT.items():
        if frame in audio.tags:
            try:
                tags[field] = str(audio.tags[frame].text[0])
            except (IndexError, AttributeError):
                pass
    if "TRCK" in audio.tags:
        try:
            parts = str(audio.tags["TRCK"].text[0]).split("/", 1)
            tags["track"] = parts[0].strip()
            if len(parts) > 1:
                tags["tracktotal"] = parts[1].strip()
        except (IndexError, AttributeError):
            pass
    if "TPOS" in audio.tags:
        try:
            tags["disc"] = str(audio.tags["TPOS"].text[0]).split("/", 1)[0].strip()
        except (IndexError, AttributeError):
            pass
    for comm in audio.tags.getall("COMM"):
        try:
            if comm.text and comm.text[0]:
                tags["comment"] = str(comm.text[0])
                break
        except AttributeError:
            continue


def _read_mp3_cover(path: str) -> tuple[str, bytes] | None:
    audio = _mp3_or_add(path)
    for apic in audio.tags.getall("APIC"):
        try:
            if apic.data:
                return (apic.mime or "image/jpeg", bytes(apic.data))
        except AttributeError:
            continue
    return None


def _write_mp3(path: str, tags: dict, cover: tuple) -> None:
    from mutagen.id3 import TIT2, TPE1, TALB, TPE2, TCON, TDRC, TCOM, TRCK, TPOS, COMM, APIC

    audio = _mp3_or_add(path)
    makers = {"title": TIT2, "artist": TPE1, "album": TALB,
              "albumartist": TPE2, "genre": TCON, "date": TDRC,
              "composer": TCOM}
    for field, maker in makers.items():
        if field not in tags:
            continue
        frame = _MP3_TEXT[field]
        try:
            del audio.tags[frame]
        except KeyError:
            pass
        if tags[field]:
            audio.tags.add(maker(encoding=3, text=str(tags[field])))
    if "track" in tags or "tracktotal" in tags:
        try:
            cur = str(audio.tags["TRCK"].text[0]).split("/", 1)
        except (KeyError, IndexError, AttributeError):
            cur = ["", ""]
        n = tags.get("track", cur[0] if len(cur) > 0 else "")
        t = tags.get("tracktotal", cur[1] if len(cur) > 1 else "")
        try:
            del audio.tags["TRCK"]
        except KeyError:
            pass
        if n or t:
            audio.tags.add(TRCK(encoding=3, text=f"{n}/{t}" if t else f"{n}"))
    if "disc" in tags:
        try:
            del audio.tags["TPOS"]
        except KeyError:
            pass
        if tags["disc"]:
            audio.tags.add(TPOS(encoding=3, text=str(tags["disc"])))
    if "comment" in tags:
        audio.tags.delall("COMM")
        if tags["comment"]:
            audio.tags.add(COMM(encoding=3, lang="eng", desc="",
                                text=str(tags["comment"])))
    if cover and cover[0] == "remove":
        audio.tags.delall("APIC")
    elif cover and cover[0] == "set":
        _, mime, data = cover
        if mime not in COVER_MIMES:
            raise ValueError(f"Cover must be JPEG or PNG, got: {mime}")
        audio.tags.delall("APIC")
        audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc="",
                            data=bytes(data)))
    audio.save()


# -- MP4 / M4A ----------------------------------------------------------------
_MP4_TEXT = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "albumartist": "aART",
    "genre": "\xa9gen",
    "date": "\xa9day",
    "composer": "\xa9wrt",
    "comment": "\xa9cmt",
}


def _read_mp4(path: str, tags: dict) -> None:
    from mutagen.mp4 import MP4
    audio = MP4(path)
    if audio.tags is None:
        return
    for field, key in _MP4_TEXT.items():
        if key in audio.tags and audio.tags[key]:
            try:
                tags[field] = str(audio.tags[key][0])
            except (IndexError, AttributeError):
                pass
    if "trkn" in audio.tags and audio.tags["trkn"]:
        try:
            n, total = audio.tags["trkn"][0]
            tags["track"] = str(n) if n else ""
            tags["tracktotal"] = str(total) if total else ""
        except (IndexError, TypeError, ValueError):
            pass
    if "disk" in audio.tags and audio.tags["disk"]:
        try:
            tags["disc"] = str(audio.tags["disk"][0][0] or "")
        except (IndexError, TypeError):
            pass


def _read_mp4_cover(path: str) -> tuple[str, bytes] | None:
    from mutagen.mp4 import MP4, MP4Cover
    audio = MP4(path)
    if audio.tags is None or "covr" not in audio.tags:
        return None
    for cov in audio.tags["covr"]:
        try:
            data = bytes(cov)
        except TypeError:
            continue
        mime = ("image/png" if cov.imageformat == MP4Cover.FORMAT_PNG
                else "image/jpeg")
        if data:
            return (mime, data)
    return None


def _write_mp4(path: str, tags: dict, cover: tuple) -> None:
    from mutagen.mp4 import MP4, MP4Cover
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    for field, key in _MP4_TEXT.items():
        if field not in tags:
            continue
        if key in audio.tags:
            del audio.tags[key]
        if tags[field]:
            audio.tags[key] = [str(tags[field])]
    if "track" in tags or "tracktotal" in tags:
        n, total = 0, 0
        try:
            n, total = audio.tags["trkn"][0]
        except (KeyError, IndexError, TypeError):
            pass
        if "track" in tags:
            n = int(tags["track"]) if str(tags["track"]).strip().isdigit() else 0
        if "tracktotal" in tags:
            total = (int(tags["tracktotal"])
                     if str(tags["tracktotal"]).strip().isdigit() else 0)
        if "trkn" in audio.tags:
            del audio.tags["trkn"]
        if n or total:
            audio.tags["trkn"] = [(n, total)]
    if "disc" in tags:
        if "disk" in audio.tags:
            del audio.tags["disk"]
        if str(tags["disc"]).strip().isdigit():
            audio.tags["disk"] = [(int(tags["disc"]), 0)]
    if cover and cover[0] == "remove":
        if "covr" in audio.tags:
            del audio.tags["covr"]
    elif cover and cover[0] == "set":
        _, mime, data = cover
        fmt = (MP4Cover.FORMAT_PNG if mime == "image/png"
               else MP4Cover.FORMAT_JPEG)
        if mime not in COVER_MIMES:
            raise ValueError(f"Cover must be JPEG or PNG, got: {mime}")
        audio.tags["covr"] = [MP4Cover(bytes(data), imageformat=fmt)]
    audio.save()


# -- Vorbis comments (OGG / Opus) ----------------------------------------------
_VORBIS_TEXT = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "albumartist": "albumartist",
    "genre": "genre",
    "date": "date",
    "composer": "composer",
    "comment": "comment",
}


def _vorbis_open(path: str):
    ext = Path(path).suffix.lower()
    if ext == ".opus":
        from mutagen.oggopus import OggOpus
        return OggOpus(path)
    from mutagen.oggvorbis import OggVorbis
    return OggVorbis(path)


def _read_vorbis(path: str, tags: dict) -> None:
    audio = _vorbis_open(path)
    if audio.tags is None:
        return
    for field, key in _VORBIS_TEXT.items():
        if key in audio.tags and audio.tags[key]:
            try:
                tags[field] = str(audio.tags[key][0])
            except IndexError:
                pass
    if "tracknumber" in audio.tags and audio.tags["tracknumber"]:
        try:
            parts = str(audio.tags["tracknumber"][0]).split("/", 1)
            tags["track"] = parts[0].strip()
            if len(parts) > 1:
                tags["tracktotal"] = parts[1].strip()
            elif "tracktotal" in audio.tags and audio.tags["tracktotal"]:
                tags["tracktotal"] = str(audio.tags["tracktotal"][0])
        except IndexError:
            pass
    if "discnumber" in audio.tags and audio.tags["discnumber"]:
        try:
            tags["disc"] = str(audio.tags["discnumber"][0]).split("/", 1)[0].strip()
        except IndexError:
            pass


def _vorbis_picture(data: bytes, mime: str):
    from mutagen.flac import Picture
    pic = Picture()
    pic.type = 3
    pic.mime = mime
    pic.desc = ""
    pic.data = bytes(data)
    return pic


def _read_vorbis_cover(path: str) -> tuple[str, bytes] | None:
    import base64
    audio = _vorbis_open(path)
    if audio.tags is None:
        return None
    for key in ("metadata_block_picture", "coverart"):
        if key in audio.tags and audio.tags[key]:
            try:
                from mutagen.flac import Picture
                pic = Picture(base64.b64decode(audio.tags[key][0]))
                if pic.data:
                    return (pic.mime or "image/jpeg", bytes(pic.data))
            except Exception:
                continue
    return None


def _write_vorbis(path: str, tags: dict, cover: tuple) -> None:
    import base64
    audio = _vorbis_open(path)
    if audio.tags is None:
        audio.add_tags()
    for field, key in _VORBIS_TEXT.items():
        if field not in tags:
            continue
        if key in audio.tags:
            del audio.tags[key]
        if tags[field]:
            audio.tags[key] = [str(tags[field])]
    if "track" in tags or "tracktotal" in tags:
        for k in ("tracknumber", "tracktotal"):
            if k in audio.tags:
                del audio.tags[k]
        n = str(tags.get("track", "")).strip()
        t = str(tags.get("tracktotal", "")).strip()
        if n or t:
            audio.tags["tracknumber"] = [f"{n}/{t}" if t else n]
            if t:
                audio.tags["tracktotal"] = [t]
    if "disc" in tags:
        if "discnumber" in audio.tags:
            del audio.tags["discnumber"]
        if str(tags["disc"]).strip():
            audio.tags["discnumber"] = [str(tags["disc"]).strip()]
    if cover and cover[0] == "remove":
        for k in ("metadata_block_picture", "coverart"):
            if k in audio.tags:
                del audio.tags[k]
    elif cover and cover[0] == "set":
        _, mime, data = cover
        if mime not in COVER_MIMES:
            raise ValueError(f"Cover must be JPEG or PNG, got: {mime}")
        pic = _vorbis_picture(bytes(data), mime)
        encoded = base64.b64encode(pic.write()).decode("ascii")
        for k in ("metadata_block_picture", "coverart"):
            if k in audio.tags:
                del audio.tags[k]
        audio.tags["metadata_block_picture"] = [encoded]
    audio.save()


# -- FLAC -----------------------------------------------------------------------
def _read_flac(path: str, tags: dict) -> None:
    from mutagen.flac import FLAC
    audio = FLAC(path)
    _read_vorbis_into(audio, tags)


def _read_vorbis_into(audio, tags: dict) -> None:
    for field, key in _VORBIS_TEXT.items():
        if key in audio and audio[key]:
            try:
                tags[field] = str(audio[key][0])
            except IndexError:
                pass
    if "tracknumber" in audio and audio["tracknumber"]:
        try:
            parts = str(audio["tracknumber"][0]).split("/", 1)
            tags["track"] = parts[0].strip()
            if len(parts) > 1:
                tags["tracktotal"] = parts[1].strip()
            elif "tracktotal" in audio and audio["tracktotal"]:
                tags["tracktotal"] = str(audio["tracktotal"][0])
        except IndexError:
            pass
    if "discnumber" in audio and audio["discnumber"]:
        try:
            tags["disc"] = str(audio["discnumber"][0]).split("/", 1)[0].strip()
        except IndexError:
            pass


def _read_flac_cover(path: str) -> tuple[str, bytes] | None:
    from mutagen.flac import FLAC
    audio = FLAC(path)
    for pic in audio.pictures:
        try:
            if pic.data:
                return (pic.mime or "image/jpeg", bytes(pic.data))
        except AttributeError:
            continue
    return None


def _write_flac(path: str, tags: dict, cover: tuple) -> None:
    from mutagen.flac import FLAC
    audio = FLAC(path)
    for field, key in _VORBIS_TEXT.items():
        if field not in tags:
            continue
        if key in audio:
            del audio[key]
        if tags[field]:
            audio[key] = [str(tags[field])]
    if "track" in tags or "tracktotal" in tags:
        for k in ("tracknumber", "tracktotal"):
            if k in audio:
                del audio[k]
        n = str(tags.get("track", "")).strip()
        t = str(tags.get("tracktotal", "")).strip()
        if n or t:
            audio["tracknumber"] = [f"{n}/{t}" if t else n]
            if t:
                audio["tracktotal"] = [t]
    if "disc" in tags:
        if "discnumber" in audio:
            del audio["discnumber"]
        if str(tags["disc"]).strip():
            audio["discnumber"] = [str(tags["disc"]).strip()]
    if cover and cover[0] == "remove":
        audio.clear_pictures()
    elif cover and cover[0] == "set":
        _, mime, data = cover
        if mime not in COVER_MIMES:
            raise ValueError(f"Cover must be JPEG or PNG, got: {mime}")
        audio.clear_pictures()
        audio.add_picture(_vorbis_picture(bytes(data), mime))
    audio.save()
