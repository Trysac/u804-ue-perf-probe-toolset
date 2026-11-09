"""Assemble the installable Unreal plugin: ``dist/<Plugin>/`` and ``dist/<Plugin>-<version>.zip``.

The plugin folder in ``plugin/`` holds the ``.uplugin`` and the toolset module; this script copies
it and vendors the library package from ``src/`` into ``Content/Python/`` so Unreal's embedded
Python can import it without pip. Standard library only.
Usage: ``uv run python tools/build_plugin.py``.
Install: unzip into ``<YourProject>/Plugins/``, enable the plugin, restart the editor.
"""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")


def find_plugin(root: Path = ROOT) -> Path:
    """Return the single plugin folder under ``plugin/``."""
    found = sorted(p.parent for p in (root / "plugin").glob("*/*.uplugin"))
    if len(found) != 1:
        raise SystemExit(f"expected exactly one plugin/*/*.uplugin, found {len(found)}")
    return found[0]


def find_package(root: Path = ROOT) -> Path:
    """Return the single library package under ``src/``."""
    found = sorted(p.parent for p in (root / "src").glob("*/__init__.py"))
    if len(found) != 1:
        raise SystemExit(f"expected exactly one src/*/__init__.py, found {len(found)}")
    return found[0]


def read_version(package: Path) -> str:
    """Read ``__version__`` from the package ``__init__.py``."""
    text = (package / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("__version__ not found")
    return match.group(1)


def build(root: Path = ROOT, out: Path | None = None) -> Path:
    """Build the plugin folder and its zip; return the zip path."""
    plugin = find_plugin(root)
    package = find_package(root)
    version = read_version(package)
    dist = out or root / "dist"
    target = dist / plugin.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(plugin, target, ignore=IGNORE)
    shutil.copytree(package, target / "Content" / "Python" / package.name, ignore=IGNORE)
    for extra in ("LICENSE", "README.md"):
        if (root / extra).is_file():
            shutil.copy2(root / extra, target / extra)
    archive = dist / f"{plugin.name}-{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(dist).as_posix())
    return archive


if __name__ == "__main__":
    print(build())
    sys.exit(0)
