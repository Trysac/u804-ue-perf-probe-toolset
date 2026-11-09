"""Tests for the CSV Profiler parser."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ue_perf_probe_toolset.core.csvparse import parse_csv_profile, parse_csv_text
from ue_perf_probe_toolset.errors import PerfError

DATA = Path(__file__).parent / "data"
HEADER = "FrameTime,GameThreadTime,RenderThreadTime,GPUTime\n"


def _codes(profile):
    return [warning.code for warning in profile.warnings]


def test_maps_fixture_columns():
    profile = parse_csv_profile(DATA / "capture_ok.csv")
    assert len(profile.frames) == 10
    assert profile.warnings == ()
    assert dict(profile.columns) == {
        "frame_ms": "FrameTime",
        "game_ms": "GameThreadTime",
        "render_ms": "RenderThreadTime",
        "gpu_ms": "GPUTime",
    }
    first = profile.frames[0]
    assert (first.frame_ms, first.game_ms, first.render_ms, first.gpu_ms) == (10.0, 6.0, 5.0, 8.0)
    assert profile.frames[1].start_ms == 10.0
    assert profile.frames[6].start_ms == 110.0
    assert profile.summary == "parsed 10 frames with 0 warnings"


def test_column_order_does_not_matter():
    ordered = parse_csv_profile(DATA / "capture_ok.csv")
    shuffled = parse_csv_profile(str(DATA / "capture_shuffled.csv"))
    assert shuffled.frames == ordered.frames
    assert shuffled.warnings == ()
    assert dict(shuffled.columns) == dict(ordered.columns)


def test_patterns_ignore_case_spaces_and_units():
    text = "Frame Time (ms),GameThread,RenderThread (ms),GPU\n16.0,5,6,7\n"
    profile = parse_csv_text(text)
    assert profile.warnings == ()
    frame = profile.frames[0]
    assert (frame.frame_ms, frame.game_ms, frame.render_ms, frame.gpu_ms) == (16.0, 5.0, 6.0, 7.0)


def test_missing_column_gives_one_warning():
    text = "FrameTime,GameThreadTime,RenderThreadTime\n10,1,2\n10,1,2\n"
    profile = parse_csv_text(text)
    assert _codes(profile) == ["missing_column"]
    assert len(profile.frames) == 2
    assert profile.frames[0].gpu_ms is None


def test_extra_column_gives_one_warning():
    text = "FrameTime,GameThreadTime,RenderThreadTime,GPUTime,Events\n10,1,2,3,x\n10,1,2,3,\n"
    profile = parse_csv_text(text)
    assert _codes(profile) == ["extra_column"]
    assert len(profile.frames) == 2


def test_truncated_last_row_gives_one_warning():
    profile = parse_csv_text(HEADER + "10,1,2,3\n10,1,2,3\n10,1")
    assert _codes(profile) == ["truncated_row"]
    assert profile.warnings[0].line == 4
    assert len(profile.frames) == 2


def test_each_problem_gives_exactly_one_warning():
    text = "FrameTime,GameThreadTime,RenderThreadTime,Events\n10,1,2,x\n10,1,2,x\n10,1"
    profile = parse_csv_text(text)
    assert sorted(_codes(profile)) == ["extra_column", "missing_column", "truncated_row"]
    assert len(profile.frames) == 2


def test_short_row_in_the_middle_is_malformed_not_truncated():
    profile = parse_csv_text(HEADER + "10,1\n10,1,2,3\n")
    assert _codes(profile) == ["malformed_row"]
    assert len(profile.frames) == 1


def test_long_row_is_malformed():
    profile = parse_csv_text(HEADER + "10,1,2,3,4\n10,1,2,3\n")
    assert _codes(profile) == ["malformed_row"]
    assert len(profile.frames) == 1


def test_bad_numbers_are_reported_per_cell():
    rows = [
        "abc,1,2,3",
        "10,x,2,3",
        "nan,1,2,3",
        "-5,1,2,3",
        "0,1,2,3",
        "inf,1,2,3",
        "10,1,2,-1",
    ]
    profile = parse_csv_text(HEADER + "\n".join(rows) + "\n")
    assert _codes(profile) == ["bad_value"] * 7
    assert len(profile.frames) == 2
    assert profile.frames[0].game_ms is None
    assert profile.frames[1].gpu_ms is None


def test_metadata_blank_and_empty_rows_are_skipped():
    text = "FrameTime,GPUTime\n\n10,3\n[HasHeaderRowAtEnd],1\n  ,  \n"
    profile = parse_csv_text(text)
    assert _codes(profile) == ["missing_column", "missing_column"]
    assert len(profile.frames) == 1


def test_duplicate_column_is_ignored_with_a_warning():
    profile = parse_csv_text("FrameTime,GPUTime,GPU Time\n10,1,2\n")
    assert "duplicate_column" in _codes(profile)
    assert profile.frames[0].gpu_ms == 1.0


def test_warnings_are_capped():
    profile = parse_csv_text(HEADER + "bad,1,2,3\n" * 150)
    assert len(profile.warnings) == 101
    assert profile.warnings[-1].code == "warnings_truncated"
    assert profile.frames == ()


@pytest.mark.parametrize("text", ["", "   \n\n", "[Meta],1\n", "GPUTime\n1\n"])
def test_unusable_input_raises_csv_unreadable(text):
    with pytest.raises(PerfError) as info:
        parse_csv_text(text)
    assert info.value.code == "csv_unreadable"


def test_bytes_and_bom():
    raw = ("\ufeff" + HEADER + "10,1,2,3\n").encode()
    assert len(parse_csv_text(raw).frames) == 1
    assert len(parse_csv_text("\ufeff" + HEADER + "10,1,2,3\n").frames) == 1


def test_invalid_utf8_raises():
    with pytest.raises(PerfError) as info:
        parse_csv_text(b"\xff\xfe\x00")
    assert info.value.code == "csv_unreadable"


def test_huge_field_raises_csv_unreadable():
    with pytest.raises(PerfError) as info:
        parse_csv_text(HEADER + "10," + "x" * 200000 + ",2,3\n")
    assert info.value.code == "csv_unreadable"


def test_size_limits():
    text = HEADER + "10,1,2,3\n"
    for payload in (text, text.encode()):
        with pytest.raises(PerfError) as info:
            parse_csv_text(payload, max_bytes=10)
        assert info.value.code == "limit_exceeded"


def test_row_limit():
    text = HEADER + "10,1,2,3\n10,1,2,3\n"
    with pytest.raises(PerfError) as info:
        parse_csv_text(text, max_rows=1)
    assert info.value.code == "limit_exceeded"
    assert len(parse_csv_text(text, max_rows=2).frames) == 2


def test_file_errors(tmp_path):
    with pytest.raises(PerfError) as missing:
        parse_csv_profile(tmp_path / "nope.csv")
    assert missing.value.code == "csv_not_found"
    with pytest.raises(PerfError) as directory:
        parse_csv_profile(tmp_path)
    assert directory.value.code == "csv_unreadable"
    with pytest.raises(PerfError) as nul:
        parse_csv_profile("bad\0name.csv")
    assert nul.value.code == "csv_unreadable"
    with pytest.raises(PerfError) as big:
        parse_csv_profile(DATA / "capture_ok.csv", max_bytes=5)
    assert big.value.code == "limit_exceeded"


@settings(derandomize=True, max_examples=200, deadline=None)
@given(st.text(max_size=400))
def test_arbitrary_text_only_raises_perf_error(text):
    try:
        profile = parse_csv_text(text)
    except PerfError:
        return
    assert all(frame.frame_ms > 0 for frame in profile.frames)


_CELLS = st.sampled_from(["", "10", "16.7", "abc", "nan", "-1", "1e400", " 5 "])


@settings(derandomize=True, max_examples=200, deadline=None)
@given(st.lists(st.lists(_CELLS, max_size=6), max_size=12))
def test_structured_rows_never_raise(rows):
    text = HEADER + "\n".join(",".join(row) for row in rows)
    profile = parse_csv_text(text)
    assert all(math.isfinite(frame.frame_ms) and frame.frame_ms > 0 for frame in profile.frames)


def test_memory_columns_are_parsed_without_missing_warnings():
    text = "FrameTime,GameThreadTime,RenderThreadTime,GPUTime,Physical Used MB,TexturePool\n10,1,2,3,3000,800\n"
    profile = parse_csv_text(text)
    assert profile.warnings == ()
    frame = profile.frames[0]
    assert (frame.physical_mb, frame.streaming_pool_mb) == (3000.0, 800.0)
    assert parse_csv_text(HEADER + "10,1,2,3\n").frames[0].physical_mb is None


def test_repeated_header_row_is_skipped():
    profile = parse_csv_text(HEADER + "10,1,2,3\n" + HEADER + "[HasHeaderRowAtEnd],1\n")
    assert profile.warnings == ()
    assert len(profile.frames) == 1


def test_many_extra_columns_give_a_single_warning():
    names = ",".join(f"Extra{index}" for index in range(12))
    profile = parse_csv_text(f"FrameTime,{names}\n10" + ",0" * 12 + "\n")
    extra = [w for w in profile.warnings if w.code == "extra_column"]
    assert len(extra) == 1
    assert "'Extra0'" in extra[0].message and "and 2 more" in extra[0].message
