# -*- coding: utf-8 -*-
#
# Media Core - FFmpeg Utilities
#
# Adapted from Transmutia (MIT License)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg() -> str | None:
    env = os.environ.get("FFMPEG_PATH")
    if env:
        p = Path(env)
        if p.is_file():
            return str(p)
    return shutil.which("ffmpeg")


def find_ffprobe(ffmpeg_bin: str | None = None) -> str | None:
    env = os.environ.get("FFPROBE_PATH")
    if env:
        p = Path(env)
        if p.is_file():
            return str(p)

    if ffmpeg_bin:
        ffmpeg_path = Path(ffmpeg_bin)
        sibling = ffmpeg_path.with_name("ffprobe" + ffmpeg_path.suffix)
        if sibling.is_file():
            return str(sibling)

    return shutil.which("ffprobe")


def ffmpeg_version(ffmpeg_bin: str) -> str | None:
    try:
        kwargs: dict = {"capture_output": True, "text": True, "timeout": 10}
        if os.name == "nt":
            import subprocess as _subprocess
            kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW
        proc = subprocess.run([ffmpeg_bin, "-version"], **kwargs)
        if proc.returncode != 0 or not proc.stdout:
            return None
        first = proc.stdout.splitlines()[0].strip()
        return first or None
    except (OSError, subprocess.TimeoutExpired):
        return None
