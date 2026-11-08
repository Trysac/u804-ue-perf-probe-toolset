# Agent usage

This document shows how an agent is expected to drive the toolset through `call_tool`. The
Unreal plugin that exposes these functions as tools (the `ToolsetDefinition` class, `.uplugin`
and `Content/Python/`) is built in a later supervised session. The examples below describe the
intended calls; the Python functions behind them are tested here only against a fake `unreal`
module, never inside the editor.

## Typical flow

1. Start a capture. The call returns a job id immediately and never blocks the game thread:

   ```
   call_tool("start_capture", {"duration_seconds": 30})
   -> {"job_id": "capture-0001", "state": "running", ...}
   ```

2. Poll the job until `state` is `completed` (`finalizing` means the capture was stopped but
   its CSV is not visible yet):

   ```
   call_tool("capture_status", {"job_id": "capture-0001"})
   -> {"state": "completed", "csv_name": "Profile(20240101_120000).csv", ...}
   ```

3. Get the report with a budget and a warmup. The first second is excluded from every
   statistic:

   ```
   call_tool("get_report", {
       "job_id": "capture-0001",
       "budget": {"target_fps": 60, "min_fps": 45, "max_hitches_per_min": 2},
       "warmup_seconds": 1
   })
   -> {"budget_result": {"verdict": "FAIL", "reasons": ["max_hitches_per_min: ..."]}, ...}
   ```

4. Compare with a previous run (same seed, same answer):

   ```
   call_tool("compare_reports", {
       "baseline_csv": "before.csv", "candidate_csv": "after.csv", "seed": 1234
   })
   ```

5. Render a Markdown table for a pull request or a chat message:

   ```
   call_tool("perf_report_md", {"csv_path": "after.csv", "budget": {"target_fps": 60}})
   ```

6. Check the size of a build folder under the project directory:

   ```
   call_tool("build_size_report", {"build_dir": "Saved/StagedBuilds", "limit_bytes": 4000000000})
   ```

## Semantics worth knowing

- Frame times are in milliseconds. `fps_mean` is `1000 / mean frame time`; `fps_p1_low` and
  `fps_p5_low` are `1000 /` the 99th and 95th percentile frame time (nearest rank).
- A frame is a hitch when it is slower than `hitch_threshold_ms` (default 50).
- A frame is excluded by warmup when it starts before `warmup_seconds`; a frame starts at the
  sum of the frame times before it.
- `target_fps` is checked against `fps_mean` and `min_fps` against `fps_p1_low`.
- `estimated_zip_bytes` is an estimate from fixed per-extension ratios, not a measured archive.
- The cook log reader is best effort: it looks for a package path (starting with `/` or `../`)
  followed on the same line by a size such as `1234 bytes` or `1234 B`.
- The active render profile note is read from `Saved/RenderProfiles/active_profile.json` (a JSON
  object with a `name` key) when it exists. This location is an assumption about the u803
  snapshot and must be checked in the supervised session.
- Paths: CSVs are only read below `Saved/Profiling/CSV`, build folders and cook logs only below
  the project directory; anything else is rejected with `path_not_allowed`.

## Errors

Every failure is a `PerfError` with a stable `code`: `csv_not_found`, `csv_unreadable`,
`unknown_job`, `path_not_allowed`, `path_not_found`, `invalid_argument`, `limit_exceeded`,
`no_frames` and `capture_in_progress`. Use `to_dict(result)` to turn any result dataclass into
plain JSON-friendly data.
