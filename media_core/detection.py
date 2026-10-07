# -*- coding: utf-8 -*-
#
# Media Core - File Detection
#
# Adapted from Transmutia (MIT License)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from pathlib import Path

from .models import MediaCategory
from .formats import AUDIO_EXT, VIDEO_EXT, IMAGE_EXT


ANIMATED_IMAGE_EXT = frozenset({'.gif', '.webp', '.apng', '.mng'})


def detect_category(path: Path | str) -> MediaCategory:
    if isinstance(path, str):
        path = Path(path)

    ext = path.suffix.lower()
    if ext in AUDIO_EXT:
        return MediaCategory.AUDIO
    if ext in VIDEO_EXT:
        return MediaCategory.VIDEO
    if ext in IMAGE_EXT:
        return MediaCategory.IMAGE
    return MediaCategory.UNKNOWN


def is_animated_image(path: Path) -> bool:
    if isinstance(path, str):
        path = Path(path)
    ext = path.suffix.lower()
    return ext in ANIMATED_IMAGE_EXT
