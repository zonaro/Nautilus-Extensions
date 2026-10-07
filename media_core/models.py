# -*- coding: utf-8 -*-
#
# Media Core - Data Models
#
# Adapted from Transmutia (MIT License)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class MediaCategory(Enum):
    AUDIO = auto()
    VIDEO = auto()
    IMAGE = auto()
    UNKNOWN = auto()


class ConvertStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    DONE = auto()
    ERROR = auto()
    CANCELLED = auto()


@dataclass
class MediaItem:
    path: Path
    category: MediaCategory
    target_format: str = ""
    status: ConvertStatus = ConvertStatus.PENDING
    error_message: str | None = None
    output_path: Path | None = None
    progress: float = 0.0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def dir(self) -> str:
        return str(self.path.parent)
