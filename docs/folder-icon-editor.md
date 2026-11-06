# Folder icon editor

The editor is part of Folder Color Revival, not a separate icon-theme manager.
Install it with `./install.sh --only folder-color-revival`. The installer must
copy its Python helpers, shared locale resolver and licensed symbol assets as
well as the Nautilus entry point.

## Three different operations

- **Apply** changes the selected folders through GIO metadata. The Global tab
  instead changes the default folder icon through a derived icon theme. Review
  the active tab and the multi-folder confirmation before applying.
- **Save project** creates an editable, self-contained **SVG**. It is also a
  displayable icon; it is not a link to the files used to build the composition.
- **Export PNG** creates a rendered bitmap. Previously exported PNGs carrying
  `fcRev` metadata remain a legacy import format, but they are not the new
  portable project format.

Saving or reopening a project is not permission to apply it to a folder.
Cancelling a chooser must leave both the destination file and folder metadata
unchanged. Existing export targets are confirmed by the native save dialog.

## Layers and colours

Image, text, theme-emblem and monochrome-symbol layers are independent. The
layer list is top-first. Transformations, masks and opacity belong to each
layer, rather than changing the source image on disk.

Quick colours and the custom-colour chooser set **all base-colour rows in the
active scope**. A layer's own text/symbol colour remains independently editable.
Following the GNOME accent overrides the effective base colours; turning it off
allows manual colours again. A custom base image is an image, not a set of
recolourable theme shapes.

Text retains its content, font description, size, style and colour. A rendered
source snapshot preserves its appearance in a saved SVG without redistributing
font files. Editing text on another machine still requires a suitable installed
font; a fallback font can change newly rendered text.

The symbol library is an offline collection of monochrome artwork. Choosing a
symbol adds a recolourable layer; it does not apply a saved folder composition.
Generated-composition history is separate from this symbol library. Its cache
and usage tracking must not be confused with a project backup.

## Portable SVG contract

`folder_icon_project.py` implements a versioned project format independently of
GTK. The SVG contains a rendered base and one full-canvas image per layer,
painted bottom-to-top. The final layer snapshots already include scale,
rotation, offsets, colour adjustments, opacity and masks. They must not be
transformed a second time on import.

Namespaced JSON metadata retains editable state and a SHA-256-addressed asset
table. Original images, custom base images, masks and resolved emblem/symbol
artwork are embedded. Text also retains a pre-transform rendered snapshot.
Import materializes these assets into a managed cache; it does not read
arbitrary paths named by project metadata or change folder metadata.

Unchanged imported layers can use their final snapshots, while edited layers
are recomposed from their retained sources. The rendered base keeps the project
viewable when the original icon theme is unavailable. This is a portable layered
icon format, **not** a promise that all text, images and effects are editable
native vector paths in a general-purpose SVG editor.

The importer rejects scripts, event handlers, external file/network references,
DOCTYPE/entities, unsupported project versions and oversized/invalid assets.
An invalid project must produce an error, not silently reopen as a plain image.
Safe ordinary SVGs remain image assets rather than being mistaken for projects.

Default project limits are 64 MiB per project file, 16 MiB per asset, 48 MiB of
embedded sources, 2 MiB of state metadata, 16 million pixels per image and
128 layers per scope. Animated or multipage source images are not project
assets. See the module constants and tests for the authoritative limits.

## Practical limits and recovery

- GIO `metadata::custom-icon` is local metadata. Copying a folder to another
  machine, filesystem or account does not necessarily copy that metadata.
  Export an SVG project to transfer the composition deliberately.
- Applied icons and imported source assets live in cache directories. Removing
  a cache that an applied icon references can break that icon. Keep saved SVG
  projects outside the cache and reapply after restoring them.
- Theme emblems must be resolved into embedded assets when a project is saved.
  Merely storing a theme's emblem name would not make it portable.
- Restoration must only remove or restore customization owned by this extension.
  A later change by another extension must be left alone. Dolphin `.directory`
  files and external artwork are never project cleanup targets.
- Global customization changes a derived theme. It is broader than customizing
  one folder; do not use a live user's theme as a test fixture.

## Relationship to Iconic

The Iconic requests track desired behaviours, not a claim of complete parity
with a particular upstream release. The extension keeps Nautilus integration,
NameToColor, installed-theme folder shapes and Dolphin colour import. Its SVG
project format, offline symbol catalogue and generated-composition history have
different purposes; none should be presented as an upstream-compatible project
format without a separate compatibility test.

## Verification

Pure project/catalogue tests and installer tests should not need a desktop
session. GTK tests require a real display, such as an isolated Xvfb server:

```sh
python -m pytest tests/unit/test_folder_icon_project.py -q
python -m pytest tests/unit/test_folder_icon_catalog.py -q
python -m pytest tests/unit/test_folder_icon_install.py -q
dbus-run-session -- xvfb-run -a -s '-screen 0 1280x1000x24' \
  env GDK_BACKEND=x11 python -m pytest tests/gtk -q
bash -n install.sh
sh -n debian/zonaro-nautilus-link
```

Use temporary HOME/XDG directories for integration tests. Installation tests
stub privileged package installation, network downloads and the Nautilus restart;
they must never mutate the running user's extension directory. The Debian
manifest test is not equivalent to building a `.deb` on Debian/Ubuntu.

### Manual acceptance checklist

- Resize the same mapped window from narrow to wide and back, without moving
  the pointer over its content. No action may disappear to the right.
- Inspect distinct, consistently sized quick-colour swatches. Pick a custom
  colour, confirm, and check every base-colour input and the preview.
- Add image, text and symbol layers using their visible actions. Change a text
  font and a symbol colour. Search the actual offline symbol catalogue.
- Toggle advanced controls off/on and reopen the editor to check persistence.
- Toggle accent following in Folder and Global; verify the preview, saved state
  and actual regenerated colour using isolated settings and test folders.
- Save a project with image/text/symbol/emblem/mask layers, delete the originals,
  reopen it, compare the rendered result, edit a layer and save it again.
- Cancel save/open/colour/multi-folder dialogs. Confirm no unintended write.
- Apply to one and several temporary folders, check GIO attributes, reopen the
  editor and restore. Preserve a foreign icon installed after our customization.

Record commands, observed results, screenshots and environment in the linked
issue. Test counts or compilation alone are not evidence for these user flows.
