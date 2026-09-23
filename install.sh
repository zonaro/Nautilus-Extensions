#!/usr/bin/env bash
#
# install.sh — Nautilus Extensions on Fedora (dnf)
# Repo: https://github.com/zonaro/Nautilus-Extensions (fork of ToFpon/Nautilus-Extensions)
#
# Usage: ./install.sh
#
set -euo pipefail

EXT_DIR="$HOME/.local/share/nautilus-python/extensions"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing dependencies (Fedora / dnf)..."
sudo dnf install -y \
  nautilus-python \
  python3-gobject \
  gtk4 \
  libadwaita \
  nautilus-extensions \
  ghostscript \
  ffmpeg \
  ffmpegthumbnailer \
  python3-pypdf \
  python3-cairo \
  python3-libarchive-c \
  p7zip \
  p7zip-plugins \
  poppler-utils \
  rsync \
  ripgrep

# unrar is optional (RPM Fusion nonfree only) — fallback for password-protected RAR.
# 7z already covers regular RAR extraction.
if ! command -v unrar >/dev/null 2>&1; then
  echo "==> Trying optional unrar (requires RPM Fusion nonfree)..."
  sudo dnf install -y unrar || echo "WARNING: unrar unavailable — password-protected RAR will use 7z."
fi

echo "==> Installing extensions into $EXT_DIR ..."
mkdir -p "$EXT_DIR"
cp "$SCRIPT_DIR"/*.py "$EXT_DIR"/
# Data files needed by some extensions (e.g. color_database.json for folder-color-revival)
for data in "$SCRIPT_DIR"/color_database.json; do
  [ -e "$data" ] && cp "$data" "$EXT_DIR"/
done
rm -rf "$EXT_DIR/__pycache__"

echo "==> Restarting Nautilus..."
nautilus -q || true

echo "Done! Open Nautilus and right-click, or use F3 F4 F7 F8 F9."
