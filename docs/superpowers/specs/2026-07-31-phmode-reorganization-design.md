# ph_mode Reorganization: Merge + Constant-Memory USampler + Coarse Voigt Table

**Date:** 2026-07-31
**Status:** Approved (revised: drop Humlicek, use coarse 1D Voigt table)
**Scope:** Kratos `usr_ext/line_rt` (C++) + pipeline test scripts (Python)

## Motivation

Validation proved ph_mode=1 (USampler v1, `n_u=1201, du=0.01`) and ph_mode=2
(USampler v2, `n_u=2401, du=0.005`) are statistically identical
(med|x| agree within 0.1-1.3%, both within Poisson noise). The v2 grid provides
zero measurable benefit at 2.3x the memory cost.

The new ph_mode=2 targets constant-memory tables for both USampler and Voigt,
eliminating global-memory allocations and frees. The Humlicek analytic Voigt
was considered but dropped: it would require double-precision (`float2_t` =
`double` under PRECISION=1) on the GPU for adequate accuracy, and consumer GPUs
have poor FP64 throughput. Instead, a coarse **1D** Voigt table (fixed `a_voigt`
per run) fits alongside the USampler in the 60 KiB constant-memory pool, using
`float` throughout.

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

### Part 2: New ph_mode=2 - coarse USampler + coarse 1D Voigt, both in const mem

#### Constant-memory budget

GPU constant-memory pool: **60 KiB** (CUDA/HIP, `cuda.cpp:32`, `hip.cpp:18`),
20 KiB (MUSA). The pool is a bump allocator (`device.cpp:45-54`); allocations
are never freed.

**Budget allocation (60 KiB = 61,440 bytes):**

| Component | Grid | Floats | Bytes |
|-----------|------|--------|-------|
| USampler log-CDF | 251 x 40 | 10,040 | 40,160 |
| USampler xg | 40 | 40 | 160 |
| Voigt 1D log-H(a,u) | 5,000 | 5,000 | 20,000 |
| **Total** | | **15,080** | **60,320 (58.9 KiB)** |

Fits with ~1 KiB headroom. All `float` (FP32), no double on GPU.

#### 2a: Coarse log-space USampler table

**Grid parameters:**
- `n_u = 251`, `du = 0.048`, `u_max = 6.0` (covers [-6, 6], ~4x coarser than v1)
- `n_xg = 40` (18 linear 0-8 + 22 log 8-300, ~4x coarser than v1's 180)
- Total: 251 x 40 = 10,040 floats = 39.2 KiB + xg 40 x 4 = 160 B

**Log-space storage:**
The CDF has huge dynamic range (especially at small `a` and large `|x|`).
Store `log(CDF)`:
- Build CDF as before (FP64 prefix sum + normalize on host - the `float2_t`
  double is used ONLY on the host during table construction, never on GPU)
- Floor: `log_cdf[k] = logf(fmaxf(cdf[k], 1e-38f))` (range ~-87 to 0)
- xg stored in linear space (coordinate, not probability)

**Inverse CDF lookup in log-space (device, all `float`):**
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

**Allocation:** Use `dev.malloc_const`/`dev.f_cc` (raw pointers, same pattern
as current `dev.malloc_device`/`dev.f_cp`, just swapping to const pool):
```cpp
d_logcdf_c = (float_t *)dev.malloc_const<char>(n_total * sizeof(float_t));
d_xg_c     = (float_t *)dev.malloc_const<char>(n_xg   * sizeof(float_t));
dev.f_cc(d_logcdf_c, h_logcdf, n_total * sizeof(float_t));
dev.f_cc(d_xg_c,     h_xg,     n_xg   * sizeof(float_t));
```
In `finalize()`: do NOT free const-mem pointers (the pool is managed by the
system bump allocator, `device.cpp:45-54`).

#### 2b: Coarse 1D Voigt table in constant memory

**Key insight:** `a_voigt` is fixed per run. The current 2D table
`(log_a, u)` is overkill. A 1D table `H(a_fixed, u)` suffices.

**Grid:** `n_vu = 5000`, uniform in `u` from 0 to `u_voigt_max` (default 50,
covering the Lorentz wing; the Gaussian core decays by `u ~ 3`). du = 0.01.
Total: 5,000 floats = 19.5 KiB.

**Log-space storage:** `log_H[k] = logf(fmaxf(H(a, k*du), 1e-38f))`.
The Voigt profile spans many orders of magnitude (Gaussian core ~exp(-u^2)
drops below 1e-38 at u ~ 4.3; Lorentz wing ~1/u^2 is still >1e-38 at u=50).
Log-space ensures smooth interpolation across the core-wing transition.

**Lookup (device, all `float`):**
```
// u >= 0 (H is even in u)
float x = fminf(fabsf(u), u_voigt_max);
int k = (int)(x / du_voigt);
k = max(0, min(k, n_vu - 2));
float f = (x - k * du_voigt) / du_voigt;
float log_h = log_H[k] + f * (log_H[k+1] - log_H[k]);
float h = expf(log_h);  // guard: log_h in [-87, 0], no overflow
```

**Build (host, using `float2_t` = double for accuracy):**
- Use the existing `voigt_profile()` from `gen_voigt_table.py` (scipy
  `voigt_profile(u, sigma=1, a)` = raw Hjerting H(a,u), already verified).
- Or implement Humlicek w4 on the host (FP64 is fine on host) and store the
  result in the 1D table. This keeps the table accurate while avoiding
  FP64 on GPU.

**Dispatch:** `intg_t::voigt_H(a, u)` checks ph_mode:
- `ph_mode == 0 || ph_mode == 1`: existing 2D table lookup (unchanged)
- `ph_mode == 2`: 1D const-mem table lookup (ignores `a` argument; uses the
  pre-built table for the run's fixed `a_voigt`)

When `ph_mode == 2`, the 2D Voigt table (`voigt_table_data.h`,
`voigt_interp`) is NOT loaded (skip `setup`/`to_device` in `init()`).

#### 2c: ph_mode summary after reorganization

```
ph_mode=0: CFR (Gaussian) + 2D Voigt table (global mem, 128 KiB)
ph_mode=1: R_IIA (USampler v1, global mem, 865 KiB) + 2D Voigt table (global mem, 128 KiB)
ph_mode=2: R_IIA (coarse USampler, const mem, 39 KiB, log-space)
         + 1D Voigt table (const mem, 20 KiB, log-space)
         Total const mem: 59 KiB (fits in 60 KiB pool)
```

### Part 3: Testing

Use existing `test_scaling_wide.py --ph-mode-list 0,1,2` (already supports
ph_mode list overlay). Compare all three modes against Neufeld analytic at
`a=0.149`, `tau0 in {200, 500, 2000, 8000, 32000}`, `N=100000`.

**Success criteria:** med|x|/Neufeld within +/-5% for all modes at `a*tau0 >= 100`.

If the coarse USampler loses accuracy, grid-search:
- `n_u in {201, 251, 301}`
- `n_xg in {31, 40, 47}`

to find the minimum that maintains +/-5%, rebalancing the Voigt table size
(`n_vu`) to stay within the 60 KiB budget.

### Part 4: Files touched

| File | Change |
|------|--------|
| `usr_ext/line_rt/intg.h` | Delete v2 code; add coarse USampler (const mem, log-space); add 1D Voigt table (const mem, log-space); conditional table loading by ph_mode |
| `usr_ext/line_rt/photon.h` | Remove old ph_mode==2 branch in `scat()`; `voigt_H` dispatches to 1D const table for ph_mode==2 |
| `usr_ext/line_rt/gen.h` | No change (ph_mode passes through) |
| `usr_ext/line_rt/voigt_table_data.h` | No change (still used by ph_mode=0,1) |
| `tests/test_scaling_wide.py` | Update `--ph-mode-list` default if needed |
| `docs/debug/debug.md` | Document the mode reorganization |
| `AGENTS.md` | Update ph_mode descriptions |

### Part 5: Risks and mitigations

1. **Coarse USampler accuracy loss**: The 4x coarser grid may lose accuracy
   at extreme tau or small `a`. Log-space interpolation mitigates this.
   Grid-search fallback if needed (rebalance n_u / n_xg / n_vu).

2. **1D Voigt table accuracy**: The 1D table at du=0.01 matches the current
   2D table's u-resolution (VOIGT_NU=512 over [0, 50] -> du=0.098, so 1D is
   actually finer). Log-space interpolation handles the core-wing transition.

3. **MUSA 20 KiB const mem**: Table is 59 KiB, exceeds MUSA limit. If MUSA
   is needed, fall back to global memory (use `malloc_device` instead of
   `malloc_const`). This is a secondary concern (current dev is HIP).

4. **Constant memory exhaustion**: The pool is shared. If other modules
   already use const mem, `malloc_const` may throw "const oversize". Check
   `device.cpp:50-51`. Mitigation: catch and fall back to global mem.

5. **`a_voigt` runtime variability**: The 1D Voigt table is built per-run
   for the specific `a_voigt`. If `a_voigt` changes between cycles (e.g.,
   temperature-dependent Voigt), the table must be rebuilt. Currently
   `a_voigt` is a par-file constant, so this is not an issue.

## Verification

- Build: `make USRDIR=usr_ext/line_rt -j8` in `~/apps/kratos_line_rt/`
- Test: `cd ~/scratch/line_rt && python3 test_scaling_wide.py --ph-mode-list 0,1,2`
- Check: med|x|/Neufeld within +/-5% at a*tau0 >= 100 for all three modes
