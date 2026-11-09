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
- note: physical_mb (physical memory used): no column or no values in the capture; omitted
- note: streaming_pool_mb (texture streaming pool): no column or no values in the capture; omitted

| channel | unit | mean | p50 | p95 | p99 |
|---|---|---|---|---|---|
| game_ms | ms | 13.18 | 6.40 | 41.00 | 41.00 |
| render_ms | ms | 10.38 | 5.40 | 31.00 | 31.00 |
| gpu_ms | ms | 17.78 | 8.40 | 56.00 | 56.00 |
