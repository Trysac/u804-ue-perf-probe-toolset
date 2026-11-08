"""Tests for frame statistics."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ue_perf_probe_toolset.core import stats as stats_module
from ue_perf_probe_toolset.core.stats import apply_warmup, frame_stats, percentile
from ue_perf_probe_toolset.errors import PerfError


def _naive_pct(ordered, pct):
    count = len(ordered)
    rank = -(-pct * count // 100)
    return ordered[max(rank, 1) - 1]


@settings(derandomize=True, max_examples=200, deadline=None)
@given(
    st.lists(
        st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=300,
    )
)
def test_stats_match_naive_reference(values):
    result = frame_stats(values)
    ordered = sorted(values)
    assert result.frame_count == len(values)
    assert result.frame_ms_mean == pytest.approx(sum(ordered) / len(ordered))
    assert result.frame_ms_p50 == _naive_pct(ordered, 50)
    assert result.frame_ms_p95 == _naive_pct(ordered, 95)
    assert result.frame_ms_p99 == _naive_pct(ordered, 99)
    assert result.frame_ms_max == ordered[-1]


def test_known_values():
    result = frame_stats([10.0, 20.0, 30.0, 40.0])
    assert result.frame_ms_mean == 25.0
    assert result.frame_ms_p50 == 20.0
    assert result.frame_ms_p95 == 40.0
    assert result.frame_ms_p99 == 40.0
    assert result.fps_mean == 40.0
    assert result.fps_min == 25.0
    assert result.fps_p1_low == 25.0
    assert result.fps_p5_low == 25.0
    assert result.duration_s == 0.1


def test_single_frame():
    result = frame_stats([16.0])
    assert result.frame_ms_mean == 16.0
    assert result.fps_min == 62.5
    assert result.hitch_count == 0
    assert result.hitches_per_min == 0.0
    assert "1 frames" in result.summary


def test_warmup_excludes_first_second():
    result = frame_stats([10.0] * 100 + [20.0] * 50, warmup_seconds=1)
    assert result.frame_count == 50
    assert result.excluded_frames == 100
    assert result.frame_ms_mean == 20.0
    assert result.frame_ms_p50 == 20.0
    assert result.frame_ms_p95 == 20.0
    assert result.frame_ms_p99 == 20.0
    assert result.fps_mean == 50.0
    assert result.duration_s == 1.0
    assert result.warmup_seconds == 1.0


def test_partial_warmup():
    kept, excluded = apply_warmup([10.0] * 100 + [20.0] * 50, 0.5)
    assert excluded == 50
    assert len(kept) == 100
    assert apply_warmup([5.0, 5.0], 0.0) == ([5.0, 5.0], 0)


def test_hitches():
    result = frame_stats([10.0] * 9 + [100.0])
    assert result.hitch_count == 1
    assert result.hitches_per_min == pytest.approx(60000.0 / 190.0)
    custom = frame_stats([10.0] * 9 + [100.0], hitch_threshold_ms=5.0)
    assert custom.hitch_count == 10
    assert custom.hitch_threshold_ms == 5.0


def test_percentile_direct():
    assert percentile([1, 2, 3, 4], 50) == 2
    assert percentile([1, 2, 3, 4], 100) == 4
    assert percentile([5], 1) == 5
    with pytest.raises(PerfError):
        percentile([], 50)
    with pytest.raises(PerfError):
        percentile([1], 0)
    with pytest.raises(PerfError):
        percentile([1], 101)


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ([], "no_frames"),
        ([0.0], "invalid_argument"),
        ([-1.0], "invalid_argument"),
        ([float("nan")], "invalid_argument"),
        ([float("inf")], "invalid_argument"),
        ([True], "invalid_argument"),
        (["a"], "invalid_argument"),
    ],
)
def test_invalid_frame_times(values, code):
    with pytest.raises(PerfError) as info:
        frame_stats(values)
    assert info.value.code == code


def test_frame_limit(monkeypatch):
    monkeypatch.setattr(stats_module, "MAX_FRAMES", 2)
    with pytest.raises(PerfError) as info:
        frame_stats([1.0, 1.0, 1.0])
    assert info.value.code == "limit_exceeded"


@pytest.mark.parametrize("warmup", [-1.0, float("nan"), float("inf")])
def test_invalid_warmup(warmup):
    with pytest.raises(PerfError) as info:
        frame_stats([10.0], warmup_seconds=warmup)
    assert info.value.code == "invalid_argument"


@pytest.mark.parametrize("threshold", [0, -5.0, float("nan")])
def test_invalid_threshold(threshold):
    with pytest.raises(PerfError) as info:
        frame_stats([10.0], hitch_threshold_ms=threshold)
    assert info.value.code == "invalid_argument"


def test_everything_inside_warmup_is_no_frames():
    with pytest.raises(PerfError) as info:
        frame_stats([10.0] * 5, warmup_seconds=10)
    assert info.value.code == "no_frames"
