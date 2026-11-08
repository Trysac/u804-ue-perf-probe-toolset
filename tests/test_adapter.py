"""Adapter tests on the fake unreal module. Nothing here runs inside Unreal."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from ue_perf_probe_toolset.adapter import (
    JobStore,
    build_size_report,
    capture_status,
    compare_reports,
    get_report,
    perf_report_md,
    start_capture,
)
from ue_perf_probe_toolset.core.budget import PerfBudget
from ue_perf_probe_toolset.errors import PerfError

DATA = Path(__file__).parent / "data"
GOLDEN = Path(__file__).parent / "golden"
BUDGET = {"target_fps": 45, "min_fps": 30, "max_hitches_per_min": 1000}


@pytest.fixture
def store():
    return JobStore()


def _code(excinfo):
    return excinfo.value.code


def test_start_capture_schedules_stop_without_sleeping(fake_ue, store, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("sleep must not be called")

    monkeypatch.setattr(time, "sleep", boom)
    job = start_capture(fake_ue, 30.0, store=store)
    assert job.job_id == "capture-0001"
    assert job.state == "running"
    assert job.duration_seconds == 30.0
    assert fake_ue.commands == ["csvprofile start"]
    assert fake_ue.callback_count == 1


def test_capture_lifecycle(fake_ue, store, write_csv):
    write_csv(fake_ue.csv_dir, "old.csv", [10.0], mtime_s=100)
    job = start_capture(fake_ue, 30, store=store)
    assert capture_status(fake_ue, job.job_id, store=store).state == "running"
    fake_ue.tick(10.0)
    assert capture_status(fake_ue, job.job_id, store=store).state == "running"
    assert fake_ue.commands == ["csvprofile start"]
    fake_ue.tick(25.0)
    assert fake_ue.commands == ["csvprofile start", "csvprofile stop"]
    assert fake_ue.callback_count == 0
    status = capture_status(fake_ue, job.job_id, store=store)
    assert (status.state, status.csv_name) == ("finalizing", None)
    write_csv(fake_ue.csv_dir, "new.csv", [10.0] * 20, mtime_s=200)
    status = capture_status(fake_ue, job.job_id, store=store)
    assert (status.state, status.csv_name) == ("completed", "new.csv")
    assert capture_status(fake_ue, job.job_id, store=store).state == "completed"
    assert get_report(fake_ue, job_id=job.job_id, store=store).source == "new.csv"


def test_report_for_a_job_without_csv(fake_ue, store):
    job = start_capture(fake_ue, 5, store=store)
    with pytest.raises(PerfError) as info:
        get_report(fake_ue, job_id=job.job_id, store=store)
    assert _code(info) == "csv_not_found"


@pytest.mark.parametrize("duration", [0, 0.5, 3601, float("nan"), True, "10"])
def test_invalid_duration(fake_ue, store, duration):
    with pytest.raises(PerfError) as info:
        start_capture(fake_ue, duration, store=store)
    assert _code(info) == "invalid_argument"
    assert fake_ue.commands == []


def test_second_capture_is_refused_while_running(fake_ue, store):
    start_capture(fake_ue, 5, store=store)
    with pytest.raises(PerfError) as info:
        start_capture(fake_ue, 5, store=store)
    assert _code(info) == "capture_in_progress"
    fake_ue.tick(100.0)
    assert start_capture(fake_ue, 5, store=store).job_id == "capture-0002"


def test_unknown_job(fake_ue, store):
    with pytest.raises(PerfError) as info:
        capture_status(fake_ue, "nope", store=store)
    assert _code(info) == "unknown_job"


def test_store_evicts_oldest_entries():
    small = JobStore(max_entries=2)
    first = small.create(5.0, frozenset())
    small.create(5.0, frozenset())
    small.create(5.0, frozenset())
    with pytest.raises(PerfError) as info:
        small.get(first.job_id)
    assert _code(info) == "unknown_job"
    assert small.get("capture-0003").job_id == "capture-0003"
    with pytest.raises(PerfError):
        JobStore(max_entries=0)


def test_default_store_is_used_without_a_store_argument(fake_ue):
    job = start_capture(fake_ue, 5)
    fake_ue.tick(5.0)
    assert capture_status(fake_ue, job.job_id).state == "finalizing"


def test_get_report_by_name_path_and_newest(fake_ue, write_csv):
    write_csv(fake_ue.csv_dir, "a.csv", [10.0] * 5, mtime_s=1000)
    write_csv(fake_ue.csv_dir, "b.csv", [20.0] * 5, mtime_s=2000)
    assert get_report(fake_ue, csv_path="a.csv").stats.frame_ms_mean == 10.0
    absolute = str(fake_ue.csv_dir / "a.csv")
    assert get_report(fake_ue, csv_path=absolute).source == "a.csv"
    newest = get_report(fake_ue)
    assert newest.source == "b.csv"
    assert newest.stats.frame_ms_mean == 20.0


def test_get_report_budget_and_warmup(fake_ue, write_csv):
    write_csv(fake_ue.csv_dir, "a.csv", [10.0] * 150)
    from_dict = get_report(fake_ue, csv_path="a.csv", budget={"target_fps": 60}, warmup_seconds=1)
    assert from_dict.stats.frame_count == 50
    assert from_dict.stats.excluded_frames == 100
    assert from_dict.budget_result.verdict == "PASS"
    from_obj = get_report(fake_ue, csv_path="a.csv", budget=PerfBudget(target_fps=500))
    assert from_obj.budget_result.verdict == "FAIL"
    with pytest.raises(PerfError):
        get_report(fake_ue, csv_path="a.csv", budget={"unknown": 1})


def test_get_report_without_any_csv(fake_ue):
    with pytest.raises(PerfError) as info:
        get_report(fake_ue)
    assert _code(info) == "csv_not_found"


def test_missing_csv_dir_is_csv_not_found(tmp_path):
    from fakes.unreal import FakeUnreal

    with pytest.raises(PerfError) as info:
        get_report(FakeUnreal(tmp_path / "Empty"))
    assert _code(info) == "csv_not_found"


def test_missing_named_csv(fake_ue):
    with pytest.raises(PerfError) as info:
        get_report(fake_ue, csv_path="nope.csv")
    assert _code(info) == "csv_not_found"


def test_paths_outside_the_csv_folder_are_refused(fake_ue, write_csv, tmp_path):
    write_csv(tmp_path, "outside.csv", [10.0])
    (fake_ue.csv_dir / "notes.txt").write_text("x", encoding="utf-8")
    for bad in ("../../outside.csv", str(tmp_path / "outside.csv"), "notes.txt", "../x.csv"):
        with pytest.raises(PerfError) as info:
            get_report(fake_ue, csv_path=bad)
        assert _code(info) == "path_not_allowed"


def test_symlink_escape_is_refused(fake_ue, write_csv, tmp_path):
    outside = write_csv(tmp_path, "outside.csv", [10.0])
    try:
        (fake_ue.csv_dir / "link.csv").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(PerfError) as info:
        get_report(fake_ue, csv_path="link.csv")
    assert _code(info) == "path_not_allowed"


def test_perf_report_md_equals_golden(fake_ue):
    shutil.copy(DATA / "capture_ok.csv", fake_ue.csv_dir / "capture_ok.csv")
    markdown = perf_report_md(fake_ue, csv_path="capture_ok.csv", budget=BUDGET)
    assert markdown == (GOLDEN / "perf.md").read_text(encoding="utf-8")
    assert markdown.splitlines()[0] == "| metric | value | budget | verdict |"


def _write_profile(ue, payload):
    folder = ue.project_dir / "Saved" / "RenderProfiles"
    folder.mkdir(parents=True)
    (folder / "active_profile.json").write_bytes(payload)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b'{"name": "Mobile_Low"}', "Mobile_Low"),
        ((b'{"name": "' + b"n" * 300 + b'"}'), "n" * 100),
        (b'{"name": 5}', None),
        (b'{"name": ""}', None),
        (b"[1]", None),
        (b"not json", None),
        (b"\xff\xfe", None),
        ((b'{"name": "' + b"x" * 70000 + b'"}'), None),
    ],
)
def test_render_profile_note(fake_ue, write_csv, payload, expected):
    write_csv(fake_ue.csv_dir, "a.csv", [10.0])
    _write_profile(fake_ue, payload)
    assert get_report(fake_ue, csv_path="a.csv").render_profile == expected


def test_render_profile_absent_and_shown_in_markdown(fake_ue, write_csv):
    write_csv(fake_ue.csv_dir, "a.csv", [10.0])
    assert get_report(fake_ue, csv_path="a.csv").render_profile is None
    _write_profile(fake_ue, b'{"name": "Epic"}')
    assert "- render profile: Epic" in perf_report_md(fake_ue, csv_path="a.csv")


def test_compare_reports_is_reproducible(fake_ue, write_csv):
    write_csv(fake_ue.csv_dir, "base.csv", [10.0] * 30)
    write_csv(fake_ue.csv_dir, "cand.csv", [20.0] * 30)
    _write_profile(fake_ue, b'{"name": "Epic"}')
    first = compare_reports(fake_ue, "base.csv", "cand.csv", seed=1234, iterations=50)
    second = compare_reports(fake_ue, "base.csv", "cand.csv", seed=1234, iterations=50)
    assert first == second
    assert first.verdict == "regression"
    assert first.notes == ("render profile: Epic",)
    assert first.baseline_count == 30


def test_compare_reports_warmup_and_errors(fake_ue, write_csv):
    write_csv(fake_ue.csv_dir, "base.csv", [10.0] * 150)
    write_csv(fake_ue.csv_dir, "cand.csv", [10.0] * 150)
    result = compare_reports(fake_ue, "base.csv", "cand.csv", iterations=20, warmup_seconds=1)
    assert result.baseline_count == 50
    assert result.notes == ()
    with pytest.raises(PerfError) as outside:
        compare_reports(fake_ue, "base.csv", "../../x.csv")
    assert _code(outside) == "path_not_allowed"
    with pytest.raises(PerfError) as empty:
        compare_reports(fake_ue, "base.csv", "cand.csv", warmup_seconds=100)
    assert _code(empty) == "no_frames"


def test_build_size_report_inside_the_project(fake_ue):
    build = fake_ue.project_dir / "Saved" / "StagedBuilds"
    build.mkdir(parents=True)
    (build / "a.pak").write_bytes(b"x" * 100)
    (build / "b.utoc").write_bytes(b"x" * 50)
    log = fake_ue.project_dir / "Saved" / "cook.log"
    log.write_text("Cooked /Game/Maps/Big 70 bytes\n", encoding="utf-8")
    _write_profile(fake_ue, b'{"name": "Epic"}')
    report = build_size_report(
        fake_ue, "Saved/StagedBuilds", limit_bytes=160, cook_log="Saved/cook.log"
    )
    assert report.total_bytes == 150
    assert [item.extension for item in report.breakdown] == [".pak", ".utoc"]
    assert len(report.warnings) == 1
    assert report.largest_contributors[0].name == "/Game/Maps/Big"
    assert report.notes == ("render profile: Epic",)
    absolute = build_size_report(fake_ue, str(build))
    assert absolute.total_bytes == 150


def test_build_size_report_refuses_outside_paths(fake_ue, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(PerfError) as folder:
        build_size_report(fake_ue, str(other))
    assert _code(folder) == "path_not_allowed"
    inside = fake_ue.project_dir / "Saved"
    inside.mkdir(exist_ok=True)
    with pytest.raises(PerfError) as log:
        build_size_report(fake_ue, str(inside), cook_log=str(tmp_path / "cook.log"))
    assert _code(log) == "path_not_allowed"
    with pytest.raises(PerfError) as missing:
        build_size_report(fake_ue, "Saved/NoSuchFolder")
    assert _code(missing) == "path_not_found"
