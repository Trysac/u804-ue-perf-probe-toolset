"""The Content/Python toolset module forwards every tool to the MCP layer with ``unreal``."""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from fakes.unreal import FakeUnreal

from ue_perf_probe_toolset import adapter
from ue_perf_probe_toolset.adapter import JobStore

ROOT = Path(__file__).resolve().parents[1]
SHELLS = sorted((ROOT / "plugin").glob("*/Content/Python/*_mcp.py"))


@pytest.fixture
def shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    fake = FakeUnreal(tmp_path / "Proj")
    fake.csv_dir.mkdir(parents=True)
    fake.uclass = lambda: lambda cls: cls
    fake.ToolsetDefinition = type("ToolsetDefinition", (), {})
    registry = types.ModuleType("toolset_registry")
    registry.tool_call = lambda fn: setattr(fn, "is_tool", True) or fn
    monkeypatch.setitem(sys.modules, "unreal", fake)
    monkeypatch.setitem(sys.modules, "toolset_registry", registry)
    monkeypatch.setattr(adapter, "DEFAULT_STORE", JobStore())
    assert len(SHELLS) == 1
    spec = importlib.util.spec_from_file_location("shell_under_test", SHELLS[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, fake


def _toolset(module: Any) -> Any:
    classes = [
        c for _, c in inspect.getmembers(module, inspect.isclass) if c.__module__ == module.__name__
    ]
    assert len(classes) == 1
    return classes[0]


def test_every_mcp_function_is_a_documented_tool(shell: Any) -> None:
    module, _ = shell
    toolset = _toolset(module)
    from ue_perf_probe_toolset import mcp

    assert toolset.__name__ == "PerfProbeTools"
    assert inspect.getdoc(toolset)
    public = {
        n
        for n, f in inspect.getmembers(mcp, inspect.isfunction)
        if f.__module__ == mcp.__name__ and not n.startswith("_") and n != "to_json"
    }
    tools = {n for n, f in vars(toolset).items() if isinstance(f, staticmethod)}
    assert public == tools
    for name in tools:
        fn = getattr(toolset, name)
        assert getattr(fn, "is_tool", False), name
        doc = inspect.getdoc(fn) or ""
        assert "Args:" in doc or not inspect.signature(fn).parameters, name
        assert "Returns:" in doc, name
        assert inspect.signature(fn).return_annotation in (str, "str")
        assert "ue" not in inspect.signature(fn).parameters
        for param in inspect.signature(fn).parameters.values():
            assert param.annotation in (str, int, float, bool, "str", "int", "float", "bool")
            assert f"{param.name}:" in doc, (name, param.name)


def test_tool_defaults_match_the_mcp_layer(shell: Any) -> None:
    module, _ = shell
    toolset = _toolset(module)
    from ue_perf_probe_toolset import mcp

    for name, fn in vars(toolset).items():
        if not isinstance(fn, staticmethod):
            continue
        shell_params = inspect.signature(getattr(toolset, name)).parameters
        mcp_params = dict(inspect.signature(getattr(mcp, name)).parameters)
        mcp_params.pop("ue")
        assert list(shell_params) == list(mcp_params), name
        for key, param in shell_params.items():
            assert param.default == mcp_params[key].default, (name, key)


def test_tools_forward_with_unreal(shell: Any) -> None:
    module, fake = shell
    toolset = _toolset(module)
    started = json.loads(toolset.start_capture(5.0))
    assert started["state"] == "running"
    assert json.loads(toolset.capture_status(started["job_id"]))["state"] == "running"
    fake.tick(5.0)
    assert fake.commands == ["csvprofile start", "csvprofile stop"]
    (fake.csv_dir / "a.csv").write_text("FrameTime\n10\n12\n", encoding="utf-8")
    assert json.loads(toolset.get_report(csv_path="a.csv"))["stats"]["frame_count"] == 2
    assert json.loads(toolset.perf_report_md(csv_path="a.csv"))["markdown"].startswith("| metric")
    assert json.loads(toolset.compare_reports("a.csv", "a.csv", iterations=10))["verdict"]
    assert json.loads(toolset.build_size_report("Saved"))["file_count"] == 1
