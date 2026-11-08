"""Shared fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fakes.unreal import FakeUnreal


def _csv_text(frame_ms):
    lines = ["FrameTime,GameThreadTime,RenderThreadTime,GPUTime"]
    lines.extend(f"{ms},{ms / 2},{ms / 3},{ms / 4}" for ms in frame_ms)
    return "\n".join(lines) + "\n"


@pytest.fixture
def fake_ue(tmp_path):
    ue = FakeUnreal(tmp_path / "Proj")
    ue.csv_dir.mkdir(parents=True)
    return ue


@pytest.fixture
def write_csv():
    def _write(directory, name, frame_ms, mtime_s=None):
        path = Path(directory) / name
        path.write_text(_csv_text(frame_ms), encoding="utf-8")
        if mtime_s is not None:
            os.utime(path, (mtime_s, mtime_s))
        return path

    return _write
