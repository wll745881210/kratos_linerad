# Profiling in `line_rt/tests`

## Overview

The `--profile` flag provides a per-step timing breakdown for each Kratos
invocation in the standalone tests.  It measures:

1. **Python-side** — field/photon binary generation + I/O + output readback
2. **Kratos-side** — split into `init` (binary read, GPU allocation, table
   construction) and `evolve` (MC transport + output write)

All timing is wall-clock, measured with `time.perf_counter()` (Python) and
`std::chrono::steady_clock` (C++).

---

## Implementation

### Kratos side (`usr_ext/line_rt/usr.cpp`)

A `[profile] enabled` par-file key gates the timing.  When `enabled = 1`,
`std::chrono::steady_clock` timestamps are taken around `mesh.init()` and
`mesh.evolve()`:

```cpp
#include <chrono>
// ...
bool profile = args.get<bool>("profile", "enabled", false);

auto t0 = std::chrono::steady_clock::now();
mesh. init   ( args );
auto t1 = std::chrono::steady_clock::now();
mesh. evolve (      );
auto t2 = std::chrono::steady_clock::now();

if( profile )
{
    std::cout << "[profile] init:   "
              << std::chrono::duration<double>(t1-t0).count() << " s\n";
    std::cout << "[profile] evolve: "
              << std::chrono::duration<double>(t2-t1).count() << " s\n";
}
```

When the key is absent or `enabled = 0`, no timing output is produced and
the overhead is zero (two `steady_clock::now()` calls, ~20 ns).

The existing `Duration` timer (in `cycle.cpp`, printed as
`Duration = X.XXX s`) gives the GPU MC-transport time.  The `[profile]`
lines give the full `init` and `evolve` phases, so:

| Kratos phase | Source |
|---|---|
| `init` | `[profile] init:` |
| GPU transport | `Duration =` |
| MC scattering | `[profile] mcrt:` |
| Imaging ray trace | `[profile] imaging:` |
| Output write | `[profile] evolve:` − `Duration =` |

### Python side (`test_scaling_image.py`)

A `--profile` CLI flag (default off) controls the Python-side timing and
enables the `[profile]` par section:

```python
p.add_argument('--profile', action='store_true',
               help='print per-step timing breakdown')
```

Inside `run_one()`, `time.perf_counter()` timestamps wrap each step:

| Python step | Variable |
|---|---|
| Field/photon generation + binary write | `gen_inputs` |
| `subprocess.run(kratos_bin par)` wall time | `kratos_wall` |
| Output binary readback | `read_output` |

Kratos log lines are parsed via regex:

```python
timing['kratos_gpu']    = _parse_float_log(log, r'Duration = ([\d.eE+-]+) s')
timing['kratos_init']   = _parse_float_log(log, r'\[profile\] init:\s+([\d.eE+-]+) s')
timing['kratos_evolve'] = _parse_float_log(log, r'\[profile\] evolve:\s+([\d.eE+-]+) s')
timing['kratos_output'] = timing['kratos_evolve'] - timing['kratos_gpu']
```

`_print_timing()` prints the full breakdown:

```
    [profile] gen_inputs:      0.009 s
    [profile] kratos_wall:     11.471 s
    [profile]   kratos_init:   0.270 s
    [profile]   kratos_gpu:    10.985 s
    [profile]     mcrt:       10.979 s
    [profile]     imaging:     0.006 s
    [profile]   kratos_output: 0.010 s
    [profile] read_output:    0.000 s
    [profile] TOTAL:           11.480 s
```

The `mcrt` and `imaging` lines (printed only when non-zero)
break down the GPU time into scattering MC transport and
formal-solution ray tracing.  The `init` line includes the
GPU construction of the USampler CDF (40-thread kernel) and
R_IIA table (200×200×40 grid), both using `float_t` (single
precision).  The USampler CDF + xg are then copied to const
memory (Option B, 39.4 KB) for broadcast-cache reads in the
MCRT hot path.  Total init: ~0.27 s (was ~2.9 s with CPU
construction, 10.6× speed-up).

The `[profile]` par section is injected into `PAR_TEMPLATE` only when
`--profile` is passed:

```ini
[profile]
enabled = {profile_enabled}
```

---

## Usage

```bash
# Single tau0 with timing
python3 usr_ext/line_rt/tests/test_scaling_image.py \
    --kratos-root ~/apps/kratos_line_rt \
    --tau0-fid-list 32000 \
    --profile

# Full sweep with timing
python3 usr_ext/line_rt/tests/test_scaling_image.py \
    --kratos-root ~/apps/kratos_line_rt \
    --profile

# Combine with --plots (timing is printed alongside results)
python3 usr_ext/line_rt/tests/test_scaling_image.py \
    --kratos-root ~/apps/kratos_line_rt \
    --tau0-fid-list 200 32000 \
    --profile --plots
```

Without `--profile`, the test runs normally with no timing output.

---

## Example results (`test_scaling_image.py`)

Configuration: `a = 0.149`, `ph_mode = 2` (R\_IIA, GPU-constructed tables,
USampler in const mem), `n_radiation = 100 000`, `n_chan = 64`
(adaptive `v_chan`), RTX 3090 (82 SM, sm\_80), AMD Ryzen 7 5800X.

| tau0 | a·tau0 | init (s) | mcrt (s) | imaging (s) | output (s) | Python (s) | total (s) | GPU % |
|-----:|-------:|---------:|---------:|------------:|-----------:|-----------:|----------:|------:|
|  200 |     30 | 0.27 | 0.47 | 0.01 | 0.01 | 0.02 | 0.77 | 63 |
|  500 |     74 | 0.27 | 0.65 | 0.01 | 0.01 | 0.01 | 0.95 | 69 |
| 2000 |    298 | 0.27 | 1.36 | 0.01 | 0.01 | 0.01 | 1.67 | 82 |
| 8000 |   1192 | 0.27 | 3.47 | 0.01 | 0.01 | 0.01 | 3.78 | 92 |
|32000 |   4768 | 0.27 | 9.41 | 0.01 | 0.01 | 0.01 | 9.71 | 97 |

The `GPU` column here is `mcrt + imaging` (total GPU work).
The `output` column is `kratos_evolve − (mcrt + imaging)`.

### Key observations

1. **Init is constant ~0.27 s** — independent of optical depth.  Both the
   USampler CDF (251×40 = 10 040 floats) and the R\_IIA kernel table
   (200×200×40 = 1.6 M floats) are constructed on the **GPU** using
   `float_t` (single precision).  The USampler CDF + xg are then copied
   to **constant memory** (Option B, 39.4 KB) for broadcast-cache reads
   in the MCRT hot path; the R\_IIA table (6.4 MB) stays in global memory.
   Total table construction: ~0.05 s GPU vs ~2.9 s CPU (58× speed-up).

2. **GPU transport (mcrt) scales with tau0** — 0.47 s at tau0 = 200 to
   9.41 s at tau0 = 32 000 (20× increase), roughly proportional to the
   mean number of scatterings (~tau0).

3. **Imaging ray trace is ~10 ms** — negligible compared to mcrt.

4. **Python overhead is <20 ms** — field/photon generation, binary write,
   and output readback are all negligible.

5. **For tau0 < 500, init is 28–35 %** of total wall time.
   For tau0 >= 2000, GPU transport dominates (82–97 %).

### Breakdown of init (~0.27 s)

The init phase (`mesh.init()`) includes:

| Sub-step | Description |
|---|---|
| Binary read | `ini_t::read()` — read field/photon binaries from disk |
| GPU allocation | `cudaMalloc` for all device arrays (fields, tables, photon pool) |
| `interp_t::to_device` | Copy field interpolation tables to device memory |
| `riia_table_t::build()` | USampler CDF (**GPU**, `float_t`) + R\_IIA kernel table (**GPU**, `float_t`) + const-mem copy (Option B) |
| `init_cond` kernel | Zero field arrays + sample interp tables at cell centres |

The USampler CDF is built on the **GPU** via `build_usampler_gpu_kernel`:
40 threads compute 40 rows of the 251-element CDF (log-space, `float_t`).
The R\_IIA table is built on the **GPU** via `build_riia_gpu_kernel`:
a kernel grid of `(ceil(200/64), 200, 40)` = 32 000 blocks × 64 threads
computes the 3.2 M table entries in parallel, each summing 251 USampler
values via `expf(d_cdf[idx])`.  After construction, if `use_const_mem`
(ph\_mode 2/3), the USampler CDF + xg are copied to constant memory
(39.4 KB, Option B) for broadcast-cache reads.  The R\_IIA table
(6.4 MB, too large for the 64 KB HW limit) stays in global memory.
Total table construction: ~0.05 s GPU vs ~2.5 s CPU (50× speed-up).

### Speed-up vs SKIRT9

For the same Ly-alpha slab (tau0 = 1000, 100 k photons), the wall-time
comparison is:

| Code | Wall time (s) | Overhead |
|---|---|---|
| Kratos (init + GPU + output) | ~2.0 s | init = 0.27 s |
| SKIRT9 (CPU, 16 threads) | ~5.8 s | setup = 0.05 s |

Kratos is faster overall, and the init overhead is now comparable to
SKIRT9's setup.  For long runs (high tau0), the GPU advantage dominates.

---

## Adapting to other tests

The `--profile` pattern is self-contained in `usr_ext/line_rt/`:

1. Add `#include <chrono>` and the `[profile]` par key + timing block to
   `usr.cpp` (already done).
2. In any standalone test script, add:
   - `import time, re`
   - `--profile` CLI flag
   - `[profile] enabled = {profile_enabled}` in the par template
   - `time.perf_counter()` around `generate_*()`, `subprocess.run()`,
     `read_output()`
   - Parse `Duration =` and `[profile]` lines from stdout
   - Print the breakdown

The `[profile]` par key is read by `usr.cpp` and is global — any test
that uses the `line_rt` `usr.cpp` automatically supports it.
