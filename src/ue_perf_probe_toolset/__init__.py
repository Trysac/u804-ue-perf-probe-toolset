"""Pure core and Unreal adapter of an Unreal MCP toolset for CSV captures and build sizes."""

from __future__ import annotations

from .adapter import (
    JobStore,
    build_size_report,
    capture_status,
    compare_reports,
    get_report,
    perf_report_md,
    start_capture,
    to_dict,
)
from .core.budget import PerfBudget, evaluate_budget
from .core.csvparse import parse_csv_profile, parse_csv_text
from .core.stats import frame_stats
from .errors import ERROR_CODES, PerfError

__all__ = [
    "ERROR_CODES",
    "JobStore",
    "PerfBudget",
    "PerfError",
    "__version__",
    "build_size_report",
    "capture_status",
    "compare_reports",
    "evaluate_budget",
    "frame_stats",
    "get_report",
    "parse_csv_profile",
    "parse_csv_text",
    "perf_report_md",
    "start_capture",
    "to_dict",
]

__version__ = "0.1.0"
