"""Typed errors raised by ue_perf_probe_toolset."""

from __future__ import annotations

__all__ = ["ERROR_CODES", "PerfError"]

ERROR_CODES: frozenset[str] = frozenset(
    {
        "capture_in_progress",
        "csv_not_found",
        "csv_unreadable",
        "invalid_argument",
        "limit_exceeded",
        "no_frames",
        "path_not_allowed",
        "path_not_found",
        "unknown_job",
    }
)

_MAX_MESSAGE = 200


class PerfError(Exception):
    """Base error of the library.

    Attributes:
        code: stable machine-readable code, one of ``ERROR_CODES``.
        message: human-readable text, never longer than 200 characters.
    """

    def __init__(self, code: str, message: str) -> None:
        clipped = message[:_MAX_MESSAGE]
        super().__init__(clipped)
        self.code = code
        self.message = clipped

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"
