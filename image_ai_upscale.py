#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: image_ai_upscale — AI image upscale via Upscayl NCNN CLI
# DESC: Standalone helper for the "Ferramentas de IA → Upscale…" entry of
#       image-tools.py. Detects the `upscayl-bin` backend (never the Electron
#       app), builds the inference arguments, shows a GTK4/libadwaita dialog
#       and runs one subprocess per image with progress, cancel and atomic
#       output. No weights, GPU or models are initialised in the Nautilus
#       process; nothing is downloaded silently.
#
# LICENSE: GNU General Public License v3.0

import os
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GObject, Gtk, Adw, Gio, GLib

try:
    from nautilus_i18n import resolve_locale
except ImportError:  # nautilus_i18n.py not installed next to this file
    import locale

    def resolve_locale():
        return locale.getlocale()[0] or ""

_lang = resolve_locale()

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
if _lang.startswith("fr"):
    T = {
        "ai_top_menu":     "Outils IA",
        "ai_top_tip":      "Outils d'image basés sur l'IA (backend Upscayl NCNN)",
        "ai_upscale":      "Upscaler…",
        "ai_upscale_tip":  "Upscaler des images par IA (backend Upscayl)",
        "ai_title":        "Upscaler les images",
        "ai_model":        "Modèle",
        "ai_model_hint":   "Aucun modèle compatible trouvé — installez ou configurez un modèle",
        "ai_scale":        "Échelle finale",
        "ai_scale_2":      "2×",
        "ai_scale_3":      "3×",
        "ai_scale_4":      "4×",
        "ai_output":       "Dossier de sortie",
        "ai_output_same":  "Même dossier que chaque image originale (par défaut)",
        "ai_output_custom": "Dossier personnalisé…",
        "ai_name":         "Nom de sortie",
        "ai_format":       "Format",
        "ai_format_preserve": "Préserver (PNG/JPEG/WebP)",
        "ai_format_png":   "PNG",
        "ai_format_jpeg":  "JPEG",
        "ai_format_webp":  "WebP",
        "ai_quality":      "Compression / qualité",
        "ai_gpu":          "GPU",
        "ai_gpu_auto":     "Automatique",
        "ai_tile":         "Taille de tuile",
        "ai_tile_auto":    "Automatique",
        "ai_tta":          "TTA (augmentation au temps de test)",
        "ai_threads":      "Threads (−j)",
        "ai_advanced":     "Avancé",
        "ai_processing":   "Traitement…",
        "ai_done":         "Upscale terminé",
        "ai_done_msg":     "{count} image(s) upscalée(s) avec succès.",
        "ai_done_failed":  "{count} image(s) upscalée(s), {failed} échec(s).",
        "ai_cancelled":    "Annulé.",
        "ai_err_no_bin":   "Le CLI `upscayl-bin` est introuvable.",
        "ai_err_no_bin_hint": "Installez le backend autonome ou configurez son chemin.\n"
                              "Aucun téléchargement ne s'exécute automatiquement.",
        "ai_err_no_model": "Aucun modèle compatible trouvé.",
        "ai_err_no_compat": "Aucune image compatible sélectionnée.",
        "ai_cancel":       "Annuler",
        "ai_apply":        "Appliquer",
        "ai_close":        "Fermer",
        "ai_browse":       "Parcourir…",
        "ai_files":        "Fichier(s)",
        "ai_vulkan":       "GPU Vulkan requise",
    }
elif _lang.startswith("de"):
    T = {
        "ai_top_menu":     "KI-Tools",
        "ai_top_tip":      "KI-gestützte Bildwerkzeuge (Upscayl NCNN Backend)",
        "ai_upscale":      "Hochskalieren…",
        "ai_upscale_tip":  "Bilder per KI hochskalieren (Upscayl-Backend)",
        "ai_title":        "Bilder hochskalieren",
        "ai_model":        "Modell",
        "ai_model_hint":   "Kein kompatibles Modell gefunden — installieren oder konfigurieren",
        "ai_scale":        "Endgültige Skalierung",
        "ai_scale_2":      "2×",
        "ai_scale_3":      "3×",
        "ai_scale_4":      "4×",
        "ai_output":       "Ausgabeordner",
        "ai_output_same":  "Gleicher Ordner wie jedes Original (standard)",
        "ai_output_custom": "Benutzerdefinierter Ordner…",
        "ai_name":         "Ausgabename",
        "ai_format":       "Format",
        "ai_format_preserve": "Beibehalten (PNG/JPEG/WebP)",
        "ai_format_png":   "PNG",
        "ai_format_jpeg":  "JPEG",
        "ai_format_webp":  "WebP",
        "ai_quality":      "Kompression / Qualität",
        "ai_gpu":          "GPU",
        "ai_gpu_auto":     "Automatisch",
        "ai_tile":         "Kachelgröße",
        "ai_tile_auto":    "Automatisch",
        "ai_tta":          "TTA (Test-Time Augmentation)",
        "ai_threads":      "Threads (−j)",
        "ai_advanced":     "Erweitert",
        "ai_processing":   "Verarbeitung…",
        "ai_done":         "Hochskalierung abgeschlossen",
        "ai_done_msg":     "{count} Bild(er) erfolgreich hochskaliert.",
        "ai_done_failed":  "{count} Bild(er) hochskaliert, {failed} fehlgeschlagen.",
        "ai_cancelled":    "Abbrochen.",
        "ai_err_no_bin":   "Die CLI `upscayl-bin` wurde nicht gefunden.",
        "ai_err_no_bin_hint": "Installieren Sie das eigenständige Backend oder konfigurieren Sie den Pfad.\n"
                              "Kein automatischer Download.",
        "ai_err_no_model": "Kein kompatibles Modell encontrado.",
        "ai_err_no_compat": "Kein kompatibles Bild ausgewählt.",
        "ai_cancel":       "Abbrechen",
        "ai_apply":        "Anwenden",
        "ai_close":        "Schließen",
        "ai_browse":       "Auswählen…",
        "ai_files":        "Datei(en)",
        "ai_vulkan":       "Vulkan-GPU erforderlich",
    }
elif _lang.startswith("es"):
    T = {
        "ai_top_menu":     "Herramientas IA",
        "ai_top_tip":      "Herramientas de imagen con IA (backend Upscayl NCNN)",
        "ai_upscale":      "Superescalar…",
        "ai_upscale_tip":  "Superescalar imágenes con IA (backend Upscayl)",
        "ai_title":        "Superescalar imágenes",
        "ai_model":        "Modelo",
        "ai_model_hint":   "No se encontró ningún modelo compatible — instale o configure uno",
        "ai_scale":        "Escala final",
        "ai_scale_2":      "2×",
        "ai_scale_3":      "3×",
        "ai_scale_4":      "4×",
        "ai_output":       "Carpeta de salida",
        "ai_output_same":  "Misma carpeta que cada original (por defecto)",
        "ai_output_custom": "Carpeta personalizada…",
        "ai_name":         "Nombre de salida",
        "ai_format":       "Formato",
        "ai_format_preserve": "Conservar (PNG/JPEG/WebP)",
        "ai_format_png":   "PNG",
        "ai_format_jpeg":  "JPEG",
        "ai_format_webp":  "WebP",
        "ai_quality":      "Compresión / calidad",
        "ai_gpu":          "GPU",
        "ai_gpu_auto":     "Automático",
        "ai_tile":         "Tamaño de mosaico",
        "ai_tile_auto":    "Automático",
        "ai_tta":          "TTA (aumento en tiempo de prueba)",
        "ai_threads":      "Hilos (−j)",
        "ai_advanced":     "Avanzado",
        "ai_processing":   "Procesando…",
        "ai_done":         "Superescalado completado",
        "ai_done_msg":     "{count} imagen(es) superescalada(s) correctamente.",
        "ai_done_failed":  "{count} imagen(es) superescalada(s), {failed} fallo(s).",
        "ai_cancelled":    "Cancelado.",
        "ai_err_no_bin":   "No se encontró la CLI `upscayl-bin`.",
        "ai_err_no_bin_hint": "Instale el backend standalone o configure su ruta.\n"
                              "No se ejecuta ninguna descarga automáticamente.",
        "ai_err_no_model": "No se encontró ningún modelo compatible.",
        "ai_err_no_compat": "No se seleccionó ninguna imagen compatible.",
        "ai_cancel":       "Cancelar",
        "ai_apply":        "Aplicar",
        "ai_close":        "Cerrar",
        "ai_browse":       "Examinar…",
        "ai_files":        "Archivo(s)",
        "ai_vulkan":       "GPU Vulkan requerida",
    }
elif _lang.startswith("pt"):
    T = {
        "ai_top_menu":     "Ferramentas de IA",
        "ai_top_tip":      "Ferramentas de imagem com IA (backend Upscayl NCNN)",
        "ai_upscale":      "Upscale…",
        "ai_upscale_tip":  "Upscale de imagens por IA (backend Upscayl)",
        "ai_title":        "Upscale de imagens",
        "ai_model":        "Modelo",
        "ai_model_hint":   "Nenhum modelo compatível encontrado — instale ou configure um",
        "ai_scale":        "Escala final",
        "ai_scale_2":      "2×",
        "ai_scale_3":      "3×",
        "ai_scale_4":      "4×",
        "ai_output":       "Pasta de saída",
        "ai_output_same":  "Mesma pasta de cada imagem original (padrão)",
        "ai_output_custom": "Pasta personalizada…",
        "ai_name":         "Nome de saída",
        "ai_format":       "Formato",
        "ai_format_preserve": "Preservar (PNG/JPEG/WebP)",
        "ai_format_png":   "PNG",
        "ai_format_jpeg":  "JPEG",
        "ai_format_webp":  "WebP",
        "ai_quality":      "Compressão / qualidade",
        "ai_gpu":          "GPU",
        "ai_gpu_auto":     "Automática",
        "ai_tile":         "Tamanho do ladrilho",
        "ai_tile_auto":    "Automático",
        "ai_tta":          "TTA (aumento no tempo de teste)",
        "ai_threads":      "Threads (−j)",
        "ai_advanced":     "Avançado",
        "ai_processing":   "Processando…",
        "ai_done":         "Upscale concluído",
        "ai_done_msg":     "{count} imagem(ns) upscalada(s) com sucesso.",
        "ai_done_failed":  "{count} imagem(ns) upscalada(s), {failed} falha(s).",
        "ai_cancelled":    "Cancelado.",
        "ai_err_no_bin":   "O CLI `upscayl-bin` não foi encontrado.",
        "ai_err_no_bin_hint": "Instale o backend autônomo ou configure seu caminho.\n"
                              "Nenhum download é executado automaticamente.",
        "ai_err_no_model": "Nenhum modelo compatível encontrado.",
        "ai_err_no_compat": "Nenhuma imagem compatível selecionada.",
        "ai_cancel":       "Cancelar",
        "ai_apply":        "Aplicar",
        "ai_close":        "Fechar",
        "ai_browse":       "Procurar…",
        "ai_files":        "Arquivo(s)",
        "ai_vulkan":       "GPU Vulkan necessária",
    }
else:  # English
    T = {
        "ai_top_menu":     "AI Tools",
        "ai_top_tip":      "AI-powered image tools (Upscayl NCNN backend)",
        "ai_upscale":      "Upscale…",
        "ai_upscale_tip":  "Upscale images with AI (Upscayl backend)",
        "ai_title":        "Upscale images",
        "ai_model":        "Model",
        "ai_model_hint":   "No compatible model found — install or configure one",
        "ai_scale":        "Final scale",
        "ai_scale_2":      "2×",
        "ai_scale_3":      "3×",
        "ai_scale_4":      "4×",
        "ai_output":       "Output folder",
        "ai_output_same":  "Same folder as each original (default)",
        "ai_output_custom": "Custom folder…",
        "ai_name":         "Output name",
        "ai_format":       "Format",
        "ai_format_preserve": "Preserve (PNG/JPEG/WebP)",
        "ai_format_png":   "PNG",
        "ai_format_jpeg":  "JPEG",
        "ai_format_webp":  "WebP",
        "ai_quality":      "Compression / quality",
        "ai_gpu":          "GPU",
        "ai_gpu_auto":     "Automatic",
        "ai_tile":         "Tile size",
        "ai_tile_auto":    "Automatic",
        "ai_tta":          "TTA (test-time augmentation)",
        "ai_threads":      "Threads (−j)",
        "ai_advanced":     "Advanced",
        "ai_processing":   "Processing…",
        "ai_done":         "Upscale complete",
        "ai_done_msg":     "{count} image(s) upscaled successfully.",
        "ai_done_failed":  "{count} image(s) upscaled, {failed} failed.",
        "ai_cancelled":    "Cancelled.",
        "ai_err_no_bin":   "The `upscayl-bin` CLI was not found.",
        "ai_err_no_bin_hint": "Install the standalone backend or configure its path.\n"
                              "No download runs automatically.",
        "ai_err_no_model": "No compatible model found.",
        "ai_err_no_compat": "No compatible image selected.",
        "ai_cancel":       "Cancel",
        "ai_apply":        "Apply",
        "ai_close":        "Close",
        "ai_browse":       "Browse…",
        "ai_files":        "File(s)",
        "ai_vulkan":       "Vulkan GPU required",
    }

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")

# Backend candidates in order of preference. The official Upscayl NCNN CLI is
# typically shipped as `upscayl-bin`; `realesrgan-ncnn-vulkan` is a generic
# alternative kept only as a last-resort fallback.
BACKEND_CANDIDATES = ("upscayl-bin", "upscayl", "realesrgan-ncnn-vulkan")

# User-controlled XDG locations (per-user, no root required).
_XDG_DATA = os.environ.get("XDG_DATA_HOME") or os.path.join(
    os.path.expanduser("~"), ".local", "share")
XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
    os.path.expanduser("~"), ".config")
CONFIG_DIR = os.path.join(XDG_CONFIG, "nautilus-extensions")
CONFIG_FILE = os.path.join(CONFIG_DIR, "ai-upscale")
MODELS_DIR = os.path.join(_XDG_DATA, "nautilus-extensions", "upscayl", "models")

# Known Upscayl-style models: friendly name + native scale. Used to label
# discovered models and to suggest a default. Not authoritative: discovery is
# driven by the actual .param/.bin pairs on disk.
_KNOWN_MODELS = {
    "upscayl-standard-4x": ("Upscayl Standard 4×", 4),
    "real-esrgan-general-x4v3": ("Real-ESRGAN General 4×", 4),
    "upscayl-remacri-4x": ("Upscayl Remacri 4×", 4),
    "upscayl-digital-art-4x": ("Upscayl Digital Art 4×", 4),
    "upscayl-esrgan-4x": ("Upscayl ESRGAN 4×", 4),
    "real-esrgan-general-x4v2": ("Real-ESRGAN General v2 4×", 4),
}

# nautilus-python drops its Python reference as soon as .present() returns, so
# a GC'd dialog stops responding to clicks (dead popup). Retain references.
_ai_upscale_windows: list = []


def _nautilus_window():
    app = Gtk.Application.get_default()
    if app is None:
        return None
    win = app.get_active_window()
    if win is not None:
        return win
    windows = app.get_windows()
    return windows[0] if windows else None


def _show_message(msg: str):
    Gtk.AlertDialog(message=msg).show(_nautilus_window())


def _ai_forget(win: Gtk.Window):
    if win in _ai_upscale_windows:
        _ai_upscale_windows.remove(win)


def _ai_add_escape(win: Gtk.Window):
    ctrl = Gtk.ShortcutController()
    ctrl.set_scope(Gtk.ShortcutScope.MANAGED)
    trigger = Gtk.ShortcutTrigger.parse_string("Escape")
    action = Gtk.CallbackAction.new(lambda *a: (win.close(), True)[1])
    ctrl.add_shortcut(Gtk.Shortcut.new(trigger, action))
    win.add_controller(ctrl)


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

_ai_configured_backend: str | None = None


def configure_backend(path: str | None):
    """Store a user-configured backend path (persisted by the caller)."""
    global _ai_configured_backend
    _ai_configured_backend = path


def detect_backend(configured_path: str | None = None) -> str | None:
    """Return a usable backend executable path, or None.

    Preference: explicit user-configured path, then PATH candidates
    (`upscayl-bin`, `upscayl`, `realesrgan-ncnn-vulkan`).
    """
    candidates = []
    if configured_path:
        candidates.append(configured_path)
    candidates.extend(_ai_configured_backend and [_ai_configured_backend] or [])
    candidates.extend(BACKEND_CANDIDATES)
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
        # Also try PATH lookup for bare names.
        found = shutil.which(path)
        if found:
            return found
    return None


def backend_version(bin_path: str) -> str:
    """Best-effort version string from the backend. Never raises."""
    try:
        proc = subprocess.run(
            [bin_path, "-v"], capture_output=True, text=True, timeout=10)
        out = (proc.stdout or proc.stderr or "").strip()
        return out.splitlines()[0] if out else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def backend_compatible(bin_path: str) -> bool:
    """Check the backend is invocable. `-h` may exit non-zero, so ignore rc."""
    if not bin_path or not os.path.isfile(bin_path):
        return False
    try:
        subprocess.run(
            [bin_path, "-h"], capture_output=True, text=True, timeout=15)
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class UpscaleModel:
    name: str          # folder/file stem used as -n argument
    friendly: str      # user-facing label
    param: str | None  # path to .param (or None when unknown)
    bin: str | None    # path to .bin (or None when unknown)
    native_scale: int  # model's native upscale factor


def _model_name_from_param(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def discover_models(models_dir: str | None = None) -> list[UpscaleModel]:
    """Scan a directory for compatible `.param` + `.bin` model pairs.

    Returns a list of UpscaleModel, sorted with known models first. A `.param`
    without a matching `.bin` (or vice-versa) is skipped.
    """
    directory = models_dir or MODELS_DIR
    models: dict[str, UpscaleModel] = {}
    if not directory or not os.path.isdir(directory):
        return []
    try:
        entries = os.listdir(directory)
    except OSError:
        return []
    params = {}
    bins = {}
    for entry in entries:
        full = os.path.join(directory, entry)
        if not os.path.isfile(full):
            continue
        lower = entry.lower()
        if lower.endswith(".param"):
            params[_model_name_from_param(entry)] = full
        elif lower.endswith(".bin"):
            bins[_model_name_from_param(entry)] = full
    for name, param in sorted(params.items()):
        bpath = bins.get(name)
        if bpath is None:
            continue  # incomplete pair
        friendly, native = _KNOWN_MODELS.get(
            name, (name.replace("-", " ").title(), 4))
        models[name] = UpscaleModel(
            name=name, friendly=friendly, param=param, bin=bpath,
            native_scale=native)
    # Sort: known models first, then alphabetical.
    def sort_key(m: UpscaleModel):
        return (m.name not in _KNOWN_MODELS, m.name)
    return sorted(models.values(), key=sort_key)


def default_model(models: list[UpscaleModel]) -> UpscaleModel | None:
    """Pick a sensible default: Upscayl Standard 4x, else the first model."""
    if not models:
        return None
    for m in models:
        if m.name == "upscayl-standard-4x":
            return m
    return models[0]


# ---------------------------------------------------------------------------
# Output path planning (same folder, predictable name, collision safe)
# ---------------------------------------------------------------------------

def _split_ext(path: str):
    base, ext = os.path.splitext(path)
    return base, ext.lower()


def planned_output(src: str, scale: int, output_dir: str | None = None,
                   force_ext: str | None = None) -> str:
    """Predictable output path next to the source by default.

    Default name: `name-upscaled-4x.ext`. `output_dir`, when set, overrides the
    source directory.
    """
    directory = output_dir or (os.path.dirname(src) or ".")
    base, ext = _split_ext(os.path.basename(src))
    if force_ext:
        ext = force_ext if force_ext.startswith(".") else "." + force_ext
    name = f"{base}-upscaled-{scale}x{ext}"
    return os.path.join(directory, name)


def unique_output_path(path: str) -> str:
    """Return `path` if free, otherwise `name(-2)(-3...)ext`."""
    if not os.path.exists(path):
        return path
    base, ext = _split_ext(path)
    counter = 2
    while True:
        candidate = f"{base}-{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Argument vector construction
# ---------------------------------------------------------------------------

@dataclass
class UpscaleJob:
    input: str
    output: str
    models_dir: str
    model: UpscaleModel
    scale: int
    width: int | None
    format: str
    quality: int
    gpu: str | int
    tile: int | None
    tta: bool
    threads: str


def build_argv(job: UpscaleJob, backend: str) -> list[str]:
    """Build the upscayl-bin argument vector for a single job."""
    argv = [backend]
    argv += ["-i", job.input]
    argv += ["-o", job.output]
    argv += ["-m", job.models_dir]
    argv += ["-n", job.model.name]
    argv += ["-z", str(job.model.native_scale)]
    argv += ["-s", str(job.scale)]
    if job.width:
        argv += ["-w", str(job.width)]
    argv += ["-f", job.format]
    argv += ["-c", str(job.quality)]
    argv += ["-g", str(job.gpu)]
    if job.tile:
        argv += ["-t", str(job.tile)]
    if job.tta:
        argv.append("-x")
    if job.threads:
        argv += ["-j", job.threads]
    return argv


# ---------------------------------------------------------------------------
# Runner: one subprocess per image, progress, cancel, atomic output
# ---------------------------------------------------------------------------

def _parse_progress(line: str) -> float | None:
    """Best-effort progress ratio (0..1) from a backend log line."""
    text = line.strip()
    for token in text.split():
        if token.startswith("progress="):
            try:
                return max(0.0, min(1.0, float(token.split("=", 1)[1])))
            except ValueError:
                return None
        if "%" in token:
            try:
                value = float(token.replace("%", ""))
                return max(0.0, min(1.0, value / 100.0))
            except ValueError:
                return None
    return None


class UpscaleProgressDialog(Adw.Window):
    """Batch progress window for one or more upscale jobs."""

    __gtype_name__ = "ImageToolsAiUpscaleProgressDialog"

    def __init__(self, jobs: list[UpscaleJob], backend: str):
        super().__init__(title=T["ai_done"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_deletable(False)
        self.set_default_size(460, -1)
        self._jobs = jobs
        self._backend = backend
        self._cancelled = False
        self._done = 0
        self._failed = 0
        self._processed = 0
        _ai_upscale_windows.append(self)
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", lambda *_: _ai_forget(self))
        _ai_add_escape(self)

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14); box.set_margin_bottom(14)
        box.set_margin_start(16); box.set_margin_end(16)

        box.append(Gtk.Label(label=T["ai_processing"]))

        self._bar = Gtk.ProgressBar()
        self._bar.set_pulse_step(0.06)
        box.append(self._bar)

        self._current_lbl = Gtk.Label(label="")
        self._current_lbl.set_halign(Gtk.Align.START)
        self._current_lbl.set_wrap(True)
        self._current_lbl.add_css_class("dim-label")
        box.append(self._current_lbl)

        self._status_lbl = Gtk.Label(label="0/{0}".format(len(jobs)))
        self._status_lbl.set_halign(Gtk.Align.START)
        self._status_lbl.add_css_class("dim-label")
        box.append(self._status_lbl)

        self._cancel_btn = Gtk.Button(label=T["ai_cancel"])
        self._cancel_btn.connect("clicked", self._on_cancel)
        box.append(self._cancel_btn)

        tv.set_content(box)
        self.set_content(tv)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        GObject.timeout_add(80, self._pulse)

    def present(self):
        GLib.idle_add(super().present)

    def _pulse(self):
        if self._thread.is_alive():
            self._bar.pulse()
            return True
        self._bar.set_fraction(1.0)
        return False

    def _on_close_request(self, *_args):
        self._cancelled = True
        self._cancel_btn.set_sensitive(False)
        return False

    def _on_cancel(self, _btn):
        self._cancelled = True
        self._cancel_btn.set_sensitive(False)

    def _set_status(self):
        self._status_lbl.set_label("{0}/{1}".format(
            self._processed, len(self._jobs)))

    def _run_one(self, job: UpscaleJob) -> int:
        """Run a single upscale subprocess. Returns exit code."""
        tmp_output = job.output + ".partial"
        tmp_argv = build_argv(job, self._backend)
        for idx, part in enumerate(tmp_argv):
            if part == "-o" and idx + 1 < len(tmp_argv):
                tmp_argv[idx + 1] = tmp_output
        try:
            proc = subprocess.Popen(
                tmp_argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True)
        except Exception as exc:  # noqa: BLE001
            return -1
        assert proc.stdout is not None
        for line in proc.stdout:
            if self._cancelled:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.kill()
                break
            ratio = _parse_progress(line)
            if ratio is not None:
                GLib.idle_add(self._bar.set_fraction, ratio)
            GLib.idle_add(self._current_lbl.set_text,
                          os.path.basename(job.input))
        rc = proc.wait()
        if rc == 0 and os.path.exists(tmp_output):
            try:
                os.replace(tmp_output, job.output)
            except OSError:
                try:
                    shutil.move(tmp_output, job.output)
                except OSError:
                    pass
        elif os.path.exists(tmp_output):
            try:
                os.remove(tmp_output)
            except OSError:
                pass
        return rc

    def _run(self):
        for job in self._jobs:
            if self._cancelled:
                break
            rc = self._run_one(job)
            self._processed += 1
            if rc == 0:
                self._done += 1
            else:
                self._failed += 1
            GLib.idle_add(self._set_status)
        GLib.idle_add(self._finish)

    def _finish(self):
        if self._cancelled:
            self.destroy()
            return
        if self._failed:
            line = T["ai_done_failed"].format(count=self._done,
                                             failed=self._failed)
        else:
            line = T["ai_done_msg"].format(count=self._done)
        _show_message(line)
        self.destroy()


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class UpscaleDialog(Adw.Window):
    """GTK4/libadwaita dialog collecting upscale options."""

    __gtype_name__ = "ImageToolsAiUpscaleDialog"

    def __init__(self, images: list[str], backend: str | None = None,
                 models_dir: str | None = None):
        super().__init__(title=T["ai_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_deletable(False)
        self.set_default_size(560, 700)
        self._images = images
        self._backend = backend or detect_backend()
        self._models_dir = models_dir or MODELS_DIR
        self._models = discover_models(self._models_dir)
        self._callback = None
        self._closed = False
        _ai_upscale_windows.append(self)
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", lambda *_: _ai_forget(self))
        _ai_add_escape(self)

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        self._header = Adw.HeaderBar()
        self._header.set_decoration_layout(":close")
        tv.add_top_bar(self._header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(16); body.set_margin_bottom(16)
        body.set_margin_start(18); body.set_margin_end(18)
        self._body = body
        self._build(body)
        scroll.set_child(body)
        tv.set_content(scroll)
        self.set_content(tv)

    def present(self):
        GLib.idle_add(super().present)

    def _on_close_request(self, *_args):
        self._closed = True
        _ai_forget(self)
        return False

    def set_callback(self, cb):
        self._callback = cb

    # -- UI builders -------------------------------------------------------

    def _section(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=f"<b>{text}</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        return lbl

    def _spin(self, low: int, high: int, step: int, default: int) -> Gtk.SpinButton:
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        spin.set_value(default)
        return spin

    def _dropdown(self, items: list[str], active: int = 0) -> Gtk.DropDown:
        dd = Gtk.DropDown.new_from_strings(items)
        dd.set_selected(active)
        return dd

    def _switch(self, label: str, active: bool = False) -> Gtk.Switch:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        lbl.set_wrap(True)
        sw = Gtk.Switch()
        sw.set_active(active)
        sw.set_halign(Gtk.Align.END)
        row.append(lbl); row.append(sw)
        self._body.append(row)
        return sw

    def _note(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.add_css_class("dim-label")
        self._body.append(lbl)
        return lbl

    def _build(self, body: Gtk.Box):
        # Backend availability banner.
        if not self._backend:
            self._note(f"{T['ai_err_no_bin']}\n{T['ai_err_no_bin_hint']}")
            self._build_action_buttons(body, enabled=False)
            return
        if not self._models:
            self._note(f"{T['ai_err_no_model']}\n"
                       f"Models expected in: {self._models_dir}")

        body.append(self._section(T["ai_model"]))
        model_items = [m.friendly for m in self._models]
        default_idx = 0
        default_m = default_model(self._models)
        if default_m is not None:
            default_idx = [m.name for m in self._models].index(default_m.name)
        self._model_dd = self._dropdown(model_items, default_idx)
        body.append(self._model_dd)
        self._note(T["ai_model_hint"])

        body.append(self._section(T["ai_scale"]))
        self._scale_dd = self._dropdown(
            [T["ai_scale_2"], T["ai_scale_3"], T["ai_scale_4"]], 2)
        body.append(self._scale_dd)

        # Output destination.
        body.append(self._section(T["ai_output"]))
        self._out_same = Gtk.CheckButton(label=T["ai_output_same"])
        self._out_same.set_active(True)
        body.append(self._out_same)
        out_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._out_custom = Gtk.CheckButton(label=T["ai_output_custom"])
        self._out_custom.set_active(False)
        self._out_entry = Gtk.Entry()
        self._out_entry.set_hexpand(True)
        self._out_entry.set_sensitive(False)
        out_btn = Gtk.Button(label=T["ai_browse"])
        out_btn.set_sensitive(False)
        out_btn.connect("clicked", self._pick_output)
        out_row.append(self._out_custom)
        out_row.append(self._out_entry)
        out_row.append(out_btn)
        body.append(out_row)
        self._out_custom.connect("toggled", self._sync_output)
        self._out_same.connect("toggled", self._sync_output)

        # Format + name.
        body.append(self._section(T["ai_format"]))
        self._format_dd = self._dropdown(
            [T["ai_format_preserve"], T["ai_format_png"], T["ai_format_jpeg"],
             T["ai_format_webp"]], 0)
        body.append(self._format_dd)
        self._note("JPEG descarta transparência." if _lang.startswith("pt")
                   else "JPEG drops transparency.")

        body.append(self._section(T["ai_name"]))
        self._name_entry = Gtk.Entry()
        self._name_entry.set_text("")
        self._name_entry.set_placeholder_text(
            "name-upscaled-4x.ext (default)")
        body.append(self._name_entry)

        # Advanced section.
        self._adv = self._switch(T["ai_advanced"], False)
        self._adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._adv_box.set_visible(False)
        body.append(self._adv_box)
        self._adv.connect("notify::active", lambda *_: self._adv_box.set_visible(
            self._adv.get_active()))

        adv = self._adv_box
        adv.append(self._section(T["ai_gpu"]))
        self._gpu_dd = self._dropdown(
            [T["ai_gpu_auto"], "0", "1", "2", "3"], 0)
        adv.append(self._gpu_dd)
        adv.append(self._section(T["ai_tile"]))
        self._tile_dd = self._dropdown(
            [T["ai_tile_auto"], "256", "512", "1024", "2048"], 0)
        adv.append(self._tile_dd)
        self._tta = self._switch(T["ai_tta"], False)
        self._threads_entry = Gtk.Entry()
        self._threads_entry.set_text("1:1:1")
        adv.append(self._note("Threads (−j) load:processing:saving."))

        # Action buttons.
        sep = Gtk.Separator()
        body.append(sep)
        self._build_action_buttons(body, enabled=True)

    def _build_action_buttons(self, body: Gtk.Box, enabled: bool):
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=T["ai_cancel"])
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)
        self._apply_btn = Gtk.Button(label=T["ai_apply"])
        self._apply_btn.add_css_class("suggested-action")
        self._apply_btn.set_sensitive(enabled)
        self._apply_btn.connect("clicked", self._on_apply)
        btn_box.append(self._apply_btn)
        body.append(btn_box)

    def _sync_output(self, *_):
        custom = self._out_custom.get_active()
        same = self._out_same.get_active()
        if custom and same:
            self._out_same.set_active(False)
        if not custom and not same:
            self._out_same.set_active(True)
        self._out_entry.set_sensitive(custom)

    def _pick_output(self, _btn):
        dlg = Gtk.FileDialog(title=T["ai_output"])
        dlg.select_folder(_nautilus_window(), None, self._on_folder_done)

    def _on_folder_done(self, dlg, result):
        try:
            path = dlg.select_folder_finish(result).get_path()
        except Exception:  # noqa: BLE001
            return
        if path:
            self._out_entry.set_text(path)
            self._out_custom.set_active(True)
            self._out_same.set_active(False)

    # -- Values -----------------------------------------------------------

    def _values(self):
        if not self._backend:
            _show_message(f"{T['ai_err_no_bin']}\n{T['ai_err_no_bin_hint']}")
            return None
        if not self._models:
            _show_message(T["ai_err_no_model"])
            return None
        model = self._models[self._model_dd.get_selected()]
        scale_label = [T["ai_scale_2"], T["ai_scale_3"],
                       T["ai_scale_4"]][self._scale_dd.get_selected()]
        scale = int("".join(ch for ch in scale_label if ch.isdigit()) or 4)
        output_dir = None
        if self._out_custom.get_active():
            output_dir = self._out_entry.get_text().strip() or None
        fmt_sel = self._format_dd.get_selected()
        if fmt_sel == 0:
            fmt = "preserve"
        elif fmt_sel == 1:
            fmt = "png"
        elif fmt_sel == 2:
            fmt = "jpg"
        else:
            fmt = "webp"
        gpu_sel = self._gpu_dd.get_selected()
        gpu = "auto" if gpu_sel == 0 else str(gpu_sel - 1)
        tile_sel = self._tile_dd.get_selected()
        tile = None if tile_sel == 0 else int(
            ["auto", "256", "512", "1024", "2048"][tile_sel])
        return {
            "model": model,
            "scale": scale,
            "output_dir": output_dir,
            "format": fmt,
            "quality": 85,
            "gpu": gpu,
            "tile": tile,
            "tta": self._tta.get_active(),
            "threads": self._threads_entry.get_text().strip() or "1:1:1",
        }

    def _on_apply(self, _btn):
        vals = self._values()
        if vals is None:
            return
        self.close()
        if self._callback:
            self._callback(vals)
        else:
            self._run_upscale(vals)

    def _run_upscale(self, vals: dict):
        jobs = []
        for src in self._images:
            output = planned_output(
                src, vals["scale"], vals["output_dir"])
            output = unique_output_path(output)
            job = UpscaleJob(
                input=src, output=output, models_dir=self._models_dir,
                model=vals["model"], scale=vals["scale"],
                width=None, format=vals["format"], quality=vals["quality"],
                gpu=vals["gpu"], tile=vals["tile"], tta=vals["tta"],
                threads=vals["threads"])
            jobs.append(job)
        dlg = UpscaleProgressDialog(jobs, self._backend)
        dlg.present()


# ---------------------------------------------------------------------------
# Public entry point used by image-tools.py menu handler
# ---------------------------------------------------------------------------

def run_upscale_for(images: list[str]):
    """Open the upscale dialog for the given image paths."""
    backend = detect_backend(_ai_configured_backend)
    dlg = UpscaleDialog(images, backend=backend)
    dlg.present()
