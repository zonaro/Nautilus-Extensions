#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: nautilus_i18n — shared locale resolution for the Nautilus Python extensions
# DESC: Every extension of this repo used to resolve its language on its own
#       with `locale.getlocale()[0] or ""`, which left the user no way to
#       pick a language: the only choice was whatever the system locale
#       happened to be. This module centralises that decision and adds the
#       explicit user override required by the project i18n rules.
#
#       Resolution order (first hit wins):
#         1. the NAUTILUS_EXT_LANG environment variable
#         2. ~/.config/nautilus-extensions/language (written by
#            extensions-manager.py, which exposes the picker)
#         3. locale.getlocale() — automatic detection
#         4. "" — the English fallback branch of each extension
#
#       An explicit user choice (1 or 2) always wins over auto-detection (3).
#       A missing or unknown locale never silently produces an empty string:
#       the extensions fall back to English.
#
# INSTALL:
#   nautilus_i18n.py must sit next to the extension files in
#   ~/.local/share/nautilus-python/extensions/ — install.sh copies it.
#   The extensions import it defensively, so a manual single-file install
#   keeps working (they fall back to plain locale detection).
#
# LICENSE: GNU General Public License v3.0

import locale
import os

# Environment variable used for a one-off override (useful for testing and
# for running a single extension in another language).
ENV_VAR = "NAUTILUS_EXT_LANG"

# Where the explicit user choice is persisted.
CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
    "nautilus-extensions",
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "language")

# The languages the extensions ship translations for. Labels are endonyms:
# a language picker shows each language in its own language.
LANGUAGES = (
    ("pt_BR", "Português (Brasil)"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
)


def normalize(code):
    """Normalise a locale code to the lowercase underscore form.

    "pt-BR", "pt_BR" and "pt_BR.UTF-8" all become "pt_br". Returns an empty
    string for anything empty or unusable, so callers can treat it as
    "not set" and move on to the next source.
    """
    if not code:
        return ""
    code = str(code).strip().replace("-", "_").lower()
    if not code:
        return ""
    # Drop the codeset and the modifier ("pt_br@euro", "pt_br.utf8").
    return code.split(".")[0].split("@")[0]


def get_language():
    """Return the user's explicit language choice, or None.

    Checks the environment variable first, then the config file. Returns the
    normalised code ("pt_br") or None when the user made no explicit choice.
    """
    env = os.environ.get(ENV_VAR, "")
    if env.strip():
        return normalize(env) or None
    try:
        with open(CONFIG_FILE, encoding="utf-8") as handle:
            stored = handle.read().strip()
    except OSError:
        return None
    return normalize(stored) or None


def set_language(code):
    """Persist the user's explicit language choice.

    Returns True on success, False when the code cannot be written. An empty
    code clears the choice and restores automatic detection.
    """
    normalized = normalize(code)
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
            handle.write((normalized + "\n") if normalized else "")
    except OSError:
        return False
    return True


def clear_language():
    """Drop the explicit choice and go back to automatic detection."""
    return set_language("")


def resolve_locale():
    """Return the locale code the extensions should branch on.

    The result is the normalised form of the explicit user choice when there
    is one, otherwise of the detected system locale, otherwise an empty
    string — which lands every extension on its English fallback branch.
    """
    override = get_language()
    if override:
        return override
    try:
        detected = locale.getlocale()[0]
    except (ValueError, TypeError):
        detected = None
    return normalize(detected)
