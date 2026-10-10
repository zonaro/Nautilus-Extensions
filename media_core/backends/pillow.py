# -*- coding: utf-8 -*-
#
# Media Core - Pillow Backend for Static Images
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from pathlib import Path
from typing import Callable, Iterable

try:
    from PIL import Image
except Exception:
    Image = None


ALPHA_FORMATS = ("PNG", "WEBP", "ICO")
DPI_FORMATS = ("PNG", "JPEG", "BMP", "TIFF")


class PillowNotAvailableError(Exception):
    pass


class PillowBackend:
    def __init__(self) -> None:
        if Image is None:
            raise PillowNotAvailableError("Pillow/PIL not available")

    @classmethod
    def can_register(cls) -> bool:
        return Image is not None

    def can_convert(self, input_fmt: str | None = None, output_fmt: str | None = None) -> bool:
        if not cls.can_register():
            return False
        # Pillow handles common static image formats well
        return True

    def _get_format(self, ext: str) -> str:
        extl = ext.lower().lstrip(".")
        mapping = {
            "jpg": "JPEG",
            "jpeg": "JPEG",
            "png": "PNG",
            "webp": "WEBP",
            "bmp": "BMP",
            "tiff": "TIFF",
            "tif": "TIFF",
            "ico": "ICO",
            "gif": "GIF",
        }
        return mapping.get(extl, extl.upper())

    def build_output_path(self, src_path: Path, output_dir: Path, target_ext: str, overwrite: bool = False) -> Path:
        target_ext_norm = target_ext if target_ext.startswith(".") else f".{target_ext.lower()}"
        base = output_dir / f"{src_path.stem}{target_ext_norm}"
        if overwrite or not base.exists():
            return base
        i = 1
        while True:
            candidate = output_dir / f"{src_path.stem} ({i}){target_ext_norm}"
            if not candidate.exists():
                return candidate
            i += 1
            if i > 999:
                return base

    def convert_image(
        self,
        src_path: Path,
        output_dir: Path,
        target_format: str,
        quality: int = 92,
        overwrite: bool = False,
        progress_callback: Callable[[float], None] | None = None,
        max_side: int | None = None,
    ) -> Path:
        if Image is None:
            raise PillowNotAvailableError("Pillow not available")

        dst = self.build_output_path(src_path, output_dir, target_format, overwrite=overwrite)
        fmt = self._get_format(Path(target_format).suffix if "." in target_format else target_format)
        if fmt in ("JPG", "JPEG"):
            fmt = "JPEG"

        with Image.open(src_path) as img:
            img = img.copy()
            if max_side and max_side > 0:
                img.thumbnail((max_side, max_side), Image.LANCZOS)
            mode = img.mode
            if mode in ("RGBA", "LA", "PA"):
                if fmt not in ALPHA_FORMATS:
                    # Apply white background for JPEG conversion
                    flat = Image.new("RGB", img.size, (255, 255, 255))
                    flat.paste(img, mask=img.split()[-1])
                    img = flat
            elif mode == "P":
                if fmt not in ALPHA_FORMATS:
                    img = img.convert("RGB")
                else:
                    img = img.convert("RGBA")

            params = {}
            if fmt == "JPEG":
                params["quality"] = quality
                params["optimize"] = True
                params["progressive"] = True
            elif fmt == "WEBP":
                params["quality"] = quality
            elif fmt == "PNG":
                params["optimize"] = True

            img.save(dst, fmt, **params)

        if progress_callback:
            progress_callback(1.0)
        return dst

    def convert_batch(
        self,
        src_paths: Iterable[Path],
        output_dir: Path,
        target_format: str,
        quality: int = 92,
        overwrite: bool = False,
        progress_callback: Callable[[float, int, int], None] | None = None,
        max_side: int | None = None,
    ) -> list[Path]:
        results = []
        items = list(src_paths)
        total = len(items)
        for i, src in enumerate(items):
            try:
                out = self.convert_image(
                    src,
                    output_dir,
                    target_format,
                    quality=quality,
                    overwrite=overwrite,
                    progress_callback=lambda f, idx=i: progress_callback(
                        (idx + f) / total, idx + 1, total
                    ) if progress_callback else None,
                    max_side=max_side,
                )
                results.append(out)
            except Exception:
                raise
        return results
