# -*- coding: utf-8 -*-
#
# Media Core - Format Definitions
#
# Adapted from Transmutia (MIT License)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

AUDIO_EXT: frozenset[str] = frozenset({
    ".mp3", ".flac", ".wav", ".aac", ".m4a", ".m4b", ".ogg", ".oga", ".opus",
    ".wma", ".ape", ".alac", ".ac3", ".eac3", ".dts", ".dtshd", ".amr", ".awb",
    ".au", ".aiff", ".aif", ".caf", ".mpc", ".tta", ".wv", ".mp2", ".mpa",
    ".mka", ".weba", ".ra", ".gsm", ".voc", ".shn", ".tak", ".dsf", ".dff",
    ".spx", ".sln", ".nist", ".ircam", ".sds", ".pvf", ".snd",
})

VIDEO_EXT: frozenset[str] = frozenset({
    ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".qt", ".webm", ".flv", ".f4v",
    ".wmv", ".asf", ".mpg", ".mpeg", ".m2ts", ".mts", ".m2t", ".ts", ".vob",
    ".ogv", ".3gp", ".3g2", ".divx", ".dv", ".mxf", ".nut", ".rm", ".rmvb",
    ".swf", ".wtv", ".dvr-ms", ".roq", ".y4m", ".h264", ".264", ".hevc", ".h265",
    ".ivf", ".nuv", ".yuv", ".apng",
})

IMAGE_EXT: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif",
    ".heic", ".heif", ".avif", ".jxl", ".ico", ".tga", ".pcx", ".ppm",
    ".pgm", ".pbm", ".pnm", ".svg", ".exr", ".hdr", ".jp2", ".j2k", ".psd",
    ".xpm", ".xbm", ".dds", ".bpg", ".qoi", ".sgi", ".sun", ".ras", ".im1",
})

OUTPUT_AUDIO: tuple[str, ...] = (
    "mp3", "aac", "flac", "wav", "aiff", "ogg", "opus", "m4a", "wma",
    "alac", "ac3", "eac3", "mp2",
)

OUTPUT_VIDEO: tuple[str, ...] = (
    "mp4", "mkv", "webm", "mov", "avi", "m4v", "flv", "wmv",
    "gif", "mpeg", "mpg", "ts", "3gp", "ogv", "f4v",
)

OUTPUT_IMAGE: tuple[str, ...] = (
    "jpg", "jpeg", "png", "webp", "bmp", "tiff", "gif", "ico",
    "avif", "tga",
)

_FORMAT_CATEGORIES = {
    **{fmt: 'audio' for fmt in OUTPUT_AUDIO},
    **{fmt: 'video' for fmt in OUTPUT_VIDEO},
    **{fmt: 'image' for fmt in OUTPUT_IMAGE},
}

_OUTPUT_EXTENSION_OVERRIDES: dict[str, str] = {
    "jpeg": "jpg",
    "alac": "m4a",
    "m4a": "m4a",
}


def format_output_extension(fmt: str) -> str:
    if not fmt:
        return "bin"
    normalized = fmt.strip().lower()
    return _OUTPUT_EXTENSION_OVERRIDES.get(normalized, normalized)


def format_display_label(fmt: str) -> str:
    normalized = fmt.strip().lower()
    ext = format_output_extension(normalized)
    return f"{normalized.upper()} (.{ext})"
