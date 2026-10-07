# Publishing `zonaro-nautilus-extensions` to Launchpad PPA

This repo ships full `debian/` packaging so Launchpad can build a PPA with
one binary package per extension (`zonaro-nautilus-*`), plus
`zonaro-nautilus-common` and the `zonaro-nautilus-all` metapackage.

Upstream (`ToFpon/Nautilus-Extensions`, `ppa:nourpon/nautilus-extensions`)
keeps its packaging outside git. This fork keeps it **in git** on purpose, so
anyone can rebuild or publish their own PPA. Binary names and paths use the
`zonaro-` prefix to avoid clashing with the upstream PPA:

- system payload: `/usr/share/zonaro-nautilus-extensions/`
- linker: `/usr/bin/zonaro-nautilus-link`
- autostart: `/etc/xdg/autostart/zonaro-nautilus-link.desktop`

## 1. Create the PPA

1. Log in to https://launchpad.net/ and create a PPA, e.g.
   `ppa:zonaro/nautilus-extensions`.
2. Import this git branch (`main`) as the recipe source, or push a release
   tarball. Target series: `noble` (24.04) and optionally `jammy` (22.04).
3. Suggested recipe:
   - Recipe name: `zonaro-nautilus-extensions-noble`
   - Branch: `https://github.com/zonaro/Nautilus-Extensions.git` (main)
   - Build for: noble (amd64)
   - Debian version suffix: `~zonaro1` (already in `debian/changelog`)

## 2. Build locally (Ubuntu/Debian with debhelper)

```bash
sudo apt install debhelper dh-python
dpkg-buildpackage -us -uc -b
ls ../*.deb
```

## 3. Install from your PPA (per-extension)

```bash
sudo add-apt-repository ppa:zonaro/nautilus-extensions
sudo apt update

# everything:
sudo apt install zonaro-nautilus-all

# or pick individual extensions — apt pulls only what each one needs:
sudo apt install zonaro-nautilus-dual-panel zonaro-nautilus-image-tools

# variant: dim only the icon instead of icon+label
sudo apt install zonaro-nautilus-hidden-dim-icon

# activate now (otherwise at next login via autostart):
zonaro-nautilus-link
nautilus -q
```

`zonaro-nautilus-hidden-dim-all` and `zonaro-nautilus-hidden-dim-icon`
conflict with each other — install only one.

## 4. Coexistence with install.sh

`install.sh` (repo root) is the manual/curl-pipe way and works on
apt/dnf/pacman/zypper with `--only`/`--exclude` selection. If a
system-wide install exists at `/usr/share/zonaro-nautilus-extensions`,
`install.sh` warns before shadowing it with per-user copies. Pick one
method per machine; the PPA is recommended on Ubuntu.
