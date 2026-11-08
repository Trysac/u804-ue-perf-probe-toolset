"""Performance budgets and their PASS/FAIL evaluation. Pure."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from ..errors import PerfError
from .stats import FrameStats

_FIELDS = (
    "target_fps",
    "min_fps",
    "max_hitches_per_min",
    "max_frame_ms_p95",
    "max_frame_ms_p99",
)

# (budget key, FrameStats attribute, comparison that must hold: actual <op> limit)
_RULES = (
    ("target_fps", "fps_mean", ">="),
    ("min_fps", "fps_p1_low", ">="),
    ("max_hitches_per_min", "hitches_per_min", "<="),
    ("max_frame_ms_p95", "frame_ms_p95", "<="),
    ("max_frame_ms_p99", "frame_ms_p99", "<="),
)


@dataclass(frozen=True)
class PerfBudget:
    """Limits a capture must respect. ``None`` disables a limit.

    ``target_fps`` is compared with the mean fps and ``min_fps`` with the 1 percent low fps.
    """

    target_fps: float | None = None
    min_fps: float | None = None
    max_hitches_per_min: float | None = None
    max_frame_ms_p95: float | None = None
    max_frame_ms_p99: float | None = None

    def __post_init__(self) -> None:
        for name in _FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise PerfError("invalid_argument", f"{name} must be a number")
            if not math.isfinite(value):
                raise PerfError("invalid_argument", f"{name} must be finite")
            minimum_ok = value >= 0 if name == "max_hitches_per_min" else value > 0
            if not minimum_ok:
                raise PerfError("invalid_argument", f"{name} is out of range")

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> PerfBudget:
        """Build a budget from a plain mapping, rejecting unknown keys.

        Raises:
            PerfError: ``invalid_argument`` for non-mappings, unknown keys or bad values.
        """
        if not isinstance(data, Mapping):
            raise PerfError("invalid_argument", "budget must be a mapping")
        unknown = sorted(str(key)[:30] for key in data if key not in _FIELDS)
        if unknown:
            raise PerfError("invalid_argument", f"unknown budget keys: {', '.join(unknown)[:100]}")
        return cls(
            target_fps=_number(data, "target_fps"),
            min_fps=_number(data, "min_fps"),
            max_hitches_per_min=_number(data, "max_hitches_per_min"),
            max_frame_ms_p95=_number(data, "max_frame_ms_p95"),
            max_frame_ms_p99=_number(data, "max_frame_ms_p99"),
        )


def _number(data: Mapping[str, object], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PerfError("invalid_argument", f"{key} must be a number")
    return float(value)


@dataclass(frozen=True)
class BudgetCheck:
    """One evaluated limit."""

    metric: str
    stat: str
    actual: float
    limit: float
    op: str
    passed: bool


@dataclass(frozen=True)
class BudgetResult:
    """Verdict of a budget evaluation: ``PASS`` or ``FAIL`` with reasons."""

    verdict: str
    checks: tuple[BudgetCheck, ...]
    reasons: tuple[str, ...]
    failed_metrics: tuple[str, ...]
    summary: str


def evaluate_budget(stats: FrameStats, budget: PerfBudget) -> BudgetResult:
    """Compare ``stats`` with ``budget``; every limit that is set must hold."""
    checks: list[BudgetCheck] = []
    reasons: list[str] = []
    for metric, stat, op in _RULES:
        limit = getattr(budget, metric)
        if limit is None:
            continue
        actual = float(getattr(stats, stat))
        passed = actual >= limit if op == ">=" else actual <= limit
        checks.append(BudgetCheck(metric, stat, actual, float(limit), op, passed))
        if not passed:
            reasons.append(f"{metric}: {stat} {actual:.2f} is not {op} {limit:g}")
    failed = tuple(check.metric for check in checks if not check.passed)
    verdict = "FAIL" if failed else "PASS"
    ok_count = sum(1 for check in checks if check.passed)
    summary = f"{verdict}: {ok_count}/{len(checks)} budget checks passed"
    return BudgetResult(verdict, tuple(checks), tuple(reasons), failed, summary)
