"""The plugin build vendors the package next to the toolset module and zips it."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_plugin", ROOT / "tools" / "build_plugin.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_creates_installable_zip(tmp_path: Path) -> None:
    bp = _load()
    archive = bp.build(ROOT, tmp_path)
    plugin = bp.find_plugin(ROOT).name
    package = bp.find_package(ROOT).name
    names = set(zipfile.ZipFile(archive).namelist())
    assert f"{plugin}/{plugin}.uplugin" in names
    assert f"{plugin}/Content/Python/{package}/__init__.py" in names
    assert any(n.startswith(f"{plugin}/Content/Python/") and n.endswith("_mcp.py") for n in names)
    assert not any("__pycache__" in n for n in names)


def test_uplugin_is_valid_and_depends_on_registry() -> None:
    bp = _load()
    plugin = bp.find_plugin(ROOT)
    data = json.loads((plugin / f"{plugin.name}.uplugin").read_text(encoding="utf-8"))
    deps = {p["Name"] for p in data["Plugins"]}
    assert {"PythonScriptPlugin", "ToolsetRegistry"} <= deps
    version = bp.read_version(bp.find_package(ROOT))
    assert data["VersionName"] == version
