"""Tests for the typed error."""

from __future__ import annotations

from ue_perf_probe_toolset.errors import ERROR_CODES, PerfError


def test_error_has_code_and_message():
    error = PerfError("csv_not_found", "missing")
    assert error.code == "csv_not_found"
    assert error.message == "missing"
    assert str(error) == "[csv_not_found] missing"
    assert isinstance(error, Exception)


def test_message_is_clipped_to_200_characters():
    error = PerfError("csv_unreadable", "x" * 500)
    assert len(error.message) == 200


def test_documented_codes_are_registered():
    for code in ("csv_not_found", "csv_unreadable", "unknown_job", "path_not_allowed"):
        assert code in ERROR_CODES
