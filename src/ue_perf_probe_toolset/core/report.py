"""Single-capture performance report. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from .budget import BudgetResult, PerfBudget, evaluate_budget
from .channels import ChannelStats, channel_stats
from .csvparse import ParsedProfile
from .stats import DEFAULT_HITCH_THRESHOLD_MS, FrameStats, frame_stats


@dataclass(frozen=True)
class PerfReport:
    """Statistics of one capture, the optional budget verdict and parser warnings.

    ``channels`` holds game/render (draw)/GPU time and memory/streaming statistics for the columns
    the capture has; ``notes`` names the omitted ones. ``label`` comes from ``start_capture``.
    """

    source: str
    stats: FrameStats
    budget_result: BudgetResult | None
    warnings: tuple[str, ...]
    render_profile: str | None
    summary: str
    channels: tuple[ChannelStats, ...] = ()
    notes: tuple[str, ...] = ()
    label: str | None = None


def build_report(
    source: str,
    profile: ParsedProfile,
    *,
    warmup_seconds: float = 0.0,
    hitch_threshold_ms: float = DEFAULT_HITCH_THRESHOLD_MS,
    budget: PerfBudget | None = None,
    render_profile: str | None = None,
    label: str | None = None,
) -> PerfReport:
    """Compute statistics for ``profile`` and evaluate ``budget`` when given.

    Raises:
        PerfError: see ``frame_stats``.
    """
    stats = frame_stats(
        [frame.frame_ms for frame in profile.frames],
        warmup_seconds=warmup_seconds,
        hitch_threshold_ms=hitch_threshold_ms,
    )
    channels, notes = channel_stats(profile.frames, warmup_seconds)
    result = evaluate_budget(stats, budget) if budget is not None else None
    warnings = tuple(
        f"{item.code}: {item.message}" + (f" (line {item.line})" if item.line else "")
        for item in profile.warnings
    )
    tail = f"; budget {result.verdict}" if result is not None else ""
    summary = f"{source}: {stats.summary}{tail}"
    return PerfReport(
        source,
        stats,
        result,
        warnings,
        render_profile,
        summary,
        channels=channels,
        notes=notes,
        label=label or None,
    )
