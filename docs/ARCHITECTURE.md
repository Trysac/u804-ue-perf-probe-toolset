# Architecture

## Purpose

`trysac-ue-perf-probe-toolset` is a small Python library. It is the pure core and the Unreal adapter of an Unreal MCP toolset that records CSV Profiler captures, computes frame statistics against budgets and reports build size.

## Shape

```text
AI agent --MCP--> Unreal MCP server --> Toolset Registry
                                            |
   plugin/PerfProbeToolset/Content/Python/perf_probe_toolset_mcp.py  (PerfProbeTools)
                                            |  forwards with the real unreal module
                                            v
   ue_perf_probe_toolset.mcp       flat params in, JSON string out, errors as data
                                            v
   ue_perf_probe_toolset.adapter   functions that take the ue module as first argument
          |                 \
          v                  DEFAULT_STORE  module-level JobStore (survives between calls)
   core/  pure functions, no unreal import        errors.py  PerfError with a stable code
```

- **core/** contains `csvparse` (CSV parsing with column mapping by regular expression), `stats` (frame statistics and percentiles), `budget` (`PerfBudget` and `evaluate_budget`), `compare` (seeded bootstrap comparison), `sizes` (build size walk and cook log reading), `report` (`PerfReport` assembly) and `markdown` (Markdown rendering). Its `__init__.py` says that the submodules must be imported directly.
- **adapter.py** contains `start_capture`, `capture_status`, `get_report`, `compare_reports`, `build_size_report`, `perf_report_md` and `to_dict`, plus `JobStore`. Every adapter function receives `ue` as its first argument and never imports `unreal`. Tests can pass a fake module.
- **Public API** is the list in `__all__` of `src/ue_perf_probe_toolset/__init__.py`. The package root exports the adapter version of `build_size_report`. The core version is reachable only through `core.sizes`.

## Errors

All expected failures raise `PerfError`, which carries a `code` string from `ERROR_CODES` and a message of at most 200 characters. Unexpected exceptions from the editor console are wrapped in `capture_failed` where the adapter starts or schedules a capture.

## Capture flow

1. `start_capture` checks the duration, refuses to start when a job is still running, records the CSV files that already exist, and runs `csvprofile start` through `execute_console_command`.
2. It registers a Slate post-tick callback. The callback adds the frame delta to the job's elapsed time and, once the duration is reached, runs `csvprofile stop` and unregisters itself.
3. `capture_status` finds a new CSV file that was not present at start. The job becomes `completed` when that file exists.

Nothing sleeps. Time is driven only by the editor tick.

## Side effects

The core has no I/O. The adapter reads CSV files, reads one optional render profile snapshot, walks build folders read-only, and issues two fixed console commands. Nothing is written to disk and no network is used (the CSV itself is written by the engine's profiler).

## Unreal integration

- `plugin/PerfProbeToolset/PerfProbeToolset.uplugin` declares a Python-only editor plugin that
  depends on `PythonScriptPlugin` and `ToolsetRegistry`.
- `plugin/PerfProbeToolset/Content/Python/perf_probe_toolset_mcp.py` defines
  `PerfProbeTools(unreal.ToolsetDefinition)`; each tool is a static method marked with
  `@toolset_registry.tool_call`, with Google-style docstrings that the registry turns into the tool
  schema. It contains no logic: it forwards to `mcp.py`.
- `mcp.py` takes primitive parameters only (the budget is flat: `target_fps`, `min_fps`,
  `max_hitches_per_min`, `hitch_ms`) and returns a JSON string with `summary` first; errors are
  returned as data.
- Tool calls run serially on the game thread, so `start_capture` returns a job id at once and the
  stop is driven by a Slate post-tick callback. Jobs live in `adapter.DEFAULT_STORE`, created when
  the module is imported, so they survive between MCP calls; a reload of the package loses them,
  while the CSV files stay in `Saved/Profiling/CSV/` and can be passed as `csv_path`.
- `tools/build_plugin.py` copies the plugin and vendors the package into `Content/Python/` so the
  editor's Python can import it without pip.
- The real-engine check is `tests/ue_smoke.py` plus the manual steps in `docs/TESTING.md`. The
  plugin is tested in CI against fakes only and has not yet been verified inside Unreal.

## Decisions

See `docs/decisions/` (0002: pure core with a thin duck-typed adapter; 0003: Python plugin shell
with flat parameters and JSON string results).
