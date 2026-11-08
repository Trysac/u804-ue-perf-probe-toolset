# Pure core with a thin duck-typed Unreal adapter

Status: accepted (generated, pending human review)

## Context

The toolset must record CSV Profiler captures, compute frame statistics against budgets and report build sizes for Unreal Engine 5.8 agents. Unreal MCP tools run serially on the game thread, so long work must return a job id, and the code has to be testable without the engine.

## Decision

All logic lives in a pure core under core/ (csvparse, stats, budget, compare, sizes, report, markdown) that uses only the standard library and never imports unreal. A thin adapter takes the unreal module as its first argument and uses only SystemLibrary.execute_console_command, Paths and the slate post-tick callbacks, so tests substitute a fake. Captures are stopped by a tick callback instead of sleeping, and jobs live in a bounded in-memory store with oldest-first eviction. Columns are matched by regex on normalized names, percentiles use nearest rank, and the bootstrap uses random.Random(seed), thinning very long samples by a deterministic stride. Paths are confined to Saved/Profiling/CSV for CSVs and to the project directory for build folders.

## Consequences

The core is fully unit-testable and deterministic, and the adapter stays small. The real engine behaviour (console command output, tick delta semantics, CSV file naming and the render profile snapshot location) is unverified until the supervised session. The bootstrap interval of very long captures is computed on a thinned sample, and the estimated zip size is only a heuristic.
