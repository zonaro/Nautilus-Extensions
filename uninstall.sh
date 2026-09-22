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

echo "==> Restarting Nautilus..."
nautilus -q || true

echo "Done! Extensions removed (system packages kept)."
