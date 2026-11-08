| metric | value | budget | verdict |
|---|---|---|---|
| fps_mean | 50.00 | >= 45 | PASS |
| fps_min | 16.67 | - | - |
| fps_p1_low | 16.67 | >= 30 | FAIL |
| fps_p5_low | 16.67 | - | - |
| frame_ms_mean | 20.00 | - | - |
| frame_ms_p50 | 10.00 | - | - |
| frame_ms_p95 | 60.00 | - | - |
| frame_ms_p99 | 60.00 | - | - |
| hitches_per_min | 600.00 | <= 1000 | PASS |

**Verdict: FAIL**

- source: capture_ok.csv
- frames: 10 (0 excluded as warmup)
- duration_s: 0.20
- hitches: 2 above 50 ms
- render profile: not available
