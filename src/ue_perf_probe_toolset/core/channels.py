"""Per-column statistics for thread, GPU, memory and streaming columns. Pure."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..errors import PerfError
from .csvparse import Frame
from .stats import percentile

# (Frame attribute, unit, what it is). Draw time is the render thread time.
CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("game_ms", "ms", "game thread time"),
    ("render_ms", "ms", "render thread (draw) time"),
    ("gpu_ms", "ms", "GPU time"),
    ("physical_mb", "MB", "physical memory used"),
    ("streaming_pool_mb", "MB", "texture streaming pool"),
)
CHANNEL_NAMES: tuple[str, ...] = tuple(name for name, _, _ in CHANNELS)
CHANNEL_UNITS: dict[str, str] = {name: unit for name, unit, _ in CHANNELS}


@dataclass(frozen=True)
class ChannelStats:
    """Mean and nearest-rank percentiles of one column over the frames kept after warmup."""

    channel: str
    unit: str
    count: int
    mean: float
    p50: float
    p95: float
    p99: float


def channel_samples(frames: Sequence[Frame], warmup_seconds: float = 0.0) -> dict[str, list[float]]:
    """Values of ``frame_ms`` and of every channel for frames that start after the warmup.

    A frame is kept when its ``start_ms`` is at least ``warmup_seconds`` (the same rule as
    ``stats.apply_warmup``). Missing values are left out, so a channel can be empty.

    Raises:
        PerfError: ``invalid_argument`` when ``warmup_seconds`` is negative or not finite.
    """
    if not math.isfinite(warmup_seconds) or warmup_seconds < 0:
        raise PerfError("invalid_argument", "warmup_seconds must be finite and >= 0")
    limit_ms = warmup_seconds * 1000.0
    samples: dict[str, list[float]] = {"frame_ms": [], **{name: [] for name in CHANNEL_NAMES}}
    for frame in frames:
        if frame.start_ms < limit_ms:
            continue
        samples["frame_ms"].append(frame.frame_ms)
        for name in CHANNEL_NAMES:
            value = getattr(frame, name)
            if value is not None:
                samples[name].append(value)
    return samples


def channel_stats(
    frames: Sequence[Frame], warmup_seconds: float = 0.0
) -> tuple[tuple[ChannelStats, ...], tuple[str, ...]]:
    """Statistics of every channel with values, and one note per channel that is omitted.

    Raises:
        PerfError: ``invalid_argument`` for a bad ``warmup_seconds``.
    """
    samples = channel_samples(frames, warmup_seconds)
    found: list[ChannelStats] = []
    notes: list[str] = []
    for name, unit, label in CHANNELS:
        values = samples[name]
        if not values:
            notes.append(f"{name} ({label}): no column or no values in the capture; omitted")
            continue
        ordered = sorted(values)
        found.append(
            ChannelStats(
                channel=name,
                unit=unit,
                count=len(values),
                mean=math.fsum(values) / len(values),
                p50=percentile(ordered, 50),
                p95=percentile(ordered, 95),
                p99=percentile(ordered, 99),
            )
        )
    return tuple(found), tuple(notes)
