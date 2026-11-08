"""Tolerant parser for CSV Profiler captures. Pure: never imports ``unreal``."""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path

from ..errors import PerfError

DEFAULT_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_ROWS = 2_000_000
MAX_WARNINGS = 100
_CLIP = 60

# Column names change between engine versions, so columns are matched by pattern on the
# lower-cased name with every non-alphanumeric character removed.
COLUMN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("frame_ms", re.compile(r"^frametime(ms)?$")),
    ("game_ms", re.compile(r"^(gamethreadtime|gamethread)(ms)?$")),
    ("render_ms", re.compile(r"^(renderthreadtime|renderthread)(ms)?$")),
    ("gpu_ms", re.compile(r"^(gputime|gpu)(ms)?$")),
)
_OPTIONAL_FIELDS = ("game_ms", "render_ms", "gpu_ms")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True)
class ParseWarning:
    """One problem found while parsing; parsing continues after it."""

    code: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class Frame:
    """One captured frame. Times are in milliseconds; ``start_ms`` is the cumulative offset."""

    index: int
    start_ms: float
    frame_ms: float
    game_ms: float | None
    render_ms: float | None
    gpu_ms: float | None


@dataclass(frozen=True)
class ParsedProfile:
    """Result of parsing a capture."""

    frames: tuple[Frame, ...]
    warnings: tuple[ParseWarning, ...]
    columns: tuple[tuple[str, str], ...]
    summary: str


class _WarningSink:
    """Collects warnings up to ``MAX_WARNINGS`` and counts the rest."""

    def __init__(self) -> None:
        self.items: list[ParseWarning] = []
        self.suppressed = 0

    def add(self, code: str, message: str, line: int | None = None) -> None:
        if len(self.items) < MAX_WARNINGS:
            self.items.append(ParseWarning(code, message, line))
        else:
            self.suppressed += 1

    def freeze(self) -> tuple[ParseWarning, ...]:
        if self.suppressed:
            note = ParseWarning(
                "warnings_truncated", f"{self.suppressed} further warnings suppressed"
            )
            return (*self.items, note)
        return tuple(self.items)


def _clip(text: str) -> str:
    return text[:_CLIP]


def _field_for(name: str) -> str | None:
    normalized = _NON_ALNUM.sub("", name.lower())
    for field, pattern in COLUMN_PATTERNS:
        if pattern.match(normalized):
            return field
    return None


def _to_float(cell: str) -> float | None:
    try:
        value = float(cell.strip())
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _read_rows(text: str, max_rows: int) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    reader = csv.reader(io.StringIO(text))
    try:
        for row in reader:
            if all(not cell.strip() for cell in row):
                continue
            if row[0].lstrip().startswith("["):
                continue
            rows.append((reader.line_num, row))
            if len(rows) > max_rows + 1:
                raise PerfError("limit_exceeded", f"CSV has more than {max_rows} data rows")
    except csv.Error:
        raise PerfError("csv_unreadable", "CSV structure is malformed") from None
    return rows


def parse_csv_text(
    text: str | bytes,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> ParsedProfile:
    """Parse CSV Profiler text (or UTF-8 bytes) into frames and warnings.

    The first non-blank row is the header; rows starting with ``[`` (profiler metadata) and
    blank rows are skipped. Problems (missing, extra or duplicate columns, truncated or
    malformed rows, bad numbers) produce one warning each and never abort parsing.

    Raises:
        PerfError: ``limit_exceeded`` above the size or row limits, ``csv_unreadable`` when
            there is no header, no frame time column, invalid UTF-8 or broken CSV structure.
    """
    if isinstance(text, bytes):
        if len(text) > max_bytes:
            raise PerfError("limit_exceeded", f"CSV is larger than {max_bytes} bytes")
        try:
            text = text.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise PerfError("csv_unreadable", "CSV is not valid UTF-8") from None
    elif len(text.encode("utf-8", "replace")) > max_bytes:
        raise PerfError("limit_exceeded", f"CSV is larger than {max_bytes} bytes")
    text = text.removeprefix("\ufeff")

    rows = _read_rows(text, max_rows)
    if not rows:
        raise PerfError("csv_unreadable", "CSV has no header row")
    sink = _WarningSink()
    header_line, raw_header = rows[0]
    header = [cell.strip() for cell in raw_header]
    mapping: dict[str, int] = {}
    for position, name in enumerate(header):
        field = _field_for(name)
        if field is None:
            sink.add("extra_column", f"unrecognized column {_clip(name)!r} ignored", header_line)
        elif field in mapping:
            sink.add("duplicate_column", f"duplicate column {_clip(name)!r} ignored", header_line)
        else:
            mapping[field] = position
    if "frame_ms" not in mapping:
        raise PerfError("csv_unreadable", "no frame time column found")
    present = [field for field in _OPTIONAL_FIELDS if field in mapping]
    for field in _OPTIONAL_FIELDS:
        if field not in mapping:
            sink.add("missing_column", f"no column found for {field}; values unavailable")

    data = rows[1:]
    frames: list[Frame] = []
    clock = 0.0
    for position, (line, row) in enumerate(data):
        if len(row) != len(header):
            truncated = len(row) < len(header) and position == len(data) - 1
            code = "truncated_row" if truncated else "malformed_row"
            sink.add(code, f"row has {len(row)} cells, expected {len(header)}; row skipped", line)
            continue
        raw_frame = row[mapping["frame_ms"]]
        frame_ms = _to_float(raw_frame)
        if frame_ms is None or frame_ms <= 0:
            sink.add("bad_value", f"invalid frame time {_clip(raw_frame)!r}; row skipped", line)
            continue
        optional: dict[str, float | None] = {}
        for field in present:
            raw = row[mapping[field]]
            value = _to_float(raw)
            if value is None or value < 0:
                sink.add("bad_value", f"invalid {field} {_clip(raw)!r}; treated as missing", line)
                value = None
            optional[field] = value
        frames.append(
            Frame(
                index=len(frames),
                start_ms=clock,
                frame_ms=frame_ms,
                game_ms=optional.get("game_ms"),
                render_ms=optional.get("render_ms"),
                gpu_ms=optional.get("gpu_ms"),
            )
        )
        clock += frame_ms

    warnings = sink.freeze()
    columns = tuple((field, _clip(header[index])) for field, index in mapping.items())
    summary = f"parsed {len(frames)} frames with {len(warnings)} warnings"
    return ParsedProfile(tuple(frames), warnings, columns, summary)


def parse_csv_profile(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> ParsedProfile:
    """Read a CSV Profiler capture from ``path`` and parse it with ``parse_csv_text``.

    Raises:
        PerfError: ``csv_not_found`` when the file does not exist, ``csv_unreadable`` when it
            cannot be read or parsed, ``limit_exceeded`` above the limits.
    """
    target = Path(path)
    try:
        size = target.stat().st_size
    except FileNotFoundError:
        raise PerfError("csv_not_found", f"CSV file not found: {_clip(target.name)}") from None
    except (OSError, ValueError):
        raise PerfError(
            "csv_unreadable", f"CSV file cannot be read: {_clip(target.name)}"
        ) from None
    if size > max_bytes:
        raise PerfError("limit_exceeded", f"CSV is larger than {max_bytes} bytes")
    try:
        data = target.read_bytes()
    except OSError:
        raise PerfError(
            "csv_unreadable", f"CSV file cannot be read: {_clip(target.name)}"
        ) from None
    return parse_csv_text(data, max_bytes=max_bytes, max_rows=max_rows)
