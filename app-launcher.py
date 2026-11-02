#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: App Launcher — Nautilus Python Extension
# DESC: Turn a portable executable (AppImage, ELF binary, .run/.sh script) into a
#       real desktop application — and take it back out again. The icon is found
#       automatically (inside the AppImage, in a shipped .desktop file, or in the
#       program's own folder) and can be replaced with any image the user picks.
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
# INSTALL:
#   cp app-launcher.py nautilus_i18n.py ~/.local/share/nautilus-python/extensions/
#   nautilus -q
#
# WHAT IT DOES
#   Right-clicking a single portable executable offers one of two actions:
#     * "Add to Applications"    -> writes ~/.local/share/applications/<slug>.desktop
#     * "Remove from Applications" -> deletes the user entry that launches it
#   Only one of them is ever shown, so the action is never ambiguous.
#
# ICON RESOLUTION (first hit wins)
#   1. the icon embedded in the AppImage (squashfs), located through its own
#      .desktop "Icon=" key, its .DirIcon, or the largest bundled icon;
#   2. the "Icon=" of a .desktop file shipped next to the executable;
#   3. an icon-like image found in the program's folder and sub-folders;
#   4. the generic "application-x-executable" theme icon, so an entry is never
#      icon-less.
#   A file icon is copied into a per-user folder owned by this extension, which
#   is also what the removal path cleans up.
#
# SIMPLIFICATIONS (deliberate, each with its upgrade path)
#   * One executable per action: a multi-selection shows no menu item. Batch
#     creation would need a progress dialog per file — worth it only if asked.
#   * Windows .exe / Flatpak / Snap bundles are out of scope: they need Wine or a
#     sandbox-aware launcher, which is a different feature.
#   * The generated Exec has no field code (%U/%F): portable binaries are not
#     guaranteed to accept file arguments, so the entry stays argument-free.
#     Add %U here if a future need for drag-and-drop appears.

import os
import re
import shutil
import subprocess
import tempfile
import threading
import unicodedata

import gi
gi.require_version("Gtk",      "4.0")
gi.require_version("Adw",      "1")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    # Nautilus >= 4.1 is pre-loaded by nautilus-python (e.g. Nautilus 50);
    # naming a version that is already imported only produces a warning.
    for _nautilus_version in ("4.1", "4.2"):
        try:
            gi.require_version("Nautilus", _nautilus_version)
            break
        except ValueError:
            continue

from gi.repository import GObject, Gtk, Adw, Gio, GLib, Nautilus

try:
    from nautilus_i18n import resolve_locale
except ImportError:  # nautilus_i18n.py not installed next to this file
    import locale

    def resolve_locale():
        return locale.getlocale()[0] or ""

try:  # Optional: only used to rank icons by real pixel size.
    from PIL import Image as _PILImage
except Exception:  # pragma: no cover - depends on the local install
    _PILImage = None


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
_lang = resolve_locale()

if _lang.startswith("fr"):
    T = {
        "menu_add":       "Ajouter aux applications",
        "menu_remove":    "Retirer des applications",
        "tip_add":        "Créer une entrée d'application pour ce programme",
        "tip_remove":     "Supprimer l'entrée d'application de ce programme",
        "add_title":      "Ajouter aux applications",
        "remove_title":   "Retirer des applications",
        "name":           "Nom",
        "comment":        "Commentaire",
        "terminal":       "Lancer dans un terminal",
        "make_exec":      "Rendre exécutable",
        "choose_icon":    "Choisir une icône…",
        "images":         "Images",
        "create":         "Ajouter",
        "remove":         "Retirer",
        "cancel":         "Annuler",
        "close":          "Fermer",
        "detecting":      "Recherche de l'icône…",
        "icon_appimage":  "Icône extraite de l'AppImage",
        "icon_desktop":   "Icône du fichier .desktop fourni",
        "icon_folder":    "Icône trouvée dans le dossier du programme",
        "icon_theme":     "Aucune icône trouvée — icône générique",
        "icon_custom":    "Icône choisie par vous",
        "will_create":    "Sera créé : {path}",
        "created":        "✓ Ajouté aux applications.",
        "create_failed":  "✗ Impossible de créer l'entrée : {error}",
        "confirm_remove": "Voulez-vous retirer ce programme des applications ?",
        "entries":        "Entrées qui seront supprimées :",
        "removed":        "✓ Retiré des applications.",
        "remove_failed":  "✗ Impossible de supprimer : {error}",
        "nothing_to_do":  "Aucune entrée d'application trouvée.",
        "name_required":  "Le nom ne peut pas être vide.",
    }
elif _lang.startswith("de"):
    T = {
        "menu_add":       "Zu Anwendungen hinzufügen",
        "menu_remove":    "Aus Anwendungen entfernen",
        "tip_add":        "Einen Anwendungseintrag für dieses Programm erstellen",
        "tip_remove":     "Den Anwendungseintrag dieses Programms entfernen",
        "add_title":      "Zu Anwendungen hinzufügen",
        "remove_title":   "Aus Anwendungen entfernen",
        "name":           "Name",
        "comment":        "Kommentar",
        "terminal":       "Im Terminal ausführen",
        "make_exec":      "Ausführbar machen",
        "choose_icon":    "Symbol auswählen…",
        "images":         "Bilder",
        "create":         "Hinzufügen",
        "remove":         "Entfernen",
        "cancel":         "Abbrechen",
        "close":          "Schließen",
        "detecting":      "Symbol wird gesucht…",
        "icon_appimage":  "Symbol aus dem AppImage extrahiert",
        "icon_desktop":   "Symbol aus der mitgelieferten .desktop-Datei",
        "icon_folder":    "Symbol im Programmordner gefunden",
        "icon_theme":     "Kein Symbol gefunden — generisches Symbol",
        "icon_custom":    "Von Ihnen gewähltes Symbol",
        "will_create":    "Wird erstellt: {path}",
        "created":        "✓ Zu den Anwendungen hinzugefügt.",
        "create_failed":  "✗ Eintrag konnte nicht erstellt werden: {error}",
        "confirm_remove": "Dieses Programm aus den Anwendungen entfernen?",
        "entries":        "Folgende Einträge werden gelöscht:",
        "removed":        "✓ Aus den Anwendungen entfernt.",
        "remove_failed":  "✗ Löschen fehlgeschlagen: {error}",
        "nothing_to_do":  "Kein Anwendungseintrag gefunden.",
        "name_required":  "Der Name darf nicht leer sein.",
    }
elif _lang.startswith("es"):
    T = {
        "menu_add":       "Añadir a aplicaciones",
        "menu_remove":    "Quitar de aplicaciones",
        "tip_add":        "Crear una entrada de aplicación para este programa",
        "tip_remove":     "Eliminar la entrada de aplicación de este programa",
        "add_title":      "Añadir a aplicaciones",
        "remove_title":   "Quitar de aplicaciones",
        "name":           "Nombre",
        "comment":        "Comentario",
        "terminal":       "Ejecutar en la terminal",
        "make_exec":      "Hacer ejecutable",
        "choose_icon":    "Elegir icono…",
        "images":         "Imágenes",
        "create":         "Añadir",
        "remove":         "Quitar",
        "cancel":         "Cancelar",
        "close":          "Cerrar",
        "detecting":      "Buscando el icono…",
        "icon_appimage":  "Icono extraído del AppImage",
        "icon_desktop":   "Icono del archivo .desktop incluido",
        "icon_folder":    "Icono encontrado en la carpeta del programa",
        "icon_theme":     "No se encontró icono — icono genérico",
        "icon_custom":    "Icono elegido por usted",
        "will_create":    "Se creará: {path}",
        "created":        "✓ Añadido a las aplicaciones.",
        "create_failed":  "✗ No se pudo crear la entrada: {error}",
        "confirm_remove": "¿Quitar este programa de las aplicaciones?",
        "entries":        "Entradas que se eliminarán:",
        "removed":        "✓ Eliminado de las aplicaciones.",
        "remove_failed":  "✗ No se pudo eliminar: {error}",
        "nothing_to_do":  "No se encontró ninguna entrada de aplicación.",
        "name_required":  "El nombre no puede estar vacío.",
    }
elif _lang.startswith("pt"):
    T = {
        "menu_add":       "Adicionar aos aplicativos",
        "menu_remove":    "Remover dos aplicativos",
        "tip_add":        "Criar um atalho de aplicativo para este programa",
        "tip_remove":     "Remover o atalho de aplicativo deste programa",
        "add_title":      "Adicionar aos aplicativos",
        "remove_title":   "Remover dos aplicativos",
        "name":           "Nome",
        "comment":        "Comentário",
        "terminal":       "Executar no terminal",
        "make_exec":      "Tornar executável",
        "choose_icon":    "Escolher ícone…",
        "images":         "Imagens",
        "create":         "Adicionar",
        "remove":         "Remover",
        "cancel":         "Cancelar",
        "close":          "Fechar",
        "detecting":      "Procurando o ícone…",
        "icon_appimage":  "Ícone extraído do AppImage",
        "icon_desktop":   "Ícone do arquivo .desktop que acompanha o programa",
        "icon_folder":    "Ícone encontrado na pasta do programa",
        "icon_theme":     "Nenhum ícone encontrado — ícone genérico",
        "icon_custom":    "Ícone escolhido por você",
        "will_create":    "Será criado: {path}",
        "created":        "✓ Adicionado aos aplicativos.",
        "create_failed":  "✗ Não foi possível criar o atalho: {error}",
        "confirm_remove": "Deseja remover este programa dos aplicativos?",
        "entries":        "Atalhos que serão removidos:",
        "removed":        "✓ Removido dos aplicativos.",
        "remove_failed":  "✗ Não foi possível remover: {error}",
        "nothing_to_do":  "Nenhum atalho de aplicativo encontrado.",
        "name_required":  "O nome não pode ficar vazio.",
    }
else:
    T = {
        "menu_add":       "Add to Applications",
        "menu_remove":    "Remove from Applications",
        "tip_add":        "Create an application entry for this program",
        "tip_remove":     "Delete this program's application entry",
        "add_title":      "Add to Applications",
        "remove_title":   "Remove from Applications",
        "name":           "Name",
        "comment":        "Comment",
        "terminal":       "Run in a terminal",
        "make_exec":      "Make executable",
        "choose_icon":    "Choose icon…",
        "images":         "Images",
        "create":         "Add",
        "remove":         "Remove",
        "cancel":         "Cancel",
        "close":          "Close",
        "detecting":      "Looking for the icon…",
        "icon_appimage":  "Icon extracted from the AppImage",
        "icon_desktop":   "Icon from the shipped .desktop file",
        "icon_folder":    "Icon found in the program's folder",
        "icon_theme":     "No icon found — generic icon",
        "icon_custom":    "Icon chosen by you",
        "will_create":    "Will be created: {path}",
        "created":        "✓ Added to the applications.",
        "create_failed":  "✗ Could not create the entry: {error}",
        "confirm_remove": "Remove this program from the applications?",
        "entries":        "Entries that will be deleted:",
        "removed":        "✓ Removed from the applications.",
        "remove_failed":  "✗ Could not remove: {error}",
        "nothing_to_do":  "No application entry found.",
        "name_required":  "The name cannot be empty.",
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FALLBACK_ICON = "application-x-executable"

# Executables that are just a script/binary in a file: offered when +x.
SCRIPT_SUFFIXES = (".run", ".bin", ".sh")

APPIMAGE_MAGIC = (b"AI\x01", b"AI\x02")  # at byte offset 8 of the ELF header
ELF_MAGIC = b"\x7fELF"
SHEBANG = b"#!"

# SquashFS superblock magic. The superblock is never compressed, so it sits
# verbatim at the start of the filesystem inside the AppImage.
SQUASHFS_MAGIC = b"hsqs"
SQUASHFS_SCAN_BYTES = 4 * 1024 * 1024

# Icon files a .desktop "Icon=" may point at, best format first.
ICON_EXTENSIONS = (".png", ".svg", ".xpm", ".webp")
ICON_EXT_RANK = {".svg": 0, ".png": 1, ".webp": 2, ".xpm": 3}

# Folder scan bounds: the program's folder is level 0.
SCAN_MAX_DEPTH = 3
SCAN_MAX_FILES = 4000
SCAN_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", "vendor", "build", "dist",
    "target", ".venv", "venv", "locale", "locales", "translations", "lang",
})

# Folder names that conventionally hold an application icon.
ICONISH_DIRS = frozenset({
    "icons", "icon", "iconset", "pixmaps", "resources", "resource",
    "assets", "asset", "images", "image", "img", "data", "share", "media",
    "graphics", "artwork",
})

# File stems that name an icon without naming the program.
GENERIC_ICON_STEMS = frozenset({
    "icon", "icons", "logo", "app", "application", "appicon", "program",
    "main", "default", "brand", "symbol", "emblem", "avatar", "launcher",
    "icone", "logotipo", "simbolo", "programa", "anwendung", "programme",
})

# Version / architecture noise removed from a file name to get a pretty title.
NAME_NOISE = re.compile(
    r"^(v?\d+(\.\d+)*[a-z0-9]*|x86[_-]?64|amd64|aarch64|arm64|armhf|i[3-6]86|"
    r"linux|gnu|glibc|musl|appimage|portable|static|bin|run|sh|elf)$",
    re.IGNORECASE,
)

EXEC_FIELD_CODES = ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N",
                    "%i", "%c", "%k", "%v", "%m")

EXTRACTION_TIMEOUT = 45   # seconds, per external extraction call

# Scratch folders holding an icon lifted out of an AppImage. They survive the
# extraction clean-up (the dialog still shows the preview) and are dropped when
# the dialog closes or the entry is created.
_EXTRACTED_ICON_DIRS = []


def cleanup_extracted_icons():
    """Remove the temporary icon folders of finished dialogs."""
    for directory in list(_EXTRACTED_ICON_DIRS):
        shutil.rmtree(directory, ignore_errors=True)
        try:
            _EXTRACTED_ICON_DIRS.remove(directory)
        except ValueError:
            pass


def log(message):
    """Diagnostics land in the journal (`journalctl --user -g app-launcher`)."""
    print(f"[app-launcher] {message}")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _text_key(text):
    """Lower case, accent-free, alphanumeric only: comparable stems."""
    folded = unicodedata.normalize("NFKD", str(text or "").lower())
    plain = "".join(char for char in folded if not unicodedata.combining(char))
    return "".join(char for char in plain if char.isalnum())


def _read_prefix(path, size=16):
    try:
        with open(path, "rb") as handle:
            return handle.read(size)
    except OSError:
        return b""


def user_data_home():
    """$XDG_DATA_HOME with the spec's fallback."""
    return os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")


def user_applications_dir():
    """Where per-user .desktop entries live. Never the system one."""
    return os.path.join(user_data_home(), "applications")


def user_icon_dir():
    """Icons copied by this extension: trivially removable, never in the theme."""
    return os.path.join(user_data_home(), "nautilus-extensions",
                        "app-launcher", "icons")


def scratch_root():
    """Scratch space for AppImage extraction, under the user's cache dir."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return os.path.join(base, "nautilus-app-launcher")


# ---------------------------------------------------------------------------
# Executable detection
# ---------------------------------------------------------------------------
def is_appimage(path):
    """AppImage by extension *or* by magic, so a renamed file still works."""
    if str(path).lower().endswith(".appimage"):
        return True
    prefix = _read_prefix(path, 12)
    return prefix[8:11] in APPIMAGE_MAGIC


def is_elf_executable(path):
    return _read_prefix(path, 4) == ELF_MAGIC or _read_prefix(path, 2) == SHEBANG


def is_portable_executable(path):
    """True for the file kinds this extension can turn into an application.

    AppImages are offered even without the executable bit: the missing bit is a
    very common download artefact, and the dialog exposes it as an explicit
    "Make executable" switch instead of silently refusing the file.
    """
    if not path or not os.path.isfile(path):
        return False
    name = os.path.basename(str(path))
    if not name or name.startswith("."):
        return False
    if name.lower().endswith(".desktop"):
        return False
    if is_appimage(path):
        return True
    if not os.access(path, os.X_OK):
        return False
    if str(name).lower().endswith(SCRIPT_SUFFIXES):
        return True
    return is_elf_executable(path)


def is_executable_bit_set(path):
    return bool(path) and os.access(path, os.X_OK)


def pretty_name(filename):
    """'MyApp-1.2.3-x86_64.AppImage' -> 'MyApp'.

    Version and architecture tokens are dropped only when they are the whole
    token, so a program genuinely called "Run" keeps its name.
    """
    base = os.path.basename(str(filename))
    for suffix in (".appimage",) + SCRIPT_SUFFIXES:
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
            break
    tokens = [token for token in re.split(r"[\s.\-]+", base) if token]
    kept = [token for token in tokens if not NAME_NOISE.match(token)]
    # A noise token can hide behind an underscore ("x86_64"); strip it whole
    # before underscores are treated as word separators.
    kept = [part for token in kept
            for part in re.split(r"_+", token) if part]
    kept = [token for token in kept if not NAME_NOISE.match(token)]
    if not kept:
        kept = tokens or [base or "app"]
    title = " ".join(kept)
    # Keep an intentional camel case ("GIMP") but capitalise the plain ones.
    return title if title != title.lower() else title.title()


def slugify(name):
    """File stem for the .desktop: lowercase, [a-z0-9-], no empty result."""
    key = _text_key(name)
    slug = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", key)).strip("-")
    return slug[:64] or "app"


# ---------------------------------------------------------------------------
# .desktop reading / writing
# ---------------------------------------------------------------------------
def read_desktop_entry(path):
    """The plain keys of the [Desktop Entry] group, tolerant to real files.

    Localised keys (Name[pt_BR]) are skipped on purpose: the caller wants the
    default value. Duplicate keys keep the first occurrence, like the spec.
    """
    data = {}
    group = None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    group = line[1:-1]
                    continue
                if group != "Desktop Entry" or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or "[" in key or key in data:
                    continue
                data[key] = value.strip()
    except OSError as error:
        log(f"cannot read {path}: {error}")
        return {}
    return data


def quote_exec_argument(value):
    """A single Exec argument, quoted and escaped the way the spec demands.

    Inside double quotes the reserved characters are \" ` $ and \\; the field
    code marker % becomes %%.
    """
    escaped = str(value).replace("%", "%%")
    escaped = escaped.replace("\\", "\\\\")
    for char in ('"', "`", "$"):
        escaped = escaped.replace(char, "\\" + char)
    return f'"{escaped}"'


def build_desktop_entry(name, exec_path, icon, comment="", terminal=False,
                        categories="Utility;"):
    """The [Desktop Entry] text, ready to be written to disk."""
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={_single_line(name)}",
    ]
    if comment:
        lines.append(f"Comment={_single_line(comment)}")
    lines.append(f"Exec={quote_exec_argument(exec_path)}")
    lines.append(f"Icon={_single_line(icon) or FALLBACK_ICON}")
    lines.append(f"Terminal={'true' if terminal else 'false'}")
    lines.append(f"Categories={_single_line(categories) or 'Utility;'}")
    lines.append("StartupNotify=true")
    return "\n".join(lines) + "\n"


def _single_line(value):
    """Desktop entry values are single-line, always."""
    return " ".join(str(value or "").split())


def split_exec_value(exec_value):
    """Tokenise an Exec value the way the desktop spec quotes it.

    `shlex` is *almost* right but not quite: the spec's double-quote escaping
    and its %% escape for a literal % are not shell rules, so the parser is
    explicit here.
    """
    tokens = []
    current = []
    quote = None
    index = 0
    text = str(exec_value or "")
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            current.append(text[index + 1])
            index += 2
            continue
        if char in "\"'":
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            else:
                current.append(char)
            index += 1
            continue
        if char in " \t" and quote is None:
            if current:
                tokens.append("".join(current))
                current = []
            index += 1
            continue
        current.append(char)
        index += 1
    if current:
        tokens.append("".join(current))
    return [token.replace("%%", "%") for token in tokens]


def exec_argv(exec_value):
    """Split an Exec value into arguments, dropping the field codes."""
    argv = split_exec_value(exec_value)
    result = []
    for token in argv:
        if token.lower() in EXEC_FIELD_CODES:
            continue
        result.append(token)
    # "env VAR=value command" -> command
    if result and os.path.basename(result[0]) == "env":
        result.pop(0)
        while result and (result[0].startswith("-") or "=" in result[0]):
            result.pop(0)
    return result


def exec_program(exec_value):
    """The absolute path of the program an Exec value launches, or None."""
    argv = exec_argv(exec_value)
    if not argv:
        return None
    program = os.path.expanduser(argv[0])
    if os.path.isabs(program):
        return program
    return shutil.which(program)


def desktop_entries_for(executable, apps_dir=None):
    """Every user .desktop entry whose Exec resolves to this exact file."""
    apps_dir = apps_dir or user_applications_dir()
    try:
        names = sorted(os.listdir(apps_dir))
    except OSError:
        return []
    target = os.path.realpath(executable)
    found = []
    for name in names:
        if not name.endswith(".desktop"):
            continue
        path = os.path.join(apps_dir, name)
        if not os.path.isfile(path):
            continue
        entry = read_desktop_entry(path)
        if entry.get("Type", "Application") != "Application":
            continue
        program = exec_program(entry.get("Exec", ""))
        if not program:
            continue
        if os.path.realpath(program) == target:
            found.append(path)
    return found


def unique_desktop_path(slug, executable, apps_dir=None):
    """`<slug>.desktop`, suffixed until it does not clash with another program."""
    apps_dir = apps_dir or user_applications_dir()
    target = os.path.realpath(executable)
    candidate = os.path.join(apps_dir, f"{slug}.desktop")
    index = 2
    while os.path.exists(candidate):
        if os.path.realpath(exec_program(
                read_desktop_entry(candidate).get("Exec", "")) or "") == target:
            return candidate  # already ours: overwrite in place
        candidate = os.path.join(apps_dir, f"{slug}-{index}.desktop")
        index += 1
    return candidate


def refresh_desktop_database(apps_dir=None):
    """Make the new entry visible to the Shell without restarting anything."""
    apps_dir = apps_dir or user_applications_dir()
    tool = shutil.which("update-desktop-database")
    if tool:
        try:
            subprocess.run([tool, apps_dir], timeout=20,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as error:
            log(f"update-desktop-database failed: {error}")


def copy_icon_file(source, slug):
    """Copy an icon into the extension's own folder, keeping its extension."""
    extension = os.path.splitext(source)[1].lower() or ".png"
    if extension not in ICON_EXTENSIONS:
        extension = ".png"
    target_dir = user_icon_dir()
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, f"{slug}{extension}")
    shutil.copyfile(source, target)
    return target


# ---------------------------------------------------------------------------
# Icon discovery — the program folder
# ---------------------------------------------------------------------------
def _image_dimensions(path):
    """(width, height) of a raster icon, or (0, 0) when unknowable."""
    if _PILImage is None or path.lower().endswith(".svg"):
        return (0, 0)
    try:
        with _PILImage.open(path) as image:
            return image.size
    except Exception:
        return (0, 0)


def _is_iconish(path, program_key):
    """Cheap filter before ranking: could this file plausibly be the icon?"""
    stem = _text_key(os.path.splitext(os.path.basename(path))[0])
    if not stem:
        return False
    if program_key and (program_key in stem or stem in program_key):
        return True
    if stem in GENERIC_ICON_STEMS:
        return True
    if any(hint in stem for hint in ("icon", "logo", "emblem", "icone")):
        return True
    parent = os.path.basename(os.path.dirname(path)).lower()
    return parent in ICONISH_DIRS


def find_folder_icons(root, program_key):
    """Ranked icon-like images under `root`, best candidate first.

    Mtime and inode order are never used, so the same tree always yields the
    same icon: the ranking is (name match, size, format, depth, path).
    """
    ranked = []
    seen_paths = 0
    for dirpath, dirnames, filenames in os.walk(root):
        relative = os.path.relpath(dirpath, root)
        depth = 0 if relative in (".", "") else len(relative.split(os.sep))
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".") and name.lower() not in SCAN_SKIP_DIRS
        )
        if depth >= SCAN_MAX_DEPTH:
            dirnames[:] = []
        for name in sorted(filenames):
            seen_paths += 1
            if seen_paths > SCAN_MAX_FILES:
                return _sorted_icons(ranked)
            if name.startswith("."):
                continue
            extension = os.path.splitext(name)[1].lower()
            if extension not in ICON_EXTENSIONS:
                continue
            path = os.path.join(dirpath, name)
            if not _is_iconish(path, program_key):
                continue
            stem = _text_key(os.path.splitext(name)[0])
            if stem == program_key:
                name_rank = 0
            elif program_key and stem.startswith(program_key):
                name_rank = 1
            elif program_key and program_key in stem:
                name_rank = 2
            elif stem in GENERIC_ICON_STEMS:
                name_rank = 3
            else:
                name_rank = 4
            width, height = _image_dimensions(path)
            side = min(width, height) if width and height else 0
            # Prefer a real application icon size; 0 means "unknown", ranked
            # after the known-good sizes but before the tiny ones.
            if side >= 128:
                size_rank = 0
            elif side == 0:
                size_rank = 1
            else:
                size_rank = 2
            ranked.append((
                name_rank, size_rank, ICON_EXT_RANK.get(extension, 9),
                depth, -side, name.lower(), path,
            ))
    return _sorted_icons(ranked)


def _sorted_icons(ranked):
    ranked.sort(key=lambda item: item[:6])
    return [item[-1] for item in ranked]


def find_bundled_desktop(executable):
    """The nearest .desktop shipped next to (or inside) the program's folder."""
    folder = os.path.dirname(os.path.realpath(executable))
    if not os.path.isdir(folder):
        return None
    candidates = []
    for dirpath, dirnames, filenames in os.walk(folder):
        relative = os.path.relpath(dirpath, folder)
        depth = 0 if relative in (".", "") else len(relative.split(os.sep))
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".") and name.lower() not in SCAN_SKIP_DIRS
        )
        if depth >= SCAN_MAX_DEPTH:
            dirnames[:] = []
        for name in sorted(filenames):
            if not name.endswith(".desktop"):
                continue
            path = os.path.join(dirpath, name)
            if not os.path.isfile(path):
                continue
            entry = read_desktop_entry(path)
            if not entry.get("Name") or not entry.get("Exec"):
                continue
            # Same folder wins, then share/applications, then the rest.
            is_share = os.path.basename(dirpath) == "applications"
            candidates.append((depth, 0 if is_share else 1, name.lower(), path))
        if candidates and depth == 0:
            break  # a same-folder entry is the intended one
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][-1]


def looks_like_theme_icon(value):
    """A bare icon *name* ("org.gnome.Terminal") rather than a file path."""
    value = str(value or "").strip()
    if not value or "/" in value:
        return False
    extension = os.path.splitext(value)[1].lower()
    return extension not in ICON_EXTENSIONS + (".ico", ".jpg", ".jpeg")


def resolve_icon_reference(value, entry_dir, root, search_stems=True):
    """Turn an Icon= value into a file path, searching `root` when needed.

    `Icon=` may be an absolute path, a path relative to the .desktop file, a
    path relative to the image root, or a bare theme name. `search_stems`
    enables the bare-name walk, which is cheap inside an extracted AppImage but
    would crawl a real program folder — hence the switch.
    """
    value = str(value or "").strip()
    if not value:
        return None
    if os.path.isabs(value):
        if os.path.isfile(value):
            return value
        inside = os.path.join(root, value.lstrip(os.sep))
        return inside if os.path.isfile(inside) else None
    if "/" in value:
        for base in (entry_dir, root):
            candidate = os.path.normpath(os.path.join(base, value))
            if os.path.isfile(candidate):
                return candidate
        return None
    if not search_stems:
        return None
    # Bare name: find a file with that stem anywhere in the extracted tree.
    wanted = _text_key(value)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in sorted(filenames):
            stem, extension = os.path.splitext(name)
            if extension.lower() in ICON_EXTENSIONS and _text_key(stem) == wanted:
                return os.path.join(dirpath, name)
    return None


# ---------------------------------------------------------------------------
# Icon discovery — the AppImage
# ---------------------------------------------------------------------------
def squashfs_offsets(path, max_scan=SQUASHFS_SCAN_BYTES):
    """Byte offsets of every SquashFS superblock in the AppImage preamble."""
    offsets = []
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(max_scan)
    except OSError as error:
        log(f"cannot read {path}: {error}")
        return offsets
    start = chunk.find(SQUASHFS_MAGIC)
    while start != -1:
        offsets.append(start)
        start = chunk.find(SQUASHFS_MAGIC, start + 1)
    return offsets


UNSQUASHFS_PATTERNS = (
    ".DirIcon", "*.desktop", "*.png", "*.svg", "*.xpm",
    "usr/share/applications/*", "usr/share/icons/*", "usr/share/pixmaps/*",
)


def _dir_has_content(directory):
    try:
        with os.scandir(directory) as entries:
            return any(True for _ in entries)
    except OSError:
        return False


def _extract_with_unsquashfs(image, destination):
    tool = shutil.which("unsquashfs")
    if not tool:
        return False
    for offset in squashfs_offsets(image):
        command = [tool, "-o", str(offset), "-d", destination, "-n", "-q",
                   image, *UNSQUASHFS_PATTERNS]
        try:
            result = subprocess.run(command, timeout=EXTRACTION_TIMEOUT,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as error:
            log(f"unsquashfs failed at offset {offset}: {error}")
            continue
        # A pattern that matches nothing makes unsquashfs exit non-zero while
        # still extracting the patterns that did match, so content wins.
        if os.path.isdir(destination) and _dir_has_content(destination):
            return True
        if result.returncode == 0:
            return False  # valid image, but nothing worth extracting
        shutil.rmtree(destination, ignore_errors=True)
    return False


def _extract_with_runtime(image, destination):
    """Fallback when squashfs-tools is absent: the AppImage's own runtime.

    Only the AppImage *runtime stub* runs here, never the application inside it
    — which is the documented way to read an AppImage's contents without a
    squashfs reader. It is the file the user is about to launch anyway.
    """
    if not is_executable_bit_set(image):
        return False
    try:
        subprocess.run(
            [os.path.realpath(image), "--appimage-extract", *UNSQUASHFS_PATTERNS],
            cwd=destination, timeout=EXTRACTION_TIMEOUT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log(f"appimage runtime extraction failed: {error}")
        return False
    extracted = os.path.join(destination, "squashfs-root")
    if not os.path.isdir(extracted) or not _dir_has_content(extracted):
        return False
    # Flatten, so both extraction strategies produce the same layout.
    for name in os.listdir(extracted):
        shutil.move(os.path.join(extracted, name), destination)
    shutil.rmtree(extracted, ignore_errors=True)
    return True


def extract_appimage(image):
    """Extract an AppImage's icon + .desktop into a scratch dir (or nothing).

    Returns (desktop_dict, icon_path); both may be None. The extraction tree is
    always removed; the icon that survives lives in a tracked temporary folder
    dropped by cleanup_extracted_icons().
    """
    os.makedirs(scratch_root(), exist_ok=True)
    destination = tempfile.mkdtemp(prefix="extract-", dir=scratch_root())
    try:
        extracted = _extract_with_unsquashfs(image, destination)
        if not extracted:
            extracted = _extract_with_runtime(image, destination)
        if not extracted:
            log(f"could not extract {image}")
            return (None, None)
        desktop, icon = _pick_from_extracted_tree(destination)
        if icon:
            # The scratch dir is removed below: move the winner out first.
            keep = tempfile.mkdtemp(prefix="icon-", dir=scratch_root())
            _EXTRACTED_ICON_DIRS.append(keep)
            target = os.path.join(keep, os.path.basename(icon) or "icon.png")
            shutil.copyfile(os.path.realpath(icon), target)
            icon = target
        return (desktop, icon)
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def _pick_from_extracted_tree(root):
    """Best .desktop entry and best icon file inside an extracted AppImage."""
    desktops = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(".desktop"):
                desktops.append(os.path.join(dirpath, name))
    desktops.sort(key=lambda path: (os.path.basename(os.path.dirname(path))
                                    != "applications", path))

    desktop_entry = None
    for path in desktops:
        entry = read_desktop_entry(path)
        if not entry.get("Name"):
            continue
        desktop_entry = desktop_entry or entry
        icon = resolve_icon_reference(entry.get("Icon"), os.path.dirname(path), root)
        if icon:
            return (desktop_entry, icon)

    dir_icon = os.path.join(root, ".DirIcon")
    if os.path.lexists(dir_icon):
        # .DirIcon is usually a symlink; unsquashfs keeps it as one.
        if os.path.exists(dir_icon):
            return (desktop_entry, os.path.realpath(dir_icon))
        wanted = os.path.basename(os.readlink(dir_icon)) if os.path.islink(dir_icon) else ""
        if wanted:
            for dirpath, _dirnames, filenames in os.walk(root):
                if wanted in filenames:
                    return (desktop_entry, os.path.join(dirpath, wanted))

    ranked = find_folder_icons(root, "")
    return (desktop_entry, ranked[0] if ranked else None)


# ---------------------------------------------------------------------------
# What the dialog needs to know
# ---------------------------------------------------------------------------
class IconChoice:
    """Either a file to copy, or a theme icon name used as-is."""

    __slots__ = ("kind", "value", "source")

    def __init__(self, kind, value, source):
        self.kind = kind          # "file" | "theme"
        self.value = value        # absolute path | theme icon name
        self.source = source      # appimage | desktop | folder | theme | custom

    def is_file(self):
        return self.kind == "file"


class LauncherInfo:
    """Everything the dialog pre-fills, discovered without touching GTK."""

    __slots__ = ("path", "name", "comment", "terminal", "categories",
                 "icon", "needs_chmod", "desktop_path")

    def __init__(self, path, name, comment, terminal, categories, icon,
                 needs_chmod, desktop_path):
        self.path = path
        self.name = name
        self.comment = comment
        self.terminal = terminal
        self.categories = categories
        self.icon = icon
        self.needs_chmod = needs_chmod
        self.desktop_path = desktop_path


def inspect_executable(path):
    """Discover name, comment, terminal flag and icon for one executable."""
    embedded_desktop = None
    embedded_icon = None
    if is_appimage(path):
        embedded_desktop, embedded_icon = extract_appimage(path)

    bundled_desktop = find_bundled_desktop(path)
    bundled_entry = read_desktop_entry(bundled_desktop) if bundled_desktop else {}

    # Embedded metadata is authoritative for an AppImage; a loose .desktop next
    # to the program is the next best source.
    metadata = embedded_desktop or bundled_entry
    name = _single_line(metadata.get("Name")) or pretty_name(os.path.basename(path))
    comment = _single_line(metadata.get("Comment"))
    categories = _single_line(metadata.get("Categories")) or "Utility;"
    terminal = str(metadata.get("Terminal", "")).lower() == "true"
    if not metadata and str(path).lower().endswith(".sh"):
        terminal = True  # a shell script almost always wants a terminal

    icon = None
    if embedded_icon:
        icon = IconChoice("file", embedded_icon, "appimage")
    elif bundled_desktop and bundled_entry.get("Icon"):
        value = _single_line(bundled_entry["Icon"])
        resolved = resolve_icon_reference(
            value, os.path.dirname(bundled_desktop),
            os.path.dirname(bundled_desktop), search_stems=False)
        if resolved:
            icon = IconChoice("file", resolved, "desktop")
        elif looks_like_theme_icon(value):
            # A bare name is a theme icon: it needs no copy at all.
            icon = IconChoice("theme", value, "desktop")
    if icon is None:
        program_key = _text_key(pretty_name(os.path.basename(path)))
        found = find_folder_icons(os.path.dirname(os.path.realpath(path)),
                                  program_key)
        if found:
            icon = IconChoice("file", found[0], "folder")
    if icon is None:
        icon = IconChoice("theme", FALLBACK_ICON, "theme")

    slug = slugify(name)
    return LauncherInfo(
        path=path,
        name=name,
        comment=comment,
        terminal=terminal,
        categories=categories,
        icon=icon,
        needs_chmod=not is_executable_bit_set(path),
        desktop_path=unique_desktop_path(slug, path),
    )


# ---------------------------------------------------------------------------
# Installing / removing the entry
# ---------------------------------------------------------------------------
def create_application(info, name=None, comment=None, terminal=None,
                       icon=None, make_executable=None):
    """Write the .desktop entry (and its icon) and refresh the database.

    Returns the path of the created entry. Raises OSError/RuntimeError on
    failure, so the dialog can show the real reason instead of a silent no-op.
    """
    name = _single_line(name if name is not None else info.name)
    if not name:
        raise ValueError("empty name")
    comment = _single_line(comment if comment is not None else info.comment)
    terminal = info.terminal if terminal is None else bool(terminal)
    icon = icon or info.icon
    make_executable = (info.needs_chmod if make_executable is None
                       else bool(make_executable))

    executable = os.path.realpath(info.path)
    if make_executable and not is_executable_bit_set(executable):
        mode = os.stat(executable).st_mode
        os.chmod(executable, mode | 0o111)

    slug = slugify(name)
    if icon.is_file():
        icon_reference = copy_icon_file(icon.value, slug)
    else:
        icon_reference = icon.value or FALLBACK_ICON

    content = build_desktop_entry(
        name=name,
        exec_path=executable,
        icon=icon_reference,
        comment=comment,
        terminal=terminal,
        categories=info.categories,
    )
    target = unique_desktop_path(slug, executable)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(temporary, 0o755)
    os.replace(temporary, target)
    refresh_desktop_database(os.path.dirname(target))
    return target


def icon_files_of(entry_path):
    """Icon files this extension installed for an entry (never foreign ones)."""
    entry = read_desktop_entry(entry_path)
    value = entry.get("Icon", "")
    if not value or not os.path.isabs(value):
        return []
    owned = os.path.realpath(user_icon_dir()) + os.sep
    real = os.path.realpath(value)
    return [real] if real.startswith(owned) and os.path.isfile(real) else []


def remove_applications(executable, entries=None):
    """Delete the user entries (and owned icons) launching this executable.

    Returns the list of removed .desktop paths. Only files inside the user
    applications directory are ever touched.
    """
    entries = entries if entries is not None else desktop_entries_for(executable)
    apps_dir = os.path.realpath(user_applications_dir()) + os.sep
    removed = []
    for path in entries:
        real = os.path.realpath(path)
        if not real.startswith(apps_dir) or not os.path.isfile(real):
            log(f"refusing to delete outside the user entries: {path}")
            continue
        icons = icon_files_of(real)
        try:
            os.remove(real)
        except OSError as error:
            log(f"cannot remove {real}: {error}")
            continue
        for icon in icons:
            try:
                os.remove(icon)
            except OSError:
                pass
        removed.append(real)
    if removed:
        refresh_desktop_database(os.path.dirname(removed[0]))
    return removed


# ---------------------------------------------------------------------------
# GTK helpers
# ---------------------------------------------------------------------------
def _nautilus_window():
    app = Gtk.Application.get_default()
    return app.get_active_window() if app else None


def _present_when_idle(widget):
    """Wayland: presenting inside a menu-activate handler leaves dead buttons.

    One idle turn lets Nautilus finish dismissing the menu first.
    """
    GLib.idle_add(widget.present)


def _alert(heading, body, responses, destructive=None):
    """Adw.AlertDialog when available, Adw.MessageDialog on older libadwaita."""
    dialog = None
    if hasattr(Adw, "AlertDialog"):
        dialog = Adw.AlertDialog(heading=heading)
    elif hasattr(Adw, "MessageDialog"):  # libadwaita < 1.5 (e.g. Ubuntu 22.04)
        try:
            dialog = Adw.MessageDialog(transient_for=_nautilus_window(),
                                       heading=heading)
        except TypeError:
            dialog = Adw.MessageDialog()
            dialog.set_heading(heading)
    if dialog is None:
        return None
    if body:
        dialog.set_body(body)
    for identifier, label in responses:
        dialog.add_response(identifier, label)
    if destructive:
        try:
            dialog.set_response_appearance(
                destructive, Adw.ResponseAppearance.DESTRUCTIVE)
        except Exception:
            pass
    if responses:
        try:
            dialog.set_default_response(responses[-1][0])
            dialog.set_close_response(responses[0][0])
        except Exception:
            pass
    return dialog


def _show_alert(heading, body, responses=(("close", T["close"]),)):
    dialog = _alert(heading, body, responses)

    def on_response(_dialog, identifier):
        try:
            _dialog.close()
        except Exception:
            pass

    dialog.connect("response", on_response)
    _present_when_idle(dialog)
    return dialog


# ---------------------------------------------------------------------------
# Add dialog
# ---------------------------------------------------------------------------
class AddToApplicationsWindow(Adw.Window):
    __gtype_name__ = "AppLauncherAddWindow"

    def __init__(self, path):
        super().__init__(title=T["add_title"])
        self.set_default_size(560, 600)
        self.set_resizable(True)
        self.set_transient_for(_nautilus_window())

        self._path = path
        self._info = None
        self._icon = IconChoice("theme", FALLBACK_ICON, "theme")
        self._busy = True

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_decoration_layout(":close")
        header.set_title_widget(Gtk.Label(label=T["add_title"]))
        toolbar.add_top_bar(header)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        body.set_margin_start(18)
        body.set_margin_end(18)
        body.set_margin_top(18)
        body.set_margin_bottom(18)

        # ── icon preview ──────────────────────────────────────────────────
        icon_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self._preview = Gtk.Image.new_from_icon_name(FALLBACK_ICON)
        self._preview.set_pixel_size(72)
        icon_row.append(self._preview)

        icon_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        icon_text.set_valign(Gtk.Align.CENTER)

        self._source_label = Gtk.Label(label=T["detecting"])
        self._source_label.set_halign(Gtk.Align.START)
        self._source_label.set_wrap(True)
        self._source_label.set_xalign(0)
        self._source_label.add_css_class("dim-label")
        icon_text.append(self._source_label)

        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(True)
        self._spinner.start()
        self._spinner.set_halign(Gtk.Align.START)
        icon_text.append(self._spinner)

        self._choose_button = Gtk.Button(label=T["choose_icon"])
        self._choose_button.set_halign(Gtk.Align.START)
        self._choose_button.add_css_class("pill")
        self._choose_button.connect("clicked", self._on_choose_icon)
        icon_text.append(self._choose_button)

        icon_row.append(icon_text)
        body.append(icon_row)

        # ── metadata ──────────────────────────────────────────────────────
        group = Adw.PreferencesGroup()
        self._name_row = Adw.EntryRow(title=T["name"])
        group.add(self._name_row)
        self._comment_row = Adw.EntryRow(title=T["comment"])
        group.add(self._comment_row)
        self._terminal_row = Adw.SwitchRow(title=T["terminal"])
        group.add(self._terminal_row)
        self._chmod_row = Adw.SwitchRow(title=T["make_exec"])
        self._chmod_row.set_visible(False)
        group.add(self._chmod_row)
        body.append(group)

        self._path_label = Gtk.Label(label="")
        self._path_label.set_halign(Gtk.Align.START)
        self._path_label.set_xalign(0)
        self._path_label.set_wrap(True)
        self._path_label.add_css_class("caption")
        self._path_label.add_css_class("dim-label")
        body.append(self._path_label)

        self._status_label = Gtk.Label(label="")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_xalign(0)
        self._status_label.set_wrap(True)
        self._status_label.add_css_class("caption")
        self._status_label.set_visible(False)
        body.append(self._status_label)

        scroller.set_child(body)
        toolbar.set_content(scroller)
        # ── bottom bar ────────────────────────────────────────────────────
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom.set_margin_start(12)
        bottom.set_margin_end(12)
        bottom.set_margin_top(8)
        bottom.set_margin_bottom(8)
        bottom.set_halign(Gtk.Align.END)

        self._cancel_button = Gtk.Button(label=T["cancel"])
        self._cancel_button.connect("clicked", lambda *_: self.close())
        bottom.append(self._cancel_button)

        self._create_button = Gtk.Button(label=T["create"])
        self._create_button.add_css_class("suggested-action")
        self._create_button.connect("clicked", self._on_create)
        bottom.append(self._create_button)

        toolbar.add_bottom_bar(bottom)
        self.set_content(toolbar)

        # Everything is disabled until the detection thread reports back.
        self._set_sensitive(False)
        threading.Thread(target=self._detect, daemon=True).start()

    # ── detection ─────────────────────────────────────────────────────────

    def _detect(self):
        try:
            info = inspect_executable(self._path)
        except Exception as error:  # never leave the dialog stuck on a spinner
            log(f"detection failed for {self._path}: {error}")
            info = None
        GLib.idle_add(self._apply_info, info)

    def _apply_info(self, info):
        self._info = info
        self._spinner.stop()
        self._spinner.set_visible(False)
        self._busy = False

        if info is None:
            self._source_label.set_text(T["icon_theme"])
            self._set_sensitive(True)
            return

        self._icon = info.icon
        self._render_icon()
        self._name_row.set_text(info.name)
        self._comment_row.set_text(info.comment)
        self._terminal_row.set_active(info.terminal)
        self._chmod_row.set_active(info.needs_chmod)
        self._chmod_row.set_visible(info.needs_chmod)
        self._path_label.set_text(T["will_create"].format(path=info.desktop_path))
        self._set_sensitive(True)
        return False

    def _render_icon(self):
        icon = self._icon
        source_key = f"icon_{icon.source}"
        self._source_label.set_text(T.get(source_key, T["icon_theme"]))
        if icon.is_file() and os.path.isfile(icon.value):
            self._preview.set_from_file(icon.value)
        else:
            self._preview.set_from_icon_name(icon.value or FALLBACK_ICON)
        self._preview.set_pixel_size(72)

    def _set_sensitive(self, sensitive):
        for widget in (self._name_row, self._comment_row, self._terminal_row,
                       self._chmod_row, self._create_button):
            widget.set_sensitive(sensitive)

    # ── custom icon ───────────────────────────────────────────────────────

    def _on_choose_icon(self, _button):
        image_filter = Gtk.FileFilter()
        image_filter.set_name(T["images"])
        image_filter.add_mime_type("image/*")
        for pattern in ("*.png", "*.svg", "*.xpm", "*.webp", "*.jpg", "*.jpeg",
                        "*.ico"):
            image_filter.add_pattern(pattern)

        if hasattr(Gtk, "FileDialog"):  # GTK >= 4.10
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(image_filter)
            dialog = Gtk.FileDialog.new()
            dialog.set_title(T["choose_icon"])
            dialog.set_filters(filters)
            dialog.open(self, None, self._on_file_dialog_done, None)
            return

        chooser = Gtk.FileChooserNative.new(  # GTK 4.0 - 4.8
            T["choose_icon"], self, Gtk.FileChooserAction.OPEN,
            T["choose_icon"], T["cancel"])
        chooser.set_filter(image_filter)
        chooser.connect("response", self._on_chooser_response)
        _ICON_CHOOSERS.append(chooser)
        chooser.show()

    def _on_file_dialog_done(self, dialog, result, _data=None):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # the user cancelled
        if file:
            self._apply_custom_icon(file.get_path())

    def _on_chooser_response(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = chooser.get_file()
            if file:
                self._apply_custom_icon(file.get_path())
        chooser.destroy()
        if chooser in _ICON_CHOOSERS:
            _ICON_CHOOSERS.remove(chooser)

    def _apply_custom_icon(self, path):
        if not path:
            return
        self._icon = IconChoice("file", path, "custom")
        self._render_icon()

    # ── create ────────────────────────────────────────────────────────────

    def _on_create(self, _button):
        if self._info is None:
            return
        name = self._name_row.get_text().strip()
        if not name:
            self._show_status(T["name_required"], error=True)
            return
        self._create_button.set_sensitive(False)
        try:
            create_application(
                self._info,
                name=name,
                comment=self._comment_row.get_text(),
                terminal=self._terminal_row.get_active(),
                icon=self._icon,
                make_executable=(self._chmod_row.get_active()
                                 if self._chmod_row.get_visible() else None),
            )
        except Exception as error:
            log(f"create failed for {self._info.path}: {error}")
            self._show_status(T["create_failed"].format(error=error), error=True)
            self._create_button.set_sensitive(True)
            return
        self._show_status(T["created"], error=False)
        GLib.timeout_add(900, self.close)

    def _show_status(self, message, error=False):
        self._status_label.set_text(message)
        self._status_label.set_visible(True)
        for css_class in ("error", "success", "dim-label"):
            self._status_label.remove_css_class(css_class)
        self._status_label.add_css_class("error" if error else "success")


# ---------------------------------------------------------------------------
# Remove dialog
# ---------------------------------------------------------------------------
class RemoveFromApplicationsDialog:
    """Confirm and delete the user entries that launch this executable."""

    def __init__(self, path):
        self._path = path
        self._entries = desktop_entries_for(path)
        names = "\n".join(f"• {os.path.basename(entry)}" for entry in self._entries)
        body = f"{T['entries']}\n{names}" if names else T["nothing_to_do"]
        self._dialog = _alert(
            T["remove_title"], body,
            (("cancel", T["cancel"]), ("remove", T["remove"])),
            destructive="remove",
        )
        self._dialog.connect("response", self._on_response)

    def present(self):
        _present_when_idle(self._dialog)

    def _on_response(self, dialog, identifier):
        try:
            dialog.close()
        except Exception:
            pass
        if identifier != "remove":
            return
        try:
            removed = remove_applications(self._path, self._entries)
        except Exception as error:
            log(f"remove failed for {self._path}: {error}")
            _show_alert(T["remove_title"], T["remove_failed"].format(error=error))
            return
        if removed:
            log(f"removed {len(removed)} entry/entries for {self._path}")
        else:
            _show_alert(T["remove_title"], T["nothing_to_do"])


# ---------------------------------------------------------------------------
# Nautilus extension
# ---------------------------------------------------------------------------
_ICON_CHOOSERS = []      # keep native chooser references alive
_OPEN_DIALOGS = []       # same for windows, so they survive garbage collection


class AppLauncherExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "AppLauncherExtension"

    def get_file_items(self, files):
        if len(files) != 1:
            return []
        selected = files[0]
        if selected.get_uri_scheme() != "file":
            return []
        path = selected.get_location().get_path()
        if not is_portable_executable(path):
            return []

        if desktop_entries_for(path):
            item = Nautilus.MenuItem(
                name="AppLauncher::Remove",
                label=T["menu_remove"],
                tip=T["tip_remove"],
                icon="edit-delete-symbolic",
            )
            item.connect("activate", self._on_remove, path)
            return [item]

        item = Nautilus.MenuItem(
            name="AppLauncher::Add",
            label=T["menu_add"],
            tip=T["tip_add"],
            icon="application-x-executable-symbolic",
        )
        item.connect("activate", self._on_add, path)
        return [item]

    def get_background_items(self, folder):
        return []

    def _on_add(self, _item, path):
        window = AddToApplicationsWindow(path)
        _OPEN_DIALOGS.append(window)
        window.connect("destroy", self._on_window_destroyed)
        _present_when_idle(window)

    @staticmethod
    def _on_window_destroyed(window):
        if window in _OPEN_DIALOGS:
            _OPEN_DIALOGS.remove(window)
        # The only consumer of a lifted AppImage icon is an open dialog.
        if not _OPEN_DIALOGS:
            cleanup_extracted_icons()

    def _on_remove(self, _item, path):
        RemoveFromApplicationsDialog(path).present()
