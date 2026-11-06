"""Exercise real selective installation without sudo, network or desktop changes."""

import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EDITOR_FILES = {
    "folder-color-revival.py", "folder_icon_editor.py", "folder_icon_theme.py",
    "folder_icon_project.py", "folder_icon_catalog.py", "name_to_color.py",
    "color_database.json", "nautilus_i18n.py",
}


def _install(tmp_path, slug):
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "external-calls"
    for name in ("sudo", "nautilus"):
        stub = bin_dir / name
        stub.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$INSTALL_CALLS"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    # Any accidental clone/download is a failing test, not a network request.
    for name in ("git", "curl", "wget"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 98\n", encoding="utf-8")
        stub.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "INSTALL_CALLS": str(calls),
        "OPENCODE_NO_SESSION_ENV": "1",
    }
    result = subprocess.run(
        ["bash", str(ROOT / "install.sh"), "--only", slug,
         "--yes", "--no-optional"],
        env=env, cwd=tmp_path, text=True, capture_output=True, timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return home / ".local/share/nautilus-python/extensions", env


def test_selective_install_contains_editor_helpers_and_licensed_catalog(tmp_path):
    dest, env = _install(tmp_path, "folder-color-revival")
    assert EDITOR_FILES <= {path.name for path in dest.iterdir()}
    source_assets = ROOT / "assets/folder-icons"
    source_files = {path.relative_to(source_assets) for path in source_assets.rglob("*")
                    if path.is_file()}
    assert source_files
    for relative in source_files:
        assert (dest / "assets/folder-icons" / relative).read_bytes() == (
            source_assets / relative).read_bytes()
    assert any("license" in str(path).lower() for path in source_files)
    result = subprocess.run(
        [sys.executable, "-c", "import folder_icon_project, folder_icon_catalog, nautilus_i18n"],
        cwd=tmp_path, env={**env, "PYTHONPATH": str(dest)},
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_unrelated_selective_install_does_not_copy_symbol_assets(tmp_path):
    dest, _env = _install(tmp_path, "cut-dim")
    assert (dest / "cut-dim.py").is_file()
    assert not (dest / "folder_icon_editor.py").exists()
    assert not (dest / "assets/folder-icons").exists()


def _package_sources(manifest):
    return [line.split()[0] for line in (ROOT / "debian" / manifest).read_text().splitlines()
            if line.strip() and not line.startswith("#")]


def test_debian_manifest_includes_all_editor_helpers_and_assets():
    sources = _package_sources("zonaro-nautilus-folder-color-revival.install")
    common = _package_sources("zonaro-nautilus-common.install")
    assert EDITOR_FILES <= set(sources + common)
    assert "assets/folder-icons" in sources
    for source in sources + common:
        assert list(ROOT.glob(source)), f"Missing Debian payload: {source}"


def test_debian_linker_keeps_catalog_available_via_symlinks(tmp_path):
    payload = tmp_path / "payload"
    payload.mkdir()
    for module in ("folder_icon_catalog.py", "folder_icon_project.py"):
        shutil.copy2(ROOT / module, payload / module)
    shutil.copytree(ROOT / "assets", payload / "assets")
    home = tmp_path / "home"
    home.mkdir()
    linker = tmp_path / "linker"
    linker.write_text((ROOT / "debian/zonaro-nautilus-link").read_text().replace(
        'SRC="/usr/share/zonaro-nautilus-extensions"', f'SRC="{payload}"'),
        encoding="utf-8")
    env = {**os.environ, "HOME": str(home),
           "XDG_DATA_HOME": str(home / ".local/share")}
    result = subprocess.run(["sh", str(linker)], env=env, capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    dest = home / ".local/share/nautilus-python/extensions"
    assert (dest / "assets").is_symlink()
    assert (dest / "folder_icon_catalog.py").is_symlink()
    result = subprocess.run(
        [sys.executable, "-c", "import folder_icon_catalog, folder_icon_project"],
        env={**env, "PYTHONPATH": str(dest)}, cwd=tmp_path,
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
