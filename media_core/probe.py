# -*- coding: utf-8 -*-
#
# Media Core - Media Probing
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Optional

from .ffmpeg_utils import find_ffmpeg, find_ffprobe


class MediaProbe:
    def __init__(self) -> None:
        self._ffmpeg = find_ffmpeg()
        self._ffprobe = find_ffprobe(self._ffmpeg)

    @property
    def has_ffprobe(self) -> bool:
        return self._ffprobe is not None

    def get_duration(self, path: Path) -> float | None:
        if not self._ffprobe or not path.exists():
            return None

        cmd = [
            self._ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            kwargs = {"capture_output": True, "text": True, "timeout": 10}
            if os.name == "nt":
                import subprocess as _subprocess
                kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW
            proc = subprocess.run(cmd, **kwargs)
            if proc.returncode != 0 or not proc.stdout:
                return None
            value = float(proc.stdout.strip())
            return value if value > 0 else None
        except Exception:
            return None

    def get_streams_info(self, path: Path) -> dict | None:
        # Basic info; can be expanded as needed
        return None
