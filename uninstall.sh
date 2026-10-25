#!/usr/bin/env bash
#
# uninstall.sh — Remove Nautilus Extensions installed by install.sh (Fedora)
#
# Usage: ./uninstall.sh
#
set -euo pipefail

EXT_DIR="$HOME/.local/share/nautilus-python/extensions"

echo "==> Removing extensions from $EXT_DIR ..."
rm -f "$EXT_DIR"/*.py
rm -rf "$EXT_DIR/__pycache__"

# Comic Tools extras: its launcher, its desktop entry, and the defaults it set.
rm -f "$HOME/.local/bin/comic-reader" \
      "$HOME/.local/share/applications/comic-reader.desktop"
if [ -f "$HOME/.config/mimeapps.list" ]; then
  python3 - "$HOME/.config/mimeapps.list" <<'PY'
import os
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    lines = fh.readlines()
kept = [line for line in lines if "comic-reader.desktop" not in line]
if kept != lines:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.writelines(kept)
    os.replace(tmp, path)
    print("==> Dropped comic-reader.desktop defaults from mimeapps.list")
PY
fi

echo "==> Restarting Nautilus..."
nautilus -q || true

echo "Done! Extensions removed (system packages kept)."
