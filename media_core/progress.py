# -*- coding: utf-8 -*-
#
# Media Core - Progress Utilities
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from typing import Callable


ProgressCallback = Callable[[float], None]
BatchProgressCallback = Callable[[float, int, int], None]
