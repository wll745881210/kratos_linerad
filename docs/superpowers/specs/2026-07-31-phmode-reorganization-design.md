# ph_mode Reorganization: Merge + Constant-Memory USampler + Analytic Voigt

**Date:** 2026-07-31
**Status:** Approved
**Scope:** Kratos `usr_ext/line_rt` (C++) + pipeline test scripts (Python)

## Motivation

Validation proved ph_mode=1 (USampler v1, `n_u=1201, du=0.01`) and ph_mode=2
(USampler v2, `n_u=2401, du=0.005`) are statistically identical
(med|x| agree within 0.1-1.3%, both within Poisson noise). The v2 grid provides
zero measurable benefit at 2.3x the memory cost. Additionally, the Voigt opacity
table (128 KiB global memory) can be replaced by the analytic Humlicek (1982) w4
algorithm (~1e-4 accuracy, ~30-50 FLOPs), already proven in the Python reference
(`mcrt.py:307-336`). This frees memory and improves accuracy.

## Design

### Part 1: Merge old ph_mode=2 into ph_mode=1

Delete all v2 USampler code from `intg.h`. Old ph_mode=2 par files will use the
v1 USampler (no separate v2 path).

**`usr_ext/line_rt/intg.h` deletions:**
- Members: `d_cdf2`, `d_xg2`, `n_u2`, `n_xg2`, `u_max2`, `du2`
- Methods: `_build_usampler_v2()`, `_invcdf_v2()`, `sample_upar_v2()`
- `init()`: remove `if( ph_mode == 2 ) _build_usampler_v2(...)`
- `finalize()`: remove the `d_cdf2`/`d_xg2` free blocks

**`usr_ext/line_rt/photon.h` `scat()` edit:**
- Remove the `ph_mode == 2` branch (lines ~156-158).
- `ph_mode == 1 || ph_mode == 2` (old) becomes just `ph_mode == 1`.

ph_mode=1 keeps its current USampler v1 (global mem, 865 KiB) + Voigt table
(global mem, 128 KiB). Behavior unchanged.

### Part 2: New ph_mode=2 - coarse USampler in constant memory + analytic Voigt

#### 2a: Coarse log-space USampler table

**Memory budget:** 56 KiB CDF + ~1 KiB xg = 57 KiB total.
GPU constant memory pool: 60 KiB (CUDA/HIP), 20 KiB (MUSA).
The table fits in 60 KiB. MUSA support is secondary (could fall back to global
mem if `malloc_const` throws "const oversize").

**Grid parameters:**
- `n_u = 301`, `du = 0.04`, `u_max = 6.0` (covers [-6, 6], 4x coarser than v1)
- `n_xg = 47` (20 linear 0-8 + 27 log 8-300, ~4x coarser than v1's 180)
- Total: 301 x 47 = 14,147 floats = 55.3 KiB + xg 47 x 4 = 188 B = 55.4 KiB

**Log-space storage:**
The CDF has huge dynamic range (especially at small `a` and large `|x|`).
Store `log(CDF)`:
- Build CDF as before (FP64 prefix sum + normalize on host)
- Floor: `log_cdf[k] = logf(fmaxf(cdf[k], 1e-38f))` (range ~-87 to 0)
- xg stored in linear space (coordinate, not probability)

**Inverse CDF lookup in log-space (device):**
```
log_r = logf(fmaxf(r, 1e-38f));
// binary search: find k where log_cdf[k-1] <= log_r < log_cdf[k]
frac = (log_r - log_cdf[k-1]) / fmaxf(log_cdf[k] - log_cdf[k-1], 1e-35f);
u = (-u_max + du * (k-1)) + frac * du;
```
No `expf` on the output `u` (it is a coordinate, already in linear space).
The `expf`/`logf` guards are on inputs: `fmaxf(r, 1e-38)`,
`fmaxf(cdf, 1e-38)`, denominator `fmaxf(diff, 1e-35)`.

**Benefit:** Linear interpolation in log-space is more accurate for steep CDF
transitions (the step-function-like CDF at x=0, small a becomes smooth in
log-space). This compensates for the 4x coarser grid.

**Allocation approach:** Keep the current manual binary-search pattern (do NOT
refactor to `interp_t::operator()`). Swap `dev.malloc_device`/`dev.f_cp` for
`dev.malloc_const`/`dev.f_cc`:
```cpp
d_logcdf_c = (float_t *)dev.malloc_const<char>(n_total * sizeof(float_t));
d_xg_c     = (float_t *)dev.malloc_const<char>(n_xg   * sizeof(float_t));
dev.f_cc(d_logcdf_c, h_logcdf, n_total * sizeof(float_t));
dev.f_cc(d_xg_c,     h_xg,     n_xg   * sizeof(float_t));
```
In `finalize()`: do NOT free const-mem pointers (the pool is managed by the
system bump allocator, `device.cpp:45-54`).

#### 2b: Analytic Voigt (Humlicek w4)

Replace the `voigt_interp` table lookup with a `__device__` function
implementing Humlicek (1982) w4 - the same algorithm in Python
`mcrt.py:307-336`.

**Algorithm:** `H(a, u) = Re[w(z)]`, `z = |u| + i*a`, 4-region rational
approximation:
- Region 1 (`s = |u| + a >= 15`): asymptotic, `w = t * 0.5641896 / (0.5 + t*t)`
- Region 2 (`s >= 5.5`): `w = t * (1.410474 + t*t*0.5641896) / (0.75 + t*t*(3.0 + t*t))`
- Region 3 (`y >= 0.195*x - 0.176`): 4th-order rational
- Region 4 (else): 7th-order rational with `exp(t*t)` term

Uses `float2_t` (re, im) for complex arithmetic. All operations are basic
float multiply/add/divide. ~30-50 FLOPs per evaluation. Accuracy ~1e-4
everywhere.

**Dispatch:** `intg_t::voigt_H(a, u)` checks ph_mode:
- `ph_mode == 0 || ph_mode == 1`: existing table lookup (unchanged)
- `ph_mode == 2`: call `voigt_H_humlicek(a, u)`

When `ph_mode == 2`, the Voigt table (`voigt_table_data.h`,
`voigt_interp`) is NOT loaded (skip `setup`/`to_device` in `init()`).

#### 2c: ph_mode summary after reorganization

```
ph_mode=0: CFR (Gaussian) + Voigt table (global mem, 128 KiB)
ph_mode=1: R_IIA (USampler v1, global mem, 865 KiB) + Voigt table (global mem, 128 KiB)
ph_mode=2: R_IIA (coarse USampler, const mem, 56 KiB, log-space) + Humlicek w4 (no table)
```

### Part 3: Testing

Use existing `test_scaling_wide.py --ph-mode-list 0,1,2` (already supports
ph_mode list overlay). Compare all three modes against Neufeld analytic at
`a=0.149`, `tau0 in {200, 500, 2000, 8000, 32000}`, `N=100000`.

**Success criteria:** med|x|/Neufeld within +/-5% for all modes at `a*tau0 >= 100`.

If the coarse USampler loses accuracy, grid-search:
- `n_u in {201, 301, 401}`
- `n_xg in {31, 47, 63}`

to find the minimum that maintains +/-5%.

### Part 4: Files touched

| File | Change |
|------|--------|
| `usr_ext/line_rt/intg.h` | Delete v2 code; add coarse USampler (const mem, log-space); add Humlicek w4; conditional table loading by ph_mode |
| `usr_ext/line_rt/photon.h` | Remove old ph_mode==2 branch in `scat()`; voigt_H dispatches to Humlicek for ph_mode==2 |
| `usr_ext/line_rt/gen.h` | No change (ph_mode passes through) |
| `usr_ext/line_rt/voigt_table_data.h` | No change (still used by ph_mode=0,1) |
| `tests/test_scaling_wide.py` | Update `--ph-mode-list` default if needed |
| `docs/debug/debug.md` | Document the mode reorganization |
| `AGENTS.md` | Update ph_mode descriptions |

### Part 5: Risks and mitigations

1. **Coarse USampler accuracy loss**: The 4x coarser grid may lose accuracy
   at extreme tau or small `a`. Log-space interpolation mitigates this.
   Grid-search fallback if needed.

2. **Humlicek on GPU**: Complex arithmetic via float2_t is standard. All
   operations map to native float ops. No special functions needed.

3. **MUSA 20 KiB const mem**: Table is 56 KiB, exceeds MUSA limit. If MUSA
   is needed, fall back to global memory (use `malloc_device` instead of
   `malloc_const`). This is a secondary concern (current dev is HIP).

4. **Constant memory exhaustion**: The pool is shared. If other modules
   already use const mem, `malloc_const` may throw "const oversize". Check
   `device.cpp:50-51`. Mitigation: catch and fall back to global mem.

## Verification

- Build: `make USRDIR=usr_ext/line_rt -j8` in `~/apps/kratos_line_rt/`
- Test: `cd ~/scratch/line_rt && python3 test_scaling_wide.py --ph-mode-list 0,1,2`
- Check: med|x|/Neufeld within +/-5% at a*tau0 >= 100 for all three modes
