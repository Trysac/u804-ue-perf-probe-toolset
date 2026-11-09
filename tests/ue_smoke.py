"""In-editor smoke test (NOT collected by pytest). Run inside Unreal Editor 5.8 with the plugin on.

Output Log > Cmd > Python:  py "<repo>/tests/ue_smoke.py"
It starts a 5 second CSV Profiler capture and returns at once: the editor keeps running. A Slate
post-tick callback polls the job and, when it is completed (or after a timeout), builds the report
and writes ``<Project>/Saved/Smoke/u804-ue-perf-probe-toolset.json`` with one entry per step.
Nothing sleeps on the game thread. It never deletes anything; the capture CSV stays in
``Saved/Profiling/CSV/``.
"""

import json
import time
import traceback
from pathlib import Path

import unreal

REPO = "u804-ue-perf-probe-toolset"
CAPTURE_SECONDS = 5.0
TIMEOUT_SECONDS = 60.0


def main() -> None:
    from ue_perf_probe_toolset import mcp

    out_dir = Path(unreal.Paths.project_saved_dir()) / "Smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    state = {"job_id": None, "elapsed": 0.0, "handle": None, "done": False}

    def step(name, fn):
        started = time.time()
        try:
            value = fn()
            parsed = json.loads(value) if isinstance(value, str) else value
            ok = not (isinstance(parsed, dict) and "error" in parsed)
            results.append({"step": name, "ok": ok, "result": parsed})
        except Exception:  # the smoke test records every failure instead of stopping
            results.append({"step": name, "ok": False, "error": traceback.format_exc()[-2000:]})
            parsed = None
        results[-1]["seconds"] = round(time.time() - started, 3)
        return parsed

    def finish():
        state["done"] = True
        if state["handle"] is not None:
            unreal.unregister_slate_post_tick_callback(state["handle"])
        report = {
            "repo": REPO,
            "engine": unreal.SystemLibrary.get_engine_version(),
            "passed": sum(r["ok"] for r in results),
            "total": len(results),
            "steps": results,
        }
        target = out_dir / f"{REPO}.json"
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        unreal.log(f"[smoke] {REPO}: {report['passed']}/{report['total']} ok -> {target}")

    def on_tick(delta_seconds):
        if state["done"]:
            return
        state["elapsed"] += delta_seconds
        try:
            status = json.loads(mcp.capture_status(unreal, state["job_id"]))
        except Exception:  # never let the callback raise every frame
            error = traceback.format_exc()[-2000:]
            results.append({"step": "capture_status", "ok": False, "error": error})
            finish()
            return
        if status.get("state") == "completed":
            job_id = state["job_id"]
            step("capture completed", lambda: json.dumps(status))
            step(
                "get_report",
                lambda: mcp.get_report(
                    unreal, job_id=job_id, target_fps=30, max_hitches_per_min=1000
                ),
            )
            step("perf_report_md", lambda: mcp.perf_report_md(unreal, job_id=job_id))
            step(
                "channels found",
                lambda: {
                    "channels": [
                        c["channel"]
                        for c in json.loads(mcp.get_report(unreal, job_id=job_id))["channels"]
                    ]
                },
            )
            step(
                "compare_reports (same csv)",
                lambda: mcp.compare_reports(
                    unreal, status["csv_name"], status["csv_name"], iterations=50
                ),
            )
            finish()
        elif state["elapsed"] > TIMEOUT_SECONDS:
            results.append({"step": "capture completed", "ok": False, "error": f"timeout {status}"})
            finish()

    step(
        "toolset module imports",
        lambda: {"module": __import__("perf_probe_toolset_mcp").__name__},
    )
    step(
        "api names",
        lambda: {
            name: hasattr(unreal, name)
            for name in (
                "register_slate_post_tick_callback",
                "unregister_slate_post_tick_callback",
                "SystemLibrary",
                "Paths",
            )
        },
    )
    step("build_size_report (Config)", lambda: mcp.build_size_report(unreal, "Config"))
    started = step("start_capture", lambda: mcp.start_capture(unreal, CAPTURE_SECONDS, "smoke"))
    step("second capture refused", lambda: _expect_error(mcp.start_capture(unreal, 5)))
    if started and "job_id" in started:
        state["job_id"] = started["job_id"]
        state["handle"] = unreal.register_slate_post_tick_callback(on_tick)
        unreal.log(f"[smoke] {REPO}: capture running, results in ~{CAPTURE_SECONDS:g} s")
    else:
        finish()


def _expect_error(raw):
    data = json.loads(raw)
    if data.get("error", {}).get("code") == "capture_in_progress":
        return {"summary": "refused as expected"}
    return {"error": data}


main()
