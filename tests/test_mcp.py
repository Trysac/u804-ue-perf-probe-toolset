"""The MCP layer: flat params in, JSON out, errors as data, jobs kept between calls."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from ue_perf_probe_toolset import adapter, mcp
from ue_perf_probe_toolset.adapter import JobStore

DATA = Path(__file__).parent / "data"
GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    store = JobStore()
    monkeypatch.setattr(adapter, "DEFAULT_STORE", store)
    return store


def _load(raw: str) -> dict:
    data = json.loads(raw)
    assert next(iter(data)) == "summary"
    return data


def test_capture_flow_across_separate_calls(fake_ue, write_csv, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("sleep must not be called")

    monkeypatch.setattr(time, "sleep", boom)
    started = _load(mcp.start_capture(fake_ue, 5, label="baseline"))
    job_id = started["job_id"]
    assert (started["state"], started["label"]) == ("running", "baseline")
    assert fake_ue.commands == ["csvprofile start"]
    assert _load(mcp.capture_status(fake_ue, job_id))["state"] == "running"
    fake_ue.tick(6.0)
    assert fake_ue.commands[-1] == "csvprofile stop"
    assert _load(mcp.capture_status(fake_ue, job_id))["state"] == "finalizing"
    write_csv(fake_ue.csv_dir, "Profile(20261108_120000).csv", [10.0] * 200)
    done = _load(mcp.capture_status(fake_ue, job_id))
    assert (done["state"], done["csv_name"]) == ("completed", "Profile(20261108_120000).csv")
    report = _load(mcp.get_report(fake_ue, job_id=job_id, target_fps=60, warmup_seconds=1))
    assert report["budget_result"]["verdict"] == "PASS"
    assert report["stats"]["excluded_frames"] == 100
    assert report["label"] == "baseline"
    assert [c["channel"] for c in report["channels"]] == ["game_ms", "render_ms", "gpu_ms"]
    md = _load(mcp.perf_report_md(fake_ue, job_id=job_id))["markdown"]
    assert "- label: baseline" in md and "| game_ms | ms |" in md


def test_only_one_capture_at_a_time(fake_ue):
    _load(mcp.start_capture(fake_ue, 5))
    second = _load(mcp.start_capture(fake_ue, 5))
    assert second["error"]["code"] == "capture_in_progress"
    assert second["summary"].startswith("error:")
    fake_ue.tick(5.0)
    assert _load(mcp.start_capture(fake_ue, 5))["job_id"] == "capture-0002"


def test_get_report_by_csv_path_after_jobs_are_lost(fake_ue, write_csv, monkeypatch):
    write_csv(fake_ue.csv_dir, "a.csv", [10.0] * 20)
    _load(mcp.start_capture(fake_ue, 5))
    monkeypatch.setattr(adapter, "DEFAULT_STORE", JobStore())  # as after a module reload
    assert _load(mcp.capture_status(fake_ue, "capture-0001"))["error"]["code"] == "unknown_job"
    report = _load(mcp.get_report(fake_ue, csv_path="a.csv"))
    assert report["source"] == "a.csv"
    assert report["budget_result"] is None
    assert _load(mcp.get_report(fake_ue))["source"] == "a.csv"


@pytest.mark.parametrize(
    ("kwargs", "verdict", "checks"),
    [
        ({"target_fps": 120}, "FAIL", 1),
        ({"min_fps": 30, "max_hitches_per_min": 0}, "FAIL", 2),
        ({"max_hitches_per_min": 1000}, "PASS", 1),
        ({"hitch_ms": 100, "max_hitches_per_min": 0}, "PASS", 1),
    ],
)
def test_flat_budget(fake_ue, write_csv, kwargs, verdict, checks):
    write_csv(fake_ue.csv_dir, "a.csv", [10.0] * 50 + [60.0])
    result = _load(mcp.get_report(fake_ue, csv_path="a.csv", **kwargs))["budget_result"]
    assert result["verdict"] == verdict
    assert len(result["checks"]) == checks


@pytest.mark.parametrize(
    ("call", "code"),
    [
        (lambda ue: mcp.start_capture(ue, 0), "invalid_argument"),
        (lambda ue: mcp.get_report(ue, csv_path="../../x.csv"), "path_not_allowed"),
        (lambda ue: mcp.get_report(ue, csv_path="none.csv"), "csv_not_found"),
        (lambda ue: mcp.get_report(ue, target_fps=-5), "invalid_argument"),
        (lambda ue: mcp.perf_report_md(ue), "csv_not_found"),
        (lambda ue: mcp.compare_reports(ue, "../b.csv", "a.csv"), "path_not_allowed"),
        (lambda ue: mcp.build_size_report(ue, "/"), "path_not_allowed"),
        (lambda ue: mcp.build_size_report(ue, "Saved/Nope"), "path_not_found"),
    ],
)
def test_errors_come_back_as_data(fake_ue, call, code):
    data = _load(call(fake_ue))
    assert data["error"]["code"] == code
    assert data["summary"].startswith("error:")


def test_unexpected_unreal_failure_is_reported(fake_ue):
    def broken(*args, **kwargs):
        raise AttributeError("no Paths")

    fake_ue.Paths.project_saved_dir = broken
    data = _load(mcp.get_report(fake_ue))
    assert data["error"]["code"] == "unreal_error"
    assert "AttributeError" in data["error"]["message"]


def test_failed_console_command_is_capture_failed(fake_ue):
    def broken(*args, **kwargs):
        raise RuntimeError("console unavailable")

    fake_ue.SystemLibrary.execute_console_command = broken
    data = _load(mcp.start_capture(fake_ue, 5))
    assert data["error"]["code"] == "capture_failed"


def test_compare_reports_is_reproducible(fake_ue, write_csv):
    write_csv(fake_ue.csv_dir, "base.csv", [10.0] * 30)
    write_csv(fake_ue.csv_dir, "cand.csv", [20.0] * 30)
    first = _load(mcp.compare_reports(fake_ue, "base.csv", "cand.csv", iterations=50))
    second = _load(mcp.compare_reports(fake_ue, "base.csv", "cand.csv", iterations=50))
    assert first == second
    assert first["verdict"] == "regression"
    assert {m["metric"] for m in first["metrics"]} >= {"frame_ms_p95", "frame_ms_p99"}


def test_build_size_report_default_limit_and_disabled(fake_ue):
    build = fake_ue.project_dir / "Build"
    build.mkdir()
    (build / "game.pak").write_bytes(b"x" * 1000)
    (build / "game.utoc").write_bytes(b"x" * 24)
    data = _load(mcp.build_size_report(fake_ue, "Build"))
    assert data["total_bytes"] == 1024
    assert data["limit_bytes"] == mcp.GIB
    assert data["warnings"] == []
    near = _load(mcp.build_size_report(fake_ue, "Build", limit_bytes=1000))
    assert len(near["warnings"]) == 2
    off = _load(mcp.build_size_report(fake_ue, str(build), limit_bytes=0))
    assert off["limit_bytes"] is None and off["usage_ratio"] is None


def test_perf_report_md_matches_golden(fake_ue):
    shutil.copy(DATA / "capture_ok.csv", fake_ue.csv_dir / "capture_ok.csv")
    data = _load(
        mcp.perf_report_md(
            fake_ue, csv_path="capture_ok.csv", target_fps=45, min_fps=30, max_hitches_per_min=1000
        )
    )
    assert data["markdown"] == (GOLDEN / "perf.md").read_text(encoding="utf-8")
    assert data["summary"].startswith("capture_ok.csv:")


def test_to_json_handles_plain_values():
    raw = mcp.to_json({"a": (1, 2), "summary": "s", "p": object.__new__(object)})
    data = json.loads(raw)
    assert next(iter(data)) == "summary" and data["a"] == [1, 2]
    assert json.loads(mcp.to_json([1, None]))[1] is None
