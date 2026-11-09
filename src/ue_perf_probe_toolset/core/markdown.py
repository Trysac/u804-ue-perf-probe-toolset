"""Markdown rendering of a performance report. Pure."""

from __future__ import annotations

from .report import PerfReport

_STAT_ROWS = (
    "fps_mean",
    "fps_min",
    "fps_p1_low",
    "fps_p5_low",
    "frame_ms_mean",
    "frame_ms_p50",
    "frame_ms_p95",
    "frame_ms_p99",
    "hitches_per_min",
)


def _clean(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "/")[:200]


def render_perf_markdown(report: PerfReport) -> str:
    """Render ``report`` as Markdown; the first line is the table header."""
    stats = report.stats
    result = report.budget_result
    checks = {check.stat: check for check in result.checks} if result is not None else {}
    lines = ["| metric | value | budget | verdict |", "|---|---|---|---|"]
    for name in _STAT_ROWS:
        value = float(getattr(stats, name))
        check = checks.get(name)
        if check is None:
            budget_text, verdict_text = "-", "-"
        else:
            budget_text = f"{check.op} {check.limit:g}"
            verdict_text = "PASS" if check.passed else "FAIL"
        lines.append(f"| {name} | {value:.2f} | {budget_text} | {verdict_text} |")
    overall = result.verdict if result is not None else "n/a (no budget)"
    profile = _clean(report.render_profile) if report.render_profile else "not available"
    lines.extend(
        [
            "",
            f"**Verdict: {overall}**",
            "",
            f"- source: {_clean(report.source)}",
            *([f"- label: {_clean(report.label)}"] if report.label else []),
            f"- frames: {stats.frame_count} ({stats.excluded_frames} excluded as warmup)",
            f"- duration_s: {stats.duration_s:.2f}",
            f"- hitches: {stats.hitch_count} above {stats.hitch_threshold_ms:g} ms",
            f"- render profile: {profile}",
        ]
    )
    lines.extend(f"- note: {_clean(note)}" for note in report.notes)
    lines.extend(f"- warning: {_clean(warning)}" for warning in report.warnings)
    if report.channels:
        lines.extend(
            ["", "| channel | unit | mean | p50 | p95 | p99 |", "|---|---|---|---|---|---|"]
        )
        lines.extend(
            f"| {item.channel} | {item.unit} | {item.mean:.2f} | {item.p50:.2f} | "
            f"{item.p95:.2f} | {item.p99:.2f} |"
            for item in report.channels
        )
    return "\n".join(lines) + "\n"
