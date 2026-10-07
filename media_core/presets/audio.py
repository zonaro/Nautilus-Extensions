# -*- coding: utf-8 -*-
#
# Audio Presets
#
# SPDX-License-Identifier: GPL-3.0-or-later

AUDIO_FORMATS = ["mp3", "m4a", "aac", "opus", "ogg", "flac", "wav", "aiff", "ac3"]

AUDIO_QUALITIES = {
    "mp3": {"high": "-q:a 0", "medium": "-q:a 2", "low": "-q:a 5", "lossless": "-q:a 0"},
    "opus": {"high": "-b:a 256k", "medium": "-b:a 128k", "low": "-b:a 64k", "lossless": "-b:a 320k"},
    "aac": {"high": "-b:a 256k", "medium": "-b:a 192k", "low": "-b:a 128k", "lossless": "-b:a 256k"},
    "m4a": {"high": "-b:a 256k", "medium": "-b:a 192k", "low": "-b:a 128k", "lossless": "-b:a 256k"},
}
