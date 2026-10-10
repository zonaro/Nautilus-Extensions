# -*- coding: utf-8 -*-
#
# Media Core - FFmpeg Backend
#
# Adapted from Transmutia (MIT License)
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
import logging
import os
import signal
import subprocess
from pathlib import Path
from typing import Callable, Iterable

from ..ffmpeg_format_args import audio_ffmpeg_args, image_ffmpeg_args, video_ffmpeg_args
from ..ffmpeg_utils import find_ffmpeg, find_ffprobe
from ..formats import format_output_extension
from ..models import MediaCategory, MediaItem
from ..probe import MediaProbe

logger = logging.getLogger(__name__)


class FFmpegNotFoundError(FileNotFoundError):
    pass


class FFmpegConversionError(RuntimeError):
    pass


class FFmpegAborted(RuntimeError):
    pass


class FFmpegBackend:
    supported_input_formats = None  # computed from capabilities or broad
    supported_output_formats = None

    def __init__(self, ffmpeg_bin: str | None = None) -> None:
        self._bin = ffmpeg_bin or find_ffmpeg()
        self._probe_bin = find_ffprobe(self._bin)
        self._active_process: subprocess.Popen | None = None
        self._abort_requested = False
        self._probe = MediaProbe()

    @classmethod
    def can_register(cls) -> bool:
        return find_ffmpeg() is not None

    def can_convert(self, input_fmt: str | None = None, output_fmt: str | None = None) -> bool:
        if not self._bin:
            return False
        if output_fmt:
            out = output_fmt.lower()
            # Basic check - we try to build args
            return True
        return True

    @property
    def binary(self) -> str | None:
        return self._bin

    def abort(self) -> None:
        self._abort_requested = True
        if self._active_process and self._active_process.poll() is None:
            try:
                # Try to terminate process group for robustness
                try:
                    os.killpg(os.getpgid(self._active_process.pid), signal.SIGKILL)
                except (Exception, OSError):
                    self._active_process.kill()
            except Exception:
                pass

    def build_output_path(self, item: MediaItem, output_dir: Path, overwrite: bool = False) -> Path:
        ext = format_output_extension(item.target_format)
        base = output_dir / f"{item.path.stem}.{ext}"
        if overwrite or not base.exists():
            return base
        # Find non-conflicting name
        i = 1
        while True:
            candidate = output_dir / f"{item.path.stem} ({i}).{ext}"
            if not candidate.exists():
                return candidate
            i += 1
            if i > 999:
                return base

    def build_command(self, item: MediaItem, output: Path, hwaccel: str = "cpu",
                      opts: dict | None = None) -> list[str]:
        cmd: list[str] = [
            self._bin,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-threads", "0",
            "-i", str(item.path),
        ]

        # Hardware acceleration
        from .. import hw_utils
        if hwaccel == "nvenc":
            cmd.insert(1, "-hwaccel")
            cmd.insert(2, "cuda")
        elif hwaccel == "vaapi":
            cmd.insert(1, "-hwaccel")
            cmd.insert(2, "vaapi")
            devices = hw_utils.detect_dri_devices()
            cmd.insert(3, "-vaapi_device")
            cmd.insert(4, devices[0] if devices else "/dev/dri/renderD128")
        elif hwaccel == "qsv":
            cmd.insert(1, "-hwaccel")
            cmd.insert(2, "qsv")

        from .. import ffmpeg_format_args as _ffa
        # If converting video to audio format, treat as audio extraction
        target = item.target_format.lower()
        audio_targets = {'mp3','aac','flac','wav','aiff','ogg','opus','m4a','wma','alac','ac3','eac3','mp2'}
        if item.category == MediaCategory.AUDIO:
            args = audio_ffmpeg_args(item.target_format)
            if not args:
                raise FFmpegConversionError(f"Unsupported audio format: {item.target_format}")
            cmd.extend(args)
        elif item.category == MediaCategory.VIDEO:
            if target in audio_targets:
                args = audio_ffmpeg_args(item.target_format)
                if not args:
                    raise FFmpegConversionError(f"Unsupported audio format: {item.target_format}")
                cmd.extend(args)
            else:
                args = video_ffmpeg_args(item.target_format)
                if not args:
                    raise FFmpegConversionError(f"Unsupported video format: {item.target_format}")
                cmd.extend(args)
        elif item.category == MediaCategory.IMAGE:
            args = image_ffmpeg_args(item.target_format)
            if not args:
                raise FFmpegConversionError(f"Unsupported image format: {item.target_format}")
            cmd.extend(args)
        else:
            raise FFmpegConversionError(f"Unsupported category: {item.category}")

        if opts:
            self._apply_opts(cmd, item.target_format, opts)

        # Machine-readable progress on stdout, consumed line by line in
        # convert_item to feed _parse_progress_ratio. Without this flag
        # ffmpeg prints nothing to stdout and the progress bar never moves.
        cmd += ["-progress", "pipe:1", "-nostats"]
        cmd.append(str(output))
        return cmd

    # -- advanced overrides -------------------------------------------------
    _CRF_CODECS = frozenset(
        {"libx264", "libx265", "libvpx-vp9", "libaom-av1", "libsvtav1"})
    _SPEED_CODECS = frozenset({"libx264", "libx265"})
    _LOSSLESS_AUDIO = frozenset({"flac", "wav", "aiff", "alac"})
    _RESOLUTIONS = {
        "480p": "-2:480",
        "720p": "-2:720",
        "1080p": "-2:1080",
        "2160p": "-2:2160",
    }

    @staticmethod
    def _set_opt(args: list[str], keys: tuple[str, ...], value: str) -> None:
        for i, a in enumerate(args):
            if a in keys and i + 1 < len(args):
                args[i + 1] = value
                return
        args.extend([keys[0], value])

    @staticmethod
    def _opt_value(args: list[str], keys: tuple[str, ...]) -> str | None:
        for i, a in enumerate(args):
            if a in keys and i + 1 < len(args):
                return args[i + 1]
        return None

    def _apply_opts(self, cmd: list[str], target_format: str,
                    opts: dict) -> None:
        from ..ffmpeg_format_args import normalize_video_format
        fmt = normalize_video_format(str(target_format).lower())
        if fmt == "gif":
            return
        has_audio = "-an" not in cmd

        vcodec = opts.get("vcodec")
        if vcodec and "-c:v" in cmd:
            idx = cmd.index("-c:v")
            if idx + 1 < len(cmd):
                cmd[idx + 1] = vcodec
        effective_v = (vcodec or self._opt_value(cmd, ("-c:v",)) or "")

        crf = opts.get("crf")
        if crf is not None:
            if "-crf" in cmd:
                self._set_opt(cmd, ("-crf",), str(crf))
            elif effective_v in self._CRF_CODECS:
                cmd.extend(["-crf", str(crf)])

        speed = opts.get("speed")
        if speed:
            if "-preset" in cmd:
                self._set_opt(cmd, ("-preset",), str(speed))
            elif effective_v in self._SPEED_CODECS:
                cmd.extend(["-preset", str(speed)])

        res = opts.get("resolution")
        if res and "-vf" not in cmd:
            scale = self._RESOLUTIONS.get(str(res).lower())
            if scale is None and "x" in str(res).lower():
                try:
                    w, h = str(res).lower().split("x", 1)
                    int(w)
                    int(h)
                    scale = f"{w}:{h}"
                except ValueError:
                    scale = None
            if scale:
                cmd.extend(["-vf", f"scale={scale}"])

        fps = opts.get("fps")
        if fps and "-r" not in cmd:
            cmd.extend(["-r", str(fps)])

        if has_audio:
            acodec = opts.get("acodec")
            if acodec:
                if "-c:a" in cmd or "-acodec" in cmd:
                    self._set_opt(cmd, ("-c:a", "-acodec"), str(acodec))
                else:
                    cmd.extend(["-c:a", str(acodec)])
            abitrate = opts.get("abitrate")
            if abitrate and fmt not in self._LOSSLESS_AUDIO:
                self._set_opt(cmd, ("-b:a",), str(abitrate))
            if opts.get("sample_rate"):
                self._set_opt(cmd, ("-ar",), str(opts["sample_rate"]))
            if opts.get("channels"):
                self._set_opt(cmd, ("-ac",), str(opts["channels"]))

    def _parse_progress_ratio(self, line: str, duration_seconds: float | None) -> float | None:
        if duration_seconds is None or duration_seconds <= 0:
            return None
        if "=" not in line:
            return None
        key, raw_value = line.split("=", 1)
        if key in {"out_time_ms", "out_time_us"}:
            try:
                processed_microseconds = float(raw_value)
            except ValueError:
                return None
            total_microseconds = duration_seconds * 1_000_000.0
            if total_microseconds <= 0:
                return None
            return max(0.0, min(processed_microseconds / total_microseconds, 1.0))
        if key == "out_time":
            try:
                hh, mm, ss = raw_value.split(":")
                processed_seconds = int(hh) * 3600 + int(mm) * 60 + float(ss)
            except ValueError:
                return None
            return max(0.0, min(processed_seconds / duration_seconds, 1.0))
        return None

    def convert_item(
        self,
        item: MediaItem,
        output_dir: Path,
        progress_callback: Callable[[float, MediaItem], None] | None = None,
        hwaccel: str = "cpu",
        overwrite: bool = False,
        opts: dict | None = None,
    ) -> Path:
        if self._abort_requested:
            raise FFmpegAborted("Aborted")
        if not self._bin:
            raise FFmpegNotFoundError("ffmpeg not found")

        output = self.build_output_path(item, output_dir, overwrite=overwrite)
        cmd = self.build_command(item, output, hwaccel=hwaccel, opts=opts)
        duration = self._probe.get_duration(item.path)

        kwargs = {"text": True}
        if os.name == "nt":
            import subprocess as _subprocess
            kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW

        try:
            # Start with process group on Unix for better kill
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                start_new_session=True if os.name != "nt" else False,
                **kwargs,
            )
            self._active_process = proc
        except OSError as e:
            raise FFmpegConversionError(str(e)) from e

        stderr_text = ""
        try:
            if proc.stdout is not None:
                for raw_line in proc.stdout:
                    if self._abort_requested:
                        break
                    line = raw_line.strip()
                    if progress_callback:
                        ratio = self._parse_progress_ratio(line, duration)
                        if ratio is not None:
                            progress_callback(ratio, item)
            if proc.stderr is not None:
                stderr_text = proc.stderr.read()
            proc.wait()
        finally:
            self._active_process = None
            try:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass

        if self._abort_requested:
            # Remove incomplete output if it exists
            try:
                if output.exists():
                    output.unlink()
            except Exception:
                pass
            raise FFmpegAborted("Aborted")

        if proc.returncode != 0:
            raise FFmpegConversionError(stderr_text or f"ffmpeg exited with {proc.returncode}")

        return output

    def convert_batch(
        self,
        items: Iterable[MediaItem],
        output_dir: Path,
        progress_callback: Callable[[float, MediaItem, int, int], None] | None = None,
        hwaccel: str = "cpu",
        overwrite: bool = False,
        opts: dict | None = None,
    ) -> list[Path]:
        results = []
        item_list = list(items)
        total = len(item_list)
        for i, item in enumerate(item_list):
            if self._abort_requested:
                raise FFmpegAborted("Batch aborted")
            try:
                out_path = self.convert_item(
                    item,
                    output_dir,
                    progress_callback=lambda f, it=item: progress_callback(
                        (i + f) / total if progress_callback else 0, it, i + 1, total
                    ) if progress_callback else None,
                    hwaccel=hwaccel,
                    overwrite=overwrite,
                    opts=opts,
                )
                results.append(out_path)
            except Exception as e:
                logger.error("Failed to convert %s: %s", item.path, e)
                raise
        return results
