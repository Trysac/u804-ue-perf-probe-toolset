# Testing

## Running

```sh
uv run python scripts/check.py               # every gate (lint, format, types, tests, docs...)
uv run pytest --cov=ue_perf_probe_toolset    # tests with branch coverage report
uv run python tools/build_plugin.py          # build the Unreal plugin zip into dist/
```

## Policy

- Coverage target for `src/ue_perf_probe_toolset` is 85 % (branch coverage).
- Tests call the public API and assert return values, `PerfError` codes, the JSON returned by the
  MCP layer and the console commands and tick callbacks recorded on the fake `unreal` module.
- Deterministic: no network, no wall clock (the fake editor tick is driven by hand and `time.sleep`
  is forbidden in the capture tests), no dependence on test order.

## Tests in CI (no Unreal needed)

| File | What it covers |
|---|---|
| `tests/test_csvparse.py` | Parser: columns mapped by pattern, missing/extra/duplicate columns, truncated and malformed rows, limits; Hypothesis: only `PerfError` is ever raised. |
| `tests/test_stats.py` | Frame statistics, percentiles, warmup, hitches; Hypothesis: matches a naive reference. |
| `tests/test_budget.py`, `tests/test_compare.py` | Budget verdicts; seeded bootstrap is reproducible. |
| `tests/test_channels.py` | Game/render (draw)/GPU/memory/streaming column statistics with and without those columns (omitted with a note), Hypothesis: matches a naive reference; per-column comparison with the same seed (memory does not decide the verdict); Markdown channel table and label; the synthetic UE 5.8-shaped fixture parses. |
| `tests/test_sizes.py`, `tests/test_markdown.py` | Build size sums exact bytes, warnings, cook log; Markdown against `tests/golden/perf.md`. |
| `tests/test_adapter.py` | Adapter against `tests/fakes/unreal.py`: `csvprofile start/stop`, stop scheduled by a tick callback, job states, one capture at a time, path confinement, capture label sanitized and carried into reports and comparison notes. |
| `tests/test_mcp.py` | MCP layer: a capture followed across separate calls, flat budget parameters, errors returned as data (`capture_in_progress`, `capture_failed`, `unreal_error`...), report by `csv_path` after the job store is lost, 1 GiB default size limit. |
| `tests/test_plugin_shell.py` | Loads `plugin/.../Content/Python/perf_probe_toolset_mcp.py` with a fake `unreal` and a fake `toolset_registry`: every MCP function is a documented `tool_call` static method with primitive parameters returning `str`, defaults match the MCP layer, and each forwards correctly. |
| `tests/test_build_plugin.py` | The plugin zip contains the `.uplugin`, the toolset module and the vendored package; the `.uplugin` depends on `PythonScriptPlugin` and `ToolsetRegistry` and its version matches the package. |
| `tests/test_errors.py`, `tests/test_ue_perf_probe_toolset.py` | Error type, version and exports. |

The CSV files in `tests/data/` are synthetic. `capture_ok.csv` and `capture_shuffled.csv` are
written by hand. `synthetic_ue58_capture.csv` is generated (fixed seed) to look like a UE 5.8 CSV
Profiler export: typical columns (`EventCount`, `FrameTime`, `GameThreadTime`, `RenderThreadTime`,
`RHIThreadTime`, `GPUTime`, `PhysicalUsedMB`, `TextureStreaming/StreamingPool`, ...), an `events`
column, shader-compile spikes in the first frames, one hitch, the header repeated at the end and a
`[HasHeaderRowAtEnd]` metadata trailer with anonymized values. Its column names and layout are
assumptions from the documentation, not taken from a real file.

**A REAL capture is still missing.** After running the in-editor check (step 8 below), an
anonymized real UE 5.8 CSV must be added to `tests/data/` with a parsing test; until then no test
proves that the parser reads a real export.

## Assumptions to confirm in Unreal Engine 5.8

The adapter was written against the documentation and checked only against the fake module. These
are the points the in-editor check must confirm:

- `unreal.SystemLibrary.execute_console_command(None, "csvprofile start")` and `"csvprofile stop"`
  start and stop the CSV Profiler from editor Python (a `None` world context is accepted), both in
  the editor and during PIE.
- `unreal.register_slate_post_tick_callback(fn)` calls `fn(delta_seconds)` every frame and
  `unreal.unregister_slate_post_tick_callback(handle)` removes it.
- `unreal.Paths.project_saved_dir()` and `unreal.Paths.project_dir()` return the expected folders.
- The CSV is written to `<Project>/Saved/Profiling/CSV/` as a plain `.csv` file (not compressed or
  binary `.csv.bin`), shortly after `csvprofile stop`.
- Column names: `FrameTime`, `GameThreadTime`, `RenderThreadTime` and `GPUTime` (matched by pattern;
  note which names UE 5.8 really writes, and whether GPU timing needs `-csvGpuStats`). Rows that
  start with `[` (metadata) are skipped; a header repeated at the end of the file only produces
  `bad_value` warnings.
- Memory and streaming columns are matched as `PhysicalUsedMB` (pattern
  `(memory)physicalused(mb)`) and `TextureStreaming/StreamingPool` (pattern
  `(texturestreaming)(streamingpool|texturepool)(mb)`). Record the exact names UE 5.8 writes (they
  may need `-csvStats`/categories enabled) and adjust `COLUMN_PATTERNS` in `core/csvparse.py`.
- The trailer: a repeated header row and a metadata row starting with `[HasHeaderRowAtEnd]`.

## In-editor check (manual, Unreal Engine 5.8)

CI cannot run Unreal, so these steps are the acceptance test for the real engine. Never mark the
plugin as verified in Unreal without running them.

1. Install the plugin (README, "Install in Unreal Engine") in a blank UE 5.8 project.
2. Compare the decorator order in `perf_probe_toolset_mcp.py` (`@staticmethod` above
   `@toolset_registry.tool_call`) with the engine's own example,
   `Engine/Plugins/Experimental/ToolsetRegistry/Content/Python/toolset_registry/toolsets/core/actor.py`,
   and match it if it differs.
3. Enable Python *Developer Mode* (Editor Preferences > Plugins > Python), restart, and check in
   `Intermediate/PythonStub/unreal.py` that `SystemLibrary.execute_console_command`,
   `register_slate_post_tick_callback`, `unregister_slate_post_tick_callback`,
   `Paths.project_saved_dir`, `Paths.project_dir` and `ToolsetDefinition` exist.
4. Run `py "<repo>/tests/ue_smoke.py"` in the Output Log (Python). It returns at once and the
   editor stays responsive during the 5 second capture. Then open
   `Saved/Smoke/u804-ue-perf-probe-toolset.json`: every step must have `"ok": true`.
5. From the agent: `list_toolsets` shows `PerfProbeTools`; `describe_toolset` lists six tools with
   their parameter descriptions.
6. With a test map in PIE: `start_capture` for 30 s, keep moving the camera (the editor must not
   freeze), poll `capture_status` until `completed`, then `get_report` with a budget and
   `perf_report_md`. Check every assumption listed above against the produced CSV.
7. Acceptance against `stat unit`: during the same 30 s run `stat unit` on screen and note its
   Frame, Game, Draw and GPU values by hand; the report's mean frame time must be within 1 % of the
   noted Frame value, and the `game_ms`, `render_ms` and `gpu_ms` means must match Game, Draw and GPU. Run `build_size_report` on a packaged build and compare `total_bytes` with the
   folder size reported by the operating system (it must match exactly).
8. Copy one anonymized real capture into `tests/data/` with a test. Record the date, engine
   version, smoke result and the `stat unit` comparison in `docs/PROJECT.md`.

## Not covered

Unreal Insights traces, per draw call analysis, memory columns other than physical memory used and
the texture streaming pool, and behavior on engine versions other than 5.8.
