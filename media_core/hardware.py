# -*- coding: utf-8 -*-
#
# Media Core - Hardware Acceleration
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import subprocess
import os
from typing import Literal

from .ffmpeg_utils import find_ffmpeg

HWAccelType = Literal["Auto", "CPU", "VAAPI", "NVENC", "QSV"]


class HWAccelDetector:
    def __init__(self) -> None:
        self._ffmpeg = find_ffmpeg()
        self._cache: dict | None = None

    @property
    def available(self) -> dict:
        if self._cache is not None:
            return self._cache

        result = {
            "nvenc": False,
            "vaapi": False,
            "qsv": False,
            "hwaccels": [],
        }

        if not self._ffmpeg:
            self._cache = result
            return result

        try:
            kwargs = {"capture_output": True, "text": True, "timeout": 5}
            if os.name == "nt":
                import subprocess as _subprocess
                kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW
            proc = subprocess.run([self._ffmpeg, "-hwaccels"], **kwargs)
            if proc.returncode == 0 and proc.stdout:
                for line in proc.stdout.splitlines()[1:]:  # skip header
                    line = line.strip()
                    if line:
                        result["hwaccels"].append(line)
                        lname = line.lower()
                        if "nvenc" in lname or "cuda" in lname:
                            result["nvenc"] = True
                        if "vaapi" in lname:
                            result["vaapi"] = True
                        if "qsv" in lname:
                            result["qsv"] = True
        except Exception:
            pass

        # Fallback: check encoders
        try:
            kwargs = {"capture_output": True, "text": True, "timeout": 10}
            if os.name == "nt":
                import subprocess as _subprocess
                kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW
            proc = subprocess.run([self._ffmpeg, "-encoders"], **kwargs)
            if proc.returncode == 0 and proc.stdout:
                out = proc.stdout.lower()
                if "h264_nvenc" in out or "hevc_nvenc" in out or "av1_nvenc" in out:
                    result["nvenc"] = True
                if "h264_vaapi" in out or "hevc_vaapi" in out:
                    result["vaapi"] = True
                if "h264_qsv" in out or "hevc_qsv" in out:
                    result["qsv"] = True
        except Exception:
            pass

        self._cache = result
        return result

    def select_best(self, mode: HWAccelType = "Auto") -> str:
        avail = self.available
        if mode == "CPU":
            return "cpu"
        if mode == "NVENC" and avail["nvenc"]:
            return "nvenc"
        if mode == "QSV" and avail["qsv"]:
            return "qsv"
        if mode == "VAAPI" and avail["vaapi"]:
            return "vaapi"
        if mode == "Auto":
            # Prefer safe, common options
            if avail["nvenc"]:
                return "nvenc"
            if avail["qsv"]:
                return "qsv"
            if avail["vaapi"]:
                return "vaapi"
        return "cpu"
