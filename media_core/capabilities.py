# -*- coding: utf-8 -*-
#
# Media Core - FFmpeg Capabilities Detection
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import subprocess
import os
from pathlib import Path

from .ffmpeg_utils import find_ffmpeg, ffmpeg_version


class Capabilities:
    def __init__(self) -> None:
        self._ffmpeg = find_ffmpeg()
        self._version = ffmpeg_version(self._ffmpeg) if self._ffmpeg else None
        self._cache = None

    @property
    def has_ffmpeg(self) -> bool:
        return self._ffmpeg is not None

    @property
    def version(self) -> str | None:
        return self._version

    def detect(self) -> dict:
        if self._cache is not None:
            return self._cache

        result = {
            "encoders": set(),
            "decoders": set(),
            "formats": set(),
            "hwaccels": [],
        }

        if not self._ffmpeg:
            self._cache = result
            return result

        for cmd_type in ["-encoders", "-decoders", "-formats", "-hwaccels"]:
            try:
                kwargs = {"capture_output": True, "text": True, "timeout": 15}
                if os.name == "nt":
                    import subprocess as _subprocess
                    kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW
                proc = subprocess.run([self._ffmpeg, cmd_type], **kwargs)
                if proc.returncode != 0 or not proc.stdout:
                    continue
                out = proc.stdout
                for line in out.splitlines():
                    if cmd_type == "-hwaccels":
                        if line.strip() and not line.strip().startswith("Hardware"):
                            result["hwaccels"].append(line.strip())
                        continue
                    # Skip header lines
                    if "encoder" in line or "decoder" in line or "format" in line:
                        if line.startswith(" ") or line.startswith("\t"):
                            # These contain info
                            pass
                    # Extract codec/format names (simple heuristic)
                    parts = line.split()
                    if len(parts) > 1:
                        key = parts[1] if cmd_type in ("-encoders", "-decoders") else parts[1] if len(parts) > 1 else None
                        if cmd_type == "-encoders":
                            result["encoders"].add(parts[1])
                        elif cmd_type == "-decoders":
                            result["decoders"].add(parts[1])
                        elif cmd_type == "-formats":
                            result["formats"].add(parts[1])
            except Exception:
                continue

        self._cache = result
        return result


_capabilities = Capabilities()


def get_capabilities() -> dict:
    return _capabilities.detect()


_VIDEO_CODEC_LABELS: tuple[tuple[str, str], ...] = (
    ("libx264", "H.264"),
    ("libx265", "H.265 / HEVC"),
    ("libvpx-vp9", "VP9"),
    ("libaom-av1", "AV1"),
    ("libsvtav1", "AV1 (SVT)"),
    ("mpeg4", "MPEG-4"),
    ("libtheora", "Theora"),
    ("mpeg2video", "MPEG-2"),
    ("wmv2", "WMV2"),
)

_AUDIO_CODEC_LABELS: tuple[tuple[str, str], ...] = (
    ("aac", "AAC"),
    ("libmp3lame", "MP3"),
    ("libopus", "Opus"),
    ("libvorbis", "Vorbis"),
    ("flac", "FLAC"),
    ("pcm_s16le", "PCM 16-bit"),
    ("pcm_s16be", "PCM 16-bit BE"),
    ("ac3", "AC-3"),
    ("wmav2", "WMA"),
    ("alac", "ALAC"),
)


def available_video_codecs() -> list[tuple[str, str]]:
    encoders = get_capabilities().get("encoders", set())
    return [(e, l) for e, l in _VIDEO_CODEC_LABELS if e in encoders]


def available_audio_codecs() -> list[tuple[str, str]]:
    encoders = get_capabilities().get("encoders", set())
    return [(e, l) for e, l in _AUDIO_CODEC_LABELS if e in encoders]


def available_hw() -> list[str]:
    caps = get_capabilities()
    accels = " ".join(str(h).lower() for h in caps.get("hwaccels", []))
    encoders = caps.get("encoders", set())
    out = ["Auto", "CPU"]
    if "vaapi" in accels or "h264_vaapi" in encoders:
        out.append("VAAPI")
    if ("cuda" in accels
            or any(f"{c}_nvenc" in encoders for c in ("h264", "hevc", "av1"))):
        out.append("NVENC")
    if ("qsv" in accels
            or any(f"{c}_qsv" in encoders for c in ("h264", "hevc", "av1"))):
        out.append("QSV")
    return out
