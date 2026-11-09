"""Thread, GPU, memory and streaming column statistics and their comparison."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ue_perf_probe_toolset.core.channels import CHANNEL_NAMES, channel_samples, channel_stats
from ue_perf_probe_toolset.core.compare import compare_profiles, compare_samples
from ue_perf_probe_toolset.core.csvparse import parse_csv_profile, parse_csv_text
from ue_perf_probe_toolset.core.markdown import render_perf_markdown
from ue_perf_probe_toolset.core.report import build_report
from ue_perf_probe_toolset.errors import PerfError

DATA = Path(__file__).parent / "data"
FULL = "FrameTime,GameThreadTime,RenderThreadTime,GPUTime,PhysicalUsedMB,TextureStreaming/StreamingPool\n"


def _full_csv(rows):
    return FULL + "".join(f"{f},{g},{r},{gpu},{m},{s}\n" for f, g, r, gpu, m, s in rows)


def _naive(values, pct):
    ordered = sorted(values)
    rank = math.ceil(pct * len(ordered) / 100)
    return ordered[max(rank, 1) - 1]


def test_all_channels_present():
    text = _full_csv([(10, 5, 4, 8, 3000, 1000), (20, 15, 9, 18, 3010, 1000)])
    stats, notes = channel_stats(parse_csv_text(text).frames)
    assert notes == ()
    by_name = {item.channel: item for item in stats}
    assert list(by_name) == list(CHANNEL_NAMES)
    assert by_name["game_ms"].mean == 10.0
    assert by_name["game_ms"].p50 == 5.0 and by_name["game_ms"].p99 == 15.0
    assert by_name["physical_mb"].unit == "MB"
    assert by_name["physical_mb"].mean == 3005.0
    assert by_name["render_ms"].count == 2


def test_missing_columns_are_omitted_with_a_note():
    stats, notes = channel_stats(parse_csv_text("FrameTime,GPUTime\n10,7\n12,9\n").frames)
    assert [item.channel for item in stats] == ["gpu_ms"]
    assert len(notes) == 4
    assert notes[0].startswith("game_ms (game thread time): no column")
    assert any(note.startswith("render_ms (render thread (draw) time)") for note in notes)


def test_bad_cells_are_left_out_of_the_channel():
    profile = parse_csv_text(_full_csv([(10, 5, 4, 8, "x", 1000), (10, 7, 4, 8, 3000, 1000)]))
    stats, _ = channel_stats(profile.frames)
    physical = next(item for item in stats if item.channel == "physical_mb")
    assert physical.count == 1


def test_warmup_uses_frame_start():
    profile = parse_csv_text(_full_csv([(100, 90, 1, 1, 1, 1)] + [(10, 5, 1, 1, 1, 1)] * 3))
    samples = channel_samples(profile.frames, warmup_seconds=0.1)
    assert samples["frame_ms"] == [10.0] * 3
    assert samples["game_ms"] == [5.0] * 3
    with pytest.raises(PerfError) as info:
        channel_samples(profile.frames, warmup_seconds=-1)
    assert info.value.code == "invalid_argument"


@settings(derandomize=True, max_examples=60)
@given(st.lists(st.floats(min_value=0.0, max_value=500.0), min_size=1, max_size=80))
def test_channel_stats_match_naive_reference(values):
    rows = [(10.0, value, 1.0, 1.0, 1.0, 1.0) for value in values]
    stats, _ = channel_stats(parse_csv_text(_full_csv(rows)).frames)
    game = next(item for item in stats if item.channel == "game_ms")
    parsed = [float(repr(value)) for value in values]
    assert game.count == len(values)
    assert game.mean == pytest.approx(math.fsum(parsed) / len(parsed))
    for pct, got in ((50, game.p50), (95, game.p95), (99, game.p99)):
        assert got == _naive(parsed, pct)


def test_report_and_markdown_include_channels_and_label():
    profile = parse_csv_text(_full_csv([(10, 5, 4, 8, 3000, 1000)] * 3))
    report = build_report("a.csv", profile, label="before LOD fix")
    assert report.label == "before LOD fix" and report.notes == ()
    markdown = render_perf_markdown(report)
    assert "- label: before LOD fix" in markdown
    assert "| channel | unit | mean | p50 | p95 | p99 |" in markdown
    assert "| physical_mb | MB | 3000.00 | 3000.00 | 3000.00 | 3000.00 |" in markdown
    bare = render_perf_markdown(build_report("b.csv", parse_csv_text("FrameTime\n10\n")))
    assert "| channel |" not in bare and "- label:" not in bare
    assert bare.count("- note: ") == 5


def test_compare_profiles_covers_every_shared_channel():
    base = channel_samples(parse_csv_text(_full_csv([(10, 5, 4, 8, 3000, 1000)] * 40)).frames)
    cand = channel_samples(parse_csv_text(_full_csv([(10, 9, 4, 8, 2000, 1000)] * 40)).frames)
    first = compare_profiles(base, cand, iterations=50)
    assert first == compare_profiles(base, cand, iterations=50)
    directions = {item.metric: item.direction for item in first.metrics}
    assert directions["game_ms_mean"] == "regression"
    assert directions["physical_mb_mean"] == "improvement"
    assert directions["frame_ms_mean"] == "unchanged"
    assert first.verdict == "regression"  # memory is informational, game time decides
    assert first.notes == ()
    assert len(first.metrics) == 4 * (1 + len(CHANNEL_NAMES))


def test_compare_profiles_memory_alone_does_not_decide():
    base = channel_samples(parse_csv_text(_full_csv([(10, 5, 4, 8, 3000, 1)] * 30)).frames)
    cand = channel_samples(parse_csv_text(_full_csv([(10, 5, 4, 8, 4000, 1)] * 30)).frames)
    result = compare_profiles(base, cand, iterations=30)
    assert result.verdict == "unchanged"
    only_memory = compare_samples([3000.0] * 5, [4000.0] * 5, iterations=20, name="physical_mb")
    assert only_memory.verdict == "regression"
    assert only_memory.metrics[0].metric == "physical_mb_mean"


def test_compare_profiles_notes_missing_channels():
    base = channel_samples(parse_csv_text("FrameTime,GPUTime\n10,8\n10,8\n").frames)
    cand = channel_samples(parse_csv_text("FrameTime\n10\n10\n").frames)
    result = compare_profiles(base, cand, iterations=20)
    assert len(result.metrics) == 4
    assert result.notes[2] == "gpu_ms: not present in both captures; not compared"
    assert len(result.notes) == len(CHANNEL_NAMES)


def test_synthetic_ue58_capture_parses():
    """A synthetic file shaped like a UE 5.8 CSV Profiler export (not a real capture)."""
    profile = parse_csv_profile(DATA / "synthetic_ue58_capture.csv")
    assert len(profile.frames) == 120
    assert dict(profile.columns) == {
        "frame_ms": "FrameTime",
        "game_ms": "GameThreadTime",
        "render_ms": "RenderThreadTime",
        "gpu_ms": "GPUTime",
        "physical_mb": "PhysicalUsedMB",
        "streaming_pool_mb": "TextureStreaming/StreamingPool",
    }
    assert [w.code for w in profile.warnings] == ["extra_column"]
    assert "and 3 more" in profile.warnings[0].message
    report = build_report("synthetic_ue58_capture.csv", profile, warmup_seconds=0.3)
    assert report.stats.excluded_frames == 3
    assert report.stats.hitch_count == 1
    assert [item.channel for item in report.channels] == list(CHANNEL_NAMES)
    assert report.notes == ()
