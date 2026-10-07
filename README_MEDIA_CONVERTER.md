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

- `media-converter.py` - Nautilus extension (GTK4/Libadwaita)

## Features

- Video/audio/image conversion via FFmpeg and Pillow
- Hardware acceleration detection (NVENC, VAAPI, QSV)
- Batch conversion with progress
- Safe output naming (no overwrite)
- Context menu integration
- Advanced dialog with format selection
