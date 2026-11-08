"""Tests for the report and its Markdown rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from ue_perf_probe_toolset.core.budget import PerfBudget
from ue_perf_probe_toolset.core.csvparse import parse_csv_profile, parse_csv_text
from ue_perf_probe_toolset.core.markdown import render_perf_markdown
from ue_perf_probe_toolset.core.report import build_report
from ue_perf_probe_toolset.errors import PerfError

DATA = Path(__file__).parent / "data"
GOLDEN = Path(__file__).parent / "golden"


def _fixture_report(**kwargs):
    profile = parse_csv_profile(DATA / "capture_ok.csv")
    return build_report("capture_ok.csv", profile, **kwargs)


def test_fixture_report_equals_golden():
    budget = PerfBudget(target_fps=45, min_fps=30, max_hitches_per_min=1000)
    markdown = render_perf_markdown(_fixture_report(budget=budget))
    assert markdown == (GOLDEN / "perf.md").read_text(encoding="utf-8")
    assert markdown.splitlines()[0] == "| metric | value | budget | verdict |"


def test_report_summary_and_verdict():
    report = _fixture_report(budget=PerfBudget(target_fps=45))
    assert report.budget_result.verdict == "PASS"
    assert report.summary.endswith("budget PASS")
    assert report.summary.startswith("capture_ok.csv: 10 frames")


def test_without_budget_rows_are_dashes():
    markdown = render_perf_markdown(_fixture_report())
    assert markdown.startswith("| metric | value | budget | verdict |\n")
    assert "| fps_mean | 50.00 | - | - |" in markdown
    assert "**Verdict: n/a (no budget)**" in markdown


def test_warnings_and_render_profile_are_listed():
    profile = parse_csv_text("FrameTime,Events\n10,a|b\n10")
    report = build_report("odd|name.csv", profile, render_profile="Mobile_Low")
    markdown = render_perf_markdown(report)
    assert "- render profile: Mobile_Low" in markdown
    assert "- source: odd/name.csv" in markdown
    assert "- warning: extra_column:" in markdown
    assert "- warning: truncated_row:" in markdown
    assert "(line 3)" in markdown
    assert markdown.endswith("\n")


def test_warmup_is_reported():
    report = _fixture_report(warmup_seconds=0.05)
    assert report.stats.excluded_frames == 5
    assert "(5 excluded as warmup)" in render_perf_markdown(report)


def test_empty_profile_raises_no_frames():
    profile = parse_csv_text("FrameTime\n")
    with pytest.raises(PerfError) as info:
        build_report("empty.csv", profile)
    assert info.value.code == "no_frames"
