---
name: ue-perf-probe
description: Measure Unreal Engine 5.8 game performance repeatably through the PerfProbeTools MCP toolset — non-blocking CSV Profiler captures, fps/frame time/hitch statistics with a PASS/FAIL budget verdict, seeded comparison with a previous capture, Markdown table for perf.md, and build size against a limit. Use for any perf pass, regression check or "is it fast enough" question.
---
# Performance probe (Unreal MCP toolset `PerfProbeTools`)

Requires the Perf Probe Toolset plugin enabled and the Unreal MCP server connected.

1. **Capture:** start PIE on the map to measure, then `call_tool` → `PerfProbeTools.start_capture`
   with `duration_seconds` (30 is the default). It returns `job_id` at once.
2. **Wait:** poll `capture_status` every few seconds (other calls are fine meanwhile) until `state`
   is `completed`. `finalizing` means stopped but the CSV is not written yet.
3. **Report:** `get_report` with `job_id`, the project budget as flat parameters (`target_fps`,
   `min_fps`, `max_hitches_per_min`, `hitch_ms`) and `warmup_seconds: 1` to drop shader-compile
   spikes. Read `budget_result.verdict` and `reasons`.
4. **Compare:** `compare_reports` with the previous capture as `baseline_csv` and the new one as
   `candidate_csv`; keep the default `seed` so the answer is reproducible.
5. **Record:** `perf_report_md` and paste `markdown` into `perf.md` or the dev log.
6. **Build:** after packaging, `build_size_report` on the build folder (under the project) with the
   size limit in `limit_bytes` (default 1 GiB).

Rules: one MCP call at a time; one capture at a time (`capture_in_progress` otherwise); if the editor
reloaded Python, job ids are gone, so pass `csv_path` (the CSV stays in `Saved/Profiling/CSV/`);
never claim a perf target is met without a report; if a result has `error`, read `error.code` and fix
the input instead of retrying blindly.
