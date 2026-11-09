# Agent usage

Once the plugin is enabled, the Unreal MCP server lists the toolset `PerfProbeTools`. With the
default *tool search* mode the agent sees three meta-tools: `list_toolsets`, `describe_toolset` and
`call_tool`. Calls run one at a time on the editor's game thread: never issue them in parallel.
Every tool is short; a capture runs in the background and is followed with `capture_status`.

Every tool returns a JSON string. The first key is always `summary` (one line). Errors are data:
`{"summary": "error: ...", "error": {"code": "...", "message": "..."}}` with codes
`invalid_argument`, `capture_in_progress`, `capture_failed`, `unknown_job`, `csv_not_found`,
`csv_unreadable`, `no_frames`, `path_not_allowed`, `path_not_found`, `limit_exceeded` or
`unreal_error` (an unexpected engine API failure).

Status: these calls are tested in CI against a fake `unreal` module; they have not yet been verified
inside Unreal (see [TESTING.md](TESTING.md)).

## Typical perf pass

1. Start PIE on the test map, then `start_capture`.
2. Poll `capture_status` until `completed`.
3. `get_report` with the budget and `warmup_seconds: 1`.
4. `compare_reports` against the previous capture.
5. `perf_report_md` for `perf.md` or the dev log.

## start_capture

```json
{"toolset": "PerfProbeTools", "tool": "start_capture", "arguments": {"duration_seconds": 30}}
```

```json
{"summary": "capture capture-0001 started", "job_id": "capture-0001", "state": "running",
 "duration_seconds": 30.0, "csv_name": null}
```

Only one capture runs at a time; a second call returns `capture_in_progress`. The tool runs
`csvprofile start`; an editor tick callback runs `csvprofile stop` when the time is up.

## capture_status

```json
{"toolset": "PerfProbeTools", "tool": "capture_status", "arguments": {"job_id": "capture-0001"}}
```

```json
{"summary": "capture capture-0001 is completed", "job_id": "capture-0001", "state": "completed",
 "duration_seconds": 30.0, "csv_name": "Profile(20261112_101500).csv"}
```

`finalizing` means the capture was stopped but its CSV is not visible yet. Jobs are kept in memory
(the last 64). If the editor reloads the Python package the job ids are lost (`unknown_job`), but
the CSV files remain in `Saved/Profiling/CSV/`: pass `csv_path` to the report tools instead.

## get_report

```json
{"toolset": "PerfProbeTools", "tool": "get_report", "arguments": {
  "job_id": "capture-0001", "target_fps": 60, "min_fps": 45, "max_hitches_per_min": 2,
  "hitch_ms": 50, "warmup_seconds": 1}}
```

```json
{"summary": "Profile(20261112_101500).csv: 1740 frames, 58.3 fps mean, p99 24.10 ms, 3 hitches; budget FAIL",
 "source": "Profile(20261112_101500).csv",
 "stats": {"fps_mean": 58.3, "fps_p1_low": 41.5, "frame_ms_p95": 19.2, "hitches_per_min": 6.2, "...": "..."},
 "budget_result": {"verdict": "FAIL", "reasons": ["target_fps: fps_mean 58.30 is not >= 60", "..."], "...": "..."},
 "warnings": [], "render_profile": null}
```

Choose the CSV with `csv_path` (a name or path inside `Saved/Profiling/CSV/`), else `job_id`, else
the newest CSV. Budget parameters are flat: `target_fps` (checked against `fps_mean`) and `min_fps`
(against `fps_p1_low`) are disabled with `0`; `max_hitches_per_min` is disabled with a negative
value (the default) so that `0` means "no hitches allowed". With no limit set, `budget_result` is
`null`.

## compare_reports

```json
{"toolset": "PerfProbeTools", "tool": "compare_reports", "arguments": {
  "baseline_csv": "Profile(20261111_180000).csv", "candidate_csv": "Profile(20261112_101500).csv",
  "seed": 1234, "warmup_seconds": 1}}
```

```json
{"summary": "regression: 2 regressions, 0 improvements (500 bootstrap iterations, seed 1234)",
 "verdict": "regression",
 "metrics": [{"metric": "frame_ms_p95", "baseline": 16.9, "candidate": 19.2, "delta": 2.3,
              "delta_pct": 13.6, "ci_low": 1.1, "ci_high": 3.4, "direction": "regression"}, "..."]}
```

## perf_report_md

Same parameters as `get_report`. Returns `{"summary": ..., "markdown": "| metric | value | budget | verdict |\n..."}`.

## build_size_report

```json
{"toolset": "PerfProbeTools", "tool": "build_size_report", "arguments": {
  "build_dir": "Saved/StagedBuilds/Windows", "limit_bytes": 1073741824,
  "cook_log": "Saved/Logs/Cook.log"}}
```

```json
{"summary": "212 files, 734003200 bytes in 6 extensions", "total_bytes": 734003200,
 "breakdown": [{"extension": ".ucas", "size_bytes": 690000000, "file_count": 2}, "..."],
 "estimated_zip_bytes": 712000000, "limit_bytes": 1073741824, "usage_ratio": 0.68,
 "warnings": [], "largest_contributors": [{"name": "/Game/Maps/Main", "size_bytes": 120000000}]}
```

`build_dir` and `cook_log` must be inside the project directory. `limit_bytes` defaults to 1 GiB;
`0` disables the limit. `estimated_zip_bytes` is an estimate from fixed ratios, not a measurement.

## Semantics worth knowing

- Frame times are in milliseconds. `fps_mean` is `1000 / mean frame time`; `fps_p1_low` and
  `fps_p5_low` are `1000 /` the 99th and 95th percentile frame time (nearest rank).
- A frame is a hitch when it is slower than `hitch_ms` (default 50).
- A frame is excluded by warmup when it starts before `warmup_seconds`.
- The active render profile name is read from `Saved/RenderProfiles/active_profile.json` (u803)
  when it exists and shown as `render_profile` / in `notes`.
