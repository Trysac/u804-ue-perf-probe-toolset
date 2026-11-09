# ue-perf-probe-toolset

[![PyPI version](https://img.shields.io/pypi/v/trysac-ue-perf-probe-toolset)](https://pypi.org/project/trysac-ue-perf-probe-toolset/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-ue-perf-probe-toolset)](LICENSE)
[![CI](https://github.com/Trysac/u804-ue-perf-probe-toolset/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u804-ue-perf-probe-toolset/actions/workflows/ci.yml)

Pure core and Unreal adapter of an Unreal MCP toolset that records CSV Profiler captures, computes frame statistics against budgets and reports build size.

## Problem

Agents optimizing an Unreal Engine 5.8 game need repeatable performance measurements with a clear PASS/FAIL against a budget and a comparison with the previous run. Reading CSV Profiler output and `stat unit` by hand is slow and inconsistent. This package parses CSV Profiler captures, computes frame statistics, evaluates budgets, compares two captures with a seeded bootstrap and reports build size.

## Install in Unreal Engine (the MCP toolset)

1. Build the plugin: `uv run python tools/build_plugin.py` (or download the zip from a release). It
   creates `dist/PerfProbeToolset-<version>.zip`.
2. Unzip it into `<YourProject>/Plugins/` (you get `Plugins/PerfProbeToolset/`).
3. In the editor enable **Unreal MCP**, **All Toolsets** and **Perf Probe Toolset**, restart, and
   turn on *Editor Preferences > General > Model Context Protocol > Auto Start Server*.
4. Run `ModelContextProtocol.GenerateClientConfig ClaudeCode` in the console (writes `.mcp.json`),
   then start your agent from the project root. If the editor was already running, run
   `ModelContextProtocol.RefreshTools`.
5. The agent finds the toolset `PerfProbeTools` through `list_toolsets` and calls it with
   `call_tool`: `start_capture`, `capture_status`, `get_report`, `compare_reports`,
   `build_size_report` and `perf_report_md`. See [docs/AGENT_USAGE.md](docs/AGENT_USAGE.md) and the
   optional Claude Code skill in [skill/SKILL.md](skill/SKILL.md).

Requirements: Unreal Engine 5.8 with the experimental Unreal MCP and Toolset Registry plugins.
Python only, nothing to compile. Status: the logic, the MCP layer and the plugin shell are tested in
CI against a fake `unreal` module; they have not yet been verified inside Unreal. The in-editor
check is `tests/ue_smoke.py` (see [docs/TESTING.md](docs/TESTING.md)).

## Install as a Python library

```sh
pip install trysac-ue-perf-probe-toolset
# or
uv add trysac-ue-perf-probe-toolset
```

Import name: `ue_perf_probe_toolset`. Requires Python 3.10 or newer. No runtime dependencies: the runtime uses the standard library only.

## Usage

```python
from ue_perf_probe_toolset import PerfBudget, evaluate_budget, frame_stats, parse_csv_text

csv_text = "FrameTime\n10\n10\n60\n"
stats = frame_stats([f.frame_ms for f in parse_csv_text(csv_text).frames])
result = evaluate_budget(stats, PerfBudget(target_fps=60, max_hitches_per_min=2))
print(result.verdict, result.reasons)
```

Inside the Unreal editor Python environment, the adapter functions take the `unreal` module as their first argument, for example `start_capture(unreal, 30)`.

`ue_perf_probe_toolset.mcp` exposes the same six operations with flat, JSON-friendly parameters and a JSON string result (first key `summary`; errors come back as `{"summary": "error: ...", "error": {...}}` instead of raising). The budget is passed as `target_fps`, `min_fps`, `max_hitches_per_min` and `hitch_ms`; `build_size_report` defaults to a 1 GiB limit. The plugin's toolset class forwards to it. Capture jobs are kept in a module-level store, so they survive between calls but are lost if the package is reloaded; the CSV files stay in `Saved/Profiling/CSV/` and can be passed as `csv_path`.

## Public API

Core (pure, never imports `unreal`):

- `parse_csv_profile(path)` returns `ParsedProfile`. Raises `PerfError` with `csv_not_found`, `csv_unreadable` or `limit_exceeded`.
- `parse_csv_text(text)` accepts `str` or UTF-8 `bytes` and returns `ParsedProfile`. Problems such as missing, extra or duplicate columns, truncated rows and bad numbers become `ParseWarning` entries and never abort parsing.
- `frame_stats(...)` returns `FrameStats`. Raises `no_frames` for an empty input and `invalid_argument` for bad values. `fps_p1_low` and `fps_p5_low` are derived from the 99th and 95th percentile frame time.
- `PerfBudget(target_fps, min_fps, max_hitches_per_min, max_frame_ms_p95, max_frame_ms_p99)`. `None` disables a limit. `min_fps` is compared with `fps_p1_low`. `PerfBudget.from_mapping` rejects unknown keys.
- `evaluate_budget(stats, budget)` returns `BudgetResult` with `verdict` (`PASS` or `FAIL`), `checks` and `reasons`.

Adapter (each function takes `ue` first and never imports `unreal`):

- `start_capture(ue, duration_seconds=30.0, *, store=None)` runs `csvprofile start` and returns a `CaptureJob` at once. The stop is scheduled by a Slate post-tick callback. Raises `invalid_argument` (duration outside 1 to 3600 seconds) and `capture_in_progress`.
- `capture_status(ue, job_id)` returns the job state `running`, `finalizing` or `completed`. Raises `unknown_job`.
- `get_report(ue, job_id=None, csv_path=None, *, budget=None, warmup_seconds=0.0, hitch_threshold_ms=..., store=None)` returns `PerfReport`.
- `perf_report_md(...)` returns the same report rendered as Markdown.
- `compare_reports(ue, baseline_csv, candidate_csv, *, seed=1234, iterations=500, warmup_seconds=0.0)` returns `ComparisonResult`. The same seed gives the same result.
- `build_size_report(ue, build_dir, *, limit_bytes=None, cook_log=None)` returns a read-only `SizeReport`. Its `estimated_zip_bytes` is an estimate from fixed per-extension ratios, not a measured archive size.
- `to_dict(result)` converts any result dataclass to plain values.
- `JobStore(max_entries=64)` holds capture jobs in memory and evicts the oldest one beyond the limit.

Errors: `PerfError` has a `code` from `ERROR_CODES`: `invalid_argument`, `path_not_allowed`, `path_not_found`, `csv_not_found`, `csv_unreadable`, `unknown_job`, `capture_in_progress`, `capture_failed`, `no_frames`, `limit_exceeded`.

Limits and options:

- Capture duration is 1 to 3600 seconds. At most 64 jobs are kept by default.
- CSV files are read only below `Saved/Profiling/CSV`. Build folders and cook logs are read only below the project directory.
- The render profile name is read from `Saved/RenderProfiles/active_profile.json` when that file exists and is at most 65536 bytes. The name is cut to 100 characters. A missing or invalid file is ignored.
- Error messages are cut to 200 characters.
- Size reports warn above 90 percent of `limit_bytes` and again when the limit is exceeded.
- Size and row limits for CSV parsing are constants in `core/csvparse.py`.

Security limits are described in [docs/SECURITY.md](docs/SECURITY.md).

## Documentation

- [Agent usage](docs/AGENT_USAGE.md) and [skill](skill/SKILL.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Testing](docs/TESTING.md) and [security notes](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
