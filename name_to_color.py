"""name_to_color.py - Faithful Python port of NameToColor's generateColor().

Original: https://github.com/zonaro/NameToColor (MIT)
Source of truth: NameToColor.js generateColor() + pt-BR pack (NameToColor.ptBR.js).

Pipeline replicated exactly (string path):
  trim -> camelCase split -> lowercase -> pt exact alias lookup
  -> pt modifier translation (greedy longest-match) -> random/transparent
  -> HEX -> RGB/RGBA -> EN exact -> EN contains -> multi-word
  (modifier reorder + recursive generateColor + 75/25 blend)
  -> EN levenshtein (<=3, author key order) -> djb2 hash fallback.

Striking fidelity details mirrored here:
  - EN exact/contains/levenshtein iterate colorDatabaseKeys AUTHOR order,
    and pt names NEVER enter that pool (registry holds packs only).
  - djb2 wraps to int32 ONLY at byte extraction (accumulator stays full
    precision, exactly like the JS doubles).
  - All Math.round() sites use half-up (Python round() is banker's).
  - Numeric strings use JS Number() semantics ('' -> 0, '0x11' -> 17).
  - contains('') matches everything -> first key (#4C4F56).
"""

from __future__ import annotations

import json
import math
import random
import re
import unicodedata
from pathlib import Path

__all__ = ["generate_color", "normalize_hex", "hex_to_rgb", "hex_to_hsl", "hsl_to_hex"]

_DB_PATH = Path(__file__).with_name("color_database.json")

_DB: dict | None = None

_ALNUM_RE = re.compile(r"[^a-z0-9]")
_WS_RE = re.compile(r"\s+")
_ACCENT_RE = re.compile(r"[\u0300-\u036f]")
_CAMEL_A_RE = re.compile(r"([a-z])([A-Z])")
_CAMEL_B_RE = re.compile(r"([A-Z])([A-Z][a-z])")
_HEX_RE = re.compile(r"^#?[0-9a-f]{3}$|^#?[0-9a-f]{6}$", re.IGNORECASE)
_RGB_RE = re.compile(r"^rgb\(\s*(\d{1,3}\s*,\s*){2}\d{1,3}\s*\)$")
_RGBA_RE = re.compile(r"^rgba\(\s*(\d{1,3}\s*,\s*){3}(0|1|0?\.\d+)\s*\)$")
_JS_HEX_NUM_RE = re.compile(r"^[+-]?0[xX][0-9a-fA-F]+$")
_MODIFIER_PREFIXES = ("dark", "light", "bright")


def _load_db() -> dict:
    """Lazy-load the database exactly once.

    Schema: {"keys": [EN hex in JS author order],
             "colors": {lowerhex: [EN names]},
             "pt_aliases": {lang-normalized alias: '#lowerhex'},
             "pt_input_aliases": [{alias, words, canonical}]}
    """
    global _DB
    if _DB is None:
        try:
            with _DB_PATH.open("r", encoding="utf-8") as f:
                _DB = json.load(f)
        except (OSError, json.JSONDecodeError, KeyError):
            _DB = {"keys": [], "colors": {}, "pt_aliases": {}, "pt_input_aliases": []}
    return _DB


def _to_int32(value: int | float) -> int:
    """Replicates JavaScript's ToInt32 (signed 32-bit wrap)."""
    value = int(value) & 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def _js_round(value: float) -> int:
    """Replicates JavaScript's Math.round (half-up, not banker's)."""
    return int(math.floor(float(value) + 0.5))


def _lang_normalize(value: str) -> str:
    """Mirrors normalizeNameToColorLanguageText() verbatim."""
    text = _CAMEL_A_RE.sub(r"\1 \2", str(value or ""))
    text = _CAMEL_B_RE.sub(r"\1 \2", text)
    text = unicodedata.normalize("NFD", text)
    text = _ACCENT_RE.sub("", text)
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_text(text: str) -> str:
    """Step-1 normalization: trim + camelCase split + lowercase (JS lines 2948-2951)."""
    text = str(text).strip()
    text = _CAMEL_A_RE.sub(r"\1 \2", text)
    text = _CAMEL_B_RE.sub(r"\1 \2", text)
    return text.lower()


def _resolve_pt_color(normalized_text: str) -> str | None:
    """Exact pt alias lookup (resolveNameToColorLanguageColor, registry only)."""
    normalized = _lang_normalize(normalized_text)
    if not normalized:
        return None
    return _load_db()["pt_aliases"].get(normalized)


def _translate_pt_input(normalized_text: str) -> str:
    """Greedy longest-match modifier translation (translateNameToColorLanguageInput).

    Returns the joined translation when anything changed, else the ORIGINAL value.
    """
    normalized = _lang_normalize(normalized_text)
    if not normalized:
        return normalized_text
    tokens = normalized.split(" ")
    records = _load_db()["pt_input_aliases"]
    translated: list[str] = []
    changed = False
    pos = 0
    while pos < len(tokens):
        best = None
        for record in records:
            words = record["words"]
            if len(words) > len(tokens) - pos:
                continue
            if tokens[pos : pos + len(words)] != words:
                continue
            if best is None or len(words) > len(best["words"]):
                best = record
        if best is not None:
            translated.append(best["canonical"])
            pos += len(best["words"])
            changed = True
        else:
            translated.append(tokens[pos])
            pos += 1
    return " ".join(translated) if changed else normalized_text


def _js_number(text: str) -> float | int | None:
    """JS Number() semantics for the numeric-string check (None = NaN)."""
    s = str(text).strip()
    if s == "":
        return 0
    if _JS_HEX_NUM_RE.match(s):
        return int(s, 16)
    try:
        return float(s)
    except ValueError:
        return None


def _deterministic_hex_from_text(text: str) -> str:
    """djb2 fallback identical to the JS tail (no per-iteration wrap).

    JS: hash = charCode + ((hash << 5) - hash) on doubles; the << wraps its
    operand via ToInt32, but the accumulator itself is only coerced once,
    at byte extraction via >>.
    """
    hash_val = 0
    for ch in text:
        shifted = _to_int32(_to_int32(hash_val) << 5)
        hash_val = ord(ch) + shifted - hash_val
    h32 = _to_int32(hash_val)
    return "#" + "".join(f"{(h32 >> (channel * 8)) & 0xFF:02x}" for channel in range(3))


def _deterministic_hex_from_number(number: int | float) -> str:
    """Out-of-range numeric fallback: (number >> (i*8)) & 0xFF per byte."""
    n = _to_int32(number)
    return "#" + "".join(f"{(n >> (i * 8)) & 0xFF:02x}" for i in range(3))


def _random_hex() -> str:
    """'#' + Math.floor(Math.random() * 16777215).toString(16).padStart(6, '0')."""
    return f"#{random.randrange(16777215):06x}"


def _levenshtein(a: str, b: str) -> int:
    """Classic Levenshtein distance (identical to JS levenshteinDistance)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _blend_colors(color1: str, color2: str, ratio: float) -> str:
    """blendColors(): Math.round half-up per channel."""
    r1, g1, b1 = hex_to_rgb(color1)
    r2, g2, b2 = hex_to_rgb(color2)
    r = _js_round(r1 * ratio + r2 * (1 - ratio))
    g = _js_round(g1 * ratio + g2 * (1 - ratio))
    b = _js_round(b1 * ratio + b2 * (1 - ratio))
    return f"#{r:02x}{g:02x}{b:02x}"


def _multiword_color(text_for_words: str) -> str:
    """Modifier reordering + iterative 75/25 blending (mirrors JS)."""
    words = [w for w in _WS_RE.split(text_for_words) if w]
    reordered: list[str] = []
    modifier_buffer: list[str] = []

    def is_modifier(word: str) -> bool:
        return word.startswith(_MODIFIER_PREFIXES)

    def is_random(word: str) -> bool:
        return word.startswith("random")

    for word in words:
        if is_modifier(word):
            base_form = re.sub(r"er$", "", word)
            if base_form != word and base_form in ("dark", "light", "bright"):
                modifier_buffer.append(base_form)
                modifier_buffer.append(base_form)
            else:
                modifier_buffer.append(word)
        elif is_random(word):
            modifier_buffer.append(word)
        else:
            reordered.append(word)
            reordered.extend(modifier_buffer)
            modifier_buffer = []
    reordered.extend(modifier_buffer)

    ratio = 0.75
    result = generate_color(reordered[0])
    for word in reordered[1:]:
        if is_random(word):
            h, s, light = hex_to_hsl(result)
            hue_shift = random.randint(-30, 30)
            sat_shift = random.randint(-20, 20)
            light_shift = random.randint(-20, 20)
            result = hsl_to_hex(
                (h + hue_shift) % 360,
                max(0, min(100, s + sat_shift)),
                max(0, min(100, light + light_shift)),
            )
        else:
            result = _blend_colors(result, generate_color(word), ratio)
    return result


def generate_color(input_value) -> str | list:
    """Faithful port of generateColor()."""
    if isinstance(input_value, bool):
        input_value = str(input_value)
    if isinstance(input_value, (list, tuple)):
        return [generate_color(item) for item in input_value]
    if isinstance(input_value, str):
        number = _js_number(input_value)
        if number is not None:
            input_value = number
    if isinstance(input_value, (int, float)):
        number = input_value
        if isinstance(number, float):
            if not math.isfinite(number):
                return _deterministic_hex_from_number(0)
            while not number.is_integer():
                number *= 10
            number = int(number)
        keys = _load_db()["keys"]
        if 0 <= number < len(keys):
            return "#" + keys[number]
        return _deterministic_hex_from_number(number)
    if input_value is None:
        return _random_hex()
    if not isinstance(input_value, str):
        return generate_color(str(input_value))

    normalized = _normalize_text(input_value)

    localized = _resolve_pt_color(normalized)
    if localized:
        return localized

    normalized = _translate_pt_input(normalized)

    if normalized == "" or normalized == "random":
        return _random_hex()
    if normalized == "transparent":
        return "#00000000"

    if _HEX_RE.match(normalized):
        return normalized if normalized.startswith("#") else "#" + normalized

    if _RGB_RE.match(normalized):
        r, g, b = (int(x) for x in re.findall(r"\d{1,3}", normalized))
        return f"#{r:02x}{g:02x}{b:02x}"

    if _RGBA_RE.match(normalized):
        parts = re.findall(r"\d{1,3}|0|1|0?\.\d+", normalized)
        r, g, b = (int(parts[i]) for i in range(3))
        alpha = _js_round(float(parts[3]) * 255)
        return f"#{r:02x}{g:02x}{b:02x}{alpha:02x}"

    text_for_words = normalized
    text_plain = _ALNUM_RE.sub("", normalized)

    db = _load_db()
    keys: list[str] = db["keys"]
    colors: dict[str, list[str]] = db["colors"]

    for key in keys:
        for name in colors.get(key.lower(), []):
            if _ALNUM_RE.sub("", name.lower()) == text_plain:
                return "#" + key

    for key in keys:
        for name in colors.get(key.lower(), []):
            if text_plain in name.lower():
                return "#" + key

    words = [w for w in _WS_RE.split(text_for_words) if w]
    if len(words) > 1:
        return _multiword_color(text_for_words)

    best_match: str | None = None
    best_distance = float("inf")
    for key in keys:
        for name in colors.get(key.lower(), []):
            distance = _levenshtein(text_plain, _ALNUM_RE.sub("", name.lower()))
            if distance < best_distance:
                best_distance = distance
                best_match = key
    if best_match is not None and best_distance <= 3:
        return "#" + best_match

    return _deterministic_hex_from_text(text_plain)


def normalize_hex(value: str) -> str:
    """Normalize black/white/#rgb/#rrggbb (JS normalizeHex essentials)."""
    text = str(value or "").strip().lower()
    mapping = {"black": "#000000", "white": "#ffffff"}
    if text in mapping:
        return mapping[text]
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3 and all(c in "0123456789abcdef" for c in text):
        return "#" + "".join(c * 2 for c in text)
    if len(text) == 6 and all(c in "0123456789abcdef" for c in text):
        return "#" + text
    if len(text) == 8 and all(c in "0123456789abcdef" for c in text):
        return "#" + text[:6]
    return str(value)


def hex_to_rgb(hex_color: str):
    """'#rrggbb' -> (r, g, b), like JS hexToRgb()."""
    h = str(hex_color).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_to_hsl(hex_color: str) -> tuple[int, int, int]:
    """'#rrggbb' -> (h 0-360, s 0-100, l 0-100), JS hexToHsl rounding."""
    r, g, b = (c / 255 for c in hex_to_rgb(hex_color))
    mx, mn = max(r, g, b), min(r, g, b)
    h = 0.0
    s = 0.0
    light = (mx + mn) / 2
    if mx != mn:
        d = mx - mn
        s = d / (2 - mx - mn) if light > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h /= 6
    return _js_round(h * 360), _js_round(s * 100), _js_round(light * 100)


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """(h, s, l) -> '#rrggbb', identical to JS hslToHex()."""
    h = (((h % 360) + 360) % 360) / 360
    s = max(0.0, min(100.0, s)) / 100
    light = max(0.0, min(100.0, l)) / 100

    def hue_to_rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    if s == 0:
        r = g = b = light
    else:
        q = light * (1 + s) if light < 0.5 else light + s - light * s
        p = 2 * light - q
        r = hue_to_rgb(p, q, h + 1 / 3)
        g = hue_to_rgb(p, q, h)
        b = hue_to_rgb(p, q, h - 1 / 3)
    return f"#{_js_round(r * 255):02x}{_js_round(g * 255):02x}{_js_round(b * 255):02x}"
