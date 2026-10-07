#!/usr/bin/env bash
#
# install.sh — Nautilus Extensions multi-distro installer
# Repo: https://github.com/zonaro/Nautilus-Extensions (fork of ToFpon/Nautilus-Extensions)
#
# Installs selected extensions per-user into
#   ~/.local/share/nautilus-python/extensions
# and auto-detects the package manager (apt / dnf / pacman / zypper), installing
# only the dependencies required by the extensions you pick.
#
# One-liner (installs everything, same as before):
#   curl -fsSL https://raw.githubusercontent.com/zonaro/Nautilus-Extensions/main/install.sh | bash
#
# Local usage:
#   ./install.sh                              # install all extensions (default)
#   ./install.sh --all                        # same as above
#   ./install.sh --list                       # list available extensions and exit
#   ./install.sh --only dual-panel,edit-with  # install just these
#   ./install.sh --exclude hidden-dim-all     # install all but these
#   ./install.sh --all --yes --no-optional    # non-interactive, no extras
#   ./install.sh --only image-tools --yes     # auto-accept the optional CLI
#
# Flags:
#   --all            install every extension (default)
#   --only LIST      comma-separated slugs to install (see --list)
#   --exclude LIST   comma-separated slugs to skip (installs the rest)
#   --list           show available extensions and exit
#   --yes, -y        assume "yes" for prompts (non-interactive)
#   --no-optional    skip optional extras (unrar, remove-ai-watermarks CLI)
#   --help, -h       show this help and exit
#
set -euo pipefail

REPO_URL="https://github.com/zonaro/Nautilus-Extensions.git"
EXT_DIR="$HOME/.local/share/nautilus-python/extensions"
PPA_DIR="/usr/share/zonaro-nautilus-extensions"

# Directory holding the media conversion core (needed by a few extensions).
MEDIA_CORE_DIR="media_core"

# ---------------------------------------------------------------------------
# Extension catalog
# ---------------------------------------------------------------------------
SLUGS=(
  archive-browser
  clone-repository
  column-browser
  compress-pdf
  cut-dim
  deb-installer
  dev-tools-minify
  dual-panel
  duration-column
  edit-with
  extensions-manager
  extract-here
  file-tools
  folder-color-revival
  hidden-dim-all
  hidden-dim-icon
  image-tools
  media-converter
  merge-pdf
  paste-into-file
  preview-panel
  progress-mirror
  search-content
  video-to-audio
  watermark-pdf
)

slug_desc() {
  case "$1" in
    archive-browser)      echo "Browse, extract and create archives";;
    clone-repository)     echo "Clone git repos and Git submenu";;
    column-browser)       echo "Miller-columns folder browser (F9)";;
    compress-pdf)         echo "Compress PDF files via Ghostscript";;
    cut-dim)              echo "Dim items cut with Ctrl+X";;
    deb-installer)        echo "Visual .deb package installer";;
    dev-tools-minify)     echo "Minify .js/.css files";;
    dual-panel)           echo "Dual-pane file manager (F3)";;
    duration-column)      echo "Duration column for audio/video";;
    edit-with)            echo "Open text files with any installed editor";;
    extensions-manager)   echo "Enable/disable extensions on the fly";;
    extract-here)         echo "Fast archive extraction (7z, rar, zip...)";;
    file-tools)           echo "Friendly rename, copy path, symlinks...";;
    folder-color-revival) echo "Folder color & emblem tagging";;
    hidden-dim-all)       echo "Dim icon + label of hidden files";;
    hidden-dim-icon)      echo "Dim only the icon of hidden files";;
    image-tools)          echo "Grayscale, crop, annotate, convert...";;
    media-converter)      echo "FFmpeg-powered media conversion UI";;
    merge-pdf)            echo "Merge multiple PDFs into one";;
    paste-into-file)      echo "Save clipboard as .txt/.png/.zip";;
    preview-panel)        echo "Dynamic file preview panel (F4)";;
    progress-mirror)      echo "Mirror copy/move progress in a window";;
    search-content)       echo "Text search & replace via grep/ripgrep (F8)";;
    video-to-audio)       echo "Extract audio from videos (ffmpeg)";;
    watermark-pdf)        echo "Text/image PDF watermarking";;
    *)                    echo "";;
  esac
}

# Files to copy for a given slug.
slug_files() {
  case "$1" in
    edit-with)            echo "nautilus_edit_ext.py";;
    folder-color-revival) echo "folder-color-revival.py name_to_color.py color_database.json";;
    *)                    echo "$1.py";;
  esac
}

# Logical dependency keys for a given slug (always plus the shared base keys).
slug_deps() {
  case "$1" in
    archive-browser|extract-here) echo "libarchive-c p7zip p7zip-plugins unrar";;
    clone-repository)             echo "git";;
    compress-pdf)                 echo "ghostscript pypdf";;
    dual-panel)                   echo "rsync";;
    duration-column)              echo "ffmpeg";;
    file-tools|paste-into-file)   echo "pillow";;
    image-tools)                  echo "pillow ffmpeg";;
    media-converter)              echo "ffmpeg pillow";;
    merge-pdf)                    echo "pypdf";;
    preview-panel)                echo "pillow cairo ffmpeg ffmpegthumbnailer poppler";;
    search-content)               echo "ripgrep";;
    video-to-audio)               echo "ffmpeg";;
    watermark-pdf)                echo "ghostscript pypdf cairo";;
    *)                            echo "";;
  esac
}

# Shared base dependencies (needed by any GTK/Nautilus extension).
BASE_KEYS=(nautilus-python gobject gtk4 libadwaita nautilus-extensions)

# Extensions that need the media_core/ package on disk.
needs_media_core() {
  case "$1" in
    media-converter|video-to-audio|image-tools|dual-panel) return 0;;
    *) return 1;;
  esac
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
die() { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARNING: $*" >&2; }

usage() {
  sed -n '3,30p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//' || true
}

# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------
MODE="all"
ONLY=""
EXCLUDE=""
ASSUME_YES=0
NO_OPTIONAL=0
WANT_LIST=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --all)          MODE="all";;
    --list)         WANT_LIST=1;;
    -h|--help)      usage; exit 0;;
    --only)         [ "$#" -ge 2 ] || die "--only requires an argument (see --help)"; ONLY="$2"; shift;;
    --only=*)       ONLY="${1#--only=}";;
    --exclude)      [ "$#" -ge 2 ] || die "--exclude requires an argument (see --help)"; EXCLUDE="$2"; shift;;
    --exclude=*)    EXCLUDE="${1#--exclude=}";;
    -y|--yes)       ASSUME_YES=1;;
    --no-optional)  NO_OPTIONAL=1;;
    *)              die "Unknown option: '$1' (see --help)";;
  esac
  shift
done

if [ "$WANT_LIST" -eq 1 ]; then
  echo "Available extensions (${#SLUGS[@]}):"
  echo
  printf '  %-22s %s\n' "SLUG" "DESCRIPTION"
  printf '  %-22s %s\n' "----------------------" "-----------------------------------"
  for slug in "${SLUGS[@]}"; do
    printf '  %-22s %s\n' "$slug" "$(slug_desc "$slug")"
  done
  exit 0
fi

if [ -n "$ONLY" ] && [ -n "$EXCLUDE" ]; then
  die "--only and --exclude are mutually exclusive."
fi
if [ -n "$ONLY" ]; then MODE="only"; fi
if [ -n "$EXCLUDE" ]; then MODE="exclude"; fi

is_slug() {
  local s
  for s in "${SLUGS[@]}"; do
    if [ "$s" = "$1" ]; then return 0; fi
  done
  return 1
}

# Resolve SELECTED[] from MODE/ONLY/EXCLUDE.
SELECTED=()
case "$MODE" in
  all)
    SELECTED=("${SLUGS[@]}")
    ;;
  only)
    IFS=',' read -ra _parts <<< "$ONLY"
    for _part in "${_parts[@]}"; do
      _slug="${_part// /}"
      [ -n "$_slug" ] || continue
      is_slug "$_slug" || die "Unknown extension slug: '$_slug' (see --list)"
      SELECTED+=("$_slug")
    done
    [ "${#SELECTED[@]}" -gt 0 ] || die "--only requires at least one slug (see --list)"
    ;;
  exclude)
    IFS=',' read -ra _parts <<< "$EXCLUDE"
    declare -A _EX=()
    for _part in "${_parts[@]}"; do
      _slug="${_part// /}"
      [ -n "$_slug" ] || continue
      is_slug "$_slug" || die "Unknown extension slug to exclude: '$_slug' (see --list)"
      _EX["$_slug"]=1
    done
    for slug in "${SLUGS[@]}"; do
      if [ -z "${_EX[$slug]:-}" ]; then SELECTED+=("$slug"); fi
    done
    [ "${#SELECTED[@]}" -gt 0 ] || die "--exclude removed every extension"
    ;;
esac

# ---------------------------------------------------------------------------
# Package manager detection
# ---------------------------------------------------------------------------
PKG_MANAGER=""
if command -v apt-get >/dev/null 2>&1; then
  PKG_MANAGER="apt"
elif command -v dnf >/dev/null 2>&1; then
  PKG_MANAGER="dnf"
elif command -v pacman >/dev/null 2>&1; then
  PKG_MANAGER="pacman"
elif command -v zypper >/dev/null 2>&1; then
  PKG_MANAGER="zypper"
fi
[ -n "$PKG_MANAGER" ] || die "Unsupported distribution: no apt-get, dnf, pacman or zypper found."

# Map a logical dependency key to the distro package name (empty = not needed).
pkg_name() {
  case "$PKG_MANAGER" in
    apt)
      case "$1" in
        nautilus-python)     echo "python3-nautilus";;
        gobject)             echo "python3-gi";;
        gtk4)                echo "gir1.2-gtk-4.0";;
        libadwaita)          echo "gir1.2-adw-1";;
        nautilus-extensions) echo "gir1.2-nautilus-4.0";;
        ghostscript)         echo "ghostscript";;
        ffmpeg)              echo "ffmpeg";;
        ffmpegthumbnailer)   echo "ffmpegthumbnailer";;
        pypdf)               echo "python3-pypdf";;
        cairo)               echo "python3-cairo";;
        pillow)              echo "python3-pil";;
        libarchive-c)        echo "python3-libarchive-c";;
        p7zip)               echo "p7zip-full";;
        p7zip-plugins)       echo "";;
        poppler)             echo "poppler-utils";;
        rsync)               echo "rsync";;
        ripgrep)             echo "ripgrep";;
        git)                 echo "git";;
        unrar)               echo "unrar";;
        *)                   echo "";;
      esac;;
    dnf)
      case "$1" in
        nautilus-python)     echo "nautilus-python";;
        gobject)             echo "python3-gobject";;
        gtk4)                echo "gtk4";;
        libadwaita)          echo "libadwaita";;
        nautilus-extensions) echo "nautilus-extensions";;
        ghostscript)         echo "ghostscript";;
        ffmpeg)              echo "ffmpeg";;
        ffmpegthumbnailer)   echo "ffmpegthumbnailer";;
        pypdf)               echo "python3-pypdf";;
        cairo)               echo "python3-cairo";;
        pillow)              echo "python3-pillow";;
        libarchive-c)        echo "python3-libarchive-c";;
        p7zip)               echo "p7zip";;
        p7zip-plugins)       echo "p7zip-plugins";;
        poppler)             echo "poppler-utils";;
        rsync)               echo "rsync";;
        ripgrep)             echo "ripgrep";;
        git)                 echo "git";;
        unrar)               echo "unrar";;
        *)                   echo "";;
      esac;;
    pacman)
      case "$1" in
        nautilus-python)     echo "python-nautilus";;
        gobject)             echo "python-gobject";;
        gtk4)                echo "gtk4";;
        libadwaita)          echo "libadwaita";;
        nautilus-extensions) echo "nautilus";;
        ghostscript)         echo "ghostscript";;
        ffmpeg)              echo "ffmpeg";;
        ffmpegthumbnailer)   echo "ffmpegthumbnailer";;
        pypdf)               echo "python-pypdf";;
        cairo)               echo "python-cairo";;
        pillow)              echo "python-pillow";;
        libarchive-c)        echo "python-libarchive-c";;
        p7zip)               echo "p7zip";;
        p7zip-plugins)       echo "";;
        poppler)             echo "poppler";;
        rsync)               echo "rsync";;
        ripgrep)             echo "ripgrep";;
        git)                 echo "git";;
        unrar)               echo "unrar";;
        *)                   echo "";;
      esac;;
    zypper)
      case "$1" in
        nautilus-python)     echo "python3-nautilus";;
        gobject)             echo "python3-gobject";;
        gtk4)                echo "typelib-1_0-Gtk-4_0";;
        libadwaita)          echo "typelib-1_0-Adw-1";;
        nautilus-extensions) echo "typelib-1_0-Nautilus-4_0";;
        ghostscript)         echo "ghostscript";;
        ffmpeg)              echo "ffmpeg";;
        ffmpegthumbnailer)   echo "ffmpegthumbnailer";;
        pypdf)               echo "python3-pypdf";;
        cairo)               echo "python3-cairo";;
        pillow)              echo "python3-Pillow";;
        libarchive-c)        echo "python3-libarchive-c";;
        p7zip)               echo "p7zip";;
        p7zip-plugins)       echo "";;
        poppler)             echo "poppler-tools";;
        rsync)               echo "rsync";;
        ripgrep)             echo "ripgrep";;
        git)                 echo "git";;
        unrar)               echo "unrar";;
        *)                   echo "";;
      esac;;
    *) echo "";;
  esac
}

pkg_install() {
  [ "$#" -eq 0 ] && return 0
  case "$PKG_MANAGER" in
    apt)    sudo apt-get install -y "$@";;
    dnf)    sudo dnf install -y "$@";;
    pacman) sudo pacman -S --needed --noconfirm "$@";;
    zypper) sudo zypper --non-interactive install "$@";;
    *)      return 1;;
  esac
}

confirm() {
  local ans=""
  if [ -e /dev/tty ]; then
    printf "%s [y/N] " "$1" > /dev/tty
    read -r ans < /dev/tty || ans=""
  fi
  case "$ans" in
    [yY]*) return 0;;
    *)     return 1;;
  esac
}

# ---------------------------------------------------------------------------
# Coexistence with the (future) system-wide PPA install
# ---------------------------------------------------------------------------
if [ -d "$PPA_DIR" ]; then
  warn "A system-wide install already exists at $PPA_DIR (PPA layout)."
  warn "A per-user install may shadow or clash with it."
  if [ "$ASSUME_YES" -eq 1 ]; then
    warn "Continuing anyway because --yes was given."
  elif ! confirm "Continue with the per-user install anyway?"; then
    die "Aborted to avoid clashing with the system install."
  fi
fi

# ---------------------------------------------------------------------------
# Locate payload: use local checkout or clone the repo (curl | bash)
# ---------------------------------------------------------------------------
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -z "$SCRIPT_DIR" ] || [ ! -f "$SCRIPT_DIR/folder-color-revival.py" ]; then
  echo "==> No local checkout found, cloning $REPO_URL ..."
  if ! command -v git >/dev/null 2>&1; then
    echo "==> Installing git first..."
    pkg_install "$(pkg_name git)"
  fi
  SCRIPT_DIR="$(mktemp -d)/Nautilus-Extensions"
  git clone --depth 1 "$REPO_URL" "$SCRIPT_DIR"
  trap 'rm -rf "$(dirname "$SCRIPT_DIR")"' EXIT
fi

# ---------------------------------------------------------------------------
# Resolve dependencies for the selected extensions
# ---------------------------------------------------------------------------
REQUIRED_PKGS=()
OPTIONAL_PKGS=()
declare -A PKG_SEEN=()

add_key() {
  local key="$1" pkg
  pkg="$(pkg_name "$key")"
  if [ -z "$pkg" ]; then return 0; fi
  if [ -n "${PKG_SEEN[$pkg]:-}" ]; then return 0; fi
  PKG_SEEN[$pkg]=1
  if [ "$key" = "unrar" ]; then
    OPTIONAL_PKGS+=("$pkg")
  else
    REQUIRED_PKGS+=("$pkg")
  fi
}

for key in "${BASE_KEYS[@]}"; do
  add_key "$key"
done
for slug in "${SELECTED[@]}"; do
  for key in $(slug_deps "$slug"); do
    add_key "$key"
  done
done

echo "==> Detected package manager: $PKG_MANAGER"
echo "==> Installing dependencies for ${#SELECTED[@]} extension(s)..."
if [ "${#REQUIRED_PKGS[@]}" -gt 0 ]; then
  pkg_install "${REQUIRED_PKGS[@]}"
fi

# unrar is optional (RPM Fusion nonfree on Fedora, not always available).
# 7z already covers regular RAR extraction.
if [ "${#OPTIONAL_PKGS[@]}" -gt 0 ] && [ "$NO_OPTIONAL" -eq 0 ]; then
  for pkg in "${OPTIONAL_PKGS[@]}"; do
    if ! command -v unrar >/dev/null 2>&1; then
      echo "==> Trying optional $pkg ..."
      pkg_install "$pkg" || warn "$pkg unavailable — password-protected RAR will use 7z."
    fi
  done
fi

# ---------------------------------------------------------------------------
# Optional: remove-ai-watermarks CLI (used by the Image Tools submenu)
# Upstream: https://github.com/wiltodelta/remove-ai-watermarks
# The Nautilus extension (image-tools.py) is always copied below; the CLI
# itself is only installed if the user opts in here.
# ---------------------------------------------------------------------------
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
    pkg_install uv >/dev/null 2>&1 || true
    if command -v uv >/dev/null 2>&1; then
      uv tool install "remove-ai-watermarks[all]" || uv tool install --force "remove-ai-watermarks[all]"
    else
      echo "==> Falling back to pip --user (may need a pip package)..."
      python3 -m pip install --user --break-system-packages "remove-ai-watermarks[all]" 2>/dev/null \
        || python3 -m pip install --user "remove-ai-watermarks[all]"
    fi
  fi
  if command -v remove-ai-watermarks >/dev/null 2>&1; then
    echo "==> remove-ai-watermarks installed: $(command -v remove-ai-watermarks)"
  elif [ -x "$HOME/.local/bin/remove-ai-watermarks" ]; then
    echo "==> Installed at \$HOME/.local/bin/remove-ai-watermarks."
    echo "    Add it to PATH if needed: export PATH=\"\$HOME/.local/bin:\$PATH\""
  else
    echo "WARNING: remove-ai-watermarks install seems to have failed."
    echo "         Install manually: uv tool install \"remove-ai-watermarks[all]\""
  fi
}

selected_has() {
  local s
  for s in "${SELECTED[@]}"; do
    if [ "$s" = "$1" ]; then return 0; fi
  done
  return 1
}

if selected_has image-tools; then
  if [ "$NO_OPTIONAL" -eq 1 ]; then
    echo "==> Skipping remove-ai-watermarks CLI (--no-optional)."
  elif [ "$ASSUME_YES" -eq 1 ]; then
    install_raiw_cli
  elif [ -e /dev/tty ]; then
    # Ask on the controlling terminal so curl|bash still prompts correctly.
    printf "Instalar o CLI remove-ai-watermarks (usado pelo submenu Image Tools)? [S/n] " > /dev/tty
    read -r RAIW_ANSWER < /dev/tty || RAIW_ANSWER=""
    case "${RAIW_ANSWER:-Y}" in
      [nN]*) echo "==> Skipping remove-ai-watermarks CLI (extension file will still be copied).";;
      *)     install_raiw_cli;;
    esac
  else
    case "${RAIW_INSTALL:-Y}" in
      [nN]*) echo "==> Skipping remove-ai-watermarks CLI (extension file will still be copied).";;
      *)     install_raiw_cli;;
    esac
  fi
else
  echo "==> Image Tools not selected, skipping remove-ai-watermarks CLI."
fi

# ---------------------------------------------------------------------------
# Install the selected extensions
# ---------------------------------------------------------------------------
echo "==> Installing extensions into $EXT_DIR ..."
mkdir -p "$EXT_DIR"

NEED_MEDIA_CORE=0
for slug in "${SELECTED[@]}"; do
  for f in $(slug_files "$slug"); do
    cp "$SCRIPT_DIR/$f" "$EXT_DIR"/
  done
  if needs_media_core "$slug"; then
    NEED_MEDIA_CORE=1
  fi
done

if [ "$NEED_MEDIA_CORE" -eq 1 ] && [ -d "$SCRIPT_DIR/$MEDIA_CORE_DIR" ]; then
  rm -rf "$EXT_DIR/$MEDIA_CORE_DIR"
  cp -r "$SCRIPT_DIR/$MEDIA_CORE_DIR" "$EXT_DIR"/
fi

# Drop any stale bytecode from a previous install (including media_core/).
rm -rf "$EXT_DIR/__pycache__"
if [ -d "$EXT_DIR/$MEDIA_CORE_DIR" ]; then
  find "$EXT_DIR/$MEDIA_CORE_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
fi

echo "==> Restarting Nautilus..."
nautilus -q || true

echo "Done! Installed ${#SELECTED[@]} extension(s). Open Nautilus and right-click, or use F3 F4 F7 F8 F9."
