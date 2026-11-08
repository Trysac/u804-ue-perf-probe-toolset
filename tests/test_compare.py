"""Tests for the seeded bootstrap comparison."""

from __future__ import annotations

import pytest

from ue_perf_probe_toolset.core.compare import compare_samples
from ue_perf_probe_toolset.errors import PerfError

BASE = [10.0 + (index % 5) * 0.1 for index in range(100)]
SLOW = [20.0 + (index % 5) * 0.1 for index in range(100)]


def test_same_seed_gives_identical_results():
    first = compare_samples(BASE, SLOW, seed=1234, iterations=200)
    second = compare_samples(BASE, SLOW, seed=1234, iterations=200)
    assert first == second
    assert first.seed == 1234


def test_different_seed_changes_the_interval():
    jittery = [10.0 + (index * 7 % 13) for index in range(60)]
    other = [11.0 + (index * 5 % 11) for index in range(60)]
    first = compare_samples(jittery, other, seed=1, iterations=200)
    second = compare_samples(jittery, other, seed=2, iterations=200)
    assert first != second


def test_regression_is_detected():
    result = compare_samples(BASE, SLOW, iterations=100)
    assert result.verdict == "regression"
    assert all(item.direction == "regression" for item in result.metrics)
    assert result.metrics[0].metric == "frame_ms_mean"
    assert result.metrics[0].delta == pytest.approx(10.0)
    assert result.summary.startswith("regression: 4 regressions")


def test_improvement_is_detected():
    result = compare_samples(SLOW, BASE, iterations=100)
    assert result.verdict == "improvement"
    assert all(item.direction == "improvement" for item in result.metrics)


def test_identical_constant_samples_are_unchanged():
    result = compare_samples([10.0] * 50, [10.0] * 50, iterations=50)
    assert result.verdict == "unchanged"
    assert all(item.delta == 0.0 and item.direction == "unchanged" for item in result.metrics)


def test_constant_shift_has_degenerate_interval():
    result = compare_samples([10.0] * 20, [20.0] * 20, iterations=50)
    mean = result.metrics[0]
    assert (mean.baseline, mean.candidate, mean.delta, mean.delta_pct) == (10.0, 20.0, 10.0, 100.0)
    assert (mean.ci_low, mean.ci_high) == (10.0, 10.0)
    assert (result.baseline_count, result.candidate_count) == (20, 20)


def test_long_samples_are_thinned_for_the_bootstrap_only():
    result = compare_samples(BASE, SLOW, iterations=20, max_points=10)
    assert result.baseline_count == 100
    assert result.metrics[0].baseline == pytest.approx(sum(BASE) / 100)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iterations": 0},
        {"iterations": 5001},
        {"iterations": True},
        {"confidence": 0.0},
        {"confidence": 1.0},
        {"max_points": 0},
    ],
)
def test_invalid_parameters(kwargs):
    with pytest.raises(PerfError) as info:
        compare_samples(BASE, SLOW, **kwargs)
    assert info.value.code == "invalid_argument"


def test_invalid_samples():
    with pytest.raises(PerfError) as empty:
        compare_samples([], SLOW)
    assert empty.value.code == "no_frames"
    with pytest.raises(PerfError) as bad:
        compare_samples(BASE, [float("nan")])
    assert bad.value.code == "invalid_argument"
