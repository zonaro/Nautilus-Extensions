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
