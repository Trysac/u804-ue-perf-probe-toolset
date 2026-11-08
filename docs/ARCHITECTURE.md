# Architecture

## Purpose

`trysac-ue-perf-probe-toolset` is a small Python library. It is the pure core and the Unreal adapter of an Unreal MCP toolset that records CSV Profiler captures, computes frame statistics against budgets and reports build size.

## Shape

```text
caller code --> ue_perf_probe_toolset (public API exported in __init__.py)
                    |
                    +-- core/        pure functions, no unreal import
                    +-- adapter.py   functions that take the ue module as first argument
                    +-- errors.py    PerfError with a stable code
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

The core has no I/O. The adapter reads CSV files, reads one optional render profile snapshot, walks build folders read-only, and issues two fixed console commands. Nothing is written to disk and no network is used.

## Decisions

No architecture decision records are included in this repository snapshot.
