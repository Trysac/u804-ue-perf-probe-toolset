"""Package-level tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ue_perf_probe_toolset as pkg
from ue_perf_probe_toolset import PerfError, to_dict
from ue_perf_probe_toolset.core.csvparse import parse_csv_profile
from ue_perf_probe_toolset.core.report import build_report

DATA = Path(__file__).parent / "data"


def test_version_and_exports():
    assert pkg.__version__ == "0.1.0"
    for name in pkg.__all__:
        assert hasattr(pkg, name)


def test_to_dict_is_json_serializable():
    report = build_report("capture_ok.csv", parse_csv_profile(DATA / "capture_ok.csv"))
    data = to_dict(report)
    assert data["stats"]["frame_count"] == 10
    assert json.loads(json.dumps(data))["source"] == "capture_ok.csv"


@pytest.mark.parametrize("value", [5, "text", None, PerfError])
def test_to_dict_rejects_non_dataclass_instances(value):
    with pytest.raises(PerfError) as info:
        to_dict(value)
    assert info.value.code == "invalid_argument"
