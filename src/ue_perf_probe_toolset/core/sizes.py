"""Build size report: a read-only walk of a build folder. Pure (standard library only)."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from ..errors import PerfError

MAX_FILES = 500_000
MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_LOG_LINE = 2000
MAX_LOG_ENTRIES = 100_000
COMPRESSED_EXTENSIONS = frozenset({".pak", ".ucas", ".utoc", ".zip", ".sig"})
# Heuristic ratios behind ``estimated_zip_bytes``; the estimate is not a measurement.
COMPRESSED_RATIO = 0.98
OTHER_RATIO = 0.6

# Best effort: a package path (starting with / or ../) followed on the same line by a size
# written like "1234 bytes" or "1234 B".
_COOK_LINE = re.compile(
    r"(?P<name>(?:/|\.\./)[^\s\x22\x27:,;()]+)[^\n\d]*?(?P<size>\d{1,15})\s*(?:bytes|B)\b"
)


@dataclass(frozen=True)
class ExtensionSize:
    """Total size of the files with one extension."""

    extension: str
    size_bytes: int
    file_count: int


@dataclass(frozen=True)
class SizeContributor:
    """A large package named in a cook log."""

    name: str
    size_bytes: int


@dataclass(frozen=True)
class SizeReport:
    """Size of a build folder.

    ``estimated_zip_bytes`` is an ESTIMATE from fixed per-extension ratios, not a measured
    archive size.
    """

    root: str
    total_bytes: int
    file_count: int
    breakdown: tuple[ExtensionSize, ...]
    estimated_zip_bytes: int
    limit_bytes: int | None
    usage_ratio: float | None
    warnings: tuple[str, ...]
    largest_contributors: tuple[SizeContributor, ...]
    summary: str
    notes: tuple[str, ...] = ()


def _file_size(path: str) -> int | None:
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return info.st_size


def _read_cook_log(path: Path, top_n: int, warnings: list[str]) -> tuple[SizeContributor, ...]:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_LOG_BYTES + 1)
    except OSError:
        warnings.append("cook log could not be read")
        return ()
    if len(data) > MAX_LOG_BYTES:
        warnings.append(f"cook log truncated at {MAX_LOG_BYTES} bytes")
        data = data[:MAX_LOG_BYTES]
    sizes: dict[str, int] = {}
    for line in data.decode("utf-8", "replace").splitlines():
        if len(line) > MAX_LOG_LINE:
            continue
        match = _COOK_LINE.search(line)
        if match is None:
            continue
        name = match.group("name")
        if name not in sizes and len(sizes) >= MAX_LOG_ENTRIES:
            continue
        sizes[name] = max(sizes.get(name, 0), int(match.group("size")))
    ranked = sorted(sizes.items(), key=lambda item: (-item[1], item[0]))
    return tuple(SizeContributor(name, size) for name, size in ranked[:top_n])


def build_size_report(
    root: str | Path,
    *,
    limit_bytes: int | None = None,
    cook_log: str | Path | None = None,
    max_files: int = MAX_FILES,
    top_n: int = 10,
) -> SizeReport:
    """Walk ``root`` (read-only, symlinks skipped) and sum file sizes by extension.

    Adds a warning when the total is above 90 percent of ``limit_bytes`` (and another when it
    is above the limit). When ``cook_log`` is given, the largest packages it names are listed.

    Raises:
        PerfError: ``path_not_found`` when ``root`` is not a directory, ``invalid_argument``
            for a bad limit, ``limit_exceeded`` when there are more than ``max_files`` files.
    """
    base = Path(root)
    if not base.is_dir():
        raise PerfError("path_not_found", f"not a directory: {base.name[:60]}")
    if limit_bytes is not None and (isinstance(limit_bytes, bool) or limit_bytes <= 0):
        raise PerfError("invalid_argument", "limit_bytes must be a positive integer")
    totals: dict[str, list[int]] = {}
    file_count = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            size = _file_size(os.path.join(dirpath, name))
            if size is None:
                continue
            file_count += 1
            if file_count > max_files:
                raise PerfError("limit_exceeded", f"more than {max_files} files")
            extension = os.path.splitext(name)[1].lower() or "(none)"
            entry = totals.setdefault(extension, [0, 0])
            entry[0] += size
            entry[1] += 1
            total += size
    ranked = sorted(totals.items(), key=lambda item: (-item[1][0], item[0]))
    breakdown = tuple(ExtensionSize(ext, values[0], values[1]) for ext, values in ranked)
    estimate = 0.0
    for extension, values in totals.items():
        ratio = COMPRESSED_RATIO if extension in COMPRESSED_EXTENSIONS else OTHER_RATIO
        estimate += values[0] * ratio
    warnings: list[str] = []
    usage: float | None = None
    if limit_bytes is not None:
        usage = total / limit_bytes
        if total * 10 > limit_bytes * 9:
            warnings.append(
                f"total size {total} bytes is above 90% of the limit of {limit_bytes} bytes"
            )
        if total > limit_bytes:
            warnings.append(f"total size {total} bytes exceeds the limit of {limit_bytes} bytes")
    contributors: tuple[SizeContributor, ...] = ()
    if cook_log is not None:
        contributors = _read_cook_log(Path(cook_log), top_n, warnings)
    summary = f"{file_count} files, {total} bytes in {len(breakdown)} extensions"
    return SizeReport(
        root=str(base),
        total_bytes=total,
        file_count=file_count,
        breakdown=breakdown,
        estimated_zip_bytes=int(estimate),
        limit_bytes=limit_bytes,
        usage_ratio=usage,
        warnings=tuple(warnings),
        largest_contributors=contributors,
        summary=summary,
    )
