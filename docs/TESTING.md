# Testing

Tests are the verification layer for the core and the adapter. The commands are `uv run python scripts/check.py` for the full gate set, or `uv run pytest --cov=ue_perf_probe_toolset` for the tests alone.

## Status

The tests were written with this code, but they have not been executed in this generation. Formatting, type checks and the test run are therefore unverified.

## Test assets in the repository

- `tests/fakes/unreal.py` is a fake `unreal` module. It provides `execute_console_command`, a registry for Slate post-tick callbacks, and a way to drive the tick by hand. Adapter tests use it, so no real time passes and nothing sleeps.
- `tests/golden/perf.md` is the expected Markdown output of `perf_report_md` for the fixture report.
- `tests/data/` holds synthetic CSV files written by hand to exercise the parser and the statistics. They are not captures from a real editor session.

## Intended coverage

- Unit tests for each public function and error path of the core and the adapter.
- Property tests with Hypothesis and `derandomize=True`: frame statistics are compared with a naive sorted-list reference, and the parser is checked to raise only `PerfError`.
- Reproducibility of the seeded bootstrap: the same seed gives the same result.
- Golden comparison of the Markdown report.
- Adapter behaviour on the fake module: console commands issued, stop scheduled through the tick callback, job states, path confinement and limits.

The individual test file names are not listed here because they were not part of the reviewed code.

## Fixtures

The CSV files under `tests/data/` are synthetic. They are not captures from a real editor session.

## What is not tested

Nothing in this repository was tested inside Unreal Engine. The adapter was exercised only against the fake module. The real anonymized CSV captured in the editor, the plugin packaging and an editor smoke test are not part of this repository state and remain to be done in a supervised session.
