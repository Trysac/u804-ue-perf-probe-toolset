# Python plugin shell with flat parameters, JSON string results and a module-level job store

Status: accepted (pending verification in Unreal Engine 5.8)

## Context

The package must become an Unreal MCP toolset: a `unreal.ToolsetDefinition` subclass in a plugin's
`Content/Python/`, discovered by the Toolset Registry. The registry is experimental and its handling
of complex parameter and return types (such as a `PerfBudget` dataclass) is not documented in
detail. Tool calls run serially on the game thread, so a 30 second capture cannot block inside one
call, and the job started by one call must still be known to the next. Nothing can run in CI inside
Unreal.

## Decision

- Ship a Python-only plugin (`plugin/PerfProbeToolset/`) whose toolset module only forwards to a
  new `mcp.py` layer. All behavior stays in the package, so it is covered by CI.
- Tools take primitive parameters (str, int, float, bool). The budget is flattened into
  `target_fps`, `min_fps` (0 disables), `max_hitches_per_min` (negative disables, so 0 means "no
  hitches") and `hitch_ms`. Every tool returns a JSON string whose first key is `summary`; errors
  are returned as data, never raised to the agent.
- `start_capture` returns a job id at once; the stop runs from a Slate post-tick callback. Jobs are
  kept in `adapter.DEFAULT_STORE`, created at import time, and only one capture may run at a time.
- `tools/build_plugin.py` vendors the package into the plugin; no pip inside the editor.

## Consequences

The schema the agent sees is simple and certain to be supported, at the cost of the agent parsing
JSON from a string. Jobs are lost when the Python package is reloaded; the CSV files remain in
`Saved/Profiling/CSV/` and every report tool also accepts `csv_path`, so no measurement is lost. The
decorator order, the console commands, the CSV location and its column names are confirmed by the
manual steps in `docs/TESTING.md`.
