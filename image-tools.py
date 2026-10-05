#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Image Tools – Nautilus Python Extension
# AUTHOR: Tof
# VERSION: 1.0
# LICENSE: GNU General Public License v3.0
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# NAME: Image Tools – Nautilus Python Extension
# DESC: Pillow-based image processing tools in an "Image Tools" submenu
#       (grayscale, invert, crop, circle, resize, combine, watermark, optimize,
#       colorize) plus a nested "Convert image" submenu
#       (PNG/JPEG/WebP/ICO/256px square), an "Annotate" single-image editor
#       (rect/ellipse/arrow/text with Ctrl+Z / Ctrl+Y undo-redo) and a
#       "Remove AI watermarks" submenu bridging every
#       `remove-ai-watermarks` CLI function for images, videos and folders.
# REQUIRES: python3-nautilus (>= 4.0), python3-pil, python3-gi, gir1.2-adw-1,
#           python3-cairo (annotate tool),
#           `remove-ai-watermarks` CLI on PATH (AI watermark entries only),
#           ffmpeg (video entries only).
# INSTALL:
#   cp image-tools.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q
#
# UPSTREAM (AI watermark removal): https://github.com/wiltodelta/remove-ai-watermarks

import os
import io
import locale
import math
import shlex
import shutil
import signal
import subprocess
import threading

import cairo

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass  # Nautilus >= 4.1 pre-loaded by nautilus-python (e.g. Nautilus 50)
from gi.repository import GObject, Gtk, Adw, Gio, Gdk, GLib, Nautilus, Pango

try:
    from PIL import Image, ImageOps, ImageDraw, ImageFont
except ImportError:
    Image = None

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = locale.getlocale()[0] or ""

if _lang.startswith("fr"):
    T = {
        "menu_label":     "Outils d'image",
        "menu_tip":       "Outils de traitement d'image (Pillow)",
        "grayscale":      "Niveaux de gris",
        "invert":         "Négatif",
        "crop":           "Recadrage centré…",
        "circle":         "Cercle",
        "resize":         "Redimensionner…",
        "combine":        "Fusionner les images…",
        "watermark":      "Filigrane…",
        "optimize":       "Optimiser pour le Web…",
        "colorize":        "Coloriser…",
        "colorize_tip":    "Teinter les images en préservant la luminance et l'alpha",
        "cz_title":        "Coloriser les images",
        "cz_color":        "Couleur",
        "cz_strength":     "Intensité",
        "an_label":        "Annoter l'image…",
        "an_tip":          "Annoter cette image : rectangle, ellipse, flèche, texte",
        "an_title":        "Annoter l'image",
        "an_rect":         "Rectangle",
        "an_ellipse":      "Ellipse",
        "an_arrow":        "Flèche",
        "an_text":         "Texte",
        "an_undo":         "Annuler",
        "an_redo":         "Rétablir",
        "an_save":         "Enregistrer",
        "an_save_as":      "Enregistrer sous…",
        "an_thickness":    "Épaisseur",
        "an_opacity":      "Opacité",
        "an_color":        "Couleur",
        "an_text_prompt":  "Saisir le texte",
        "an_text_ok":      "OK",
        "an_text_cancel":  "Annuler",
        "an_zoom_in":      "Zoom avant",
        "an_zoom_out":     "Zoom arrière",
        "an_zoom_fit":     "Ajuster à la fenêtre",
        "an_zoom_reset":   "Taille réelle (100%)",
        "processing":     "Traitement…",
        "done_title":     "Traitement terminé",
        "done_msg":       "{count} image(s) traitée(s) avec succès.",
        "done_failed":    "{count} image(s) traitée(s), {failed} échec(s).",
        "cancel":         "Annuler",
        "ok":             "Appliquer",
        "choose":         "Choisir…",
        "err_pillow":     "Pillow n'est pas installé. Installez-le avec : pip install Pillow",
        "err_empty":      "Le texte du filigrane ne peut pas être vide.",
        "err_choose":     "Veuillez choisir une image de filigrane.",
        "err_combine":    "Sélectionnez au moins deux images.",
        "err_annotate":    "Impossible d’ouvrir cette image dans l’annotateur.",
        "crop_title":     "Recadrage centré",
        "crop_width":     "Largeur",
        "crop_height":    "Hauteur",
        "resize_title":   "Redimensionner",
        "resize_width":   "Largeur",
        "resize_height":  "Hauteur",
        "resize_preset":  "Format prédéfini",
        "resize_custom":  "Personnalisé",
        "resize_keep":    "Conserver les proportions",
        "resize_mode":    "Ajustement",
        "resize_dpi":     "Résolution (DPI)",
        "fit_inside":     "À l'intérieur (bornes max)",
        "fit_fill":       "Remplir (recadrage centré)",
        "fit_stretch":    "Étirer (exact)",
        "resize_info":    "Résultat : {w} × {h} px · {ratio} · {dpi} ppp",
        "resize_nosrc":   "Image source illisible : proportions indisponibles.",
        "optimize_title": "Optimiser pour le Web",
        "optimize_max":   "Dimension max",
        "optimize_qual":  "Qualité",
        "watermark_title": "Filigrane",
        "wm_mode_text":   "Texte",
        "wm_mode_image":  "Image",
        "wm_text_hint":   "Texte du filigrane",
        "wm_pick_image":  "Image du filigrane…",
        "combine_title":  "Fusionner les images",
        "combine_vertical":   "Verticale",
        "combine_horizontal": "Horizontale",
        "s_grayscale":  "-gris",
        "s_invert":     "-négatif",
        "s_crop":       "-recadré",
        "s_circle":     "-cercle",
        "s_resize":     "-redimensionné",
        "s_watermark":  "-filigrané",
        "s_colorize":   "-colorisé",
        # --- Remove AI watermarks (CLI bridge) ---
        "top_menu":        "Supprimer les filigranes IA",
        "top_tip":         "Supprimer les filigranes IA (visible, invisible, métadonnées)",
        "identify":        "Identifier…",
        "classify":        "Classifier la photo…",
        "visible":         "Supprimer marque visible…",
        "erase":           "Effacer une région…",
        "metadata":        "Métadonnées IA…",
        "invisible":       "Suppression invisible (diffusion)…",
        "all":             "Pipeline complet…",
        "batch":           "Traiter un dossier (batch)…",
        "v_identify":      "Vidéo : identifier…",
        "v_all":           "Vidéo : nettoyage complet…",
        "v_visible":       "Vidéo : marque visible…",
        "v_metadata":      "Vidéo : métadonnées…",
        "v_invisible":     "Vidéo : SynthID (régénération)…",
        "v_batch":         "Vidéo : dossier (batch)…",
        "run":             "Exécuter",
        "close":           "Fermer",
        "browse":          "Choisir…",
        "output":          "Fichier de sortie",
        "output_dir":      "Dossier de sortie",
        "input_dir":       "Dossier d'entrée",
        "options":         "Options",
        "command":         "Commande",
        "processing_run":  "Traitement en cours…",
        "done":            "Terminé avec succès.",
        "failed":          "Échec (code {code}).",
        "cancelled":       "Annulé.",
        "json":            "Sortie JSON",
        "no_visible":      "Métadonnées uniquement (sans détecteurs pixel)",
        "mark":            "Marque",
        "backend":         "Moteur de remplissage",
        "sensitivity":     "Sensibilité stricte",
        "no_detect":       "Forcer sans détection (--no-detect)",
        "keep_metadata":   "Garder les métadonnées",
        "region":          "Région(s) x,y,l,h (séparées par ;)",
        "region_hint":     "Ex. 1640,1930,400,100 ; 20,20,180,60",
        "dilate":          "Dilatation du masque (px)",
        "inpaint":         "Méthode cv2",
        "op_check":        "Inspecter (--check)",
        "op_remove":       "Supprimer (--remove)",
        "remove_all":      "Tout supprimer (--remove-all)",
        "force":           "Forcer (--force)",
        "vendor":          "Cohorte (vendor)",
        "pipeline":        "Pipeline",
        "strength":        "Force (0=auto)",
        "seed":            "Seed",
        "cpu_offload":     "CPU offload (moins de VRAM)",
        "max_res":         "Résolution max (0=natif)",
        "tile":            "Tuiles (--tile, grandes images)",
        "mode":            "Mode",
        "with_invisible":  "Inclure régénération invisible",
        "noise_std":       "Bruit (noise-std)",
        "long_side":       "Grand côté (px)",
        "fps":             "FPS (0=source)",
        "batch_size":      "Taille de lot",
        "temporal":        "Cohérence temporelle",
        "no_temporal":     "Désactiver la cohérence temporelle",
        "suffix_note":     "Sans -o, les images écrasent la source ; les vidéos écrivent <source>_clean.",
        "err_no_bin":      "L'outil `remove-ai-watermarks` est introuvable dans le PATH.",
        "err_no_bin_hint": "Installez-le avec :\nuv tool install \"remove-ai-watermarks[all]\"\npuis relancez Nautilus (nautilus -q).",
        "err_no_compat":   "Aucun fichier compatible sélectionné.",
        "files":           "Fichier(s)",
        # --- Convert image (format conversion) ---
        "convert_menu":    "Convertir l'image",
        "convert_tip":     "Convertir les images sélectionnées dans un autre format (Pillow)",
        "cv_png":          "Convertir en PNG",
        "cv_jpeg":         "Convertir en JPEG",
        "cv_webp":         "Convertir en WebP",
        "cv_ico":          "Enregistrer en ICO",
        "cv_square":       "Carré 256×256 PNG",
        "cv_tip_ico":      "Fichier .ico multi-tailles (16–256) — sous Linux, sert surtout "
                           "aux favicons (compatibles partout)",
        "cv_done_msg":     "{count} image(s) convertie(s) avec succès.",
        "cv_done_failed":  "{count} image(s) convertie(s), {failed} échec(s).",
        "cv_nothing":      "Aucune conversion nécessaire — {count} fichier(s) déjà au format cible.",
        "done_skip":       "{skipped} fichier(s) ignoré(s) (déjà au format cible).",
    }
elif _lang.startswith("de"):
    T = {
        "menu_label":     "Bildwerkzeuge",
        "menu_tip":       "Bildbearbeitungswerkzeuge (Pillow)",
        "grayscale":      "Graustufen",
        "invert":         "Negativ",
        "crop":           "Zentriert zuschneiden…",
        "circle":         "Kreis",
        "resize":         "Größe ändern…",
        "combine":        "Bilder zusammenfügen…",
        "watermark":      "Wasserzeichen…",
        "optimize":       "Für Web optimieren…",
        "colorize":        "Colorieren…",
        "colorize_tip":    "Bilder einfärben, dabei Leuchtdichte und Alpha erhalten",
        "cz_title":        "Bilder colorieren",
        "cz_color":        "Farbe",
        "cz_strength":     "Intensität",
        "an_label":        "Bild bearbeiten…",
        "an_tip":          "Dieses Bild annotieren: Rechteck, Ellipse, Pfeil, Text",
        "an_title":        "Bild bearbeiten",
        "an_rect":         "Rechteck",
        "an_ellipse":      "Ellipse",
        "an_arrow":        "Pfeil",
        "an_text":         "Text",
        "an_undo":         "Rückgängig machen",
        "an_redo":         "Wiederherstellen",
        "an_save":         "Speichern",
        "an_save_as":      "Speichern unter…",
        "an_thickness":    "Strichstärke",
        "an_opacity":      "Deckkraft",
        "an_color":        "Farbe",
        "an_text_prompt":  "Text eingeben",
        "an_text_ok":      "OK",
        "an_text_cancel":  "Abbrechen",
        "an_zoom_in":      "Vergrößern",
        "an_zoom_out":     "Verkleinern",
        "an_zoom_fit":     "An Fenster anpassen",
        "an_zoom_reset":   "Originalgröße (100%)",
        "processing":     "Verarbeitung…",
        "done_title":     "Verarbeitung abgeschlossen",
        "done_msg":       "{count} Bild(er) erfolgreich verarbeitet.",
        "done_failed":    "{count} Bild(er) verarbeitet, {failed} fehlgeschlagen.",
        "cancel":         "Abbrechen",
        "ok":             "Anwenden",
        "choose":         "Auswählen…",
        "err_pillow":     "Pillow ist nicht installiert. Installieren Sie es mit: pip install Pillow",
        "err_empty":      "Der Wasserzeichentext darf nicht leer sein.",
        "err_choose":     "Bitte ein Wasserzeichenbild auswählen.",
        "err_combine":    "Wählen Sie mindestens zwei Bilder aus.",
        "err_annotate":    "Diese Bild kann nicht im Annotator geöffnet werden.",
        "crop_title":     "Zentriert zuschneiden",
        "crop_width":     "Breite",
        "crop_height":    "Höhe",
        "resize_title":   "Größe ändern",
        "resize_width":   "Breite",
        "resize_height":  "Höhe",
        "resize_preset":  "Voreinstellung",
        "resize_custom":  "Benutzerdefiniert",
        "resize_keep":    "Seitenverhältnis beibehalten",
        "resize_mode":    "Anpassung",
        "resize_dpi":     "Auflösung (DPI)",
        "fit_inside":     "Einpassen (max. Grenzen)",
        "fit_fill":       "Füllen (zentriert zuschneiden)",
        "fit_stretch":    "Strecken (exakt)",
        "resize_info":    "Ergebnis: {w} × {h} px · {ratio} · {dpi} dpi",
        "resize_nosrc":   "Quelldatei nicht lesbar: Seitenverhältnis unbekannt.",
        "optimize_title": "Für Web optimieren",
        "optimize_max":   "Max. Dimension",
        "optimize_qual":  "Qualität",
        "watermark_title": "Wasserzeichen",
        "wm_mode_text":   "Text",
        "wm_mode_image":  "Bild",
        "wm_text_hint":   "Wasserzeichentext",
        "wm_pick_image":  "Wasserzeichenbild…",
        "combine_title":  "Bilder zusammenfügen",
        "combine_vertical":   "Vertikal",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-graustufen",
        "s_invert":     "-negativ",
        "s_crop":       "-beschnitten",
        "s_circle":     "-kreis",
        "s_resize":     "-skaliert",
        "s_watermark":  "-wasserzeichen",
        "s_colorize":   "-coloriert",
        # --- Remove AI watermarks (CLI bridge) ---
        "top_menu":        "KI-Wasserzeichen entfernen",
        "top_tip":         "KI-Wasserzeichen entfernen (sichtbar, unsichtbar, Metadaten)",
        "identify":        "Identifizieren…",
        "classify":        "Foto klassifizieren…",
        "visible":         "Sichtbare Marke entfernen…",
        "erase":           "Bereich löschen…",
        "metadata":        "KI-Metadaten…",
        "invisible":       "Unsichtbar entfernen (Diffusion)…",
        "all":             "Komplette Pipeline…",
        "batch":           "Ordner verarbeiten (Batch)…",
        "v_identify":      "Video: identifizieren…",
        "v_all":           "Video: komplett reinigen…",
        "v_visible":       "Video: sichtbare Marke…",
        "v_metadata":      "Video: Metadaten…",
        "v_invisible":     "Video: SynthID (Regenerierung)…",
        "v_batch":         "Video: Ordner (Batch)…",
        "run":             "Ausführen",
        "close":           "Schließen",
        "browse":          "Wählen…",
        "output":          "Ausgabedatei",
        "output_dir":      "Ausgabeordner",
        "input_dir":       "Eingabeordner",
        "options":         "Optionen",
        "command":         "Befehl",
        "processing_run":  "Verarbeitung läuft…",
        "done":            "Erfolgreich abgeschlossen.",
        "failed":          "Fehlgeschlagen (Code {code}).",
        "cancelled":       "Abgebrochen.",
        "json":            "JSON-Ausgabe",
        "no_visible":      "Nur Metadaten (keine Pixel-Detektoren)",
        "mark":            "Marke",
        "backend":         "Füll-Backend",
        "sensitivity":     "Strikte Sensitivität",
        "no_detect":       "Ohne Erkennung erzwingen (--no-detect)",
        "keep_metadata":   "Metadaten behalten",
        "region":          "Region(en) x,y,b,h (mit ; trennen)",
        "region_hint":     "Z. B. 1640,1930,400,100 ; 20,20,180,60",
        "dilate":          "Masken-Erweiterung (px)",
        "inpaint":         "cv2-Methode",
        "op_check":        "Prüfen (--check)",
        "op_remove":       "Entfernen (--remove)",
        "remove_all":      "Alles entfernen (--remove-all)",
        "force":           "Erzwingen (--force)",
        "vendor":          "Kohorte (vendor)",
        "pipeline":        "Pipeline",
        "strength":        "Stärke (0=auto)",
        "seed":            "Seed",
        "cpu_offload":     "CPU-Offload (weniger VRAM)",
        "max_res":         "Max. Auflösung (0=nativ)",
        "tile":            "Kacheln (--tile, große Bilder)",
        "mode":            "Modus",
        "with_invisible":  "Unsichtbare Regenerierung einschließen",
        "noise_std":       "Rauschen (noise-std)",
        "long_side":       "Lange Seite (px)",
        "fps":             "FPS (0=Quelle)",
        "batch_size":      "Batch-Größe",
        "temporal":        "Zeitliche Konsistenz",
        "no_temporal":     "Zeitliche Konsistenz deaktivieren",
        "suffix_note":     "Ohne -o überschreiben Bilder die Quelle; Videos schreiben <source>_clean.",
        "err_no_bin":      "`remove-ai-watermarks` wurde im PATH nicht gefunden.",
        "err_no_bin_hint": "Installieren mit:\nuv tool install \"remove-ai-watermarks[all]\"\nDanach Nautilus neu starten (nautilus -q).",
        "err_no_compat":   "Keine kompatible Datei ausgewählt.",
        "files":           "Datei(en)",
        # --- Convert image (format conversion) ---
        "convert_menu":    "Bild konvertieren",
        "convert_tip":     "Ausgewählte Bilder in ein anderes Format konvertieren (Pillow)",
        "cv_png":          "In PNG konvertieren",
        "cv_jpeg":         "In JPEG konvertieren",
        "cv_webp":         "In WebP konvertieren",
        "cv_ico":          "Als ICO speichern",
        "cv_square":       "Quadrat 256×256 PNG",
        "cv_tip_ico":      "Mehrgrößen-.ico (16–256) — unter Linux hauptsächlich für "
                           "Favicons nützlich (plattformübergreifend)",
        "cv_done_msg":     "{count} Bild(er) erfolgreich konvertiert.",
        "cv_done_failed":  "{count} Bild(er) konvertiert, {failed} fehlgeschlagen.",
        "cv_nothing":      "Keine Konvertierung nötig — {count} Datei(en) bereits im Zielformat.",
        "done_skip":       "{skipped} Datei(en) übersprungen (bereits im Zielformat).",
    }
elif _lang.startswith("es"):
    T = {
        "menu_label":     "Herramientas de imagen",
        "menu_tip":       "Herramientas de edición de imágenes (Pillow)",
        "grayscale":      "Escala de grises",
        "invert":         "Negativo",
        "crop":           "Recorte centrado…",
        "circle":         "Círculo",
        "resize":         "Redimensionar…",
        "combine":        "Combinar imágenes…",
        "watermark":      "Marca de agua…",
        "optimize":       "Optimizar para web…",
        "colorize":        "Colorear…",
        "colorize_tip":    "Teñir las imágenes conservando la luminancia y el alfa",
        "cz_title":        "Colorear imágenes",
        "cz_color":        "Color",
        "cz_strength":     "Intensidad",
        "an_label":        "Anotar imagen…",
        "an_tip":          "Anotar esta imagen: rectángulo, elipse, flecha, texto",
        "an_title":        "Anotar imagen",
        "an_rect":         "Rectángulo",
        "an_ellipse":      "Elipse",
        "an_arrow":        "Flecha",
        "an_text":         "Texto",
        "an_undo":         "Deshacer",
        "an_redo":         "Rehacer",
        "an_save":         "Guardar",
        "an_save_as":      "Guardar como…",
        "an_thickness":    "Grosor",
        "an_opacity":      "Opacidad",
        "an_color":        "Color",
        "an_text_prompt":  "Introducir texto",
        "an_text_ok":      "OK",
        "an_text_cancel":  "Cancelar",
        "an_zoom_in":      "Acercar",
        "an_zoom_out":     "Alejar",
        "an_zoom_fit":     "Ajustar a la ventana",
        "an_zoom_reset":   "Tamaño real (100%)",
        "processing":     "Procesando…",
        "done_title":     "Procesamiento completado",
        "done_msg":       "{count} imagen(es) procesada(s) correctamente.",
        "done_failed":    "{count} imagen(es) procesada(s), {failed} fallo(s).",
        "cancel":         "Cancelar",
        "ok":             "Aplicar",
        "choose":         "Elegir…",
        "err_pillow":     "Pillow no está instalado. Instálelo con: pip install Pillow",
        "err_empty":      "El texto de la marca de agua no puede estar vacío.",
        "err_choose":     "Seleccione una imagen de marca de agua.",
        "err_combine":    "Seleccione al menos dos imágenes.",
        "err_annotate":    "No se puede abrir esta imagen en el anotador.",
        "crop_title":     "Recorte centrado",
        "crop_width":     "Ancho",
        "crop_height":    "Alto",
        "resize_title":   "Redimensionar",
        "resize_width":   "Ancho",
        "resize_height":  "Alto",
        "resize_preset":  "Tamaño predefinido",
        "resize_custom":  "Personalizado",
        "resize_keep":    "Mantener proporción",
        "resize_mode":    "Ajuste",
        "resize_dpi":     "Resolución (DPI)",
        "fit_inside":     "Ajustar dentro (límites máx.)",
        "fit_fill":       "Rellenar (recorte centrado)",
        "fit_stretch":    "Estirar (exacto)",
        "resize_info":    "Resultado: {w} × {h} px · {ratio} · {dpi} ppp",
        "resize_nosrc":   "Imagen de origen ilegible: proporción no disponible.",
        "optimize_title": "Optimizar para web",
        "optimize_max":   "Dimensión máx.",
        "optimize_qual":  "Calidad",
        "watermark_title": "Marca de agua",
        "wm_mode_text":   "Texto",
        "wm_mode_image":  "Imagen",
        "wm_text_hint":   "Texto de la marca de agua",
        "wm_pick_image":  "Imagen de marca de agua…",
        "combine_title":  "Combinar imágenes",
        "combine_vertical":   "Vertical",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-grises",
        "s_invert":     "-negativo",
        "s_crop":       "-recortado",
        "s_circle":     "-circulo",
        "s_resize":     "-redimensionada",
        "s_watermark":  "-marca-agua",
        "s_colorize":   "-coloreada",
        # --- Remove AI watermarks (CLI bridge) ---
        "top_menu":        "Eliminar marcas de agua de IA",
        "top_tip":         "Eliminar marcas de agua IA (visibles, invisibles, metadatos)",
        "identify":        "Identificar…",
        "classify":        "Clasificar foto…",
        "visible":         "Quitar marca visible…",
        "erase":           "Borrar región…",
        "metadata":        "Metadatos IA…",
        "invisible":       "Eliminación invisible (difusión)…",
        "all":             "Pipeline completo…",
        "batch":           "Procesar carpeta (batch)…",
        "v_identify":      "Vídeo: identificar…",
        "v_all":           "Vídeo: limpieza completa…",
        "v_visible":       "Vídeo: marca visible…",
        "v_metadata":      "Vídeo: metadatos…",
        "v_invisible":     "Vídeo: SynthID (regeneración)…",
        "v_batch":         "Vídeo: carpeta (batch)…",
        "run":             "Ejecutar",
        "close":           "Cerrar",
        "browse":          "Elegir…",
        "output":          "Archivo de salida",
        "output_dir":      "Carpeta de salida",
        "input_dir":       "Carpeta de entrada",
        "options":         "Opciones",
        "command":         "Comando",
        "processing_run":  "Procesando…",
        "done":            "Completado con éxito.",
        "failed":          "Falló (código {code}).",
        "cancelled":       "Cancelado.",
        "json":            "Salida JSON",
        "no_visible":      "Solo metadatos (sin detectores de píxeles)",
        "mark":            "Marca",
        "backend":         "Motor de relleno",
        "sensitivity":     "Sensibilidad estricta",
        "no_detect":       "Forzar sin detección (--no-detect)",
        "keep_metadata":   "Conservar metadatos",
        "region":          "Región(es) x,y,an,al (separadas por ;)",
        "region_hint":     "Ej. 1640,1930,400,100 ; 20,20,180,60",
        "dilate":          "Dilatar máscara (px)",
        "inpaint":         "Método cv2",
        "op_check":        "Inspeccionar (--check)",
        "op_remove":       "Eliminar (--remove)",
        "remove_all":      "Eliminar todo (--remove-all)",
        "force":           "Forzar (--force)",
        "vendor":          "Cohorte (vendor)",
        "pipeline":        "Pipeline",
        "strength":        "Fuerza (0=auto)",
        "seed":            "Seed",
        "cpu_offload":     "CPU offload (menos VRAM)",
        "max_res":         "Resolución máx. (0=nativa)",
        "tile":            "Mosaicos (--tile, imágenes grandes)",
        "mode":            "Modo",
        "with_invisible":  "Incluir regeneración invisible",
        "noise_std":       "Ruido (noise-std)",
        "long_side":       "Lado mayor (px)",
        "fps":             "FPS (0=origen)",
        "batch_size":      "Tamaño de lote",
        "temporal":        "Consistencia temporal",
        "no_temporal":     "Desactivar consistencia temporal",
        "suffix_note":     "Sin -o, las imágenes sobrescriben el origen; los vídeos escriben <source>_clean.",
        "err_no_bin":      "No se encontró `remove-ai-watermarks` en el PATH.",
        "err_no_bin_hint": "Instálelo con:\nuv tool install \"remove-ai-watermarks[all]\"\nluego reinicie Nautilus (nautilus -q).",
        "err_no_compat":   "Ningún archivo compatible seleccionado.",
        "files":           "Archivo(s)",
        # --- Convert image (format conversion) ---
        "convert_menu":    "Convertir imagen",
        "convert_tip":     "Convertir las imágenes seleccionadas a otro formato (Pillow)",
        "cv_png":          "Convertir a PNG",
        "cv_jpeg":         "Convertir a JPEG",
        "cv_webp":         "Convertir a WebP",
        "cv_ico":          "Guardar como ICO",
        "cv_square":       "Cuadrado 256×256 PNG",
        "cv_tip_ico":      "Archivo .ico multitamaño (16–256) — en Linux sirve sobre todo "
                           "para favicons (compatible en cualquier plataforma)",
        "cv_done_msg":     "{count} imagen(es) convertida(s) correctamente.",
        "cv_done_failed":  "{count} imagen(es) convertida(s), {failed} fallo(s).",
        "cv_nothing":      "No hace falta conversión — {count} archivo(s) ya tienen el formato destino.",
        "done_skip":       "{skipped} archivo(s) omitido(s) (ya en el formato destino).",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_label":     "Ferramentas de imagem",
        "menu_tip":       "Ferramentas de edição de imagens (Pillow)",
        "grayscale":      "Escala de cinza",
        "invert":         "Negativo",
        "crop":           "Recorte central…",
        "circle":         "Círculo",
        "resize":         "Redimensionar…",
        "combine":        "Combinar imagens…",
        "watermark":      "Marca d'água…",
        "optimize":       "Otimizar para web…",
        "colorize":        "Colorir…",
        "colorize_tip":    "Tingir as imagens preservando a luminância e o alfa",
        "cz_title":        "Colorir imagens",
        "cz_color":        "Cor",
        "cz_strength":     "Intensidade",
        "an_label":        "Anotar imagem…",
        "an_tip":          "Anotar esta imagem: retângulo, elipse, seta, texto",
        "an_title":        "Anotar imagem",
        "an_rect":         "Retângulo",
        "an_ellipse":      "Elipse",
        "an_arrow":        "Seta",
        "an_text":         "Texto",
        "an_undo":         "Desfazer",
        "an_redo":         "Refazer",
        "an_save":         "Salvar",
        "an_save_as":      "Salvar como…",
        "an_thickness":    "Espessura",
        "an_opacity":      "Opacidade",
        "an_color":        "Cor",
        "an_text_prompt":  "Digite o texto",
        "an_text_ok":      "OK",
        "an_text_cancel":  "Cancelar",
        "an_zoom_in":      "Aproximar",
        "an_zoom_out":     "Afastar",
        "an_zoom_fit":     "Ajustar à janela",
        "an_zoom_reset":   "Tamanho real (100%)",
        "processing":     "Processando…",
        "done_title":     "Processamento concluído",
        "done_msg":       "{count} imagem(ns) processada(s) com sucesso.",
        "done_failed":    "{count} imagem(ns) processada(s), {failed} falha(s).",
        "cancel":         "Cancelar",
        "ok":             "Aplicar",
        "choose":         "Escolher…",
        "err_pillow":     "O Pillow não está instalado. Instale com: pip install Pillow",
        "err_empty":      "O texto da marca d'água não pode ficar vazio.",
        "err_choose":     "Escolha uma imagem de marca d'água.",
        "err_combine":    "Selecione pelo menos duas imagens.",
        "err_annotate":    "Não foi possível abrir esta imagem no anotador.",
        "crop_title":     "Recorte central",
        "crop_width":     "Largura",
        "crop_height":    "Altura",
        "resize_title":   "Redimensionar",
        "resize_width":   "Largura",
        "resize_height":  "Altura",
        "resize_preset":  "Tamanho predefinido",
        "resize_custom":  "Personalizado",
        "resize_keep":    "Manter proporção",
        "resize_mode":    "Ajuste",
        "resize_dpi":     "Resolução (DPI)",
        "fit_inside":     "Ajustar dentro (limites máx.)",
        "fit_fill":       "Preencher (recorte central)",
        "fit_stretch":    "Esticar (exato)",
        "resize_info":    "Resultado: {w} × {h} px · {ratio} · {dpi} ppp",
        "resize_nosrc":   "Imagem de origem ilegível: proporção indisponível.",
        "optimize_title": "Otimizar para web",
        "optimize_max":   "Dimensão máx.",
        "optimize_qual":  "Qualidade",
        "watermark_title": "Marca d'água",
        "wm_mode_text":   "Texto",
        "wm_mode_image":  "Imagem",
        "wm_text_hint":   "Texto da marca d'água",
        "wm_pick_image":  "Imagem da marca d'água…",
        "combine_title":  "Combinar imagens",
        "combine_vertical":   "Vertical",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-cinza",
        "s_invert":     "-negativo",
        "s_crop":       "-recortada",
        "s_circle":     "-circulo",
        "s_resize":     "-redimensionada",
        "s_watermark":  "-marca-dagua",
        "s_colorize":   "-colorida",
        # --- Remove AI watermarks (CLI bridge) ---
        "top_menu":        "Remover marcas d'água de IA",
        "top_tip":         "Remover marcas d'água de IA (visível, invisível, metadados)",
        "identify":        "Identificar…",
        "classify":        "Classificar foto…",
        "visible":         "Remover marca visível…",
        "erase":           "Apagar região…",
        "metadata":        "Metadados IA…",
        "invisible":       "Remoção invisível (difusão)…",
        "all":             "Pipeline completo…",
        "batch":           "Processar pasta (batch)…",
        "v_identify":      "Vídeo: identificar…",
        "v_all":           "Vídeo: limpeza completa…",
        "v_visible":       "Vídeo: marca visível…",
        "v_metadata":      "Vídeo: metadados…",
        "v_invisible":     "Vídeo: SynthID (regeneração)…",
        "v_batch":         "Vídeo: pasta (batch)…",
        "run":             "Executar",
        "close":           "Fechar",
        "browse":          "Escolher…",
        "output":          "Arquivo de saída",
        "output_dir":      "Pasta de saída",
        "input_dir":       "Pasta de entrada",
        "options":         "Opções",
        "command":         "Comando",
        "processing_run":  "Processando…",
        "done":            "Concluído com sucesso.",
        "failed":          "Falhou (código {code}).",
        "cancelled":       "Cancelado.",
        "json":            "Saída JSON",
        "no_visible":      "Só metadados (sem detectores de pixel)",
        "mark":            "Marca",
        "backend":         "Motor de preenchimento",
        "sensitivity":     "Sensibilidade estrita",
        "no_detect":       "Forçar sem detecção (--no-detect)",
        "keep_metadata":   "Manter metadados",
        "region":          "Região(ões) x,y,l,a (separadas por ;)",
        "region_hint":     "Ex. 1640,1930,400,100 ; 20,20,180,60",
        "dilate":          "Dilatar máscara (px)",
        "inpaint":         "Método cv2",
        "op_check":        "Inspecionar (--check)",
        "op_remove":       "Remover (--remove)",
        "remove_all":      "Remover tudo (--remove-all)",
        "force":           "Forçar (--force)",
        "vendor":          "Coorte (vendor)",
        "pipeline":        "Pipeline",
        "strength":        "Força (0=auto)",
        "seed":            "Seed",
        "cpu_offload":     "CPU offload (menos VRAM)",
        "max_res":         "Resolução máx. (0=nativa)",
        "tile":            "Ladrilhos (--tile, imagens grandes)",
        "mode":            "Modo",
        "with_invisible":  "Incluir regeneração invisível",
        "noise_std":       "Ruído (noise-std)",
        "long_side":       "Lado maior (px)",
        "fps":             "FPS (0=origem)",
        "batch_size":      "Tamanho do lote",
        "temporal":        "Consistência temporal",
        "no_temporal":     "Desativar consistência temporal",
        "suffix_note":     "Sem -o, imagens sobrescrevem a origem; vídeos gravam <source>_clean.",
        "err_no_bin":      "`remove-ai-watermarks` não encontrado no PATH.",
        "err_no_bin_hint": "Instale com:\nuv tool install \"remove-ai-watermarks[all]\"\ndepois reinicie o Nautilus (nautilus -q).",
        "err_no_compat":   "Nenhum arquivo compatível selecionado.",
        "files":           "Arquivo(s)",
        # --- Convert image (format conversion) ---
        "convert_menu":    "Converter imagem",
        "convert_tip":     "Converter as imagens selecionadas para outro formato (Pillow)",
        "cv_png":          "Converter para PNG",
        "cv_jpeg":         "Converter para JPEG",
        "cv_webp":         "Converter para WebP",
        "cv_ico":          "Salvar como ICO",
        "cv_square":       "Quadrado 256×256 PNG",
        "cv_tip_ico":      "Arquivo .ico multi-tamanho (16–256) — no Linux serve "
                           "principalmente para favicons (cross-platform)",
        "cv_done_msg":     "{count} imagem(ns) convertida(s) com sucesso.",
        "cv_done_failed":  "{count} imagem(ns) convertida(s), {failed} falha(s).",
        "cv_nothing":      "Nenhuma conversão necessária — {count} arquivo(s) já estão no formato de destino.",
        "done_skip":       "{skipped} arquivo(s) ignorado(s) (já no formato de destino).",
    }
else:
    T = {
        "menu_label":     "Image Tools",
        "menu_tip":       "Image processing tools (Pillow)",
        "grayscale":      "Grayscale",
        "invert":         "Invert",
        "crop":           "Crop Center…",
        "circle":         "Circle",
        "resize":         "Resize…",
        "combine":        "Combine Images…",
        "watermark":      "Watermark…",
        "optimize":       "Optimize for Web…",
        "colorize":        "Colorize…",
        "colorize_tip":    "Tint images preserving luminance and alpha",
        "cz_title":        "Colorize Images",
        "cz_color":        "Color",
        "cz_strength":     "Strength",
        "an_label":        "Annotate image…",
        "an_tip":          "Annotate this image: rectangle, ellipse, arrow, text",
        "an_title":        "Annotate image",
        "an_rect":         "Rectangle",
        "an_ellipse":      "Ellipse",
        "an_arrow":        "Arrow",
        "an_text":         "Text",
        "an_undo":         "Undo",
        "an_redo":         "Redo",
        "an_save":         "Save",
        "an_save_as":      "Save as…",
        "an_thickness":    "Thickness",
        "an_opacity":      "Opacity",
        "an_color":        "Color",
        "an_text_prompt":  "Enter text",
        "an_text_ok":      "OK",
        "an_text_cancel":  "Cancel",
        "an_zoom_in":      "Zoom in",
        "an_zoom_out":     "Zoom out",
        "an_zoom_fit":     "Fit to window",
        "an_zoom_reset":   "Actual size (100%)",
        "processing":     "Processing…",
        "done_title":     "Processing complete",
        "done_msg":       "{count} image(s) processed successfully.",
        "done_failed":    "{count} image(s) processed, {failed} failed.",
        "cancel":         "Cancel",
        "ok":             "Apply",
        "choose":         "Choose…",
        "err_pillow":     "Pillow is not installed. Install it with: pip install Pillow",
        "err_empty":      "Watermark text cannot be empty.",
        "err_choose":     "Please choose a watermark image.",
        "err_combine":    "Select at least two images.",
        "err_annotate":    "Cannot open this image in the annotator.",
        "crop_title":     "Crop Center",
        "crop_width":     "Width",
        "crop_height":    "Height",
        "resize_title":   "Resize",
        "resize_width":   "Width",
        "resize_height":  "Height",
        "resize_preset":  "Preset size",
        "resize_custom":  "Custom",
        "resize_keep":    "Keep aspect ratio",
        "resize_mode":    "Fit mode",
        "resize_dpi":     "Resolution (DPI)",
        "fit_inside":     "Fit inside (max bounds)",
        "fit_fill":       "Fill (center crop)",
        "fit_stretch":    "Stretch (exact)",
        "resize_info":    "Result: {w} × {h} px · {ratio} · {dpi} dpi",
        "resize_nosrc":   "Source image unreadable: aspect ratio unavailable.",
        "optimize_title": "Optimize for Web",
        "optimize_max":   "Max dimension",
        "optimize_qual":  "Quality",
        "watermark_title": "Watermark",
        "wm_mode_text":   "Text",
        "wm_mode_image":  "Image",
        "wm_text_hint":   "Watermark text",
        "wm_pick_image":  "Watermark image…",
        "combine_title":  "Combine Images",
        "combine_vertical":   "Vertical",
        "combine_horizontal": "Horizontal",
        "s_grayscale":  "-grayscale",
        "s_invert":     "-inverted",
        "s_crop":       "-cropped",
        "s_circle":     "-circle",
        "s_resize":     "-resized",
        "s_watermark":  "-watermarked",
        "s_colorize":   "-colorized",
        # --- Remove AI watermarks (CLI bridge) ---
        "top_menu":        "Remove AI Watermarks",
        "top_tip":         "Remove AI watermarks (visible, invisible, metadata)",
        "identify":        "Identify…",
        "classify":        "Classify photo…",
        "visible":         "Remove visible mark…",
        "erase":           "Erase region…",
        "metadata":        "AI metadata…",
        "invisible":       "Invisible removal (diffusion)…",
        "all":             "Full pipeline…",
        "batch":           "Process folder (batch)…",
        "v_identify":      "Video: identify…",
        "v_all":           "Video: full clean…",
        "v_visible":       "Video: visible mark…",
        "v_metadata":      "Video: metadata…",
        "v_invisible":     "Video: SynthID (regen)…",
        "v_batch":         "Video: folder (batch)…",
        "run":             "Run",
        "close":           "Close",
        "browse":          "Browse…",
        "output":          "Output file",
        "output_dir":      "Output folder",
        "input_dir":       "Input folder",
        "options":         "Options",
        "command":         "Command",
        "processing_run":  "Processing…",
        "done":            "Completed successfully.",
        "failed":          "Failed (exit code {code}).",
        "cancelled":       "Cancelled.",
        "json":            "JSON output",
        "no_visible":      "Metadata only (no pixel detectors)",
        "mark":            "Mark",
        "backend":         "Fill backend",
        "sensitivity":     "Strict sensitivity",
        "no_detect":       "Force without detection (--no-detect)",
        "keep_metadata":   "Keep metadata",
        "region":          "Region(s) x,y,w,h (separated by ;)",
        "region_hint":     "E.g. 1640,1930,400,100 ; 20,20,180,60",
        "dilate":          "Mask dilate (px)",
        "inpaint":         "cv2 method",
        "op_check":        "Inspect (--check)",
        "op_remove":       "Remove (--remove)",
        "remove_all":      "Remove all (--remove-all)",
        "force":           "Force (--force)",
        "vendor":          "Cohort (vendor)",
        "pipeline":        "Pipeline",
        "strength":        "Strength (0=auto)",
        "seed":            "Seed",
        "cpu_offload":     "CPU offload (less VRAM)",
        "max_res":         "Max resolution (0=native)",
        "tile":            "Tiles (--tile, large images)",
        "mode":            "Mode",
        "with_invisible":  "Include invisible regeneration",
        "noise_std":       "Noise (noise-std)",
        "long_side":       "Long side (px)",
        "fps":             "FPS (0=source)",
        "batch_size":      "Batch size",
        "temporal":        "Temporal consistency",
        "no_temporal":     "Disable temporal consistency",
        "suffix_note":     "Without -o, images overwrite source; videos write <source>_clean.",
        "err_no_bin":      "`remove-ai-watermarks` was not found on PATH.",
        "err_no_bin_hint": "Install it with:\nuv tool install \"remove-ai-watermarks[all]\"\nthen restart Nautilus (nautilus -q).",
        "err_no_compat":   "No compatible file selected.",
        "files":           "File(s)",
        # --- Convert image (format conversion) ---
        "convert_menu":    "Convert Image",
        "convert_tip":     "Convert selected images to another format (Pillow)",
        "cv_png":          "Convert to PNG",
        "cv_jpeg":         "Convert to JPEG",
        "cv_webp":         "Convert to WebP",
        "cv_ico":          "Save as ICO",
        "cv_square":       "Square 256×256 PNG",
        "cv_tip_ico":      "Multi-size .ico (16–256) — on Linux mainly useful for "
                           "favicons (cross-platform)",
        "cv_done_msg":     "{count} image(s) converted successfully.",
        "cv_done_failed":  "{count} image(s) converted, {failed} failed.",
        "cv_nothing":      "No conversion needed — {count} file(s) already have the target format.",
        "done_skip":       "{skipped} file(s) skipped (already in the target format).",
    }

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".ico",
                   ".tif", ".tiff")
_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
            ".webp": "WEBP", ".bmp": "BMP", ".ico": "ICO",
            ".tif": "TIFF", ".tiff": "TIFF"}
_ALPHA_FORMATS = ("PNG", "WEBP", "ICO")
_DPI_FORMATS = ("PNG", "JPEG", "BMP", "TIFF")
_COMBINE_OUTPUT = "combined_images.png"
_CONVERT_JPEG_QUALITY = 92
_SQUARE_SIZE = 256
_SQUARE_MARK = "-256x256"
_ICO_SIZES = ((16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))

_CONVERT_MSGS = {
    "done": T["cv_done_msg"],
    "failed": T["cv_done_failed"],
    "skip": T["done_skip"],
    "nothing": T["cv_nothing"],
}


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
    windows = app.get_windows()
    return windows[0] if windows else None


def _show_message(msg: str):
    Gtk.AlertDialog(message=msg).show(_nautilus_window())


def _paths_from_files(files):
    out = []
    for f in files:
        try:
            if f.get_uri_scheme() != "file":
                continue
            p = f.get_location().get_path()
        except Exception:
            continue
        if p:
            out.append(p)
    return out


def _is_image_path(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def _suffix(src: str, suffix: str, force_ext=None) -> str:
    base, ext = os.path.splitext(src)
    if force_ext:
        ext = force_ext if force_ext.startswith(".") else "." + force_ext
    return f"{base}{suffix}{ext}"


def _same_path(a: str, b: str) -> bool:
    return os.path.abspath(a).lower() == os.path.abspath(b).lower()


def _save(img, dst: str, params=None, dpi=None):
    """Sauvegarde img dans dst en gérant alpha selon le format cible."""
    ext = os.path.splitext(dst)[1].lower()
    fmt = _FORMATS.get(ext, "PNG")
    mode = img.mode
    if mode in ("RGBA", "LA", "PA"):
        if fmt not in _ALPHA_FORMATS:
            flat = Image.new("RGB", img.size, (255, 255, 255))
            flat.paste(img, mask=img.split()[-1])
            img = flat
    elif mode == "P":
        img = img.convert("RGB" if fmt not in _ALPHA_FORMATS else "RGBA")
    opts = dict(params or {})
    if dpi and fmt in _DPI_FORMATS:
        opts["dpi"] = (dpi, dpi)
    img.save(dst, fmt, **opts)


# ---------------------------------------------------------------------------
# Resize presets and pure geometry helpers
# ---------------------------------------------------------------------------

# Known target formats: social networks first, then screens/web, then print.
_RESIZE_PRESETS = (
    ("Instagram Story", 1080, 1920),
    ("Instagram Portrait", 1080, 1350),
    ("Instagram Square", 1080, 1080),
    ("Instagram Landscape", 1350, 1080),
    ("Facebook / X Cover", 1200, 630),
    ("X (Twitter) Post", 1600, 900),
    ("LinkedIn Banner", 1584, 396),
    ("YouTube Thumbnail", 1280, 720),
    ("Pinterest Pin", 1000, 1500),
    ("Discord Banner", 960, 540),
    ("Full HD 1080p", 1920, 1080),
    ("QHD 1440p", 2560, 1440),
    ("4K UHD 2160p", 3840, 2160),
    ("Ultrawide 21:9", 3440, 1440),
    ("Super Ultrawide 32:9", 5120, 1440),
    ("App Icon / Avatar", 512, 512),
)

# Physical sizes (mm) whose pixel size follows the DPI field.
_PAPER_PRESETS = (
    ("A3", 297.0, 420.0),
    ("A4", 210.0, 297.0),
    ("A5", 148.0, 210.0),
    ("US Letter", 215.9, 279.4),
)

_PAPER_DEFAULT_DPI = 300
_MAX_DPI = 4800
_MM_PER_INCH = 25.4

_MAX_DIM = 100000


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a or 1


def _ratio_label(w: int, h: int) -> str:
    """Human readable aspect ratio, e.g. 1920x1080 -> '16:9'."""
    if w <= 0 or h <= 0:
        return "—"
    g = _gcd(w, h)
    return f"{w // g}:{h // g}"


def _linked_dim(value: int, src_size, keep_w: bool) -> int:
    """Partner dimension for the source ratio, clamped to the spin range."""
    src_w, src_h = src_size
    base = src_w if keep_w else src_h
    if base <= 0:
        return 1
    scale = (src_h / src_w) if keep_w else (src_w / src_h)
    return min(_MAX_DIM, max(1, round(value * scale)))


def _fit_size(iw: int, ih: int, box_w: int, box_h: int):
    """Fit-inside (thumbnail) result — never upscales, like Pillow."""
    if iw <= 0 or ih <= 0:
        return box_w, box_h
    scale = min(box_w / iw, box_h / ih, 1.0)
    return max(1, round(iw * scale)), max(1, round(ih * scale))


def _image_size(path):
    """(width, height) of an image, or None when unreadable."""
    if Image is None or not path:
        return None
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


def _image_dpi(path):
    """DPI recorded in an image, or None when absent/unusable."""
    if Image is None or not path:
        return None
    try:
        with Image.open(path) as im:
            value = im.info.get("dpi")
    except Exception:  # noqa: BLE001
        return None
    if isinstance(value, tuple):
        value = value[0] if value else None
    try:
        dpi = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return dpi if 1 <= dpi <= _MAX_DPI else None


def _mm_to_px(mm: float, dpi: int) -> int:
    return min(_MAX_DIM, max(1, round(mm / _MM_PER_INCH * dpi)))


# ---------------------------------------------------------------------------
# Pillow operations (pure, run inside worker threads)
# ---------------------------------------------------------------------------

def op_grayscale(src):
    dst = _suffix(src, T["s_grayscale"])
    with Image.open(src) as im:
        _save(im.convert("L"), dst)
    return dst


def op_invert(src):
    dst = _suffix(src, T["s_invert"])
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        rgb = ImageOps.invert(rgba.convert("RGB"))
        rgb.putalpha(rgba.split()[3])
        _save(rgb, dst)
    return dst


def op_crop(src, w, h):
    dst = _suffix(src, T["s_crop"])
    with Image.open(src) as im:
        iw, ih = im.size
        cw, ch = min(w, iw), min(h, ih)
        left, top = (iw - cw) // 2, (ih - ch) // 2
        _save(im.crop((left, top, left + cw, top + ch)), dst)
    return dst


def op_circle(src):
    dst = _suffix(src, T["s_circle"])
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        iw, ih = rgba.size
        side = min(iw, ih)
        left, top = (iw - side) // 2, (ih - side) // 2
        sq = rgba.crop((left, top, left + side, top + side))
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, side, side), fill=255)
        sq.putalpha(mask)
        _save(sq, dst)
    return dst


def op_resize(src, w, h, keep_ratio=False, mode="inside", axis="w", dpi=None):
    """keep_ratio links both dimensions to the image's own ratio (exact output),
    so a mixed-ratio batch keeps every picture undistorted.

    axis tells which dimension the user edited last. mode applies when the two
    dimensions are independent: "inside" fits the image in the box without
    upscaling, "fill" center-crops to the box, "stretch" distorts to the box.
    dpi is stored in the output metadata for print-oriented formats.
    """
    dst = _suffix(src, T["s_resize"])
    w, h = min(_MAX_DIM, max(1, int(w))), min(_MAX_DIM, max(1, int(h)))
    with Image.open(src) as im:
        im.load()
        work = im.copy()
        if keep_ratio:
            iw, ih = work.size
            if axis == "w":
                h = min(_MAX_DIM, max(1, round(w * ih / iw)))
            else:
                w = min(_MAX_DIM, max(1, round(h * iw / ih)))
            work = work.resize((w, h), Image.LANCZOS)
        elif mode == "stretch":
            work = work.resize((w, h), Image.LANCZOS)
        elif mode == "fill":
            work = ImageOps.fit(work, (w, h), Image.LANCZOS)
        else:
            work.thumbnail((w, h), Image.LANCZOS)
        _save(work, dst, dpi=dpi)
    return dst


def op_combine(paths, vertical):
    first = paths[0]
    out_path = os.path.join(os.path.dirname(first) or ".", _COMBINE_OUTPUT)
    imgs = []
    try:
        for p in paths:
            imgs.append(Image.open(p).convert("RGBA"))
        if vertical:
            width = max(i.width for i in imgs)
            height = sum(i.height for i in imgs)
        else:
            width = sum(i.width for i in imgs)
            height = max(i.height for i in imgs)
        canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        offset = 0
        for img in imgs:
            if vertical:
                pos = ((width - img.width) // 2, offset)
                offset += img.height
            else:
                pos = (offset, (height - img.height) // 2)
                offset += img.width
            canvas.paste(img, pos, img)
        canvas.save(out_path, "PNG")
    finally:
        for img in imgs:
            img.close()
    return out_path


def op_watermark(src, settings):
    dst = _suffix(src, T["s_watermark"])
    with Image.open(src) as im:
        base = im.convert("RGBA")
        bw, bh = base.size
        if settings["mode"] == "image":
            with Image.open(settings["image"]) as wm_img:
                wm = wm_img.convert("RGBA")
                scale = min(0.5 * bw / wm.width, 0.5 * bh / wm.height)
                if 0 < scale < 1:
                    wm = wm.resize(
                        (max(1, int(wm.width * scale)),
                         max(1, int(wm.height * scale))), Image.LANCZOS)
                wm.putalpha(128)
                x, y = (bw - wm.width) // 2, (bh - wm.height) // 2
                base.paste(wm, (x, y), wm)
        else:
            text = settings["text"]
            size = 64
            while size > 8:
                font = ImageFont.load_default(size=size)
                probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
                bbox = probe.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if tw <= bw * 0.9 and th <= bh * 0.9:
                    break
                size //= 2
            font = ImageFont.load_default(size=size)
            probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            bbox = probe.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw = ImageDraw.Draw(base)
            draw.text(((bw - tw) // 2 - bbox[0], (bh - th) // 2 - bbox[1]),
                      text, font=font, fill=(0, 0, 0, 128))
        _save(base, dst)
    return dst


def op_optimize(src, max_dim, quality):
    dst = _suffix(src, "_optimized", force_ext=".jpg")
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        rgba.thumbnail((max_dim, max_dim), Image.LANCZOS)
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[3])
        flat.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
    return dst


def _hex_lut(factor: int) -> list:
    return [int(i * factor / 255) for i in range(256)]


def op_colorize(src, rgba_color, strength):
    """Multiplie chaque canal RGB par la cible en conservant la luminance
    (niveaux de gris) et l'alpha, puis blend selon la force. Jamais in-place :
    sortie séparée avec suffixe traduit."""
    dst = _suffix(src, T["s_colorize"])
    r = min(255, max(0, int(rgba_color.red * 255)))
    g = min(255, max(0, int(rgba_color.green * 255)))
    b = min(255, max(0, int(rgba_color.blue * 255)))
    alpha = min(100, max(0, strength))
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        lum = rgba.convert("L")
        colored = Image.merge(
            "RGB",
            (lum.point(_hex_lut(r)), lum.point(_hex_lut(g)), lum.point(_hex_lut(b))),
        ).convert("RGBA")
        colored.putalpha(rgba.split()[3])
        if alpha == 0:
            result = rgba
        elif alpha == 100:
            result = colored
        else:
            result = Image.blend(rgba, colored, alpha / 100.0)
        _save(result, dst)
    return dst


# ---------------------------------------------------------------------------
# Format conversion ops
# ---------------------------------------------------------------------------
# Each op replaces the source extension instead of adding a suffix (unlike the
# editing ops above) and returns None when the file already is the target
# format, so ProgressDialog can report it as skipped instead of converted.


def _convert_to(src, ext, params=None):
    dst = _suffix(src, "", force_ext=ext)
    if _same_path(dst, src):
        return None
    with Image.open(src) as im:
        _save(im.convert("RGBA"), dst, params)
    return dst


def op_to_png(src):
    return _convert_to(src, ".png")


def op_to_jpeg(src):
    return _convert_to(src, ".jpg", {"quality": _CONVERT_JPEG_QUALITY,
                                     "optimize": True, "progressive": True})


def op_to_webp(src):
    return _convert_to(src, ".webp")


def op_to_ico(src):
    dst = _suffix(src, "", force_ext=".ico")
    if _same_path(dst, src):
        return None
    with Image.open(src) as im:
        im.convert("RGBA").save(dst, "ICO", sizes=_ICO_SIZES)
    return dst


def op_to_square(src):
    dst = _suffix(src, _SQUARE_MARK, force_ext=".png")
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        w, h = rgba.size
        scale = min(_SQUARE_SIZE / w, _SQUARE_SIZE / h)
        nw = max(1, round(w * scale))
        nh = max(1, round(h * scale))
        if (nw, nh) != (w, h):
            rgba = rgba.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (_SQUARE_SIZE, _SQUARE_SIZE), (0, 0, 0, 0))
        canvas.paste(rgba, ((_SQUARE_SIZE - nw) // 2, (_SQUARE_SIZE - nh) // 2),
                     rgba)
        canvas.save(dst, "PNG")
    return dst


# ---------------------------------------------------------------------------
# Batch progress dialog
# ---------------------------------------------------------------------------

class ProgressDialog(Adw.Window):
    __gtype_name__ = "ImageToolsProgressDialog"

    def __init__(self, tasks, messages=None):
        super().__init__(title=T["done_title"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_deletable(False)
        self.set_default_size(360, -1)

        self._tasks = tasks
        self._cancelled = False
        self._done = 0
        self._failed = 0
        self._skipped = 0
        self._processed = 0

        msgs = messages or {}
        self._msg_done = msgs.get("done", T["done_msg"])
        self._msg_failed = msgs.get("failed", T["done_failed"])
        self._msg_skip = msgs.get("skip")
        self._msg_nothing = msgs.get("nothing")

        self._header = Adw.HeaderBar()
        self._header.set_decoration_layout(":close")

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        box.append(Gtk.Label(label=T["processing"]))

        self._bar = Gtk.ProgressBar()
        self._bar.set_pulse_step(0.06)
        box.append(self._bar)

        self._status_lbl = Gtk.Label(label="0/{0}".format(len(tasks)))
        self._status_lbl.add_css_class("dim-label")
        box.append(self._status_lbl)

        self._cancel_btn = Gtk.Button(label=T["cancel"])
        self._cancel_btn.connect("clicked", self._on_cancel)
        box.append(self._cancel_btn)

        toolbar_view.set_content(box)
        self.set_content(toolbar_view)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        GObject.timeout_add(80, self._pulse)

    def present(self):
        # Counterpart of _BaseDialog.present(): the batch window opens from the
        # same menu-activate handler, so it needs the same idle turn before
        # mapping, otherwise its Cancel button is dead on Wayland.
        GLib.idle_add(super().present)

    def _pulse(self):
        if self._thread.is_alive():
            self._bar.pulse()
            return True
        return False

    def _on_cancel(self, _btn):
        self._cancelled = True
        self._cancel_btn.set_sensitive(False)

    def _set_status(self):
        self._bar.set_fraction(self._processed / max(len(self._tasks), 1))
        self._status_lbl.set_label("{0}/{1}".format(
            self._processed, len(self._tasks)))

    def _run(self):
        for task in self._tasks:
            if self._cancelled:
                break
            try:
                if task() is None:
                    self._skipped += 1
                else:
                    self._done += 1
            except Exception:
                self._failed += 1
            self._processed += 1
            GObject.idle_add(self._set_status)
        GObject.idle_add(self._finish)

    def _finish(self):
        if self._cancelled:
            self.destroy()
            return
        if self._done or self._failed:
            if self._failed:
                line = self._msg_failed.format(count=self._done,
                                                failed=self._failed)
            else:
                line = self._msg_done.format(count=self._done)
        elif self._skipped and self._msg_nothing:
            line = self._msg_nothing.format(count=self._skipped)
        else:
            line = self._msg_done.format(count=0)
        if self._skipped and self._msg_skip:
            line += "\n" + self._msg_skip.format(skipped=self._skipped)
        _show_message(line)
        self.destroy()


# ---------------------------------------------------------------------------
# Settings dialogs
# ---------------------------------------------------------------------------

class _BaseDialog(Adw.Window):
    def __init__(self, title):
        super().__init__(title=title)
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(360, -1)
        self._callback = None

        self._tv = Adw.ToolbarView()
        self._header = Adw.HeaderBar()
        self._header.set_decoration_layout(":close")
        self._tv.add_top_bar(self._header)

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._body.set_margin_top(16)
        self._body.set_margin_bottom(16)
        self._body.set_margin_start(18)
        self._body.set_margin_end(18)
        self._build(self._body)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label=T["cancel"])
        cancel_btn.connect("clicked", lambda _: self._dismiss())
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label=T["ok"])
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", lambda _: self._apply())
        btn_box.append(ok_btn)

        self._body.append(btn_box)
        self._tv.set_content(self._body)
        self.set_content(self._tv)

    def present(self):
        # Defer mapping to one idle turn: presenting synchronously from a
        # menu-activate handler leaves pointer events stuck on the dying
        # Nautilus context menu on Wayland, so the popup appears but its
        # buttons do not respond (same fix as remove-ai-watermarks.py).
        GLib.idle_add(super().present)

    def _section(self, text):
        lbl = Gtk.Label(label="<b>{0}</b>".format(text))
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        return lbl

    def _spin(self, low, high, step, default):
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        spin.set_value(default)
        return spin

    def _dropdown(self, items, active=0):
        dd = Gtk.DropDown.new_from_strings(items)
        dd.set_selected(active)
        return dd

    def _switch(self, label, active=False, sensitive=True):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        lbl.set_wrap(True)
        sw = Gtk.Switch()
        sw.set_active(active)
        sw.set_sensitive(sensitive)
        sw.set_halign(Gtk.Align.END)
        row.append(lbl)
        row.append(sw)
        self._body.append(row)
        return sw

    def _note(self):
        lbl = Gtk.Label()
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.add_css_class("dim-label")
        self._body.append(lbl)
        return lbl

    def set_callback(self, cb):
        self._callback = cb

    def _build(self, body):
        raise NotImplementedError

    def _values(self):
        raise NotImplementedError

    def _dismiss(self):
        if self._callback:
            self._callback(None)
        self.destroy()

    def _apply(self):
        vals = self._values()
        if vals is None:
            return
        if self._callback:
            self._callback(vals)
        self.destroy()


class CropDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsCropDialog"

    def __init__(self):
        super().__init__(T["crop_title"])

    def _build(self, body):
        body.append(self._section(T["crop_width"]))
        self._w = self._spin(1, 100000, 1, 512)
        body.append(self._w)
        body.append(self._section(T["crop_height"]))
        self._h = self._spin(1, 100000, 1, 512)
        body.append(self._h)

    def _values(self):
        return {"w": int(self._w.get_value()), "h": int(self._h.get_value())}


class ResizeDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsResizeDialog"

    def __init__(self, source=None):
        self._src_size = _image_size(source)
        self._src_dpi = _image_dpi(source)
        self._syncing = False
        self._axis = "w"
        super().__init__(T["resize_title"])

    def _build(self, body):
        body.append(self._section(T["resize_preset"]))
        self._preset = self._dropdown(
            [T["resize_custom"]]
            + [f"{name} · {w} × {h}" for name, w, h in _RESIZE_PRESETS]
            + [f"{name} · {mm_w:g} × {mm_h:g} mm"
               for name, mm_w, mm_h in _PAPER_PRESETS])
        self._preset.connect("notify::selected", self._on_preset)
        body.append(self._preset)

        start_w = 1024
        start_dpi = self._src_dpi or _PAPER_DEFAULT_DPI
        if self._src_size:
            start_w = min(self._src_size[0], start_w)

        body.append(self._section(T["resize_width"]))
        self._w = self._spin(1, _MAX_DIM, 1, start_w)
        self._w.connect("value-changed", lambda *_: self._on_dim(keep_w=True))
        body.append(self._w)

        body.append(self._section(T["resize_height"]))
        self._h = self._spin(1, _MAX_DIM, 1, 1)
        self._h.connect("value-changed", lambda *_: self._on_dim(keep_w=False))
        body.append(self._h)

        body.append(self._section(T["resize_dpi"]))
        self._dpi = self._spin(1, _MAX_DPI, 1, start_dpi)
        self._dpi.connect("value-changed", lambda *_: self._on_dpi())
        body.append(self._dpi)

        self._keep = self._switch(T["resize_keep"], True,
                                  self._src_size is not None)
        self._keep.connect("notify::active", self._on_keep)

        body.append(self._section(T["resize_mode"]))
        self._mode = self._dropdown(
            [T["fit_inside"], T["fit_fill"], T["fit_stretch"]])
        self._mode.connect("notify::selected", lambda *_: self._sync())
        body.append(self._mode)

        self._info = self._note()
        if self._keep.get_active():
            self._on_dim(keep_w=True)
        else:
            self._sync()

    def _paper_at(self, idx):
        """(mm_w, mm_h) when the dropdown entry is a physical size."""
        offset = len(_RESIZE_PRESETS) + 1
        if offset <= idx < offset + len(_PAPER_PRESETS):
            return _PAPER_PRESETS[idx - offset][1:]
        return None

    def _apply_paper(self, mm):
        dpi = int(self._dpi.get_value())
        self._syncing = True
        self._w.set_value(_mm_to_px(mm[0], dpi))
        self._h.set_value(_mm_to_px(mm[1], dpi))
        self._syncing = False
        self._sync()

    def _on_preset(self, *_):
        idx = self._preset.get_selected()
        if self._syncing or idx <= 0:
            self._sync()
            return
        self._syncing = True
        mm = self._paper_at(idx)
        if mm:
            self._dpi.set_value(_PAPER_DEFAULT_DPI)
        else:
            _name, w, h = _RESIZE_PRESETS[idx - 1]
            self._w.set_value(min(_MAX_DIM, w))
            self._h.set_value(min(_MAX_DIM, h))
        self._keep.set_active(False)
        self._mode.set_selected(1)
        self._syncing = False
        if mm:
            self._apply_paper(mm)
        else:
            self._sync()

    def _on_dpi(self, *_):
        if self._syncing:
            return
        mm = self._paper_at(self._preset.get_selected())
        if mm:
            self._apply_paper(mm)
        else:
            self._sync()

    def _on_dim(self, keep_w):
        if self._syncing:
            return
        self._axis = "w" if keep_w else "h"
        self._syncing = True
        self._preset.set_selected(0)
        if self._keep.get_active() and self._src_size:
            value = int(self._w.get_value() if keep_w else self._h.get_value())
            target = self._h if keep_w else self._w
            target.set_value(_linked_dim(value, self._src_size, keep_w))
        self._syncing = False
        self._sync()

    def _on_keep(self, *_):
        if not self._syncing and self._keep.get_active():
            self._on_dim(keep_w=True)
        else:
            self._sync()

    def _sync(self):
        locked = self._keep.get_active()
        self._mode.set_sensitive(not locked)
        if not self._src_size:
            self._info.set_text(T["resize_nosrc"])
            return
        w = int(self._w.get_value())
        h = int(self._h.get_value())
        if not locked and self._mode.get_selected() == 0:
            w, h = _fit_size(*self._src_size, w, h)
        self._info.set_text(T["resize_info"].format(
            w=w, h=h, ratio=_ratio_label(w, h), dpi=int(self._dpi.get_value())))

    def _values(self):
        return {"w": int(self._w.get_value()),
                "h": int(self._h.get_value()),
                "keep": self._keep.get_active(),
                "axis": self._axis,
                "dpi": int(self._dpi.get_value()),
                "mode": ("inside", "fill", "stretch")[self._mode.get_selected()]}


class OptimizeDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsOptimizeDialog"

    def __init__(self):
        super().__init__(T["optimize_title"])

    def _build(self, body):
        body.append(self._section(T["optimize_max"]))
        self._max = self._spin(100, 20000, 10, 1920)
        body.append(self._max)
        body.append(self._section(T["optimize_qual"]))
        self._qual = self._spin(1, 100, 1, 82)
        body.append(self._qual)

    def _values(self):
        return {"max": int(self._max.get_value()),
                "qual": int(self._qual.get_value())}


class WatermarkDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsWatermarkDialog"

    def __init__(self):
        super().__init__(T["watermark_title"])

    def _build(self, body):
        body.append(self._section(T["wm_mode_text"]))
        self._text_entry = Gtk.Entry()
        self._text_entry.set_placeholder_text(T["wm_text_hint"])
        body.append(self._text_entry)

        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._text_radio = Gtk.CheckButton(label=T["wm_mode_text"])
        self._text_radio.set_active(True)
        self._image_radio = Gtk.CheckButton(label=T["wm_mode_image"])
        self._image_radio.set_group(self._text_radio)
        mode_box.append(self._text_radio)
        mode_box.append(self._image_radio)
        body.append(mode_box)

        self._image_btn = Gtk.Button(label=T["wm_pick_image"])
        self._image_btn.connect("clicked", self._pick_image)
        body.append(self._image_btn)

        self._image_path = None
        self._text_radio.connect("toggled", self._sync_sensitive)
        self._image_radio.connect("toggled", self._sync_sensitive)
        self._sync_sensitive()

    def _sync_sensitive(self, *_):
        is_text = self._text_radio.get_active()
        self._text_entry.set_sensitive(is_text)
        self._image_btn.set_sensitive(not is_text)

    def _pick_image(self, _btn):
        filt = Gtk.FileFilter()
        filt.set_name(T["wm_mode_image"])
        for mime in ("image/png", "image/jpeg", "image/webp", "image/bmp"):
            filt.add_mime_type(mime)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dlg = Gtk.FileDialog(title=T["wm_pick_image"])
        dlg.set_filters(store)
        dlg.set_default_filter(filt)
        dlg.open(_nautilus_window(), None, self._on_picked)

    def _on_picked(self, dlg, result):
        try:
            path = dlg.open_finish(result).get_path()
        except Exception:
            return
        if path:
            self._image_path = path
            self._image_btn.set_label(os.path.basename(path))

    def _values(self):
        if self._text_radio.get_active():
            text = self._text_entry.get_text().strip()
            if not text:
                _show_message(T["err_empty"])
                return None
            return {"mode": "text", "text": text, "image": ""}
        if not self._image_path:
            _show_message(T["err_choose"])
            return None
        return {"mode": "image", "text": "", "image": self._image_path}


class CombineDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsCombineDialog"

    def __init__(self):
        super().__init__(T["combine_title"])

    def _build(self, body):
        self._v = Gtk.CheckButton(label=T["combine_vertical"])
        self._v.set_active(True)
        self._h = Gtk.CheckButton(label=T["combine_horizontal"])
        self._h.set_group(self._v)
        body.append(self._v)
        body.append(self._h)

    def _values(self):
        return {"vertical": self._v.get_active()}


class ColorizeDialog(_BaseDialog):
    __gtype_name__ = "ImageToolsColorizeDialog"

    def __init__(self):
        super().__init__(T["cz_title"])

    def _build(self, body):
        body.append(self._section(T["cz_color"]))
        self._color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = 0.25, 0.45, 0.95, 1.0
        self._color_btn.set_rgba(rgba)
        self._color_btn.set_halign(Gtk.Align.START)
        body.append(self._color_btn)

        body.append(self._section(T["cz_strength"]))
        self._strength = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._strength.set_value(100)
        self._strength.set_hexpand(True)
        self._strength.set_draw_value(False)
        body.append(self._strength)

    def _values(self):
        return {"color": self._color_btn.get_rgba(),
                "strength": int(self._strength.get_value())}


# ---------------------------------------------------------------------------
# Remove AI watermarks: constants + helpers
# ---------------------------------------------------------------------------

RAIW_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif",
                   ".gif", ".avif", ".heic", ".heif", ".jxl"}
RAIW_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".flv"}

# Mark names and enum values accepted by the `remove-ai-watermarks` CLI.
RAIW_IMAGE_MARKS = ["auto", "gemini", "doubao", "jimeng", "qwen", "kling",
                    "yuanbao", "baidu", "liblib", "runninghub",
                    "microsoft-badge", "samsung", "generic-ai", "openart"]
RAIW_VIDEO_MARKS = ["auto", "sora", "veo", "seedance", "doubao", "dola",
                    "hailuo", "kling"]
RAIW_BACKENDS = ["auto", "cv2", "migan", "lama"]
RAIW_INPAINT_METHODS = ["telea", "ns"]
RAIW_PIPELINES = ["qwen-zimage", "sdxl-zimage", "chroma-zimage", "auto"]
RAIW_VENDORS = ["auto", "openai", "google", "microsoft", "meta", "bytedance"]
RAIW_BATCH_MODES = ["visible", "invisible", "metadata", "all"]
RAIW_VIDEO_BATCH_MODES = ["visible", "metadata", "all"]


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _is_raiw_image(path: str) -> bool:
    return _ext(path) in RAIW_IMAGE_EXTS


def _is_raiw_video(path: str) -> bool:
    return _ext(path) in RAIW_VIDEO_EXTS


def _check_bin() -> bool:
    if not shutil.which("remove-ai-watermarks"):
        _show_message(f"{T['err_no_bin']}\n\n{T['err_no_bin_hint']}")
        return False
    return True


def _raiw_output(path: str) -> str:
    base, ext = os.path.splitext(path)
    return f"{base}_clean{ext}"


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


def _short_list(paths: list, limit: int = 3) -> str:
    names = [os.path.basename(p) for p in paths[:limit]]
    s = ", ".join(names)
    if len(paths) > limit:
        s += f" (+{len(paths) - limit})"
    return s


# nautilus-python drops its Python reference as soon as .present() returns, and
# a GC'd dialog stops responding to button/X clicks (dead popup for the user).
_raiw_windows: list = []


def _raiw_forget(win: Gtk.Window):
    if win in _raiw_windows:
        _raiw_windows.remove(win)


def _raiw_header(title: str) -> Adw.HeaderBar:
    """HeaderBar with a guaranteed working close button.

    A bare Adw.HeaderBar() relies on the system button-layout setting;
    on some desktops that leaves the dialog with no visible/working X.
    """
    header = Adw.HeaderBar()
    header.set_decoration_layout(":minimize,close")
    header.set_title_widget(Gtk.Label(label=title))
    return header


def _raiw_add_escape(win: Gtk.Window):
    ctrl = Gtk.ShortcutController()
    ctrl.set_scope(Gtk.ShortcutScope.MANAGED)
    trigger = Gtk.ShortcutTrigger.parse_string("Escape")
    action = Gtk.CallbackAction.new(lambda *a: (win.close(), True)[1])
    ctrl.add_shortcut(Gtk.Shortcut.new(trigger, action))
    win.add_controller(ctrl)


def _raiw_kill(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Remove AI watermarks: runner dialog (command + live log, cancellable)
# ---------------------------------------------------------------------------

class _RaiwRunDialog(Adw.Window):
    __gtype_name__ = "ImageToolsRaiwRunDialog"

    def __init__(self, argv: list, cwd: str | None = None):
        super().__init__(title=T["top_menu"])
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(620, 460)
        self._argv = argv
        self._cwd = cwd or os.path.expanduser("~")
        self._proc = None
        self._cancelled = False
        self._closed = False
        self._done = False
        _raiw_windows.append(self)
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", lambda *_: _raiw_forget(self))
        _raiw_add_escape(self)

        tv = Adw.ToolbarView()
        tv.add_top_bar(_raiw_header(T["top_menu"]))
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

        self._status = Gtk.Label(label=T["processing_run"])
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
        self._close_btn.connect("clicked", lambda _: self.close())
        btn_box.append(self._close_btn)
        box.append(btn_box)

        tv.set_content(box)
        self.set_content(tv)
        threading.Thread(target=self._run, daemon=True).start()
        GObject.timeout_add(90, self._pulse)

    def present(self):
        # Defer mapping to idle: presenting synchronously from a menu-activate
        # handler (or while the previous modal is still closing) leaves pointer
        # events stuck on the dying menu/window on Wayland while keyboard focus
        # already moved on (X/Close dead, Escape alive). One idle turn lets the
        # menu dismiss and the old modal unmap first.
        GLib.idle_add(super().present)

    def _pulse(self):
        if self._closed or self._done:
            return False
        if self._proc is None or self._proc.poll() is None:
            self._bar.pulse()
            return True
        return False

    def _on_close_request(self, *_args):
        self._closed = True
        self._cancelled = True
        _raiw_kill(self._proc)
        _raiw_forget(self)
        return False

    def _log(self, text: str):
        GLib.idle_add(self._append, text)

    def _append(self, text: str):
        if self._closed:
            return False
        end = self._buf.get_end_iter()
        self._buf.insert(end, text)
        return False

    def _on_cancel(self, _btn):
        self._cancelled = True
        _raiw_kill(self._proc)

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
        if self._closed:
            return False
        self._done = True
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
# Remove AI watermarks: base options dialog (one screen per CLI function)
# ---------------------------------------------------------------------------

class _RaiwDialog(Adw.Window):
    __gtype_name__ = "ImageToolsRaiwDialog"

    def __init__(self, title: str, subtitle: str, files_label: str):
        super().__init__(title=title)
        self.set_modal(True)
        self.set_transient_for(_nautilus_window())
        self.set_default_size(520, 560)
        self._closed = False
        self._out = None
        _raiw_windows.append(self)
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", lambda *_: _raiw_forget(self))
        _raiw_add_escape(self)

        tv = Adw.ToolbarView()
        tv.add_top_bar(_raiw_header(title))
        self._outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        top.set_margin_top(14)
        top.set_margin_start(18); top.set_margin_end(18)

        sub = Gtk.Label(label=subtitle)
        sub.set_halign(Gtk.Align.START)
        sub.set_wrap(True)
        sub.add_css_class("dim-label")
        top.append(sub)

        fl = Gtk.Label(label=f"{T['files']}: {files_label}")
        fl.set_halign(Gtk.Align.START)
        fl.set_wrap(True)
        fl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        top.append(fl)
        top.append(Gtk.Separator())
        self._outer.append(top)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._box.set_margin_top(6); self._box.set_margin_bottom(6)
        self._box.set_margin_start(18); self._box.set_margin_end(18)
        scroll.set_child(self._box)
        self._outer.append(scroll)

        tv.set_content(self._outer)
        self.set_content(tv)

    def present(self):
        GLib.idle_add(super().present)

    def _on_close_request(self, *_args):
        self._closed = True
        _raiw_forget(self)
        return False

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
        self._outer.append(Gtk.Separator())
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom.set_margin_top(10); bottom.set_margin_bottom(14)
        bottom.set_margin_start(18); bottom.set_margin_end(18)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_halign(Gtk.Align.END)
        box.set_hexpand(True)
        c = Gtk.Button(label=T["cancel"])
        c.connect("clicked", lambda _: self.close())
        box.append(c)
        ok = Gtk.Button(label=T["run"])
        ok.add_css_class("suggested-action")
        ok.connect("clicked", on_run)
        box.append(ok)
        bottom.append(box)
        self._outer.append(bottom)

    def _out_for(self, src: str) -> str:
        if self._out is None:
            return _raiw_output(src)
        return self._out.get_text().strip() or _raiw_output(src)


def _raiw_single_output(dlg: _RaiwDialog, paths: list) -> None:
    """Offer a custom output path only for a single file; batch overwrites
    derive the name per file instead."""
    if len(paths) == 1:
        dlg._out = dlg._path_row(T["output"], _raiw_output(paths[0]), True)
    else:
        dlg._out = None
        dlg._note(T["suffix_note"])


class _RaiwIdentifyDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwIdentifyDialog"

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
        argv += ["video", "identify"] if self._video else ["identify"]
        if self._json.get_active():
            argv.append("--json")
        if self._no_vis.get_active():
            argv.append("--no-visible")
        argv += self._paths
        self.close()
        _RaiwRunDialog(argv).present()


class _RaiwClassifyDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwClassifyDialog"

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
        self.close()
        _RaiwRunDialog(argv).present()


class _RaiwVisibleDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwVisibleDialog"

    def __init__(self, paths: list):
        super().__init__(T["visible"], T["visible"], _short_list(paths))
        self._paths = paths
        self._mark = self._dropdown(T["mark"], RAIW_IMAGE_MARKS, 0)
        self._backend = self._dropdown(T["backend"], RAIW_BACKENDS, 0)
        self._strict = self._switch(T["sensitivity"], False)
        self._no_detect = self._switch(T["no_detect"], False)
        self._keep = self._switch(T["keep_metadata"], False)
        _raiw_single_output(self, paths)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        mark = RAIW_IMAGE_MARKS[self._mark.get_selected()]
        backend = RAIW_BACKENDS[self._backend.get_selected()]
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
            argv += ["-o", self._out_for(src)]
            _RaiwRunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.close()


class _RaiwEraseDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwEraseDialog"

    def __init__(self, paths: list):
        super().__init__(T["erase"], T["erase"], _short_list(paths))
        self._paths = paths
        self._region = self._entry(T["region"], "", T["region_hint"])
        self._backend = self._dropdown(T["backend"], RAIW_BACKENDS, 0)
        self._dilate = self._spin(T["dilate"], 0, 50, 1, 3)
        self._inpaint = self._dropdown(T["inpaint"], RAIW_INPAINT_METHODS, 0)
        self._keep = self._switch(T["keep_metadata"], False)
        _raiw_single_output(self, paths)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        try:
            regs = _parse_regions(self._region.get_text())
        except ValueError:
            regs = []
        if not regs:
            _show_message(T["region_hint"])
            return
        backend = RAIW_BACKENDS[self._backend.get_selected()]
        inpaint = RAIW_INPAINT_METHODS[self._inpaint.get_selected()]
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
            argv += ["-o", self._out_for(src)]
            _RaiwRunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.close()


class _RaiwMetadataDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwMetadataDialog"

    def __init__(self, paths: list, video: bool = False):
        title = T["v_metadata"] if video else T["metadata"]
        super().__init__(title, title, _short_list(paths))
        self._paths = paths
        self._video = video
        self._mode = self._dropdown(T["options"],
                                    [T["op_check"], T["op_remove"]], 1)
        self._remove_all = self._switch(T["remove_all"], False)
        _raiw_single_output(self, paths)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        is_remove = self._mode.get_selected() == 1
        for src in self._paths:
            argv = ["remove-ai-watermarks"]
            argv += ["video", "metadata"] if self._video else ["metadata"]
            argv.append(src)
            if is_remove:
                argv.append("--remove")
                if not self._video and self._remove_all.get_active():
                    argv.append("--remove-all")
                if self._out is not None and self._out.get_text().strip():
                    argv += ["-o", self._out.get_text().strip()]
                elif self._video or len(self._paths) > 1:
                    argv += ["-o", _raiw_output(src)]
            else:
                argv.append("--check")
            _RaiwRunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.close()


class _RaiwInvisibleDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwInvisibleDialog"

    def __init__(self, paths: list, full: bool = False):
        title = T["all"] if full else T["invisible"]
        super().__init__(title, title, _short_list(paths))
        self._paths = paths
        self._full = full
        if full:
            self._mark = self._dropdown(T["mark"], RAIW_IMAGE_MARKS, 0)
            self._backend = self._dropdown(T["backend"], RAIW_BACKENDS, 0)
        self._force = self._switch(T["force"], True)
        self._vendor = self._dropdown(T["vendor"], RAIW_VENDORS, 0)
        self._pipeline = self._dropdown(T["pipeline"], RAIW_PIPELINES, 0)
        self._strength = self._spin(T["strength"], 0, 1, 0.05, 0.0, digits=2)
        self._seed = self._spin(T["seed"], 0, 999999, 1, 0)
        self._cpu = self._switch(T["cpu_offload"], False)
        self._maxres = self._spin(T["max_res"], 0, 8192, 256, 0)
        self._tile = self._switch(T["tile"], False)
        self._keep = self._switch(T["keep_metadata"], False)
        _raiw_single_output(self, paths)
        self._buttons(self._on_run)

    def _diffusion_opts(self, argv: list) -> list:
        vendor = RAIW_VENDORS[self._vendor.get_selected()]
        pipeline = RAIW_PIPELINES[self._pipeline.get_selected()]
        if vendor != "auto":
            argv += ["--vendor", vendor]
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
            argv.append("--keep-metadata")
        return argv

    def _on_run(self, _btn):
        for src in self._paths:
            argv = ["remove-ai-watermarks",
                    "all" if self._full else "invisible", src]
            if self._full:
                mark = RAIW_IMAGE_MARKS[self._mark.get_selected()]
                backend = RAIW_BACKENDS[self._backend.get_selected()]
                if mark != "auto":
                    argv += ["--mark", mark]
                if backend != "auto":
                    argv += ["--backend", backend]
            if self._force.get_active():
                argv.append("--force")
            argv = self._diffusion_opts(argv)
            argv += ["-o", self._out_for(src)]
            _RaiwRunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.close()


class _RaiwBatchDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwBatchDialog"

    def __init__(self, dirs: list, video: bool = False):
        title = T["v_batch"] if video else T["batch"]
        super().__init__(title, title, _short_list(dirs))
        self._dirs = dirs
        self._video = video
        modes = RAIW_VIDEO_BATCH_MODES if video else RAIW_BATCH_MODES
        self._mode = self._dropdown(T["mode"], modes, len(modes) - 1)
        first = dirs[0] if dirs else os.path.expanduser("~")
        default_out = f"{first.rstrip('/')}_clean" if len(dirs) == 1 else first
        self._outdir = self._path_row(T["output_dir"], default_out, False)
        if not video:
            self._pipeline = self._dropdown(T["pipeline"], RAIW_PIPELINES, 0)
            self._force = self._switch(T["force"], True)
            self._cpu = self._switch(T["cpu_offload"], False)
        else:
            self._with_inv = self._switch(T["with_invisible"], False)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        outdir = self._outdir.get_text().strip()
        for d in self._dirs:
            modes = RAIW_VIDEO_BATCH_MODES if self._video else RAIW_BATCH_MODES
            argv = ["remove-ai-watermarks"]
            argv += ["video", "batch"] if self._video else ["batch"]
            argv += [d, "--mode", modes[self._mode.get_selected()]]
            if outdir:
                argv += ["--output-dir", outdir]
            if self._video:
                if self._with_inv.get_active():
                    argv.append("--invisible")
            else:
                pipeline = RAIW_PIPELINES[self._pipeline.get_selected()]
                if pipeline != "qwen-zimage":
                    argv += ["--pipeline", pipeline]
                if self._force.get_active():
                    argv.append("--force")
                if self._cpu.get_active():
                    argv.append("--cpu-offload")
            _RaiwRunDialog(argv, cwd=d).present()
        self.close()


class _RaiwVideoVisibleDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwVideoVisibleDialog"

    def __init__(self, paths: list):
        super().__init__(T["v_visible"], T["v_visible"], _short_list(paths))
        self._paths = paths
        self._mark = self._dropdown(T["mark"], RAIW_VIDEO_MARKS, 0)
        self._backend = self._dropdown(T["backend"], RAIW_BACKENDS, 0)
        self._no_temporal = self._switch(T["no_temporal"], False)
        self._keep = self._switch(T["keep_metadata"], False)
        _raiw_single_output(self, paths)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        mark = RAIW_VIDEO_MARKS[self._mark.get_selected()]
        backend = RAIW_BACKENDS[self._backend.get_selected()]
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
            argv += ["-o", self._out_for(src)]
            _RaiwRunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.close()


class _RaiwVideoAllDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwVideoAllDialog"

    def __init__(self, paths: list):
        super().__init__(T["v_all"], T["v_all"], _short_list(paths))
        self._paths = paths
        self._with_inv = self._switch(T["with_invisible"], False)
        _raiw_single_output(self, paths)
        self._buttons(self._on_run)

    def _on_run(self, _btn):
        for src in self._paths:
            argv = ["remove-ai-watermarks", "video", "all", src]
            argv += ["-o", self._out_for(src)]
            if self._with_inv.get_active():
                argv.append("--invisible")
            _RaiwRunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.close()


class _RaiwVideoInvisibleDialog(_RaiwDialog):
    __gtype_name__ = "ImageToolsRaiwVideoInvisibleDialog"

    def __init__(self, paths: list):
        super().__init__(T["v_invisible"], T["v_invisible"], _short_list(paths))
        self._paths = paths
        self._noise = self._spin(T["noise_std"], 0.01, 1.0, 0.01, 0.15, digits=2)
        self._longside = self._spin(T["long_side"], 256, 4096, 64, 1024)
        self._fps = self._spin(T["fps"], 0, 120, 1, 0)
        self._bsize = self._spin(T["batch_size"], 1, 64, 1, 8)
        self._seed = self._spin(T["seed"], 0, 999999, 1, 0)
        _raiw_single_output(self, paths)
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
            argv += ["-o", self._out_for(src)]
            _RaiwRunDialog(argv, cwd=os.path.dirname(src) or None).present()
        self.close()


# ---------------------------------------------------------------------------
# Annotate: single-image editor (rect / ellipse / arrow / text + undo-redo)
# ---------------------------------------------------------------------------
# Ported from the former standalone annotate-image.py extension. Kept its own
# editor window rather than reusing a settings dialog: it is a full-screen
# canvas, and it must NOT be modal/transient — Mutter hides min/max on dialog
# windows, and the original was an independent window on purpose.

_ANNOT_TOOLS = ("rect", "ellipse", "arrow", "text")

# Adwaita ships no draw-rectangle-symbolic / draw-ellipse-symbolic, so asking
# the icon theme for them renders an empty tool button. Those two tools draw
# their glyph with cairo instead (_ShapeIcon); the rest resolve from the theme.
_ANNOT_ICONS = {
    "arrow": "go-up-symbolic",
    "text":  "format-text-bold-symbolic",
}
_ANNOT_SHAPES = ("rect", "ellipse")

# Same GC guard as _raiw_windows: nautilus-python drops its Python reference as
# soon as .present() returns, and a GC'd window stops responding to clicks.
_annot_windows: list = []


class Annotation:
    __slots__ = ("tool", "x1", "y1", "x2", "y2", "color", "opacity",
                 "thickness", "text")

    def __init__(self, tool, x1, y1, x2, y2, color, opacity, thickness,
                 text=""):
        self.tool      = tool
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.color     = color      # (r, g, b) floats 0-1
        self.opacity   = opacity    # float 0-1
        self.thickness = thickness  # int px
        self.text      = text


def _draw_annotation(ctx, ann, scale=1.0):
    """Dessine une annotation sur un contexte Cairo (coords image × scale)."""
    r, g, b = ann.color
    ctx.set_source_rgba(r, g, b, ann.opacity)
    lw = max(ann.thickness * scale, 1.0)
    ctx.set_line_width(lw)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)

    x1, y1 = ann.x1 * scale, ann.y1 * scale
    x2, y2 = ann.x2 * scale, ann.y2 * scale

    if ann.tool == "rect":
        ctx.rectangle(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        ctx.stroke()

    elif ann.tool == "ellipse":
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        rw, rh = abs(x2 - x1) / 2, abs(y2 - y1) / 2
        if rw > 0 and rh > 0:
            ctx.save()
            ctx.translate(cx, cy)
            ctx.scale(rw, rh)
            ctx.arc(0, 0, 1, 0, 2 * math.pi)
            ctx.restore()
            ctx.stroke()

    elif ann.tool == "arrow":
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y2)
        ctx.stroke()
        angle     = math.atan2(y2 - y1, x2 - x1)
        arr_len   = max(20 * scale, lw * 4)
        arr_angle = math.pi / 6
        for side in (-1, 1):
            ctx.move_to(x2, y2)
            ctx.line_to(
                x2 - arr_len * math.cos(angle - side * arr_angle),
                y2 - arr_len * math.sin(angle - side * arr_angle),
            )
        ctx.stroke()

    elif ann.tool == "text":
        font_size = max(12.0, ann.thickness * 7.0) * scale
        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                             cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(font_size)
        ctx.move_to(x1, y1)
        ctx.show_text(ann.text)


class _ShapeIcon(Gtk.DrawingArea):
    """Stands in for the missing draw-rectangle/ellipse-symbolic icons; themes
    automatically via Gtk.Widget.get_color()."""

    __gtype_name__ = "ImageToolsShapeIcon"

    def __init__(self, shape: str):
        super().__init__()
        self._shape = shape
        self.set_size_request(16, 16)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

    def _draw(self, _area, ctx, w, h):
        rgba = self.get_color()
        ctx.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        ctx.set_line_width(1.5)
        inset = 2.5
        if self._shape == "ellipse":
            ctx.save()
            ctx.translate(w / 2, h / 2)
            ctx.scale(max(w / 2 - inset, 0.5), max(h / 2 - inset, 0.5))
            ctx.arc(0, 0, 1, 0, 2 * math.pi)
            ctx.restore()
            ctx.stroke()
        else:
            ctx.rectangle(inset, inset, w - 2 * inset, h - 2 * inset)
            ctx.stroke()


def _annot_add_shortcuts(win):
    """Bind Ctrl+Z / Ctrl+Y (plus the Shift variants) to the window's undo and
    redo, so the keyboard and the header buttons share one code path."""
    ctrl = Gtk.ShortcutController()
    # MANAGED (as in _raiw_add_escape), not GLOBAL: GtkWindow *is* a
    # GtkShortcutManager, so this covers the whole window and fires whenever it
    # is focused, without escaping past it.
    ctrl.set_scope(Gtk.ShortcutScope.MANAGED)
    # parse_string only understands the "<Control>z" spelling; "Ctrl+z" aborts
    # the process with "constructor returned NULL".
    for accel, cb in (("<Control>z", win.undo),
                      ("<Control>y", win.redo),
                      ("<Control><Shift>z", win.redo),
                      ("<Control><Shift>y", win.redo)):
        trigger = Gtk.ShortcutTrigger.parse_string(accel)
        ctrl.add_shortcut(Gtk.Shortcut.new(
            trigger,
            Gtk.CallbackAction.new(lambda *a, cb=cb: (cb(), True)[1])))
    win.add_controller(ctrl)


def _annot_load_surface(path: str):
    """Load any supported image into a Cairo surface.

    cairo only decodes PNG, so every other format goes through Pillow and is
    re-encoded as PNG in memory first — this is what lets the annotate entry
    sit next to the other Image Tools items on JPEG/WebP/TIFF selections.
    """
    if _ext(path) == ".png":
        return cairo.ImageSurface.create_from_png(path)
    with Image.open(path) as im:
        buf = io.BytesIO()
        im.convert("RGBA").save(buf, "PNG")
    buf.seek(0)
    return cairo.ImageSurface.create_from_png(buf)


def _annot_write_surface(surface, path: str):
    """Inverse of _annot_load_surface: write PNG bytes straight out for .png,
    otherwise transcode so a .jpg never receives a PNG payload."""
    if _ext(path) == ".png":
        surface.write_to_png(path)
        return
    buf = io.BytesIO()
    surface.write_to_png(buf)
    buf.seek(0)
    with Image.open(buf) as im:
        _save(im.convert("RGBA"), path)


class AnnotatorWindow(Adw.Window):
    __gtype_name__ = "ImageToolsAnnotatorWindow"

    def __init__(self, image_path: str):
        super().__init__(title=T["an_title"])
        self.set_default_size(1100, 750)
        self.set_deletable(False)

        self._path         = image_path
        self._annotations  = []
        self._redo_stack   = []
        self._tool         = "rect"
        self._color        = (1.0, 0.0, 0.0)
        self._opacity      = 0.85
        self._thickness    = 3
        self._drawing      = False
        self._drag_start_w = (0.0, 0.0)
        self._current_ann  = None
        self._scale        = 1.0
        self._zoom         = None   # None = ajusté à la fenêtre ; sinon manuel
        self._offset_x     = 0.0
        self._offset_y     = 0.0

        self._surface = _annot_load_surface(image_path)
        self._img_w   = self._surface.get_width()
        self._img_h   = self._surface.get_height()

        _annot_windows.append(self)
        self.connect("destroy", lambda *_: _annot_windows.remove(self)
                     if self in _annot_windows else None)

        self._build_ui()
        _annot_add_shortcuts(self)

    def present(self):
        # Wayland: presenting synchronously from a menu-activate handler leaves
        # pointer events stuck on the dying Nautilus menu, so the popup shows up
        # with dead buttons. One idle turn lets the menu dismiss first.
        GLib.idle_add(super().present)

    # -- Construction UI -----------------------------------------------------

    def _build_ui(self):
        tv = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_decoration_layout(":minimize,maximize,close")

        self._undo_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        self._undo_btn.set_tooltip_text(T["an_undo"])
        self._undo_btn.connect("clicked", lambda _: self.undo())
        header.pack_start(self._undo_btn)

        self._redo_btn = Gtk.Button(icon_name="edit-redo-symbolic")
        self._redo_btn.set_tooltip_text(T["an_redo"])
        self._redo_btn.connect("clicked", lambda _: self.redo())
        header.pack_start(self._redo_btn)

        save_btn = Gtk.Button(label=T["an_save"])
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", lambda _: self._save(self._path))
        header.pack_end(save_btn)

        saveas_btn = Gtk.Button(icon_name="document-save-as-symbolic")
        saveas_btn.set_tooltip_text(T["an_save_as"])
        saveas_btn.connect("clicked", self._save_as)
        header.pack_end(saveas_btn)

        tv.add_top_bar(header)

        tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tb.set_margin_top(6)
        tb.set_margin_bottom(6)
        tb.set_margin_start(10)
        tb.set_margin_end(10)

        self._tool_btns = {}
        group = None
        for tool in _ANNOT_TOOLS:
            btn = Gtk.ToggleButton()
            if tool in _ANNOT_SHAPES:
                btn.set_child(_ShapeIcon(tool))
            else:
                btn.set_icon_name(_ANNOT_ICONS[tool])
            btn.set_tooltip_text(T["an_" + tool])
            btn.tool_id = tool
            if group is None:
                group = btn
                btn.set_active(True)
            else:
                btn.set_group(group)
            btn.connect("toggled", self._on_tool_toggled)
            tb.append(btn)
            self._tool_btns[tool] = btn

        tb.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = 1.0, 0.0, 0.0, 1.0
        self._color_btn.set_rgba(rgba)
        self._color_btn.set_tooltip_text(T["an_color"])
        self._color_btn.connect("color-set", self._on_color_set)
        tb.append(self._color_btn)

        tb.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        tb.append(Gtk.Label(label="{0} :".format(T["an_thickness"])))
        self._thick_spin = Gtk.SpinButton.new_with_range(1, 20, 1)
        self._thick_spin.set_value(3)
        self._thick_spin.connect(
            "value-changed",
            lambda s: setattr(self, "_thickness", int(s.get_value())))
        tb.append(self._thick_spin)

        tb.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        tb.append(Gtk.Label(label="{0} :".format(T["an_opacity"])))
        self._op_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.1, 1.0, 0.05)
        self._op_scale.set_value(0.85)
        self._op_scale.set_size_request(120, -1)
        self._op_scale.set_draw_value(False)
        self._op_scale.connect(
            "value-changed",
            lambda s: setattr(self, "_opacity", s.get_value()))
        tb.append(self._op_scale)

        tb.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        tb.append(spacer)

        zoom_out_btn = Gtk.Button(icon_name="zoom-out-symbolic")
        zoom_out_btn.set_tooltip_text(T["an_zoom_out"])
        zoom_out_btn.connect("clicked", lambda _: self._zoom_step(1 / 1.25))
        tb.append(zoom_out_btn)

        self._zoom_lbl = Gtk.Button(label="100%")
        self._zoom_lbl.set_tooltip_text(T["an_zoom_reset"])
        self._zoom_lbl.add_css_class("flat")
        self._zoom_lbl.set_size_request(60, -1)
        self._zoom_lbl.connect("clicked", lambda _: self._set_zoom(1.0))
        tb.append(self._zoom_lbl)

        zoom_in_btn = Gtk.Button(icon_name="zoom-in-symbolic")
        zoom_in_btn.set_tooltip_text(T["an_zoom_in"])
        zoom_in_btn.connect("clicked", lambda _: self._zoom_step(1.25))
        tb.append(zoom_in_btn)

        zoom_fit_btn = Gtk.Button(icon_name="zoom-fit-best-symbolic")
        zoom_fit_btn.set_tooltip_text(T["an_zoom_fit"])
        zoom_fit_btn.connect("clicked", lambda _: self._set_zoom(None))
        tb.append(zoom_fit_btn)

        tv.add_top_bar(tb)

        self._canvas = Gtk.DrawingArea()
        self._canvas.set_vexpand(True)
        self._canvas.set_hexpand(True)
        self._canvas.set_draw_func(self._on_draw)
        self._canvas.set_cursor(Gdk.Cursor.new_from_name("crosshair"))

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin",  self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end",    self._drag_end)
        self._canvas.add_controller(drag)

        scroll_ctrl = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_ctrl.connect("scroll", self._on_scroll)
        self._canvas.add_controller(scroll_ctrl)

        self._canvas.connect("resize", self._on_canvas_resize)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_child(self._canvas)

        tv.set_content(scroll)
        self.set_content(tv)
        self.connect("map", self._on_map)
        self._sync_history()

    # -- Map / scale / zoom --------------------------------------------------

    def _on_map(self, *_):
        self._apply_scale()
        self._update_canvas_size()
        self._update_zoom_label()

    def _on_canvas_resize(self, area, w, h):
        if self._zoom is None:
            self._apply_scale()
            self._update_zoom_label()
            self._canvas.queue_draw()

    def _apply_scale(self):
        if self._zoom is None:
            cw = self._canvas.get_width()  or (self.get_width()  - 20)
            ch = self._canvas.get_height() or (self.get_height() - 130)
            if cw > 0 and ch > 0:
                self._scale = min(cw / self._img_w, ch / self._img_h, 2.0)
        else:
            self._scale = self._zoom

    def _update_canvas_size(self):
        if self._zoom is None:
            self._canvas.set_content_width(0)
            self._canvas.set_content_height(0)
        else:
            self._canvas.set_content_width(int(self._img_w * self._scale + 40))
            self._canvas.set_content_height(int(self._img_h * self._scale + 40))

    def _update_zoom_label(self):
        self._zoom_lbl.set_label("{0}%".format(int(round(self._scale * 100))))

    def _set_zoom(self, zoom):
        self._zoom = zoom
        self._apply_scale()
        self._update_canvas_size()
        self._update_zoom_label()
        self._canvas.queue_draw()

    def _zoom_step(self, factor):
        base = self._scale if self._scale > 0 else 1.0
        self._set_zoom(max(0.1, min(8.0, base * factor)))

    def _on_scroll(self, ctrl, dx, dy):
        ev = ctrl.get_current_event()
        state = ev.get_modifier_state() if ev else 0
        if state & Gdk.ModifierType.CONTROL_MASK:
            self._zoom_step(1 / 1.25 if dy > 0 else 1.25)
            return True
        return False

    # -- Draw ----------------------------------------------------------------

    def _on_draw(self, area, ctx, w, h):
        self._apply_scale()
        s  = self._scale
        ox = (w - self._img_w * s) / 2
        oy = (h - self._img_h * s) / 2
        self._offset_x = ox
        self._offset_y = oy

        ctx.set_source_rgb(0.13, 0.13, 0.13)
        ctx.paint()

        ctx.save()
        ctx.translate(ox, oy)
        ctx.scale(s, s)
        ctx.set_source_surface(self._surface, 0, 0)
        ctx.paint()
        ctx.restore()

        ctx.save()
        ctx.translate(ox, oy)
        for ann in self._annotations:
            _draw_annotation(ctx, ann, scale=s)
        if self._current_ann:
            _draw_annotation(ctx, self._current_ann, scale=s)
        ctx.restore()

    # -- Coord conversion ----------------------------------------------------

    def _to_img(self, wx, wy):
        s = self._scale
        return (wx - self._offset_x) / s, (wy - self._offset_y) / s

    # -- Drag events ---------------------------------------------------------

    def _drag_begin(self, gesture, x, y):
        self._drag_start_w = (x, y)
        ix, iy = self._to_img(x, y)

        if self._tool == "text":
            self._ask_text(ix, iy)
            return

        self._drawing = True
        self._current_ann = Annotation(
            self._tool, ix, iy, ix, iy,
            self._color, self._opacity, self._thickness,
        )

    def _drag_update(self, gesture, dx, dy):
        if not self._drawing or not self._current_ann:
            return
        ix, iy = self._to_img(self._drag_start_w[0] + dx,
                              self._drag_start_w[1] + dy)
        self._current_ann.x2 = ix
        self._current_ann.y2 = iy
        self._canvas.queue_draw()

    def _drag_end(self, gesture, dx, dy):
        if not self._drawing or not self._current_ann:
            return
        ann = self._current_ann
        if abs(ann.x2 - ann.x1) > 2 or abs(ann.y2 - ann.y1) > 2:
            self._push(ann)
        self._current_ann = None
        self._drawing     = False
        self._canvas.queue_draw()

    # -- Text tool -----------------------------------------------------------

    def _ask_text(self, ix, iy):
        dlg = Adw.Window(title=T["an_text_prompt"])
        dlg.set_modal(True)
        dlg.set_transient_for(self)
        dlg.set_default_size(340, -1)

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)

        entry = Gtk.Entry()
        entry.set_placeholder_text(T["an_text_prompt"])
        box.append(entry)

        def on_ok(_btn):
            text = entry.get_text().strip()
            if text:
                self._push(Annotation(
                    "text", ix, iy, ix, iy,
                    self._color, self._opacity, self._thickness, text,
                ))
            dlg.destroy()

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label=T["an_text_cancel"])
        cancel_btn.connect("clicked", lambda _: dlg.destroy())
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label=T["an_text_ok"])
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", on_ok)
        btn_box.append(ok_btn)
        box.append(btn_box)

        entry.connect("activate", on_ok)

        tv.set_content(box)
        dlg.set_content(tv)
        dlg.present()
        entry.grab_focus()

    # -- History -------------------------------------------------------------

    def _push(self, ann):
        self._annotations.append(ann)
        self._redo_stack.clear()
        self._sync_history()
        self._canvas.queue_draw()

    def _sync_history(self):
        self._undo_btn.set_sensitive(bool(self._annotations))
        self._redo_btn.set_sensitive(bool(self._redo_stack))

    def undo(self):
        if self._annotations:
            self._redo_stack.append(self._annotations.pop())
            self._sync_history()
            self._canvas.queue_draw()

    def redo(self):
        if self._redo_stack:
            self._annotations.append(self._redo_stack.pop())
            self._sync_history()
            self._canvas.queue_draw()

    # -- Tools / settings ----------------------------------------------------

    def _on_tool_toggled(self, btn):
        if btn.get_active():
            self._tool = btn.tool_id

    def _on_color_set(self, btn):
        rgba = btn.get_rgba()
        self._color = (rgba.red, rgba.green, rgba.blue)

    # -- Save ----------------------------------------------------------------

    def _render(self):
        """Rend image + annotations dans une ImageSurface Cairo en résolution native."""
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, self._img_w, self._img_h)
        ctx = cairo.Context(out)
        ctx.set_source_surface(self._surface, 0, 0)
        ctx.paint()
        for ann in self._annotations:
            _draw_annotation(ctx, ann, scale=1.0)
        return out

    def _save(self, path: str):
        _annot_write_surface(self._render(), path)
        Gtk.AlertDialog(
            message="✓  {0}".format(os.path.basename(path))).show(self)

    def _save_as(self, *_):
        base = os.path.splitext(os.path.basename(self._path))[0]
        dlg = Gtk.FileDialog(title=T["an_save_as"])
        dlg.set_initial_folder(
            Gio.File.new_for_path(os.path.dirname(self._path)))
        dlg.set_initial_name("{0}-annotated.png".format(base))
        dlg.save(self, None, self._on_save_as_done)

    def _on_save_as_done(self, dlg, result):
        try:
            self._save(dlg.save_finish(result).get_path())
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Nautilus extension with submenu
# ---------------------------------------------------------------------------

class ImageToolsExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "ImageToolsExtension"

    def _add(self, submenu, name, label, cb, *args, tip=None):
        item = Nautilus.MenuItem(
            name="ImageTools::{0}".format(name),
            label=label,
            tip=tip or T["menu_tip"],
        )
        item.connect("activate", cb, *args)
        submenu.append_item(item)

    def _raiw_entry(self, name, label, dialog):
        return (name, label,
                lambda *_a, d=dialog: d().present() if _check_bin() else None)

    def _raiw_submenu(self, images, videos, dirs):
        entries = []
        files = images + videos

        if files:
            entries.append(self._raiw_entry(
                "RaiwIdentify", T["identify"],
                lambda: _RaiwIdentifyDialog(files, False)))
        if images:
            entries.append(self._raiw_entry(
                "RaiwClassify", T["classify"],
                lambda: _RaiwClassifyDialog(images)))
            entries.append(self._raiw_entry(
                "RaiwVisible", T["visible"],
                lambda: _RaiwVisibleDialog(images)))
            entries.append(self._raiw_entry(
                "RaiwErase", T["erase"],
                lambda: _RaiwEraseDialog(images)))
            entries.append(self._raiw_entry(
                "RaiwInvisible", T["invisible"],
                lambda: _RaiwInvisibleDialog(images, False)))
            entries.append(self._raiw_entry(
                "RaiwAll", T["all"],
                lambda: _RaiwInvisibleDialog(images, True)))
        if files:
            entries.append(self._raiw_entry(
                "RaiwMetadata", T["metadata"],
                lambda: _RaiwMetadataDialog(files, False)))
        if videos:
            entries.append(self._raiw_entry(
                "RaiwVideoIdentify", T["v_identify"],
                lambda: _RaiwIdentifyDialog(videos, True)))
            entries.append(self._raiw_entry(
                "RaiwVideoAll", T["v_all"],
                lambda: _RaiwVideoAllDialog(videos)))
            entries.append(self._raiw_entry(
                "RaiwVideoVisible", T["v_visible"],
                lambda: _RaiwVideoVisibleDialog(videos)))
            entries.append(self._raiw_entry(
                "RaiwVideoMetadata", T["v_metadata"],
                lambda: _RaiwMetadataDialog(videos, True)))
            entries.append(self._raiw_entry(
                "RaiwVideoInvisible", T["v_invisible"],
                lambda: _RaiwVideoInvisibleDialog(videos)))
        if dirs:
            entries.append(self._raiw_entry(
                "RaiwBatch", T["batch"],
                lambda: _RaiwBatchDialog(dirs, False)))
            entries.append(self._raiw_entry(
                "RaiwVideoBatch", T["v_batch"],
                lambda: _RaiwBatchDialog(dirs, True)))

        if not entries:
            return None
        submenu = Nautilus.Menu()
        for name, label, cb in entries:
            self._add(submenu, name, label, cb, tip=T["top_tip"])
        item = Nautilus.MenuItem(
            name="ImageTools::Raiw",
            label=T["top_menu"],
            tip=T["top_tip"],
        )
        item.set_submenu(submenu)
        return item

    def _convert_item(self, images):
        submenu = Nautilus.Menu()
        for name, label, op in (
            ("ToPNG", T["cv_png"], op_to_png),
            ("ToJPEG", T["cv_jpeg"], op_to_jpeg),
            ("ToWebP", T["cv_webp"], op_to_webp),
            ("ToICO", T["cv_ico"], op_to_ico),
            ("Square256", T["cv_square"], op_to_square),
        ):
            tip = T["cv_tip_ico"] if name == "ToICO" else T["convert_tip"]
            self._add(submenu, name, label, self._cb_convert, images, op,
                      tip=tip)
        item = Nautilus.MenuItem(
            name="ImageTools::Convert",
            label=T["convert_menu"],
            tip=T["convert_tip"],
        )
        item.set_submenu(submenu)
        return item

    def _classify(self, paths):
        images = [p for p in paths if os.path.isfile(p) and _is_image_path(p)]
        videos = [p for p in paths if os.path.isfile(p) and _is_raiw_video(p)]
        dirs = [p for p in paths if os.path.isdir(p)]
        known = len(images) + len(videos) + len(dirs)
        if known != len(paths):
            return [], [], []
        return images, videos, dirs

    def _menu_for(self, paths):
        images, videos, dirs = self._classify(paths)
        if not (images or videos or dirs):
            return []

        top = Nautilus.MenuItem(
            name="ImageTools::Top",
            label=T["menu_label"],
            tip=T["menu_tip"],
        )
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)

        # Pillow ops read every selected file with Image.open, so they only
        # appear when the selection is images and nothing else.
        if images and len(images) == len(paths):
            self._add(submenu, "Grayscale", T["grayscale"],
                      self._cb_simple, images, op_grayscale)
            self._add(submenu, "Invert", T["invert"],
                      self._cb_simple, images, op_invert)
            self._add(submenu, "Crop", T["crop"], self._cb_crop, images)
            self._add(submenu, "Circle", T["circle"],
                      self._cb_simple, images, op_circle)
            self._add(submenu, "Resize", T["resize"], self._cb_resize, images)
            self._add(submenu, "Combine", T["combine"], self._cb_combine, images)
            self._add(submenu, "Watermark", T["watermark"],
                      self._cb_watermark, images)
            self._add(submenu, "Optimize", T["optimize"],
                      self._cb_optimize, images)
            self._add(submenu, "Colorize", T["colorize"],
                      self._cb_colorize, images, tip=T["colorize_tip"])
            if len(images) == 1:
                # The annotator edits one canvas at a time.
                self._add(submenu, "Annotate", T["an_label"],
                          self._cb_annotate, images[0], tip=T["an_tip"])
            submenu.append_item(self._convert_item(images))

        raiw = self._raiw_submenu(images, videos, dirs)
        if raiw is not None:
            submenu.append_item(raiw)

        return [top]

    def get_file_items(self, files):
        return self._menu_for(_paths_from_files(files))

    def get_background_items(self, folder):
        try:
            path = folder.get_location().get_path() if folder else None
        except Exception:  # noqa: BLE001
            path = None
        if not path or not os.path.isdir(path):
            return []
        return self._menu_for([path])

    def _guard_pillow(self):
        if Image is None:
            _show_message(T["err_pillow"])
            return False
        return True

    def _start_batch(self, tasks, messages=None):
        ProgressDialog(tasks, messages).present()

    def _cb_convert(self, _item, paths, op):
        if not self._guard_pillow():
            return
        self._start_batch([lambda p=p, op=op: op(p) for p in paths],
                          messages=_CONVERT_MSGS)

    def _cb_simple(self, _item, paths, op):
        if not self._guard_pillow():
            return
        self._start_batch([lambda p=p, op=op: op(p) for p in paths])

    def _cb_crop(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = CropDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_crop(p, s["w"], s["h"]) for p in paths]))
        dlg.present()

    def _cb_resize(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = ResizeDialog(paths[0] if paths else None)
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_resize(p, s["w"], s["h"], s["keep"],
                                            s["mode"], s["axis"], s["dpi"])
                 for p in paths]))
        dlg.present()

    def _cb_combine(self, _item, paths):
        if not self._guard_pillow():
            return
        if len(paths) < 2:
            _show_message(T["err_combine"])
            return
        dlg = CombineDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda: op_combine(paths, s["vertical"])]))
        dlg.present()

    def _cb_watermark(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = WatermarkDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_watermark(p, s) for p in paths]))
        dlg.present()

    def _cb_optimize(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = OptimizeDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_optimize(p, s["max"], s["qual"])
                 for p in paths]))
        dlg.present()

    def _cb_colorize(self, _item, paths):
        if not self._guard_pillow():
            return
        dlg = ColorizeDialog()
        dlg.set_callback(
            lambda s: s is not None and self._start_batch(
                [lambda p=p, s=s: op_colorize(p, s["color"], s["strength"])
                 for p in paths]))
        dlg.present()

    def _cb_annotate(self, _item, path):
        if not self._guard_pillow():
            return
        try:
            AnnotatorWindow(path).present()
        except Exception:
            _show_message(T["err_annotate"])