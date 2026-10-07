# -*- coding: utf-8 -*-
#
# Media Core - FFmpeg Format Arguments
#
# Adapted from Transmutia (MIT License)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

_H264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "0"]
_H264_AAC = _H264 + ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]

_VIDEO_PRESETS: dict[str, list[str]] = {
    "mp4": list(_H264_AAC),
    "m4v": list(_H264_AAC),
    "mkv": _H264 + ["-c:a", "aac", "-b:a", "192k"],
    "webm": [
        "-c:v", "libvpx-vp9", "-row-mt", "1", "-crf", "35", "-b:v", "0",
        "-c:a", "libopus", "-b:a", "128k",
    ],
    "avi": _H264 + ["-c:a", "libmp3lame", "-q:a", "2"],
    "mov": list(_H264_AAC),
    "flv": _H264 + ["-c:a", "aac", "-b:a", "192k", "-f", "flv"],
    "wmv": ["-c:v", "wmv2", "-c:a", "wmav2", "-b:a", "128k"],
    "mpeg": ["-c:v", "mpeg2video", "-c:a", "mp2", "-b:a", "192k", "-f", "mpeg"],
    "ts": _H264 + ["-c:a", "aac", "-b:a", "192k", "-f", "mpegts"],
    "3gp": [
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "baseline",
        "-level", "3.0", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
        "-ar", "44100", "-ac", "2", "-movflags", "+faststart",
    ],
    "ogv": ["-c:v", "libtheora", "-q:v", "7", "-c:a", "libvorbis", "-q:a", "4"],
    "f4v": _H264 + ["-c:a", "aac", "-b:a", "192k", "-f", "flv"],
    "gif": [
        "-an",
        "-vf", "fps=15,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        "-gifflags", "+transdiff",
    ],
}

_VIDEO_ALIASES = {"mpg": "mpeg"}

_AUDIO_PRESETS: dict[str, list[str]] = {
    "mp3": ["-vn", "-acodec", "libmp3lame", "-q:a", "2"],
    "flac": ["-vn", "-acodec", "flac"],
    "wav": ["-vn", "-acodec", "pcm_s16le"],
    "aac": ["-vn", "-acodec", "aac", "-b:a", "192k"],
    "ogg": ["-vn", "-acodec", "libvorbis", "-q:a", "4"],
    "opus": ["-vn", "-acodec", "libopus", "-b:a", "128k"],
    "m4a": ["-vn", "-acodec", "aac", "-b:a", "192k"],
    "wma": ["-vn", "-acodec", "wmav2", "-b:a", "128k"],
    "alac": ["-vn", "-acodec", "alac"],
    "ac3": ["-vn", "-acodec", "ac3", "-b:a", "448k"],
    "eac3": ["-vn", "-acodec", "eac3", "-b:a", "448k"],
    "mp2": ["-vn", "-acodec", "mp2", "-b:a", "192k"],
    "aiff": ["-vn", "-acodec", "pcm_s16be"],
}

_IMAGE_ALIASES = {"jpeg": "jpg"}

_IMAGE_PRESETS: dict[str, list[str]] = {
    "jpg": ["-q:v", "2"],
    "png": ["-c:v", "png"],
    "webp": ["-c:v", "libwebp", "-quality", "85"],
    "bmp": ["-c:v", "bmp"],
    "tiff": ["-c:v", "tiff"],
    "gif": ["-c:v", "gif"],
    "ico": ["-vf", "scale=256:256:force_original_aspect_ratio=decrease"],
    "avif": ["-c:v", "libaom-av1", "-still-picture", "1", "-cpu-used", "8", "-crf", "28"],
    "tga": ["-c:v", "targa"],
}


def normalize_video_format(fmt: str) -> str:
    f = fmt.lower().strip()
    return _VIDEO_ALIASES.get(f, f)


def video_ffmpeg_args(fmt: str, **kwargs) -> list[str]:
    key = normalize_video_format(fmt)
    preset = _VIDEO_PRESETS.get(key)
    if preset is None:
        return []
    return list(preset)


def normalize_audio_format(fmt: str) -> str:
    return fmt.lower().strip()


def audio_ffmpeg_args(fmt: str, **kwargs) -> list[str]:
    key = normalize_audio_format(fmt)
    preset = _AUDIO_PRESETS.get(key)
    if preset is None:
        return []
    return list(preset)


def normalize_image_format(fmt: str) -> str:
    f = fmt.lower().strip()
    return _IMAGE_ALIASES.get(f, f)


def image_ffmpeg_args(fmt: str, **kwargs) -> list[str]:
    key = normalize_image_format(fmt)
    preset = _IMAGE_PRESETS.get(key)
    if preset is None:
        return []
    return list(preset)
