"""Frame statistics: fps, frame time percentiles and hitches. Pure."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..errors import PerfError

MAX_FRAMES = 5_000_000
DEFAULT_HITCH_THRESHOLD_MS = 50.0


@dataclass(frozen=True)
class FrameStats:
    """Statistics of the frames kept after warmup. Times in ms, rates in frames per second."""

    frame_count: int
    excluded_frames: int
    duration_s: float
    fps_mean: float
    fps_min: float
    fps_p1_low: float
    fps_p5_low: float
    frame_ms_mean: float
    frame_ms_p50: float
    frame_ms_p95: float
    frame_ms_p99: float
    frame_ms_max: float
    hitch_count: int
    hitch_threshold_ms: float
    hitches_per_min: float
    warmup_seconds: float
    summary: str


def percentile(sorted_values: Sequence[float], pct: int) -> float:
    """Nearest-rank percentile: ``sorted_values[ceil(pct * n / 100) - 1]``.

    Raises:
        PerfError: ``no_frames`` for an empty sequence, ``invalid_argument`` for ``pct``
            outside 1..100.
    """
    count = len(sorted_values)
    if count == 0:
        raise PerfError("no_frames", "cannot take a percentile of no values")
    if not 1 <= pct <= 100:
        raise PerfError("invalid_argument", "percentile must be between 1 and 100")
    rank = (pct * count + 99) // 100
    return sorted_values[rank - 1]


def validate_frame_times(values: Sequence[float]) -> None:
    """Check size and content of a list of frame times in ms.

    Raises:
        PerfError: ``limit_exceeded`` above ``MAX_FRAMES``; ``invalid_argument`` when a value
            is not a finite positive number.
    """
    if len(values) > MAX_FRAMES:
        raise PerfError("limit_exceeded", f"more than {MAX_FRAMES} frames")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise PerfError("invalid_argument", "frame times must be numbers")
        if not math.isfinite(value) or value <= 0:
            raise PerfError("invalid_argument", "frame times must be finite and positive")


def apply_warmup(
    frame_times_ms: Sequence[float], warmup_seconds: float = 0.0
) -> tuple[list[float], int]:
    """Drop frames that start inside the first ``warmup_seconds`` of the capture.

    A frame's start is the sum of the frame times before it. Returns the kept frame times and
    the number of excluded frames.

    Raises:
        PerfError: ``invalid_argument`` when ``warmup_seconds`` is negative or not finite.
    """
    if not math.isfinite(warmup_seconds) or warmup_seconds < 0:
        raise PerfError("invalid_argument", "warmup_seconds must be finite and >= 0")
    limit_ms = warmup_seconds * 1000.0
    clock = 0.0
    kept: list[float] = []
    excluded = 0
    for value in frame_times_ms:
        if clock < limit_ms:
            excluded += 1
        else:
            kept.append(value)
        clock += value
    return kept, excluded


def frame_stats(
    frame_times_ms: Sequence[float],
    *,
    warmup_seconds: float = 0.0,
    hitch_threshold_ms: float = DEFAULT_HITCH_THRESHOLD_MS,
) -> FrameStats:
    """Compute statistics for a list of frame times in milliseconds.

    ``fps_mean`` is ``1000 / mean``; ``fps_min`` uses the slowest frame; ``fps_p1_low`` and
    ``fps_p5_low`` use the 99th and 95th percentile frame time. A hitch is a frame slower
    than ``hitch_threshold_ms``.

    Raises:
        PerfError: ``invalid_argument`` for bad values or parameters, ``limit_exceeded`` for
            too many frames, ``no_frames`` when no frame remains after warmup.
    """
    validate_frame_times(frame_times_ms)
    if not math.isfinite(hitch_threshold_ms) or hitch_threshold_ms <= 0:
        raise PerfError("invalid_argument", "hitch_threshold_ms must be finite and > 0")
    kept, excluded = apply_warmup(frame_times_ms, warmup_seconds)
    if not kept:
        raise PerfError("no_frames", "no frames left to analyze")
    ordered = sorted(kept)
    count = len(kept)
    total_ms = math.fsum(kept)
    mean_ms = total_ms / count
    p50 = percentile(ordered, 50)
    p95 = percentile(ordered, 95)
    p99 = percentile(ordered, 99)
    max_ms = ordered[-1]
    hitches = sum(1 for value in kept if value > hitch_threshold_ms)
    fps_mean = 1000.0 / mean_ms
    summary = f"{count} frames, {fps_mean:.1f} fps mean, p99 {p99:.2f} ms, {hitches} hitches"
    return FrameStats(
        frame_count=count,
        excluded_frames=excluded,
        duration_s=total_ms / 1000.0,
        fps_mean=fps_mean,
        fps_min=1000.0 / max_ms,
        fps_p1_low=1000.0 / p99,
        fps_p5_low=1000.0 / p95,
        frame_ms_mean=mean_ms,
        frame_ms_p50=p50,
        frame_ms_p95=p95,
        frame_ms_p99=p99,
        frame_ms_max=max_ms,
        hitch_count=hitches,
        hitch_threshold_ms=float(hitch_threshold_ms),
        hitches_per_min=hitches * 60000.0 / total_ms,
        warmup_seconds=float(warmup_seconds),
        summary=summary,
    )
