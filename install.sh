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

# --- Optional: remove-ai-watermarks CLI (used by remove-ai-watermarks.py) ---
# Upstream: https://github.com/wiltodelta/remove-ai-watermarks
# The Nautilus extension (remove-ai-watermarks.py) is always copied below;
# the CLI itself is only installed if the user opts in here.
install_raiw_cli() {
  if command -v remove-ai-watermarks >/dev/null 2>&1; then
    echo "==> remove-ai-watermarks already on PATH ($(command -v remove-ai-watermarks)), skipping."
    return 0
  fi
  echo "==> Installing remove-ai-watermarks CLI (extras: [all])..."
  if command -v uv >/dev/null 2>&1; then
    uv tool install "remove-ai-watermarks[all]" || uv tool install --force "remove-ai-watermarks[all]"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install "remove-ai-watermarks[all]" || pipx reinstall "remove-ai-watermarks[all]"
  else
    echo "==> No uv/pipx found, trying to install uv first..."
    sudo dnf install -y uv 2>/dev/null || true
    if command -v uv >/dev/null 2>&1; then
      uv tool install "remove-ai-watermarks[all]" || uv tool install --force "remove-ai-watermarks[all]"
    else
      echo "==> Falling back to pip --user (may need 'sudo dnf install -y python3-pip')..."
      python3 -m pip install --user --break-system-packages "remove-ai-watermarks[all]" 2>/dev/null \
        || python3 -m pip install --user "remove-ai-watermarks[all]"
    fi
  fi
  if command -v remove-ai-watermarks >/dev/null 2>&1; then
    echo "==> remove-ai-watermarks installed: $(command -v remove-ai-watermarks)"
  else
    # uv tool puts binaries in ~/.local/bin — make sure it is reachable
    if [ -x "$HOME/.local/bin/remove-ai-watermarks" ]; then
      echo "==> Installed at \$HOME/.local/bin/remove-ai-watermarks."
      echo "    Add it to PATH if needed: export PATH=\"\$HOME/.local/bin:\$PATH\""
    else
      echo "WARNING: remove-ai-watermarks install seems to have failed."
      echo "         Install manually: uv tool install \"remove-ai-watermarks[all]\""
    fi
  fi
}

RAIW_ANSWER=""
if [ -e /dev/tty ]; then
  # Ask on the controlling terminal so curl|bash still prompts correctly.
  printf "Instalar Remove AI Watermarks (extensão + CLI remove-ai-watermarks no PATH)? [S/n] " > /dev/tty
  read -r RAIW_ANSWER < /dev/tty || RAIW_ANSWER=""
else
  RAIW_ANSWER="${RAIW_INSTALL:-Y}"
fi
case "${RAIW_ANSWER:-Y}" in
  [nN]*)
    echo "==> Skipping remove-ai-watermarks CLI (extension file will still be copied)."
    ;;
  *)
    install_raiw_cli
    ;;
esac

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
