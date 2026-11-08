"""Tests for the build size report."""

from __future__ import annotations

import os

import pytest

from ue_perf_probe_toolset.core import sizes as sizes_module
from ue_perf_probe_toolset.core.sizes import build_size_report
from ue_perf_probe_toolset.errors import PerfError


@pytest.fixture
def build_dir(tmp_path):
    root = tmp_path / "build"
    (root / "sub").mkdir(parents=True)
    (root / "a.pak").write_bytes(b"x" * 1000)
    (root / "b.ucas").write_bytes(b"x" * 2500)
    (root / "c.utoc").write_bytes(b"x" * 300)
    (root / "sub" / "d.pak").write_bytes(b"x" * 700)
    return root


def test_total_is_exact_sum_and_breakdown_by_extension(build_dir):
    report = build_size_report(build_dir)
    assert report.total_bytes == 4500
    assert report.file_count == 4
    assert [(item.extension, item.size_bytes, item.file_count) for item in report.breakdown] == [
        (".ucas", 2500, 1),
        (".pak", 1700, 2),
        (".utoc", 300, 1),
    ]
    assert 0 < report.estimated_zip_bytes <= report.total_bytes
    assert report.warnings == ()
    assert report.limit_bytes is None
    assert report.usage_ratio is None
    assert report.summary == "4 files, 4500 bytes in 3 extensions"


def test_warning_above_90_percent_of_limit(build_dir):
    report = build_size_report(build_dir, limit_bytes=4900)
    assert len(report.warnings) == 1
    assert "90%" in report.warnings[0]
    assert report.usage_ratio == pytest.approx(4500 / 4900)


def test_warning_when_over_the_limit(build_dir):
    report = build_size_report(build_dir, limit_bytes=4000)
    assert len(report.warnings) == 2
    assert "exceeds the limit" in report.warnings[1]


def test_no_warning_at_exactly_90_percent_or_below(build_dir):
    assert build_size_report(build_dir, limit_bytes=5000).warnings == ()
    assert build_size_report(build_dir, limit_bytes=10000).warnings == ()


def test_extensions_are_lower_cased_and_none_is_named(tmp_path):
    (tmp_path / "A.PAK").write_bytes(b"12")
    (tmp_path / "README").write_bytes(b"123")
    report = build_size_report(tmp_path)
    assert {item.extension for item in report.breakdown} == {".pak", "(none)"}


def test_empty_folder(tmp_path):
    report = build_size_report(tmp_path)
    assert (report.total_bytes, report.file_count, report.breakdown) == (0, 0, ())


def test_symlinks_are_skipped(tmp_path):
    target = tmp_path / "real.pak"
    target.write_bytes(b"x" * 10)
    root = tmp_path / "build"
    root.mkdir()
    try:
        (root / "link.pak").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert build_size_report(root).total_bytes == 0


def test_errors(tmp_path, build_dir):
    with pytest.raises(PerfError) as missing:
        build_size_report(tmp_path / "nope")
    assert missing.value.code == "path_not_found"
    with pytest.raises(PerfError) as not_dir:
        build_size_report(build_dir / "a.pak")
    assert not_dir.value.code == "path_not_found"
    for bad in (0, -1, True):
        with pytest.raises(PerfError) as info:
            build_size_report(build_dir, limit_bytes=bad)
        assert info.value.code == "invalid_argument"
    with pytest.raises(PerfError) as many:
        build_size_report(build_dir, max_files=3)
    assert many.value.code == "limit_exceeded"


COOK_LOG = """LogCook: Display: Cooked package /Game/Maps/Big (5000 bytes)
LogCook: Display: Cooked package /Game/Textures/T_Rock: 3000 bytes
LogCook: Display: Cooked package /Game/Maps/Big (4000 bytes)
noise line without sizes
../../../Proj/Content/Audio/Music.uasset 2000 B
LogCook: Display: /Game/Other 12 Bar
"""


def test_largest_contributors_from_cook_log(build_dir, tmp_path):
    log = tmp_path / "cook.log"
    log.write_text(COOK_LOG + "x" * 3000 + " /Game/Long 9 B\n", encoding="utf-8")
    report = build_size_report(build_dir, cook_log=log)
    assert [(item.name, item.size_bytes) for item in report.largest_contributors] == [
        ("/Game/Maps/Big", 5000),
        ("/Game/Textures/T_Rock", 3000),
        ("../../../Proj/Content/Audio/Music.uasset", 2000),
    ]
    limited = build_size_report(build_dir, cook_log=str(log), top_n=2)
    assert len(limited.largest_contributors) == 2


def test_missing_or_unreadable_cook_log_only_warns(build_dir, tmp_path):
    report = build_size_report(build_dir, cook_log=tmp_path / "missing.log")
    assert report.largest_contributors == ()
    assert report.warnings == ("cook log could not be read",)
    assert build_size_report(build_dir, cook_log=tmp_path).warnings == (
        "cook log could not be read",
    )


def test_cook_log_is_truncated_at_the_cap(build_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(sizes_module, "MAX_LOG_BYTES", 80)
    log = tmp_path / "cook.log"
    log.write_text(COOK_LOG, encoding="utf-8")
    report = build_size_report(build_dir, cook_log=log)
    assert any("truncated" in warning for warning in report.warnings)
    assert len(report.largest_contributors) == 1


def test_cook_log_entry_cap(build_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(sizes_module, "MAX_LOG_ENTRIES", 1)
    log = tmp_path / "cook.log"
    log.write_text(COOK_LOG, encoding="utf-8")
    report = build_size_report(build_dir, cook_log=log)
    assert [item.name for item in report.largest_contributors] == ["/Game/Maps/Big"]


def test_walk_does_not_modify_the_folder(build_dir):
    before = sorted(os.listdir(build_dir))
    build_size_report(build_dir)
    assert sorted(os.listdir(build_dir)) == before
