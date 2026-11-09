# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-08

### Added

- Unreal plugin `plugin/PerfProbeToolset/` (Python only): `PerfProbeTools` toolset registered in the Toolset Registry with six documented tools.
- `mcp` module: flat parameters (budget as `target_fps`, `min_fps`, `max_hitches_per_min`, `hitch_ms`), JSON string results with `summary` first, errors returned as data; `build_size_report` defaults to a 1 GiB limit.
- `tools/build_plugin.py` (plugin zip with the vendored package), `tests/ue_smoke.py` (non-blocking in-editor check), `skill/SKILL.md`, ADR 0003.

### Changed

- `docs/AGENT_USAGE.md` describes real `call_tool` usage; `docs/TESTING.md` lists the engine assumptions to confirm and the in-editor acceptance steps.

### Fixed

- `capture_failed` is now registered in `ERROR_CODES` (the adapter already raised it).

## [0.1.0] - 2026-11-08

### Added

- Added the pure core (CSV Profiler parser, frame statistics, budgets, seeded bootstrap comparison, build size report, Markdown report) and a thin Unreal adapter with start_capture, capture_status, get_report, compare_reports, build_size_report and perf_report_md.
- Initial project structure from the factory utility template.
