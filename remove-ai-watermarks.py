#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Remove AI Watermarks — Nautilus Python Extension
# DESC: Right-click submenu exposing every `remove-ai-watermarks` CLI function
#       (identify, classify, visible, erase, metadata, invisible, all, batch
#       + video identify/all/visible/metadata/invisible/batch) with GTK4/Adw dialogs.
# AUTHOR: zonaro (pattern by Tof)
# VERSION: 1.0
# LICENSE: GNU General Public License v3.0
#
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1,
#           `remove-ai-watermarks` CLI on PATH (see install.sh), ffmpeg for video.
# INSTALL:
#   cp remove-ai-watermarks.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q
#
# UPSTREAM: https://github.com/wiltodelta/remove-ai-watermarks
# DOCS: docs/cli.md in upstream repo (identify/classify/visible/erase/metadata/
#       invisible/all/batch + video variants).

import locale
import os
import shlex
import shutil
import signal
import subprocess
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python
from gi.repository import GObject, Gtk, Adw, Gio, GLib, Nautilus, Pango

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "top_menu": "Remove AI Watermarks", "top_tip": "Supprimer les filigranes IA (visible, invisible, métadonnées)",
        "identify": "Identifier…", "classify": "Classifier la photo…",
        "visible": "Supprimer marque visible…", "erase": "Effacer une région…",
        "metadata": "Métadonnées IA…", "invisible": "Suppression invisible (diffusion)…",
        "all": "Pipeline complet…", "batch": "Traiter un dossier (batch)…",
        "v_identify": "Vidéo : identifier…", "v_all": "Vidéo : nettoyage complet…",
        "v_visible": "Vidéo : marque visible…", "v_metadata": "Vidéo : métadonnées…",
        "v_invisible": "Vidéo : SynthID (régénération)…", "v_batch": "Vidéo : dossier (batch)…",
        "run": "Exécuter", "cancel": "Annuler", "close": "Fermer", "browse": "Choisir…",
        "output": "Fichier de sortie", "output_dir": "Dossier de sortie",
        "input_dir": "Dossier d'entrée", "options": "Options", "command": "Commande",
        "processing": "Traitement en cours…", "done": "Terminé avec succès.",
        "failed": "Échec (code {code}).", "cancelled": "Annulé.",
        "json": "Sortie JSON", "no_visible": "Métadonnées uniquement (sans détecteurs pixel)",
        "mark": "Marque", "backend": "Moteur de remplissage", "sensitivity": "Sensibilité stricte",
        "no_detect": "Forcer sans détection (--no-detect)", "keep_metadata": "Garder les métadonnées",
        "region": "Région(s) x,y,l,h (séparées par ;)", "region_hint": "Ex. 1640,1930,400,100 ; 20,20,180,60",
        "dilate": "Dilatation du masque (px)", "inpaint": "Méthode cv2",
        "op_check": "Inspecter (--check)", "op_remove": "Supprimer (--remove)",
        "remove_all": "Tout supprimer (--remove-all)", "force": "Forcer (--force)",
        "vendor": "Cohorte (vendor)", "pipeline": "Pipeline", "strength": "Force (0=auto)",
        "seed": "Seed", "cpu_offload": "CPU offload (moins de VRAM)",
        "max_res": "Résolution max (0=natif)", "tile": "Tuiles (--tile, grandes images)",
        "mode": "Mode", "with_invisible": "Inclure régénération invisible",
        "noise_std": "Bruit (noise-std)", "long_side": "Grand côté (px)",
        "fps": "FPS (0=source)", "batch_size": "Taille de lot",
        "temporal": "Cohérence temporelle", "no_temporal": "Désactiver la cohérence temporelle",
        "suffix_note": "Sans -o, les images écrasent la source ; les vidéos écrivent <source>_clean.",
        "err_no_bin": "L'outil `remove-ai-watermarks` est introuvable dans le PATH.",
        "err_no_bin_hint": "Installez-le avec :\nuv tool install \"remove-ai-watermarks[all]\"\npuis relancez Nautilus (nautilus -q).",
        "err_no_compat": "Aucun fichier compatible sélectionné.",
        "files": "Fichier(s)",
    }
elif _lang.startswith("de"):
    T = {
        "top_menu": "Remove AI Watermarks", "top_tip": "KI-Wasserzeichen entfernen (sichtbar, unsichtbar, Metadaten)",
        "identify": "Identifizieren…", "classify": "Foto klassifizieren…",
        "visible": "Sichtbare Marke entfernen…", "erase": "Bereich löschen…",
        "metadata": "KI-Metadaten…", "invisible": "Unsichtbar entfernen (Diffusion)…",
        "all": "Komplette Pipeline…", "batch": "Ordner verarbeiten (Batch)…",
        "v_identify": "Video: identifizieren…", "v_all": "Video: komplett reinigen…",
        "v_visible": "Video: sichtbare Marke…", "v_metadata": "Video: Metadaten…",
        "v_invisible": "Video: SynthID (Regenerierung)…", "v_batch": "Video: Ordner (Batch)…",
        "run": "Ausführen", "cancel": "Abbrechen", "close": "Schließen", "browse": "Wählen…",
        "output": "Ausgabedatei", "output_dir": "Ausgabeordner",
        "input_dir": "Eingabeordner", "options": "Optionen", "command": "Befehl",
        "processing": "Verarbeitung läuft…", "done": "Erfolgreich abgeschlossen.",
        "failed": "Fehlgeschlagen (Code {code}).", "cancelled": "Abgebrochen.",
        "json": "JSON-Ausgabe", "no_visible": "Nur Metadaten (keine Pixel-Detektoren)",
        "mark": "Marke", "backend": "Füll-Backend", "sensitivity": "Strikte Sensitivität",
        "no_detect": "Ohne Erkennung erzwingen (--no-detect)", "keep_metadata": "Metadaten behalten",
        "region": "Region(en) x,y,b,h (mit ; trennen)", "region_hint": "Z. B. 1640,1930,400,100 ; 20,20,180,60",
        "dilate": "Masken-Erweiterung (px)", "inpaint": "cv2-Methode",
        "op_check": "Prüfen (--check)", "op_remove": "Entfernen (--remove)",
        "remove_all": "Alles entfernen (--remove-all)", "force": "Erzwingen (--force)",
        "vendor": "Kohorte (vendor)", "pipeline": "Pipeline", "strength": "Stärke (0=auto)",
        "seed": "Seed", "cpu_offload": "CPU-Offload (weniger VRAM)",
        "max_res": "Max. Auflösung (0=nativ)", "tile": "Kacheln (--tile, große Bilder)",
        "mode": "Modus", "with_invisible": "Unsichtbare Regenerierung einschließen",
        "noise_std": "Rauschen (noise-std)", "long_side": "Lange Seite (px)",
        "fps": "FPS (0=Quelle)", "batch_size": "Batch-Größe",
        "temporal": "Zeitliche Konsistenz", "no_temporal": "Zeitliche Konsistenz deaktivieren",
        "suffix_note": "Ohne -o überschreiben Bilder die Quelle; Videos schreiben <source>_clean.",
        "err_no_bin": "`remove-ai-watermarks` wurde im PATH nicht gefunden.",
        "err_no_bin_hint": "Installieren mit:\nuv tool install \"remove-ai-watermarks[all]\"\nDanach Nautilus neu starten (nautilus -q).",
        "err_no_compat": "Keine kompatible Datei ausgewählt.",
        "files": "Datei(en)",
    }
elif _lang.startswith("es"):
    T = {
        "top_menu": "Remove AI Watermarks", "top_tip": "Eliminar marcas de agua IA (visibles, invisibles, metadatos)",
        "identify": "Identificar…", "classify": "Clasificar foto…",
        "visible": "Quitar marca visible…", "erase": "Borrar región…",
        "metadata": "Metadatos IA…", "invisible": "Eliminación invisible (difusión)…",
        "all": "Pipeline completo…", "batch": "Procesar carpeta (batch)…",
        "v_identify": "Vídeo: identificar…", "v_all": "Vídeo: limpieza completa…",
        "v_visible": "Vídeo: marca visible…", "v_metadata": "Vídeo: metadatos…",
        "v_invisible": "Vídeo: SynthID (regeneración)…", "v_batch": "Vídeo: carpeta (batch)…",
        "run": "Ejecutar", "cancel": "Cancelar", "close": "Cerrar", "browse": "Elegir…",
        "output": "Archivo de salida", "output_dir": "Carpeta de salida",
        "input_dir": "Carpeta de entrada", "options": "Opciones", "command": "Comando",
        "processing": "Procesando…", "done": "Completado con éxito.",
        "failed": "Falló (código {code}).", "cancelled": "Cancelado.",
        "json": "Salida JSON", "no_visible": "Solo metadatos (sin detectores de píxeles)",
        "mark": "Marca", "backend": "Motor de relleno", "sensitivity": "Sensibilidad estricta",
        "no_detect": "Forzar sin detección (--no-detect)", "keep_metadata": "Conservar metadatos",
        "region": "Regione(s) x,y,an,al (separadas por ;)", "region_hint": "Ej. 1640,1930,400,100 ; 20,20,180,60",
        "dilate": "Dilatar máscara (px)", "inpaint": "Método cv2",
        "op_check": "Inspeccionar (--check)", "op_remove": "Eliminar (--remove)",
        "remove_all": "Eliminar todo (--remove-all)", "force": "Forzar (--force)",
        "vendor": "Cohorte (vendor)", "pipeline": "Pipeline", "strength": "Fuerza (0=auto)",
        "seed": "Seed", "cpu_offload": "CPU offload (menos VRAM)",
        "max_res": "Resolución máx. (0=nativa)", "tile": "Mosaicos (--tile, imágenes grandes)",
        "mode": "Modo", "with_invisible": "Incluir regeneración invisible",
        "noise_std": "Ruido (noise-std)", "long_side": "Lado mayor (px)",
        "fps": "FPS (0=origen)", "batch_size": "Tamaño de lote",
        "temporal": "Consistencia temporal", "no_temporal": "Desactivar consistencia temporal",
        "suffix_note": "Sin -o, las imágenes sobrescriben el origen; los vídeos escriben <source>_clean.",
        "err_no_bin": "No se encontró `remove-ai-watermarks` en el PATH.",
        "err_no_bin_hint": "Instálelo con:\nuv tool install \"remove-ai-watermarks[all]\"\nluego reinicie Nautilus (nautilus -q).",
        "err_no_compat": "Ningún archivo compatible seleccionado.",
        "files": "Archivo(s)",
    }
elif _lang.startswith("pt"):
    T = {
        "top_menu": "Remove AI Watermarks", "top_tip": "Remover marcas d'água de IA (visível, invisível, metadados)",
        "identify": "Identificar…", "classify": "Classificar foto…",
        "visible": "Remover marca visível…", "erase": "Apagar região…",
        "metadata": "Metadados IA…", "invisible": "Remoção invisível (difusão)…",
        "all": "Pipeline completo…", "batch": "Processar pasta (batch)…",
        "v_identify": "Vídeo: identificar…", "v_all": "Vídeo: limpeza completa…",
        "v_visible": "Vídeo: marca visível…", "v_metadata": "Vídeo: metadados…",
        "v_invisible": "Vídeo: SynthID (regeneração)…", "v_batch": "Vídeo: pasta (batch)…",
        "run": "Executar", "cancel": "Cancelar", "close": "Fechar", "browse": "Escolher…",
        "output": "Arquivo de saída", "output_dir": "Pasta de saída",
        "input_dir": "Pasta de entrada", "options": "Opções", "command": "Comando",
        "processing": "Processando…", "done": "Concluído com sucesso.",
        "failed": "Falhou (código {code}).", "cancelled": "Cancelado.",
        "json": "Saída JSON", "no_visible": "Só metadados (sem detectores de pixel)",
        "mark": "Marca", "backend": "Motor de preenchimento", "sensitivity": "Sensibilidade estrita",
        "no_detect": "Forçar sem detecção (--no-detect)", "keep_metadata": "Manter metadados",
        "region": "Região(ões) x,y,l,a (separadas por ;)", "region_hint": "Ex. 1640,1930,400,100 ; 20,20,180,60",
        "dilate": "Dilatar máscara (px)", "inpaint": "Método cv2",
        "op_check": "Inspecionar (--check)", "op_remove": "Remover (--remove)",
        "remove_all": "Remover tudo (--remove-all)", "force": "Forçar (--force)",
        "vendor": "Coorte (vendor)", "pipeline": "Pipeline", "strength": "Força (0=auto)",
        "seed": "Seed", "cpu_offload": "CPU offload (menos VRAM)",
        "max_res": "Resolução máx. (0=nativa)", "tile": "Ladrilhos (--tile, imagens grandes)",
        "mode": "Modo", "with_invisible": "Incluir regeneração invisível",
        "noise_std": "Ruído (noise-std)", "long_side": "Lado maior (px)",
        "fps": "FPS (0=origem)", "batch_size": "Tamanho do lote",
        "temporal": "Consistência temporal", "no_temporal": "Desativar consistência temporal",
        "suffix_note": "Sem -o, imagens sobrescrevem a origem; vídeos gravam <source>_clean.",
        "err_no_bin": "`remove-ai-watermarks` não encontrado no PATH.",
        "err_no_bin_hint": "Instale com:\nuv tool install \"remove-ai-watermarks[all]\"\ndepois reinicie o Nautilus (nautilus -q).",
        "err_no_compat": "Nenhum arquivo compatível selecionado.",
        "files": "Arquivo(s)",
    }
else:
    T = {
        "top_menu": "Remove AI Watermarks", "top_tip": "Remove AI watermarks (visible, invisible, metadata)",
        "identify": "Identify…", "classify": "Classify photo…",
        "visible": "Remove visible mark…", "erase": "Erase region…",
        "metadata": "AI metadata…", "invisible": "Invisible removal (diffusion)…",
        "all": "Full pipeline…", "batch": "Process folder (batch)…",
        "v_identify": "Video: identify…", "v_all": "Video: full clean…",
        "v_visible": "Video: visible mark…", "v_metadata": "Video: metadata…",
        "v_invisible": "Video: SynthID (regen)…", "v_batch": "Video: folder (batch)…",
        "run": "Run", "cancel": "Cancel", "close": "Close", "browse": "Browse…",
        "output": "Output file", "output_dir": "Output folder",
        "input_dir": "Input folder", "options": "Options", "command": "Command",
        "processing": "Processing…", "done": "Completed successfully.",
        "failed": "Failed (exit code {code}).", "cancelled": "Cancelled.",
        "json": "JSON output", "no_visible": "Metadata only (no pixel detectors)",
        "mark": "Mark", "backend": "Fill backend", "sensitivity": "Strict sensitivity",
        "no_detect": "Force without detection (--no-detect)", "keep_metadata": "Keep metadata",
        "region": "Region(s) x,y,w,h (separated by ;)", "region_hint": "E.g. 1640,1930,400,100 ; 20,20,180,60",
        "dilate": "Mask dilate (px)", "inpaint": "cv2 method",
        "op_check": "Inspect (--check)", "op_remove": "Remove (--remove)",
        "remove_all": "Remove all (--remove-all)", "force": "Force (--force)",
        "vendor": "Cohort (vendor)", "pipeline": "Pipeline", "strength": "Strength (0=auto)",
        "seed": "Seed", "cpu_offload": "CPU offload (less VRAM)",
        "max_res": "Max resolution (0=native)", "tile": "Tiles (--tile, large images)",
        "mode": "Mode", "with_invisible": "Include invisible regeneration",
        "noise_std": "Noise (noise-std)", "long_side": "Long side (px)",
        "fps": "FPS (0=source)", "batch_size": "Batch size",
        "temporal": "Temporal consistency", "no_temporal": "Disable temporal consistency",
        "suffix_note": "Without -o, images overwrite source; videos write <source>_clean.",
        "err_no_bin": "`remove-ai-watermarks` was not found on PATH.",
        "err_no_bin_hint": "Install it with:\nuv tool install \"remove-ai-watermarks[all]\"\nthen restart Nautilus (nautilus -q).",
        "err_no_compat": "No compatible file selected.",
        "files": "File(s)",
    }

RAIW_BIN = shutil.which("remove-ai-watermarks")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif",
              ".gif", ".avif", ".heic", ".heif", ".jxl"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".flv"}

# Mark names known from upstream docs (docs/supported-signals.md + cli.md).
# `--mark auto` is the default; explicit names restrict detection to one provider.
IMAGE_VISIBLE_MARKS = ["auto", "gemini", "doubao", "jimeng", "qwen", "kling",
                       "yuanbao", "baidu", "liblib", "runninghub",
                       "microsoft-badge", "samsung", "generic-ai", "openart"]
VIDEO_MARKS = ["auto", "sora", "veo", "seedance", "doubao", "dola",
               "hailuo", "kling"]
BACKENDS = ["auto", "cv2", "migan", "lama"]
INPAINT_METHODS = ["telea", "ns"]
PIPELINES = ["qwen-zimage", "sdxl-zimage", "chroma-zimage", "auto"]
VENDORS = ["auto", "openai", "google", "microsoft", "meta", "bytedance"]
BATCH_MODES = ["visible", "invisible", "metadata", "all"]
VIDEO_BATCH_MODES = ["visible", "metadata", "all"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nautilus_window():
    app = Gtk.Application.get_default()
    if app is None:
        return None
    win = app.get_active_window()
    if win is not None:
        return win
    wins = app.get_windows()
    return wins[0] if wins else None


def _show_message(msg: str):
    Gtk.AlertDialog(message=msg).show(_nautilus_window())


def _check_bin() -> bool:
    global RAIW_BIN
    RAIW_BIN = shutil.which("remove-ai-watermarks")
    if not RAIW_BIN:
        _show_message(f"{T['err_no_bin']}\n\n{T['err_no_bin_hint']}")
        return False
    return True


def _suggest_output(path: str) -> str:
    base, ext = os.path.splitext(path)
    return f"{base}_clean{ext}"


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _is_image(path: str) -> bool:
    return _ext(path) in IMAGE_EXTS


def _is_video(path: str) -> bool:
    return _ext(path) in VIDEO_EXTS


def _paths_from_files(files) -> list:
    out = []
    for f in files:
        try:
            if f.get_uri_scheme() != "file":
                continue
            p = f.get_location().get_path()
            if p:
                out.append(p)
        except Exception:
            continue
    return out


def _parse_regions(text: str) -> list:
    """'x,y,w,h ; x,y,w,h' -> ['x,y,w,h', ...], raising ValueError on bad input."""
    regs = []
    for chunk in (text or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) != 4:
            raise ValueError(chunk)
        nums = [int(p) for p in parts]  # may raise
        if nums[2] <= 0 or nums[3] <= 0:
            raise ValueError(chunk)
        regs.append(f"{nums[0]},{nums[1]},{nums[2]},{nums[3]}")
    return regs


# ---------------------------------------------------------------------------
# Runner dialog: shows command + live log, cancellable
# ---------------------------------------------------------------------------

class RunDialog(Adw.Window):
    __gtype_name__ = "RaiwRunDialog"

    def __init__(self, argv: list, cwd: str | None = None):
        super().__init__(title=T["top_menu"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(620, 460)
        self._argv = argv
        self._cwd = cwd or os.path.expanduser("~")
        self._proc = None
        self._cancelled = False

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14); box.set_margin_bottom(14)
        box.set_margin_start(16); box.set_margin_end(16)

        cmd_lbl = Gtk.Label(label=f"{T['command']}: {shlex.join(argv)}")
        cmd_lbl.set_halign(Gtk.Align.START)
        cmd_lbl.set_wrap(True)
        cmd_lbl.set_ellipsize(Pango.EllipsizeMode.NONE)
        cmd_lbl.add_css_class("dim-label")
        cmd_lbl.set_selectable(True)
        box.append(cmd_lbl)

        self._status = Gtk.Label(label=T["processing"])
        self._status.set_halign(Gtk.Align.START)
        box.append(self._status)

        self._bar = Gtk.ProgressBar()
        self._bar.set_pulse_step(0.08)
        box.append(self._bar)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(220)
        self._buf = Gtk.TextBuffer()
        view = Gtk.TextView.new_with_buffer(self._buf)
        view.set_editable(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.set_child(view)
        box.append(scroll)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        self._cancel_btn = Gtk.Button(label=T["cancel"])
        self._cancel_btn.connect("clicked", self._on_cancel)
        btn_box.append(self._cancel_btn)
        self._close_btn = Gtk.Button(label=T["close"])
        self._close_btn.set_visible(False)
        self._close_btn.add_css_class("suggested-action")
        self._close_btn.connect("clicked", lambda _: self.destroy())
        btn_box.append(self._close_btn)
        box.append(btn_box)

        tv.set_content(box)
        self.set_content(tv)
        threading.Thread(target=self._run, daemon=True).start()
        GObject.timeout_add(90, self._pulse)

    def _pulse(self):
        if self._proc is None or self._proc.poll() is None:
            self._bar.pulse()
            return True
        return False

    def _log(self, text: str):
        GLib.idle_add(self._append, text)

    def _append(self, text: str):
        end = self._buf.get_end_iter()
        self._buf.insert(end, text)
        return False

    def _on_cancel(self, _btn):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def _run(self):
        try:
            self._proc = subprocess.Popen(
                self._argv, cwd=self._cwd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._log(f"{exc}\n")
            GLib.idle_add(self._finish, -1)
            return
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self._log(line)
        rc = self._proc.wait()
        GLib.idle_add(self._finish, rc)

    def _finish(self, rc: int):
        self._bar.set_fraction(1.0 if rc == 0 else 0.0)
        if self._cancelled:
            self._status.set_text(T["cancelled"])
        elif rc == 0:
            self._status.set_text(T["done"])
        else:
            self._status.set_text(T["failed"].format(code=rc))
        self._cancel_btn.set_visible(False)
        self._close_btn.set_visible(True)
        return False


# ---------------------------------------------------------------------------
# Base options dialog with small widget builders
# ---------------------------------------------------------------------------

class _BaseDialog(Adw.Window):
    __gtype_name__ = "RaiwBaseDialog"

    def __init__(self, title: str, subtitle: str, files_label: str):
        super().__init__(title=title)
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(520, -1)

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._box.set_margin_top(14); self._box.set_margin_bottom(14)
        self._box.set_margin_start(18); self._box.set_margin_end(18)

        sub = Gtk.Label(label=subtitle)
        sub.set_halign(Gtk.Align.START)
        sub.set_wrap(True)
        sub.add_css_class("dim-label")
        self._box.append(sub)

        fl = Gtk.Label(label=f"{T['files']}: {files_label}")
        fl.set_halign(Gtk.Align.START)
        fl.set_wrap(True)
        fl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self._box.append(fl)
        self._box.append(Gtk.Separator())
        tv.set_content(self._box)
        self.set_content(tv)

    def _lbl(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=f"<b>{text}</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        self._box.append(lbl)
        return lbl

    def _dropdown(self, label: str, items: list, active: int = 0) -> Gtk.DropDown:
        self._lbl(label)
        dd = Gtk.DropDown.new_from_strings(items)
        dd.set_selected(active)
        self._box.append(dd)
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
        row.append(lbl)
        row.append(sw)
        self._box.append(row)
        return sw

    def _spin(self, label: str, lo: float, hi: float, step: float,
              value: float, digits: int = 0) -> Gtk.SpinButton:
        self._lbl(label)
        adj = Gtk.Adjustment(value=value, lower=lo, upper=hi,
                             step_increment=step, page_increment=step * 10)
        sp = Gtk.SpinButton(adjustment=adj, digits=digits)
        self._box.append(sp)
        return sp

    def _entry(self, label: str, text: str = "",
               hint: str = "") -> Gtk.Entry:
        self._lbl(label)
        e = Gtk.Entry()
        e.set_text(text)
        if hint:
            e.set_placeholder_text(hint)
        self._box.append(e)
        return e

    def _path_row(self, label: str, initial: str,
                  save: bool = True) -> Gtk.Entry:
        self._lbl(label)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.Entry()
        entry.set_text(initial)
        entry.set_hexpand(True)
        row.append(entry)
        btn = Gtk.Button(label=T["browse"])
        btn.connect("clicked", self._on_browse, entry, save)
        row.append(btn)
        self._box.append(row)
        return entry

    def _on_browse(self, _btn, entry: Gtk.Entry, save: bool):
        dlg = Gtk.FileDialog(title=T["output"])
        try:
            cur = entry.get_text().strip()
            if cur:
                base = os.path.dirname(cur) or os.path.expanduser("~")
                dlg.set_initial_folder(Gio.File.new_for_path(base))
                dlg.set_initial_name(os.path.basename(cur))
        except Exception:  # noqa: BLE001
            pass
        if save:
            dlg.save(_nautilus_window(), None, self._on_save_done, entry)
        else:
            dlg.select_folder(_nautilus_window(), None, self._on_folder_done, entry)

    def _on_save_done(self, dlg, result, entry: Gtk.Entry):
        try:
            entry.set_text(dlg.save_finish(result).get_path())
        except Exception:  # noqa: BLE001
            pass

    def _on_folder_done(self, dlg, result, entry: Gtk.Entry):
        try:
            entry.set_text(dlg.select_folder_finish(result).get_path())
        except Exception:  # noqa: BLE001
            pass

    def _note(self, text: str):
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.add_css_class("dim-label")
        self._box.append(lbl)

    def _buttons(self, on_run):
        self._box.append(Gtk.Separator())
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_halign(Gtk.Align.END)
        c = Gtk.Button(label=T["cancel"])
        c.connect("clicked", lambda _: self.destroy())
        box.append(c)
        ok = Gtk.Button(label=T["run"])
        ok.add_css_class("suggested-action")
        ok.connect("clicked", on_run)
        box.append(ok)
        self._box.append(box)


def _short_list(paths: list, limit: int = 3) -> str:
    names = [os.path.basename(p) for p in paths[:limit]]
    s = ", ".join(names)
    if len(paths) > limit:
        s += f" (+{len(paths) - limit})"
    return s


# ---------------------------------------------------------------------------
# Per-command dialogs (one screen per CLI function)
# ---------------------------------------------------------------------------

class IdentifyDialog(_BaseDialog):
    __gtype_name__ = "RaiwIdentifyDialog"

    def __init__(self, paths: list, video: bool = False):
        title = T["v_identify"] if video else T["identify"]
        super().__init__(title, title, _short_list(paths))
        self._paths = paths
        self._video = video
        self._json = self._switch(T["json"], False)
        self._no_vis = self._switch(T["no_visible"], False)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        argv = ["remove-ai-watermarks"]
        if self._video:
            argv += ["video", "identify"]
        else:
            argv += ["identify"]
        if self._json.get_active():
            argv.append("--json")
        if self._no_vis.get_active():
            argv.append("--no-visible")
        argv += self._paths
        self.destroy()
        RunDialog(argv).present()


class ClassifyDialog(_BaseDialog):
    __gtype_name__ = "RaiwClassifyDialog"

    def __init__(self, paths: list):
        super().__init__(T["classify"], T["classify"], _short_list(paths))
        self._paths = paths
        self._json = self._switch(T["json"], False)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        argv = ["remove-ai-watermarks", "classify"]
        if self._json.get_active():
            argv.append("--json")
        argv += self._paths
        self.destroy()
        RunDialog(argv).present()


class VisibleDialog(_BaseDialog):
    __gtype_name__ = "RaiwVisibleDialog"

    def __init__(self, paths: list):
        super().__init__(T["visible"], T["visible"], _short_list(paths))
        self._paths = paths
        self._mark = self._dropdown(T["mark"], IMAGE_VISIBLE_MARKS, 0)
        self._backend = self._dropdown(T["backend"], BACKENDS, 0)
        self._strict = self._switch(T["sensitivity"], False)
        self._no_detect = self._switch(T["no_detect"], False)
        self._keep = self._switch(T["keep_metadata"], False)
        if len(paths) == 1:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        else:
            self._out = None
            self._note(T["suffix_note"])
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        mark = IMAGE_VISIBLE_MARKS[self._mark.get_selected()]
        backend = BACKENDS[self._backend.get_selected()]
        for src in self._paths:
            argv = ["remove-ai-watermarks", "visible", src]
            if mark != "auto":
                argv += ["--mark", mark]
            if backend != "auto":
                argv += ["--backend", backend]
            if self._strict.get_active():
                argv += ["--sensitivity", "strict"]
            if self._no_detect.get_active():
                argv += ["--no-detect"]
            if self._keep.get_active():
                argv += ["--keep-metadata"]
            if self._out is not None:
                out = self._out.get_text().strip()
                if out:
                    argv += ["-o", out]
            else:
                argv += ["-o", _suggest_output(src)]
            RunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.destroy()


class EraseDialog(_BaseDialog):
    __gtype_name__ = "RaiwEraseDialog"

    def __init__(self, paths: list):
        super().__init__(T["erase"], T["erase"], _short_list(paths))
        self._paths = paths
        self._region = self._entry(T["region"], "", T["region_hint"])
        self._backend = self._dropdown(T["backend"], BACKENDS, 0)
        self._dilate = self._spin(T["dilate"], 0, 50, 1, 3)
        self._inpaint = self._dropdown(T["inpaint"], INPAINT_METHODS, 0)
        self._keep = self._switch(T["keep_metadata"], False)
        if len(paths) == 1:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        else:
            self._out = None
            self._note(T["suffix_note"])
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        try:
            regs = _parse_regions(self._region.get_text())
        except ValueError:
            _show_message(T["region_hint"])
            return
        if not regs:
            _show_message(T["region_hint"])
            return
        backend = BACKENDS[self._backend.get_selected()]
        inpaint = INPAINT_METHODS[self._inpaint.get_selected()]
        for src in self._paths:
            argv = ["remove-ai-watermarks", "erase", src]
            for r in regs:
                argv += ["--region", r]
            if backend != "auto":
                argv += ["--backend", backend]
            argv += ["--dilate", str(int(self._dilate.get_value()))]
            if backend in ("auto", "cv2"):
                argv += ["--inpaint-method", inpaint]
            if self._keep.get_active():
                argv += ["--keep-metadata"]
            argv += ["-o", self._out.get_text().strip()
                     if self._out is not None and self._out.get_text().strip()
                     else _suggest_output(src)]
            RunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.destroy()


class MetadataDialog(_BaseDialog):
    __gtype_name__ = "RaiwMetadataDialog"

    def __init__(self, paths: list, video: bool = False):
        title = T["v_metadata"] if video else T["metadata"]
        super().__init__(title, title, _short_list(paths))
        self._paths = paths
        self._video = video
        self._mode = self._dropdown(T["options"],
                                    [T["op_check"], T["op_remove"]], 1)
        self._remove_all = self._switch(T["remove_all"], False)
        if len(paths) == 1 and not video:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        elif len(paths) == 1 and video:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        else:
            self._out = None
            self._note(T["suffix_note"])
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        is_remove = self._mode.get_selected() == 1
        for src in self._paths:
            if self._video:
                argv = ["remove-ai-watermarks", "video", "metadata", src]
            else:
                argv = ["remove-ai-watermarks", "metadata", src]
            if is_remove:
                argv.append("--remove")
                if not self._video and self._remove_all.get_active():
                    argv.append("--remove-all")
                if self._out is not None and self._out.get_text().strip():
                    argv += ["-o", self._out.get_text().strip()]
                elif self._video or len(self._paths) > 1:
                    argv += ["-o", _suggest_output(src)]
            else:
                argv.append("--check")
            RunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.destroy()


class InvisibleDialog(_BaseDialog):
    __gtype_name__ = "RaiwInvisibleDialog"

    def __init__(self, paths: list, full: bool = False):
        title = T["all"] if full else T["invisible"]
        super().__init__(title, title, _short_list(paths))
        self._paths = paths
        self._full = full
        if full:
            self._mark = self._dropdown(T["mark"], IMAGE_VISIBLE_MARKS, 0)
            self._backend = self._dropdown(T["backend"], BACKENDS, 0)
        self._force = self._switch(T["force"], True)
        self._vendor = self._dropdown(T["vendor"], VENDORS, 0)
        self._pipeline = self._dropdown(T["pipeline"], PIPELINES, 0)
        self._strength = self._spin(T["strength"], 0, 1, 0.05, 0.0, digits=2)
        self._seed = self._spin(T["seed"], 0, 999999, 1, 0)
        self._cpu = self._switch(T["cpu_offload"], False)
        self._maxres = self._spin(T["max_res"], 0, 8192, 256, 0)
        self._tile = self._switch(T["tile"], False)
        self._keep = self._switch(T["keep_metadata"], False)
        if len(paths) == 1:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        else:
            self._out = None
            self._note(T["suffix_note"])
        self._buttons(self._on_run)

    def _diffusion_opts(self, argv: list) -> list:
        vendor = VENDORS[self._vendor.get_selected()]
        pipeline = PIPELINES[self._pipeline.get_selected()]
        if vendor != "auto":
            argv += ["--vendor", vendor]
        if self._full or PIPELINES[self._pipeline.get_selected()] != "qwen-zimage":
            # `all` defaults like `invisible`; always pass explicit non-default pipeline
            pass
        if pipeline != "qwen-zimage":
            argv += ["--pipeline", pipeline]
        strength = self._strength.get_value()
        if strength > 0:
            argv += ["--strength", f"{strength:.2f}"]
        argv += ["--seed", str(int(self._seed.get_value()))]
        if self._cpu.get_active():
            argv.append("--cpu-offload")
        maxres = int(self._maxres.get_value())
        if maxres > 0:
            argv += ["--max-resolution", str(maxres)]
        if self._tile.get_active():
            argv.append("--tile")
        if self._keep.get_active():
            argv += ["--keep-metadata"]
        return argv

    def _on_run(self, _btn):
        for src in self._paths:
            argv = ["remove-ai-watermarks",
                    "all" if self._full else "invisible", src]
            if self._full:
                mark = IMAGE_VISIBLE_MARKS[self._mark.get_selected()]
                backend = BACKENDS[self._backend.get_selected()]
                if mark != "auto":
                    argv += ["--mark", mark]
                if backend != "auto":
                    argv += ["--backend", backend]
            if self._force.get_active():
                argv.append("--force")
            argv = self._diffusion_opts(argv)
            argv += ["-o", self._out.get_text().strip()
                     if self._out is not None and self._out.get_text().strip()
                     else _suggest_output(src)]
            RunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.destroy()


class BatchDialog(_BaseDialog):
    __gtype_name__ = "RaiwBatchDialog"

    def __init__(self, dirs: list, video: bool = False):
        title = T["v_batch"] if video else T["batch"]
        super().__init__(title, title, _short_list(dirs))
        self._dirs = dirs
        self._video = video
        modes = VIDEO_BATCH_MODES if video else BATCH_MODES
        self._mode = self._dropdown(T["mode"], modes, len(modes) - 1)
        first = dirs[0] if dirs else os.path.expanduser("~")
        default_out = f"{first.rstrip('/')}_clean" if len(dirs) == 1 else first
        self._outdir = self._path_row(T["output_dir"], default_out, False)
        if not video:
            self._pipeline = self._dropdown(T["pipeline"], PIPELINES, 0)
            self._force = self._switch(T["force"], True)
            self._cpu = self._switch(T["cpu_offload"], False)
        else:
            self._with_inv = self._switch(T["with_invisible"], False)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        outdir = self._outdir.get_text().strip()
        for d in self._dirs:
            if self._video:
                modes = VIDEO_BATCH_MODES
                argv = ["remove-ai-watermarks", "video", "batch", d,
                        "--mode", modes[self._mode.get_selected()]]
                if outdir:
                    argv += ["--output-dir", outdir]
                if self._with_inv.get_active():
                    argv.append("--invisible")
            else:
                modes = BATCH_MODES
                argv = ["remove-ai-watermarks", "batch", d,
                        "--mode", modes[self._mode.get_selected()]]
                if outdir:
                    argv += ["--output-dir", outdir]
                pipeline = PIPELINES[self._pipeline.get_selected()]
                if pipeline != "qwen-zimage":
                    argv += ["--pipeline", pipeline]
                if self._force.get_active():
                    argv.append("--force")
                if self._cpu.get_active():
                    argv.append("--cpu-offload")
            RunDialog(argv, cwd=d).present()
        self.destroy()


class VideoVisibleDialog(_BaseDialog):
    __gtype_name__ = "RaiwVideoVisibleDialog"

    def __init__(self, paths: list):
        super().__init__(T["v_visible"], T["v_visible"], _short_list(paths))
        self._paths = paths
        self._mark = self._dropdown(T["mark"], VIDEO_MARKS, 0)
        self._backend = self._dropdown(T["backend"], BACKENDS, 0)
        self._no_temporal = self._switch(T["no_temporal"], False)
        self._keep = self._switch(T["keep_metadata"], False)
        if len(paths) == 1:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        else:
            self._out = None
            self._note(T["suffix_note"])
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        mark = VIDEO_MARKS[self._mark.get_selected()]
        backend = BACKENDS[self._backend.get_selected()]
        for src in self._paths:
            argv = ["remove-ai-watermarks", "video", "visible", src]
            if mark != "auto":
                argv += ["--mark", mark]
            if backend != "auto":
                argv += ["--backend", backend]
            if self._no_temporal.get_active():
                argv.append("--no-temporal-consistency")
            if self._keep.get_active():
                argv.append("--keep-metadata")
            argv += ["-o", self._out.get_text().strip()
                     if self._out is not None and self._out.get_text().strip()
                     else _suggest_output(src)]
            RunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.destroy()


class VideoAllDialog(_BaseDialog):
    __gtype_name__ = "RaiwVideoAllDialog"

    def __init__(self, paths: list):
        super().__init__(T["v_all"], T["v_all"], _short_list(paths))
        self._paths = paths
        self._with_inv = self._switch(T["with_invisible"], False)
        if len(paths) == 1:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        else:
            self._out = None
            self._note(T["suffix_note"])
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        for src in self._paths:
            argv = ["remove-ai-watermarks", "video", "all", src]
            argv += ["-o", self._out.get_text().strip()
                     if self._out is not None and self._out.get_text().strip()
                     else _suggest_output(src)]
            if self._with_inv.get_active():
                argv.append("--invisible")
            RunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.destroy()


class VideoInvisibleDialog(_BaseDialog):
    __gtype_name__ = "RaiwVideoInvisibleDialog"

    def __init__(self, paths: list):
        super().__init__(T["v_invisible"], T["v_invisible"], _short_list(paths))
        self._paths = paths
        self._noise = self._spin(T["noise_std"], 0.01, 1.0, 0.01, 0.15, digits=2)
        self._longside = self._spin(T["long_side"], 256, 4096, 64, 1024)
        self._fps = self._spin(T["fps"], 0, 120, 1, 0)
        self._bsize = self._spin(T["batch_size"], 1, 64, 1, 8)
        self._seed = self._spin(T["seed"], 0, 999999, 1, 0)
        if len(paths) == 1:
            self._out = self._path_row(T["output"], _suggest_output(paths[0]), True)
        else:
            self._out = None
            self._note(T["suffix_note"])
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        for src in self._paths:
            argv = ["remove-ai-watermarks", "video", "invisible", src,
                    "--noise-std", f"{self._noise.get_value():.2f}",
                    "--long-side", str(int(self._longside.get_value())),
                    "--batch-size", str(int(self._bsize.get_value())),
                    "--seed", str(int(self._seed.get_value()))]
            fps = int(self._fps.get_value())
            if fps > 0:
                argv += ["--fps", str(fps)]
            argv += ["-o", self._out.get_text().strip()
                     if self._out is not None and self._out.get_text().strip()
                     else _suggest_output(src)]
            RunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.destroy()


# ---------------------------------------------------------------------------
# Nautilus extension with submenu
# ---------------------------------------------------------------------------

class RemoveAIWatermarksExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "RemoveAIWatermarksExtension"

    def _classify(self, files):
        paths = _paths_from_files(files)
        images = [p for p in paths if os.path.isfile(p) and _is_image(p)]
        videos = [p for p in paths if os.path.isfile(p) and _is_video(p)]
        dirs = [p for p in paths if os.path.isdir(p)]
        # Reject anything else (incompatible regular files, non-file URIs)
        for p in paths:
            if os.path.isfile(p) and not (_is_image(p) or _is_video(p)):
                return [], [], []
            if not os.path.isfile(p) and not os.path.isdir(p):
                return [], [], []
        if not (images or videos or dirs):
            return [], [], []
        return images, videos, dirs

    def _add(self, submenu, name, label, cb, *args):
        item = Nautilus.MenuItem(
            name=f"RemoveAIWatermarks::{name}",
            label=label,
            tip=T["top_tip"],
        )
        item.connect("activate", cb, *args)
        submenu.append_item(item)

    def _submenu_for(self, images, videos, dirs):
        top = Nautilus.MenuItem(
            name="RemoveAIWatermarks::Top",
            label=T["top_menu"],
            tip=T["top_tip"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)
        files = images + videos

        if files:
            self._add(submenu, "Identify", T["identify"],
                      lambda *_: IdentifyDialog(files, False).present()
                      if _check_bin() else None)
        if images:
            self._add(submenu, "Classify", T["classify"],
                      lambda *_: ClassifyDialog(images).present()
                      if _check_bin() else None)
            self._add(submenu, "Visible", T["visible"],
                      lambda *_: VisibleDialog(images).present()
                      if _check_bin() else None)
            if len(images) >= 1:
                self._add(submenu, "Erase", T["erase"],
                          lambda *_: EraseDialog(images).present()
                          if _check_bin() else None)
            self._add(submenu, "Invisible", T["invisible"],
                      lambda *_: InvisibleDialog(images, False).present()
                      if _check_bin() else None)
            self._add(submenu, "All", T["all"],
                      lambda *_: InvisibleDialog(images, True).present()
                      if _check_bin() else None)
        if files:
            self._add(submenu, "Metadata", T["metadata"],
                      lambda *_: MetadataDialog(files, False).present()
                      if _check_bin() else None)
        if videos:
            self._add(submenu, "VideoIdentify", T["v_identify"],
                      lambda *_: IdentifyDialog(videos, True).present()
                      if _check_bin() else None)
            self._add(submenu, "VideoAll", T["v_all"],
                      lambda *_: VideoAllDialog(videos).present()
                      if _check_bin() else None)
            self._add(submenu, "VideoVisible", T["v_visible"],
                      lambda *_: VideoVisibleDialog(videos).present()
                      if _check_bin() else None)
            self._add(submenu, "VideoMetadata", T["v_metadata"],
                      lambda *_: MetadataDialog(videos, True).present()
                      if _check_bin() else None)
            self._add(submenu, "VideoInvisible", T["v_invisible"],
                      lambda *_: VideoInvisibleDialog(videos).present()
                      if _check_bin() else None)
        if dirs:
            self._add(submenu, "Batch", T["batch"],
                      lambda *_: BatchDialog(dirs, False).present()
                      if _check_bin() else None)
            self._add(submenu, "VideoBatch", T["v_batch"],
                      lambda *_: BatchDialog(dirs, True).present()
                      if _check_bin() else None)
        return [top]

    def get_file_items(self, files):
        if not files:
            return []
        images, videos, dirs = self._classify(files)
        if not (images or videos or dirs):
            return []
        return self._submenu_for(images, videos, dirs)

    def get_background_items(self, folder):
        try:
            path = folder.get_location().get_path() if folder else None
        except Exception:  # noqa: BLE001
            path = None
        if not path or not os.path.isdir(path):
            return []
        return self._submenu_for([], [], [path])
