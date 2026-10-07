# -*- coding: utf-8 -*-
#
# Media Core - Conversion Registry
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

from .models import MediaCategory
from .detection import detect_category
from .backends.ffmpeg import FFmpegBackend
from .backends.pillow import PillowBackend


class ConversionRegistry:
    def __init__(self) -> None:
        self._backends: list = []
        self._register_backends()

    def _register_backends(self) -> None:
        # Register backends in order; FFmpeg is primary for media, Pillow for images
        if FFmpegBackend.can_register():
            self._backends.append(FFmpegBackend())
        if PillowBackend.can_register():
            self._backends.append(PillowBackend())

    @property
    def backends(self) -> list:
        return self._backends

    def get_media_type(self, path: str | Path) -> MediaCategory:
        return detect_category(Path(path))

    def can_convert(self, input_format: str | None = None, output_format: str | None = None) -> bool:
        for backend in self._backends:
            try:
                if backend.can_convert(input_format, output_format):
                    return True
            except Exception:
                continue
        return False

    def get_backend(self, input_format: str | None = None, output_format: str | None = None):
        # Prefer Pillow for simple image conversions
        if output_format:
            out = str(output_format).lower()
            if out in ("jpg", "jpeg", "png", "webp", "bmp", "tiff", "ico"):
                for backend in self._backends:
                    if isinstance(backend, PillowBackend):
                        return backend
        # Otherwise return FFmpeg if available
        for backend in self._backends:
            if isinstance(backend, FFmpegBackend):
                return backend
        if self._backends:
            return self._backends[0]
        return None
