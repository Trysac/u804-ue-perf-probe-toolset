"""Thin adapter between an Unreal Python module (``ue``) and the pure core.

Every function takes the ``unreal`` module (or a fake) as first argument and never imports
it. CSV files are only read below ``Saved/Profiling/CSV``; build folders only below the
project directory. Nothing here sleeps: a capture is stopped by a slate tick callback.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import math
import re
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import sizes as core_sizes
from .core.budget import PerfBudget
from .core.channels import channel_samples
from .core.compare import ComparisonResult, compare_profiles
from .core.csvparse import parse_csv_profile
from .core.markdown import render_perf_markdown
from .core.report import PerfReport, build_report
from .core.stats import DEFAULT_HITCH_THRESHOLD_MS
from .errors import PerfError

DEFAULT_MAX_JOBS = 64
MAX_CAPTURE_SECONDS = 3600.0
MAX_PROFILE_FILE_BYTES = 65536
MAX_PROFILE_NAME = 100
MAX_LABEL = 64
_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9 _.:#()/-]")


@dataclass(frozen=True)
class CaptureJob:
    """State of a capture job: ``running``, ``finalizing`` (CSV not seen) or ``completed``."""

    job_id: str
    state: str
    duration_seconds: float
    csv_name: str | None
    summary: str
    label: str = ""


@dataclass
class _Job:
    job_id: str
    duration_seconds: float
    csv_before: frozenset[str]
    state: str = "running"
    elapsed: float = 0.0
    csv_name: str | None = None
    label: str = ""


class JobStore:
    """In-memory job registry that evicts the oldest job beyond ``max_entries``."""

    def __init__(self, max_entries: int = DEFAULT_MAX_JOBS) -> None:
        if max_entries < 1:
            raise PerfError("invalid_argument", "max_entries must be >= 1")
        self._max = max_entries
        self._jobs: OrderedDict[str, _Job] = OrderedDict()
        self._counter = 0
        self._lock = threading.Lock()

    def create(self, duration_seconds: float, csv_before: frozenset[str], label: str = "") -> _Job:
        """Register a new running job and return it."""
        with self._lock:
            self._counter += 1
            job = _Job(f"capture-{self._counter:04d}", duration_seconds, csv_before, label=label)
            self._jobs[job.job_id] = job
            while len(self._jobs) > self._max:
                self._jobs.popitem(last=False)
            return job

    def get(self, job_id: str) -> _Job:
        """Return a job or raise ``PerfError`` with code ``unknown_job``."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise PerfError("unknown_job", f"unknown job id: {str(job_id)[:60]!r}")
        return job

    def label_for(self, csv_name: str) -> str:
        """Label of the newest known job whose capture produced ``csv_name`` ("" if none)."""
        with self._lock:
            for job in reversed(self._jobs.values()):
                if job.csv_name == csv_name:
                    return job.label
        return ""

    def has_running(self) -> bool:
        """Whether a capture is still running."""
        with self._lock:
            return any(job.state == "running" for job in self._jobs.values())


DEFAULT_STORE = JobStore()


def _project_dir(ue: Any) -> Path:
    return Path(str(ue.Paths.project_dir()))


def _saved_dir(ue: Any) -> Path:
    return Path(str(ue.Paths.project_saved_dir()))


def _csv_dir(ue: Any) -> Path:
    return _saved_dir(ue) / "Profiling" / "CSV"


def _exec(ue: Any, command: str) -> None:
    ue.SystemLibrary.execute_console_command(None, command)


def _csv_files(csv_dir: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    try:
        for item in csv_dir.iterdir():
            if item.suffix.lower() == ".csv" and item.is_file():
                found.append((item.stat().st_mtime_ns, item.name))
    except OSError:
        return []
    return found


def _newest_csv(csv_dir: Path, exclude: frozenset[str] = frozenset()) -> str | None:
    files = [item for item in _csv_files(csv_dir) if item[1] not in exclude]
    if not files:
        return None
    return max(files)[1]


def _confine(base: Path, raw: str, suffix: str | None) -> Path:
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = base / candidate
        resolved = candidate.resolve()
        root = base.resolve()
    except (OSError, RuntimeError, ValueError):
        raise PerfError("path_not_allowed", "path could not be resolved") from None
    if not resolved.is_relative_to(root):
        raise PerfError("path_not_allowed", "path is outside the allowed folder")
    if suffix is not None and resolved.suffix.lower() != suffix:
        raise PerfError("path_not_allowed", f"only {suffix} files are allowed here")
    return resolved


def _render_profile(ue: Any) -> str | None:
    """Name of the active render profile, read from the u803 snapshot when it exists."""
    path = _saved_dir(ue) / "RenderProfiles" / "active_profile.json"
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_PROFILE_FILE_BYTES + 1)
        if len(data) > MAX_PROFILE_FILE_BYTES:
            return None
        parsed = json.loads(data)
    except (OSError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    name = parsed.get("name")
    if not isinstance(name, str) or not name:
        return None
    return name[:MAX_PROFILE_NAME]


def sanitize_label(label: str) -> str:
    """Make a capture label safe to show: allowed characters only, one line, at most 64 chars.

    Letters, digits, space and ``_ . : # ( ) / -`` are kept; any other character becomes ``_``.

    Raises:
        PerfError: ``invalid_argument`` when ``label`` is not a string.
    """
    if not isinstance(label, str):
        raise PerfError("invalid_argument", "label must be a string")
    collapsed = " ".join(label.split())
    return _LABEL_UNSAFE.sub("_", collapsed)[:MAX_LABEL].strip()


def _notes(ue: Any) -> tuple[str, ...]:
    name = _render_profile(ue)
    return (f"render profile: {name}",) if name else ()


def start_capture(
    ue: Any,
    duration_seconds: float = 30.0,
    *,
    label: str = "",
    store: JobStore | None = None,
) -> CaptureJob:
    """Start ``csvprofile start`` and schedule the stop on an editor tick callback.

    Returns immediately with a job id; use ``capture_status`` to follow it. ``label`` is
    sanitized (see ``sanitize_label``), kept with the job and shown in its reports; it never
    reaches the console.

    Raises:
        PerfError: ``invalid_argument`` for a duration outside 1..3600 seconds,
            ``capture_in_progress`` when another capture is still running.
    """
    active = DEFAULT_STORE if store is None else store
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, int | float)
        or not math.isfinite(duration_seconds)
        or not 1.0 <= duration_seconds <= MAX_CAPTURE_SECONDS
    ):
        raise PerfError(
            "invalid_argument", f"duration_seconds must be between 1 and {MAX_CAPTURE_SECONDS:g}"
        )
    clean_label = sanitize_label(label)
    if active.has_running():
        raise PerfError("capture_in_progress", "another capture is still running")
    before = frozenset(name for _, name in _csv_files(_csv_dir(ue)))
    job = active.create(float(duration_seconds), before, clean_label)
    try:
        _exec(ue, "csvprofile start")
    except Exception as exc:
        job.state = "failed"
        if isinstance(exc, PerfError):
            raise
        raise PerfError("capture_failed", "could not start csvprofile") from exc
    handles: list[Any] = []

    def on_tick(delta_seconds: float) -> None:
        job.elapsed += delta_seconds
        if job.state == "running" and job.elapsed >= job.duration_seconds:
            try:
                _exec(ue, "csvprofile stop")
            finally:
                job.state = "stopped"
                if handles:
                    ue.unregister_slate_post_tick_callback(handles[0])

    try:
        handles.append(ue.register_slate_post_tick_callback(on_tick))
    except Exception as exc:
        job.state = "failed"
        with contextlib.suppress(Exception):
            _exec(ue, "csvprofile stop")
        raise PerfError("capture_failed", "could not schedule capture stop") from exc
    suffix = f" ({clean_label})" if clean_label else ""
    return CaptureJob(
        job.job_id,
        "running",
        job.duration_seconds,
        None,
        f"capture {job.job_id}{suffix} started",
        clean_label,
    )


def capture_status(ue: Any, job_id: str, *, store: JobStore | None = None) -> CaptureJob:
    """Report the state of a capture job.

    Raises:
        PerfError: ``unknown_job`` for an unknown or evicted job id.
    """
    active = DEFAULT_STORE if store is None else store
    job = active.get(job_id)
    if job.state == "stopped":
        found = _newest_csv(_csv_dir(ue), job.csv_before)
        if found is not None:
            job.state = "completed"
            job.csv_name = found
    state = "finalizing" if job.state == "stopped" else job.state
    suffix = f" ({job.label})" if job.label else ""
    summary = f"capture {job.job_id}{suffix} is {state}"
    return CaptureJob(job.job_id, state, job.duration_seconds, job.csv_name, summary, job.label)


def _label_of(path: Path, store: JobStore | None) -> str:
    return (DEFAULT_STORE if store is None else store).label_for(path.name)


def _resolve_csv(ue: Any, job_id: str | None, csv_path: str | None, store: JobStore | None) -> Path:
    csv_dir = _csv_dir(ue)
    if csv_path is not None:
        return _confine(csv_dir, csv_path, ".csv")
    if job_id is not None:
        status = capture_status(ue, job_id, store=store)
        if status.csv_name is None:
            raise PerfError("csv_not_found", f"capture {job_id[:60]} has no CSV yet")
        return csv_dir / status.csv_name
    newest = _newest_csv(csv_dir)
    if newest is None:
        raise PerfError("csv_not_found", "no CSV captures found under Saved/Profiling/CSV")
    return csv_dir / newest


def get_report(
    ue: Any,
    job_id: str | None = None,
    csv_path: str | None = None,
    *,
    budget: PerfBudget | Mapping[str, object] | None = None,
    warmup_seconds: float = 0.0,
    hitch_threshold_ms: float = DEFAULT_HITCH_THRESHOLD_MS,
    store: JobStore | None = None,
) -> PerfReport:
    """Build the report of a capture.

    The CSV is chosen by ``csv_path`` (a name or path inside ``Saved/Profiling/CSV``), else by
    ``job_id``, else the newest CSV in that folder. The label of the job that produced the CSV
    is attached when that job is still known.

    Raises:
        PerfError: ``path_not_allowed``, ``csv_not_found``, ``csv_unreadable``,
            ``unknown_job``, ``invalid_argument`` or ``no_frames``.
    """
    path = _resolve_csv(ue, job_id, csv_path, store)
    parsed = parse_csv_profile(path)
    if budget is None or isinstance(budget, PerfBudget):
        checked = budget
    else:
        checked = PerfBudget.from_mapping(budget)
    return build_report(
        path.name,
        parsed,
        warmup_seconds=warmup_seconds,
        hitch_threshold_ms=hitch_threshold_ms,
        budget=checked,
        render_profile=_render_profile(ue),
        label=_label_of(path, store),
    )


def _samples(path: Path, warmup_seconds: float) -> dict[str, list[float]]:
    return channel_samples(parse_csv_profile(path).frames, warmup_seconds)


def compare_reports(
    ue: Any,
    baseline_csv: str,
    candidate_csv: str,
    *,
    seed: int = 1234,
    iterations: int = 500,
    warmup_seconds: float = 0.0,
    store: JobStore | None = None,
) -> ComparisonResult:
    """Compare two captures with a seeded bootstrap (same seed, same result).

    Frame time and every game/render (draw)/GPU/memory column present in both captures are
    compared (see ``compare_profiles``); labels of known jobs are added to ``notes``.

    Raises:
        PerfError: ``path_not_allowed``, ``csv_not_found``, ``csv_unreadable``,
            ``invalid_argument`` or ``no_frames``.
    """
    csv_dir = _csv_dir(ue)
    base_path = _confine(csv_dir, baseline_csv, ".csv")
    cand_path = _confine(csv_dir, candidate_csv, ".csv")
    baseline = _samples(base_path, warmup_seconds)
    candidate = _samples(cand_path, warmup_seconds)
    result = compare_profiles(baseline, candidate, seed=seed, iterations=iterations)
    labels = tuple(
        f"{role} label: {label}"
        for role, label in (
            ("baseline", _label_of(base_path, store)),
            ("candidate", _label_of(cand_path, store)),
        )
        if label
    )
    return dataclasses.replace(result, notes=(*result.notes, *labels, *_notes(ue)))


def build_size_report(
    ue: Any,
    build_dir: str,
    *,
    limit_bytes: int | None = None,
    cook_log: str | None = None,
) -> core_sizes.SizeReport:
    """Report the size of a build folder below the project directory (read-only).

    Raises:
        PerfError: ``path_not_allowed`` outside the project, ``path_not_found``,
            ``invalid_argument`` or ``limit_exceeded``.
    """
    project = _project_dir(ue)
    root = _confine(project, build_dir, None)
    log = _confine(project, cook_log, None) if cook_log is not None else None
    report = core_sizes.build_size_report(root, limit_bytes=limit_bytes, cook_log=log)
    return dataclasses.replace(report, notes=_notes(ue))


def perf_report_md(
    ue: Any,
    job_id: str | None = None,
    csv_path: str | None = None,
    *,
    budget: PerfBudget | Mapping[str, object] | None = None,
    warmup_seconds: float = 0.0,
    hitch_threshold_ms: float = DEFAULT_HITCH_THRESHOLD_MS,
    store: JobStore | None = None,
) -> str:
    """Return ``get_report`` rendered as Markdown (see ``render_perf_markdown``)."""
    report = get_report(
        ue,
        job_id,
        csv_path,
        budget=budget,
        warmup_seconds=warmup_seconds,
        hitch_threshold_ms=hitch_threshold_ms,
        store=store,
    )
    return render_perf_markdown(report)


def to_dict(result: Any) -> dict[str, Any]:
    """Convert any result dataclass into plain dicts, lists and scalars for tool output.

    Raises:
        PerfError: ``invalid_argument`` when ``result`` is not a dataclass instance.
    """
    if not dataclasses.is_dataclass(result) or isinstance(result, type):
        raise PerfError("invalid_argument", "to_dict expects a dataclass instance")
    return dataclasses.asdict(result)
