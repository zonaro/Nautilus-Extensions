#!/usr/bin/env bash
#
# install.sh — Nautilus Extensions on Fedora (dnf)
# Repo: https://github.com/zonaro/Nautilus-Extensions (fork of ToFpon/Nautilus-Extensions)
#
# One-liner (no git clone needed):
#   curl -fsSL https://raw.githubusercontent.com/zonaro/Nautilus-Extensions/main/install.sh | bash
#
# Or locally:
#   ./install.sh
#
set -euo pipefail

REPO_URL="https://github.com/zonaro/Nautilus-Extensions.git"
EXT_DIR="$HOME/.local/share/nautilus-python/extensions"

# Figure out where the payload lives. When piped via curl|bash there is no
# script file on disk, so clone the repo to a temp dir first.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -z "$SCRIPT_DIR" ] || [ ! -f "$SCRIPT_DIR/folder-color-revival.py" ]; then
  echo "==> No local checkout found, cloning $REPO_URL ..."
  if ! command -v git >/dev/null 2>&1; then
    echo "==> Installing git first..."
    sudo dnf install -y git
  fi
  SCRIPT_DIR="$(mktemp -d)/Nautilus-Extensions"
  git clone --depth 1 "$REPO_URL" "$SCRIPT_DIR"
  trap 'rm -rf "$(dirname "$SCRIPT_DIR")"' EXIT
fi

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
