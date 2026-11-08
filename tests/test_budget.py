"""Tests for budgets."""

from __future__ import annotations

import pytest

from ue_perf_probe_toolset.core.budget import PerfBudget, evaluate_budget
from ue_perf_probe_toolset.core.stats import frame_stats
from ue_perf_probe_toolset.errors import PerfError


def test_five_hitches_per_minute_fail_the_budget():
    stats = frame_stats([10.0] * 5950 + [100.0] * 5)
    assert stats.hitches_per_min == 5.0
    budget = PerfBudget.from_mapping({"target_fps": 60, "min_fps": 45, "max_hitches_per_min": 2})
    result = evaluate_budget(stats, budget)
    assert result.verdict == "FAIL"
    assert result.failed_metrics == ("max_hitches_per_min",)
    assert "max_hitches_per_min" in result.reasons[0]
    assert result.summary == "FAIL: 2/3 budget checks passed"


def test_pass_with_every_limit():
    stats = frame_stats([10.0] * 100)
    budget = PerfBudget(
        target_fps=60,
        min_fps=45,
        max_hitches_per_min=2,
        max_frame_ms_p95=20,
        max_frame_ms_p99=20,
    )
    result = evaluate_budget(stats, budget)
    assert result.verdict == "PASS"
    assert result.reasons == ()
    assert len(result.checks) == 5
    assert all(check.passed for check in result.checks)


def test_percentile_limits_fail():
    stats = frame_stats([10.0] * 90 + [100.0] * 10)
    result = evaluate_budget(stats, PerfBudget(max_frame_ms_p95=20, max_frame_ms_p99=20))
    assert result.failed_metrics == ("max_frame_ms_p95", "max_frame_ms_p99")


def test_empty_budget_passes():
    result = evaluate_budget(frame_stats([10.0]), PerfBudget())
    assert result.verdict == "PASS"
    assert result.checks == ()


def test_limit_is_inclusive():
    stats = frame_stats([10.0] * 10)
    assert evaluate_budget(stats, PerfBudget(target_fps=100.0)).verdict == "PASS"
    assert evaluate_budget(stats, PerfBudget(max_frame_ms_p99=10.0)).verdict == "PASS"


def test_zero_hitch_budget_is_allowed():
    assert PerfBudget(max_hitches_per_min=0).max_hitches_per_min == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_fps": 0},
        {"target_fps": -1},
        {"min_fps": float("nan")},
        {"max_hitches_per_min": -1},
        {"max_frame_ms_p95": float("inf")},
        {"max_frame_ms_p99": True},
        {"target_fps": "60"},
    ],
)
def test_invalid_budget_values(kwargs):
    with pytest.raises(PerfError) as info:
        PerfBudget(**kwargs)
    assert info.value.code == "invalid_argument"


def test_from_mapping_errors():
    with pytest.raises(PerfError):
        PerfBudget.from_mapping({"target_fps": 60, "bogus": 1})
    with pytest.raises(PerfError):
        PerfBudget.from_mapping({"target_fps": "fast"})
    with pytest.raises(PerfError):
        PerfBudget.from_mapping([1])
    assert PerfBudget.from_mapping({"target_fps": None}) == PerfBudget()
