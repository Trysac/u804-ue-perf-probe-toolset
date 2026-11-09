"""Unreal MCP toolset that exposes ue_perf_probe_toolset to AI agents.

Discovered by the Toolset Registry at editor startup (this file lives in the plugin's
Content/Python). Every tool forwards to ``ue_perf_probe_toolset.mcp`` with the real ``unreal``
module and returns a JSON string whose first key is ``summary``. Every tool is short: a capture is
started by one call and stopped later by an editor tick callback, never by sleeping. All tools are
read-only except start_capture, which only runs ``csvprofile start`` / ``csvprofile stop``.
"""

import toolset_registry
import unreal

from ue_perf_probe_toolset import mcp


@unreal.uclass()
class PerfProbeTools(unreal.ToolsetDefinition):
    """Measure game performance repeatably with the CSV Profiler and report build size.

    Use it to record a capture of N seconds (in PIE or the editor) without blocking, then get frame
    statistics (fps mean/min/1%/5% low, frame time p50/p95/p99, hitches) with a PASS/FAIL verdict
    against a budget, compare a capture with a previous one (seeded bootstrap), render a Markdown
    table for a dev log, and check the size of a packaged build against a limit.
    """

    @staticmethod
    @toolset_registry.tool_call
    def start_capture(duration_seconds: float = 30.0, label: str = "") -> str:
        """Start a CSV Profiler capture that stops by itself after duration_seconds.

        Returns at once; poll capture_status with the job_id. Only one capture runs at a time.

        Args:
            duration_seconds: Capture length in seconds (1 to 3600).
            label: Short name for this capture (for example "before LOD fix"), shown in its
                reports; at most 64 characters, unusual characters become "_".

        Returns:
            JSON with summary, job_id, state ("running"), duration_seconds and label.
        """
        return mcp.start_capture(unreal, duration_seconds, label)

    @staticmethod
    @toolset_registry.tool_call
    def capture_status(job_id: str) -> str:
        """Report the state of a capture started with start_capture.

        Args:
            job_id: Id returned by start_capture (for example "capture-0001").

        Returns:
            JSON with summary, state ("running", "finalizing" or "completed") and csv_name once
            the CSV file exists in Saved/Profiling/CSV.
        """
        return mcp.capture_status(unreal, job_id)

    @staticmethod
    @toolset_registry.tool_call
    def get_report(
        job_id: str = "",
        csv_path: str = "",
        target_fps: float = 0.0,
        min_fps: float = 0.0,
        max_hitches_per_min: float = -1.0,
        hitch_ms: float = 50.0,
        warmup_seconds: float = 0.0,
    ) -> str:
        """Frame statistics of a capture with an optional PASS/FAIL budget verdict.

        The CSV is chosen by csv_path, else by job_id, else the newest CSV in Saved/Profiling/CSV.

        Args:
            job_id: Id of a completed capture (optional).
            csv_path: CSV file name or path inside Saved/Profiling/CSV (optional).
            target_fps: Minimum mean fps; 0 disables the check.
            min_fps: Minimum 1 percent low fps; 0 disables the check.
            max_hitches_per_min: Maximum hitches per minute; negative disables the check.
            hitch_ms: A frame slower than this many milliseconds is a hitch.
            warmup_seconds: Seconds at the start excluded (shader compilation spikes).

        Returns:
            JSON with summary, source, label, stats, budget_result (verdict, reasons), channels
            (mean/p50/p95/p99 of game, render (draw) and GPU time, physical memory and texture
            streaming pool when the capture has them), notes and warnings.
        """
        return mcp.get_report(
            unreal,
            job_id,
            csv_path,
            target_fps,
            min_fps,
            max_hitches_per_min,
            hitch_ms,
            warmup_seconds,
        )

    @staticmethod
    @toolset_registry.tool_call
    def compare_reports(
        baseline_csv: str,
        candidate_csv: str,
        seed: int = 1234,
        iterations: int = 500,
        warmup_seconds: float = 0.0,
    ) -> str:
        """Compare a candidate capture with a baseline capture per frame time metric.

        Args:
            baseline_csv: CSV name or path inside Saved/Profiling/CSV (the previous run).
            candidate_csv: CSV name or path inside Saved/Profiling/CSV (the new run).
            seed: Bootstrap seed; the same seed gives the same result.
            iterations: Bootstrap iterations (1 to 5000).
            warmup_seconds: Seconds at the start of each capture excluded.

        Returns:
            JSON with summary, verdict ("regression", "improvement" or "unchanged", from the time
            metrics), metrics for frame, game, render, GPU and memory columns present in both
            (delta, delta_pct, ci_low, ci_high, direction) and notes.
        """
        return mcp.compare_reports(
            unreal, baseline_csv, candidate_csv, seed, iterations, warmup_seconds
        )

    @staticmethod
    @toolset_registry.tool_call
    def build_size_report(build_dir: str, limit_bytes: int = 1073741824, cook_log: str = "") -> str:
        """Size of a packaged build folder under the project directory (read-only).

        Args:
            build_dir: Folder inside the project (relative to it or absolute).
            limit_bytes: Size limit that triggers warnings at 90 and 100 percent; 0 disables it.
            cook_log: Optional cook log inside the project used to name the largest packages.

        Returns:
            JSON with summary, total_bytes, breakdown by extension, estimated_zip_bytes (an
            estimate), usage_ratio, warnings and largest_contributors.
        """
        return mcp.build_size_report(unreal, build_dir, limit_bytes, cook_log)

    @staticmethod
    @toolset_registry.tool_call
    def perf_report_md(
        job_id: str = "",
        csv_path: str = "",
        target_fps: float = 0.0,
        min_fps: float = 0.0,
        max_hitches_per_min: float = -1.0,
        hitch_ms: float = 50.0,
        warmup_seconds: float = 0.0,
    ) -> str:
        """The report of get_report as a Markdown table ready for perf.md or a dev log.

        Args:
            job_id: Id of a completed capture (optional).
            csv_path: CSV file name or path inside Saved/Profiling/CSV (optional).
            target_fps: Minimum mean fps; 0 disables the check.
            min_fps: Minimum 1 percent low fps; 0 disables the check.
            max_hitches_per_min: Maximum hitches per minute; negative disables the check.
            hitch_ms: A frame slower than this many milliseconds is a hitch.
            warmup_seconds: Seconds at the start excluded (shader compilation spikes).

        Returns:
            JSON with summary and markdown.
        """
        return mcp.perf_report_md(
            unreal,
            job_id,
            csv_path,
            target_fps,
            min_fps,
            max_hitches_per_min,
            hitch_ms,
            warmup_seconds,
        )
