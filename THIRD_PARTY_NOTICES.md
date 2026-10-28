# Third Party Notices

This project incorporates code and concepts from third-party sources, in accordance with their licenses.

## Transmutia

- Source: https://github.com/NormalChelik/Transmutia
- License: MIT License
- Copyright (c) Transmutia Contributors

Portions of the following files were adapted from Transmutia:

- `media_core/models.py` - MediaCategory, ConvertStatus, MediaItem (concepts and structure)
- `media_core/detection.py` - detect_category logic
- `media_core/formats.py` - Format constants and extension mappings
- `media_core/ffmpeg_utils.py` - FFmpeg/ffprobe discovery utilities
- `media_core/ffmpeg_format_args.py` - FFmpeg preset argument definitions
- `media_core/backends/ffmpeg.py` - FFmpeg conversion logic, progress parsing

The original MIT license terms apply to those derived portions.

---

## Original Nautilus-Extensions

The remainder of this codebase is licensed under GPL-3.0 as specified in LICENSE.

---

## Upscayl NCNN backend (AI upscale)

The "Ferramentas de IA → Upscale…" entry optionally invokes the standalone
`upscayl-bin` CLI from the upscayl-ncnn project. This extension **does not
redistribute** the backend binary or any AI model weights; it only shells out to
a user-installed `upscayl-bin` (detected on PATH or a user-configured path).

- Project: https://github.com/upscayl/upscayl-ncnn
- Backend license: AGPL-3.0 (the backend itself)
- AI model weights: separate, model-specific licenses (check each model before use)

Because the integration merely invokes an external CLI at runtime and does not
link or bundle the backend, the backend's AGPL-3.0 does not by itself extend to
this extension. If you bundle `upscayl-bin` or model weights in a downstream
package, review the AGPL-3.0 and each model's license first.
