# -*- coding: utf-8 -*-
#
# Hardware acceleration utilities
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import os
import subprocess
from .ffmpeg_utils import find_ffmpeg


def detect_dri_devices() -> list[str]:
    dri = '/dev/dri'
    if not os.path.exists(dri):
        return []
    devices = []
    try:
        for name in os.listdir(dri):
            if name.startswith('renderD'):
                devices.append(os.path.join(dri, name))
    except Exception:
        pass
    return devices
