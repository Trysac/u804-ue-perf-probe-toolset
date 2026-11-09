# Project record

## Objective

Provide a dependency-free Python library that lets an agent measure an Unreal Engine 5.8 game repeatably. It parses CSV Profiler captures, computes frame statistics, checks them against a budget with a PASS or FAIL verdict, compares two captures with a seeded bootstrap, and reports build size.

## Scope

- In scope: the pure core (CSV parsing, frame statistics, budgets, comparison, build size, Markdown rendering) and the thin adapter that starts and reads captures through the `unreal` module passed by the caller.
- In scope: the public API listed in [README.md](../README.md), typed and tested against a fake `unreal` module.
- In scope since 0.2.0: the Unreal plugin (`.uplugin`, `ToolsetDefinition` shell), the `mcp` layer, the plugin build tool and the in-editor smoke test.

## Out of scope

- Unreal Insights traces.
- Per-draw-call analysis.
- Automatic optimization of the project.
- Real anonymized captures from the editor. Only synthetic fixtures are committed.

## Timeline

| Date | Event |
|---|---|
| 2026-11-08 | Repository created from the factory utility template; factory run (core + adapter). |
| 2026-11-08 | Interactive session (Claude Code): plugin shell, `mcp` layer, build tool, smoke test, skill, docs (0.2.0). Not yet verified inside Unreal. |
| pending | In-editor verification on UE 5.8 (`docs/TESTING.md`): date, engine version, smoke result, `stat unit` comparison. |

## Effort metrics

Only measured values are recorded here. Unmeasured values are shown as pending measurement.

| Metric | Value |
|---|---|
| Tokens (input / output) | 440362 / 129138 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.9709 |

## Factory run u804 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | claude-sonnet-5-5 | yes | 2284 | 109581 | 0 | 5188 | 0.5507 |
| fix-1 | claude-sonnet-5-5 | no | 4 | 593 | 15937 | 15186 | 0.0473 |
| audit | claude-sonnet-5-5 | no | 16 | 4160 | 55452 | 203145 | 0.2006 |
| fix-2 | claude-sonnet-5-5 | no | 8 | 2726 | 11108 | 64288 | 0.0615 |
| fix-3 | claude-sonnet-5-5 | no | 6 | 715 | 6589 | 40888 | 0.0277 |
| docs | claude-haiku-5-5 | no | 109349 | 11363 | 0 | 0 | 0.0831 |

Total: $0.9709. Prices: Anthropic list prices.
