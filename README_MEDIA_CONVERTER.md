# Media Converter

New native media conversion infrastructure for Nautilus-Extensions.

## Architecture

- `media_core/` - Shared core (no GTK dependency)
  - `models.py` - Data models
  - `detection.py` - Media type detection  
  - `formats.py` - Format definitions
  - `registry.py` - Backend/capability registry
  - `probe.py` - Media probing via ffprobe
  - `hardware.py`, `hw_utils.py` - Hardware acceleration detection
  - `capabilities.py` - FFmpeg capability detection
  - `backends/ffmpeg.py` - FFmpeg backend (video/audio/image)
  - `backends/pillow.py` - Pillow backend (static images)
  - `presets/` - Presets
  - `presets_manager.py` - Preset management

- `media_dialogs.py` - Shared GTK UI (Quick + Advanced dialogs, GTK only here)
- `video-tools.py` - "Ferramentas de vídeo": convert video + extract audio
- `audio-tools.py` - "Ferramentas de áudio": convert audio
- `image-tools.py` - "Ferramentas de imagem": Convert submenu via media_core
- `video-to-audio.py` / `media-converter.py` - Legacy shims (no menus; kept importable)

## Features

- Video/audio/image conversion via FFmpeg and Pillow
- Hardware acceleration detection (NVENC, VAAPI, QSV)
- Batch conversion with progress
- Safe output naming (no overwrite)
- Context menu integration
- Advanced dialog with format selection
