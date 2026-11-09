# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-08

### Added

- Unreal plugin `plugin/PerfProbeToolset/` (Python only): `PerfProbeTools` toolset registered in the Toolset Registry with six documented tools.
- `mcp` module: flat parameters (budget as `target_fps`, `min_fps`, `max_hitches_per_min`, `hitch_ms`), JSON string results with `summary` first, errors returned as data; `build_size_report` defaults to a 1 GiB limit.
- Report statistics (mean, p50, p95, p99) for game thread, render thread (draw) and GPU time, and for physical memory used and the texture streaming pool when those columns exist (`PerfReport.channels`, `channel_stats`); absent columns are omitted with a note. `compare_reports` compares every shared column with the same seeded bootstrap (`compare_profiles`; the verdict counts time metrics, memory is informational) and `perf_report_md` adds a channel table (golden file updated).
- `start_capture(label=...)`: a sanitized label (at most 64 characters) kept with the job and shown in its reports, Markdown and comparison notes; it never reaches the console.
- Synthetic fixture `tests/data/synthetic_ue58_capture.csv` shaped like a UE 5.8 CSV Profiler export (typical columns, events column, repeated header and metadata trailer). It is not a real capture.
- `tools/build_plugin.py` (plugin zip with the vendored package), `tests/ue_smoke.py` (non-blocking in-editor check), `skill/SKILL.md`, ADR 0003.

### Changed

- `docs/AGENT_USAGE.md` describes real `call_tool` usage; `docs/TESTING.md` lists the engine assumptions to confirm and the in-editor acceptance steps.

### Fixed

- A header row repeated at the end of a CSV is skipped instead of producing a `bad_value` warning; all unrecognized columns produce a single `extra_column` warning.
- `capture_failed` is now registered in `ERROR_CODES` (the adapter already raised it).

## [0.1.0] - 2026-11-08

### Added

- Added the pure core (CSV Profiler parser, frame statistics, budgets, seeded bootstrap comparison, build size report, Markdown report) and a thin Unreal adapter with start_capture, capture_status, get_report, compare_reports, build_size_report and perf_report_md.
- Initial project structure from the factory utility template.
