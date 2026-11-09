"""MCP-facing functions: flat, JSON-friendly parameters in, one JSON string out.

The Unreal plugin's toolset class (``plugin/PerfProbeToolset/Content/Python``) only forwards to
these functions with the real ``unreal`` module, so everything an agent sees is tested here with a
fake. Inputs are primitives and every result is a JSON object whose first key is ``summary``.
Errors never raise to the agent: they come back as
``{"summary": "error: ...", "error": {"code": ..., "message": ...}}``.

Capture jobs live in ``adapter.DEFAULT_STORE``, a module-level registry, so a job started by one
MCP call is still known to the next one. Jobs are lost if the Python package is reloaded; the CSV
files stay in ``Saved/Profiling/CSV/`` and every report tool also accepts ``csv_path``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import Any

from . import adapter
from .core.budget import PerfBudget
from .core.markdown import render_perf_markdown
from .errors import PerfError

GIB = 1024**3


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def to_json(result: Any) -> str:
    """Serialize a result with ``summary`` first."""
    data = _plain(result)
    if isinstance(data, dict) and "summary" in data:
        data = {"summary": data["summary"], **{k: v for k, v in data.items() if k != "summary"}}
    return json.dumps(data, ensure_ascii=False)


def _error(code: str, message: str) -> str:
    return json.dumps(
        {"summary": f"error: {message[:200]}", "error": {"code": code, "message": message[:200]}}
    )


def _run(call: Callable[[], Any]) -> str:
    try:
        return to_json(call())
    except PerfError as exc:
        return _error(exc.code, exc.message)
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        return _error("unreal_error", f"{type(exc).__name__}: {exc}")


def _budget(target_fps: float, min_fps: float, max_hitches_per_min: float) -> PerfBudget | None:
    """Flat budget parameters: ``0`` disables an fps limit, a negative value the hitch limit."""
    budget = PerfBudget(
        target_fps=target_fps if target_fps else None,
        min_fps=min_fps if min_fps else None,
        max_hitches_per_min=max_hitches_per_min if max_hitches_per_min >= 0 else None,
    )
    if budget == PerfBudget():
        return None
    return budget


def _report(
    ue: Any,
    job_id: str,
    csv_path: str,
    target_fps: float,
    min_fps: float,
    max_hitches_per_min: float,
    hitch_ms: float,
    warmup_seconds: float,
) -> Any:
    return adapter.get_report(
        ue,
        job_id or None,
        csv_path or None,
        budget=_budget(target_fps, min_fps, max_hitches_per_min),
        warmup_seconds=warmup_seconds,
        hitch_threshold_ms=hitch_ms,
    )


def start_capture(ue: Any, duration_seconds: float = 30.0) -> str:
    """Start a CSV Profiler capture; returns at once with ``job_id`` (never blocks)."""
    return _run(lambda: adapter.start_capture(ue, duration_seconds))


def capture_status(ue: Any, job_id: str) -> str:
    """State of a capture job: running, finalizing or completed."""
    return _run(lambda: adapter.capture_status(ue, job_id))


def get_report(
    ue: Any,
    job_id: str = "",
    csv_path: str = "",
    target_fps: float = 0.0,
    min_fps: float = 0.0,
    max_hitches_per_min: float = -1.0,
    hitch_ms: float = 50.0,
    warmup_seconds: float = 0.0,
) -> str:
    """Frame statistics of a capture and, when any limit is set, the budget verdict."""
    return _run(
        lambda: _report(
            ue,
            job_id,
            csv_path,
            target_fps,
            min_fps,
            max_hitches_per_min,
            hitch_ms,
            warmup_seconds,
        )
    )


def compare_reports(
    ue: Any,
    baseline_csv: str,
    candidate_csv: str,
    seed: int = 1234,
    iterations: int = 500,
    warmup_seconds: float = 0.0,
) -> str:
    """Seeded bootstrap comparison of two CSV captures (same seed, same result)."""
    return _run(
        lambda: adapter.compare_reports(
            ue,
            baseline_csv,
            candidate_csv,
            seed=seed,
            iterations=iterations,
            warmup_seconds=warmup_seconds,
        )
    )


def build_size_report(ue: Any, build_dir: str, limit_bytes: int = GIB, cook_log: str = "") -> str:
    """Read-only size of a build folder under the project; ``limit_bytes=0`` disables the limit."""
    return _run(
        lambda: adapter.build_size_report(
            ue, build_dir, limit_bytes=limit_bytes or None, cook_log=cook_log or None
        )
    )


def perf_report_md(
    ue: Any,
    job_id: str = "",
    csv_path: str = "",
    target_fps: float = 0.0,
    min_fps: float = 0.0,
    max_hitches_per_min: float = -1.0,
    hitch_ms: float = 50.0,
    warmup_seconds: float = 0.0,
) -> str:
    """The report of ``get_report`` as a Markdown table under ``markdown``."""

    def call() -> dict[str, Any]:
        report = _report(
            ue,
            job_id,
            csv_path,
            target_fps,
            min_fps,
            max_hitches_per_min,
            hitch_ms,
            warmup_seconds,
        )
        return {"summary": report.summary, "markdown": render_perf_markdown(report)}

    return _run(call)
