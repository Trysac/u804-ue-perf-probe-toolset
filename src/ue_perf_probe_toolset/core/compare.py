"""Per-metric comparison of two captures with a seeded bootstrap. Pure."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from ..errors import PerfError
from .stats import percentile, validate_frame_times

MAX_ITERATIONS = 5000
DEFAULT_MAX_POINTS = 5000
_METRICS = ("frame_ms_mean", "frame_ms_p50", "frame_ms_p95", "frame_ms_p99")


@dataclass(frozen=True)
class MetricDiff:
    """Difference candidate - baseline of one metric with its bootstrap interval.

    ``direction`` is ``regression`` (slower), ``improvement`` (faster) or ``unchanged``
    when the interval contains zero.
    """

    metric: str
    baseline: float
    candidate: float
    delta: float
    delta_pct: float
    ci_low: float
    ci_high: float
    direction: str


@dataclass(frozen=True)
class ComparisonResult:
    """Comparison of a candidate capture against a baseline capture."""

    baseline_count: int
    candidate_count: int
    seed: int
    iterations: int
    confidence: float
    metrics: tuple[MetricDiff, ...]
    verdict: str
    summary: str
    notes: tuple[str, ...] = ()


def _metric_values(ordered: Sequence[float]) -> tuple[float, float, float, float]:
    return (
        math.fsum(ordered) / len(ordered),
        percentile(ordered, 50),
        percentile(ordered, 95),
        percentile(ordered, 99),
    )


def _thin(values: Sequence[float], max_points: int) -> list[float]:
    count = len(values)
    if count <= max_points:
        return list(values)
    return [values[(index * count) // max_points] for index in range(max_points)]


def compare_samples(
    baseline_ms: Sequence[float],
    candidate_ms: Sequence[float],
    *,
    seed: int = 1234,
    iterations: int = 500,
    confidence: float = 0.95,
    max_points: int = DEFAULT_MAX_POINTS,
) -> ComparisonResult:
    """Compare two lists of frame times (ms), reproducibly for a given ``seed``.

    Point estimates use every frame. The percentile bootstrap interval resamples both samples
    with ``random.Random(seed)``; samples longer than ``max_points`` are first thinned by an
    even deterministic stride to bound the cost.

    Raises:
        PerfError: ``invalid_argument`` for bad values or parameters, ``no_frames`` for an
            empty sample, ``limit_exceeded`` for too many frames.
    """
    validate_frame_times(baseline_ms)
    validate_frame_times(candidate_ms)
    if not baseline_ms or not candidate_ms:
        raise PerfError("no_frames", "both captures need at least one frame")
    if isinstance(iterations, bool) or not 1 <= iterations <= MAX_ITERATIONS:
        raise PerfError("invalid_argument", f"iterations must be 1..{MAX_ITERATIONS}")
    if not 0.0 < confidence < 1.0:
        raise PerfError("invalid_argument", "confidence must be between 0 and 1")
    if max_points < 1:
        raise PerfError("invalid_argument", "max_points must be >= 1")

    base_point = _metric_values(sorted(baseline_ms))
    cand_point = _metric_values(sorted(candidate_ms))
    base_pool = _thin(baseline_ms, max_points)
    cand_pool = _thin(candidate_ms, max_points)
    rng = random.Random(seed)  # noqa: S311 - reproducible statistics, not security
    diffs: list[list[float]] = [[] for _ in _METRICS]
    for _ in range(iterations):
        base_sample = sorted(rng.choices(base_pool, k=len(base_pool)))
        cand_sample = sorted(rng.choices(cand_pool, k=len(cand_pool)))
        base_values = _metric_values(base_sample)
        cand_values = _metric_values(cand_sample)
        for index in range(len(_METRICS)):
            diffs[index].append(cand_values[index] - base_values[index])

    low_index = int((1.0 - confidence) / 2.0 * iterations)
    high_index = min(iterations - 1, int((1.0 + confidence) / 2.0 * iterations))
    metrics: list[MetricDiff] = []
    for index, name in enumerate(_METRICS):
        ordered = sorted(diffs[index])
        low, high = ordered[low_index], ordered[high_index]
        if low > 0:
            direction = "regression"
        elif high < 0:
            direction = "improvement"
        else:
            direction = "unchanged"
        delta = cand_point[index] - base_point[index]
        metrics.append(
            MetricDiff(
                metric=name,
                baseline=base_point[index],
                candidate=cand_point[index],
                delta=delta,
                delta_pct=delta / base_point[index] * 100.0,
                ci_low=low,
                ci_high=high,
                direction=direction,
            )
        )
    regressions = sum(1 for item in metrics if item.direction == "regression")
    improvements = sum(1 for item in metrics if item.direction == "improvement")
    if regressions:
        verdict = "regression"
    elif improvements:
        verdict = "improvement"
    else:
        verdict = "unchanged"
    summary = (
        f"{verdict}: {regressions} regressions, {improvements} improvements "
        f"({iterations} bootstrap iterations, seed {seed})"
    )
    return ComparisonResult(
        baseline_count=len(baseline_ms),
        candidate_count=len(candidate_ms),
        seed=seed,
        iterations=iterations,
        confidence=confidence,
        metrics=tuple(metrics),
        verdict=verdict,
        summary=summary,
    )
