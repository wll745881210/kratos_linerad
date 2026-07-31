# MCRT validation: Kratos vs Python reference

This document records the debugging journey and final validation
results for the Kratos line_rt module against a Python reference
MCRT code and the Neufeld (1990) analytic solution.

---

## Timeline of bugs found and fixed

### Bug 1: Field/mesh grid mismatch (Kimi agent, Jul 27)

**Symptom:** Kratos produced 0 escaped photons in slab geometry.

**Root cause:** The Python test script wrote field binary grids with
y/z extents `[0, 0.0156]` while the par file mesh had y/z extents
`[0, 1]`.  `radiation.h:set_fill(0)` then returned zero opacity for
all cells because the field grid did not cover the mesh.

**Fix:** Use `set_nearest()` instead of `set_fill(0)` (clamps
out-of-grid queries to the nearest edge value instead of returning
zero).  Also match field grid extents to mesh extents in all
generating scripts.

**Status:** Fixed, but this was not the main cause of the residual
gap.

---

### Bug 2: `geo_loc_t::fix` convergence loop (Kimi agent, Jul 27)

**Symptom:** Photons got stuck at domain boundaries, producing
incorrect escape statistics.

**Root cause:** Commit `efda9c2` introduced a convergence loop in
`geo_loc_t::fix` (particle_base.h) that incremented `par.i[a]` on
each iteration. Actually the integrator's proc_geo marches indices.
After 8 iterations (later reduced to 3 in `ff914e1`),
the cell index could overshoot, leaving the photon in an invalid cell.

**Fix (commit `13dd8bd`, Jul 30):** Reverted to a two-pass approach:

1. First pass: shift position only (no `par.i` increment) for
   out-of-bounds axes.
2. Second pass: if still out of bounds, shift AND increment
   `par.i[a]` by ±1.

**Status:** Fixed.

---

### Bug 3: `vel += x_new * b_sca` accumulation (Jul 30)

**Symptom:** Kratos R_IIA (ph_mode=1) gave 8-11% gap vs Python at
all optical depths.  FP32 vs FP64 testing showed identical results,
ruling out precision.

**Root cause:** `photon.h:201,230` used `vel += x_new * b_sca`
(accumulates velocity across scatters), while Python used
`vl = _scatter_riia_usampler(...) * b_cell` (sets velocity fresh
each scatter).  After N scatterings, Kratos vel =
`(x_new1 + x_new2 + ... + x_newN) * b_sca`, corrupting both the
frequency (`x_freq = vel / b_sca`) and the opacity
(`u = |vel| / b_sca`).

**Fix:** Changed to `vel = x_new * b_sca` (both ph_mode=1 and
ph_mode=2).  Also rewrote the entire `photon.h:scat()` function
(commit `0910346`).

**Status:** Fixed.

---

### Bug 4: `n_scat` par file misconfiguration (Jul 31)

**Symptom:** Single-scatter test (intended n_scat=1) showed +24.5%
gap: Kratos med|x|=0.589 vs Python 0.473.

**Root cause:** The par file had `n_scat = 2` instead of `n_scat = 1`.
Kratos allows up to N scatters when `n_scat = N`, so with n_scat=2
some photons scattered twice, broadening the spectrum.  Python's
n_scat=1 result was 0.473, n_scat=2 was 0.615, and Kratos 0.589 fell
between (effectively ~1.5 scatters on average).

**Fix:** Set `n_scat = 1` in the par file.

**Result:** Gap dropped from +24.5% to -0.12%.

**Status:** Fixed.

---

### Bug 5: Voigt profile normalization mismatch (Jul 31) — ROOT CAUSE

**Symptom:** Unlimited-scatter test showed +14.45% gap even after
all previous fixes.  Single-scatter test was fine (-0.12%), proving
the R_IIA kernel was correct.  The issue was in the transport
opacity.

**Root cause:** The Voigt profile table in `voigt_table_data.h` was
**peak-normalized**: `table[u] = voigt_profile(u, 1/√2, a) /
voigt_profile(0, 1/√2, a)`, giving `opacity(0) = mfp_i_sca_0 × 1.0`.

The Python reference (`mcrt.py:voigt_H`) and the fiducial code
(`neufeld_mc.py`) both use the raw Hjerting function
`H(a,u) = Re[w(u + ia)]`, giving `opacity(0) = mfp_i_sca_0 × H(a,0)`.

For a = 0.5: `H(0.5, 0) = 0.6157`, so Kratos was **1.624× more
opaque** than Python at line centre.  The predicted peak overestimate
is `(1.624)^(1/3) - 1 = +17.5%`, matching the observed +14-25% gap.

**Fix:** Changed `gen_voigt_table.py` from:

```python
table[u] = voigt_profile(u, sig, a) / voigt_profile(0, sig, a)
```

to:

```python
table[u] = voigt_profile(u, sig, a) * np.sqrt(np.pi)
```

This gives the raw Hjerting `H(a,u) = Re[w(u + ia)]`, matching
Python's `voigt_H`.  Regenerated `voigt_table_data.h` and rebuilt
Kratos.

**Result:** Unlimited-scatter gap dropped from +14.45% to -1.31%.

**Status:** Fixed.

---

### Bug 6: Half-slab τ bookkeeping in scaling tests (Jul 31)

**Symptom:** The wide-scaling sweep (`tests/test_scaling_wide.py`,
a=0.5, τ₀_fid ∈ {200, 500, 2000, 8000, 32000}) showed a **constant**
factor ~0.79 between both MCs (Kratos and Python, which agreed with
each other to 1-3%) and the Neufeld analytic curve.  The ratio was
flat across all aτ₀ (100-16000), ruling out statistical noise or
finite-slab effects.

**Root cause:** Two compounding τ-convention errors in the test script
(not in the physics code).  Both were documented as pitfalls in the
fiducial study (`~/scratch/line_rt/fiducial/neufeld_test.md` §2.3, §6,
§9), which the test had not consulted.

1. **Factor-2 (half-slab vs full-slab).**  Both codes use the
   raw-Hjerting opacity `κ(x) = mfp_i_sca_0 × H(a,x)` with
   `∫H(a,x)dx = √π` (Kratos `photon.h:203-207`, Python `mcrt.py:204-206`).
   The half-slab mean depth is therefore

       τ_m = mfp_i_sca_0 × √π × L_slab / 2 .

   The test set `mfp_i_sca_0 = tau0_lc / L_slab` with
   `tau0_lc = tau0_fid / √π`, giving `τ_m = tau0_fid / 2` — the MCs
   ran at **half** the intended optical depth.  The predicted ratio
   to the analytic is `2^(-1/3) = 0.7937`, exactly the observed
   constant ~0.79.

2. **Verhamme transcription assumes H(a,0)=1.**  The analytic helper
   used the Verhamme (2006) line-centre form (peak
   `1.066 (a τ_lc)^(1/3)`, cosh coefficient `√(π³/54)`), which is the
   Neufeld original with the substitution `τ_N = √π τ_lc`.  That
   substitution is only valid when the line-centre profile value
   `φ(0) = H(a,0)/√π` reduces to the Gaussian `1/√π`, i.e. `H(a,0)=1`.
   For a=0.5, `H(0.5,0) = e^{0.25} erfc(0.5) = 0.6156`, so the true
   relation is `τ_N = √π τ_lc / H(a,0)` (a 1.624× correction in τ).
   The fiducial docs flag this explicitly: *"H(a,0) = e^{a²}erfc(a):
   a≳0.1 时不可近似为 1, 影响线心深度换算"*.

**Fix (`tests/test_scaling_wide.py`):**

- `mfp_i_sca_0 = 2 × tau0_fid / (√π × L_slab)` so that `τ_m = tau0_fid`.
- Python `mcrt_slab(tau0 = 2 × tau0_fid / √π)` (its `tau0` arg is
  `mfp × L_slab`).
- Replaced the Verhamme line-centre analytic (`neufeld_peak_lc`,
  `neufeld_J_lc`) with the Neufeld **original eq. (2.24)** in the
  mean-depth convention:

      J(x) = (√6/24) × x²/(aτ₀) / cosh[(π⁴/54)^(1/2) × |x³|/(aτ₀)]

  peak `0.881 (aτ₀)^(1/3)`, evaluated with `τ₀ = tau0_fid`.  This is
  convention-independent (depends only on the frequency-integrated
  optical depth, not on `H(a,0)`).

**Result (a=0.5, N=10000, 5-point sweep):**

| τ₀    | aτ₀   | Neufeld peak | K med\|x\| | P med\|x\| | K/N (med) | P/N (med) |
| ----- | -----:| ------------:| ----------:| ----------:| ---------:| ---------:|
| 200   | 100   | 4.089        | 4.179      | 4.203      | 1.022     | 1.028     |
| 500   | 250   | 5.550        | 5.678      | 5.571      | 1.023     | 1.004     |
| 2000  | 1000  | 8.810        | 8.748      | 8.807      | 0.993     | 1.000     |
| 8000  | 4000  | 13.985       | 14.292     | 13.947     | 1.022     | 0.997     |
| 32000 | 16000 | 22.200       | 21.949     | 22.203     | 0.989     | 1.000     |

`med|x|` agrees with Neufeld within ±3% at all points (was constant
0.79 before).  The `x_peak` column (histogram argmax) is noisy at high
τ (single-bin outliers); `med|x|` is the robust statistic.  Plots in
`~/scratch/line_rt/scaling_wide_{xpeak,ratio,spectra}.png`.

**Note on the archived `test_scaling.py`:** it had the same latent
factor-2 (mfp = `tau0/L_slab`), but at a=0.01 the effect is small
(`(√π/2)^(1/3) = 0.924`, ~4% in the asymptotic regime, previously
absorbed into the "<6% agreement" claim).  The H(a,0) issue is
negligible at a=0.01 (`H(0.01,0) = 0.9888`).

**Status:** Fixed.  No Kratos or Python physics change was needed —
both codes agreed with each other and with the fiducial; only the
analytic comparison was mis-calibrated.

---

## Verification: USampler tables are identical

To rule out the R_IIA redistribution kernel as a source of error,
both the Python and Kratos USampler CDF tables were built and sampled
with the same RNG seed:

- Python: `du=0.005, n_u=2401, n_xg=221`
- Kratos: `du=0.01, n_u=1201, n_xg=180`

Sampling `u_par` at `x=0` with identical random numbers:

- Python std = 0.4577
- Kratos std = 0.4576
- Ratio = 0.9997 (gap = -0.02%)

After a full R_IIA scatter at `x_freq=0`, both codes gave
`med|x| = 0.4676`.  **The kernel is NOT the issue.**

---

## RNG seed audit

With `[device] seed_rng = {seed}` added to the par file, Kratos
becomes reproducible (5.67% spread across seeds vs 0.08% without
seeding).  Five seeds tested at a=0.5, tau0_LC=1128.4,
unlimited scatter:

| Seed  | Kratos med\|x\| | Python med\|x\| | Gap%   |
| ----- | ---------------:| ---------------:| ------:|
| 1     | 8.5993          | 8.8171          | -2.47% |
| 42    | 8.9398          | 8.8632          | +0.86% |
| 100   | 8.7483          | 8.8344          | -0.97% |
| 777   | 9.0980          | 8.8853          | +2.39% |
| 12345 | 8.6174          | 8.9025          | -3.20% |

Mean gap: -0.68%, std: 2.07%.  Agreement is within statistical noise
for 5000 photons.

---

## Jul 31 afternoon session: ph_mode=2/3 (const-mem tables) + unified USampler

After the bugs above were fixed and the a=0.5 scaling sweep passed,
the R_IIA implementation was reorganized for speed and validated
against Neufeld eq. (2.24) at **a=0.149** (the LAMDA fiducial value)
in a wide `aτ₀` sweep (τ=200…32000, N=1e5, seed_rng=42).

### Unified USampler (all R_IIA modes share one table)

The old ph_mode=2 (USampler v2, fine grid `du=0.01, 1201×180`) was
**merged into ph_mode=1**. All R_IIA modes now use one coarse
log-space CDF table (251×40, `du=0.048`, `u_max=6`) with `free_dev_mem`
controlling whether `finalize` frees it:

- `ph_mode=1`: tables in **global memory** (debug; freed)
- `ph_mode=2`: same tables in the **constant-memory pool** (60 KiB
  bump allocator, never freed) + a 1D log-space Voigt table
  (5000 pts, `u∈[0,50]`) sampled from the host-side scipy 2D table
- `ph_mode=3`: const-mem USampler only; the scattering profile uses
  the approximate analytic `voigt_H` blend in `photon.h` (Gauss core
  + Lorentz wing crossover)

### Voigt evaluation saga (why not Humlicek)

Two analytic formulas were considered for an on-device Voigt profile:

- **TG2006** (Tepper-García 2006, rational): REJECTED — it is only
  valid for `a ≲ 1e-4`; at a=0.149 it gives H(a,0)=1.028 vs true
  0.852 (20.7% error).
- **Humlicek W4** (4-region, complex arithmetic): validated on host
  to 0.007% max error for a=0.01/0.149/0.5/1.0 (H(a,u)=Re[w(u+ia)]).
  Also dropped: under `PRECISION=1` the `float2_t` complex type is
  `double` on device, and FP64 complex arithmetic is slow on
  consumer GPUs.

**Final choice:** 1D Voigt table in constant memory (log-space,
5000 pts, built once on host by sampling the existing scipy 2D
`voigt_table_data` — no FP64 on device, no 128 KiB global-memory
2D table for ph_mode=2).

### Results (a=0.149, med|x|, golden table)

| τ | aτ₀ | pm1 | pm2 | pm3 | pm1/Neufeld | pm3/Neufeld |
|---|-----|-----|-----|-----|-------------|-------------|
| 200 | 30 | 3.1213 | 3.1148 | 2.0965 | 1.14 | 0.77 |
| 500 | 74 | 4.0350 | 4.0249 | 3.0330 | 1.09 | 0.82 |
| 2000 | 298 | 6.1552 | 6.1476 | 5.5094 | 1.05 | 0.94 |
| 8000 | 1192 | 9.7628 | 9.7357 | 8.9381 | 1.05 | 0.96 |
| 32000 | 4768 | 15.7006 | 15.7114 | 15.1140 | 1.06 | 1.02 |

(Neufeld peak = 0.881·(aτ₀)^(1/3); low-τ points sit in the
Doppler→wing transition where Neufeld is not valid.)

**Conclusions:**
- ph_mode=1 and ph_mode=2 agree to ~1% (identical `x_peak`); the
  coarse log-space table is lossless for R_IIA.
- ph_mode=3 underestimates `med|x|` by 6–23% for `aτ₀ ≲ 300`
  (the blend's H(0.149,0)=1.022 vs 0.852, a 20% line-center error),
  converging at high `aτ₀`. Use pm3 only when speed matters and
  accuracy at low aτ₀ is not critical.

### Regression test

`usr_ext/line_rt/tests/test_scaling_wide.py` — standalone (no
pipeline imports), self-contained golden table above, PASS/FAIL
exit code. Default WORKDIR `/tmp/line_rt_regress` (overridable with
`--workdir`), `--kratos-bin` required:

```bash
python3 test_scaling_wide.py --kratos-bin ~/apps/kratos_line_rt/bin/kratos
```

---

## Final validation results

### a=0 pure-Gaussian (ph_mode=0)

Plane-parallel slab: L_half = 5 code units, periodic y/z, isotropic
midplane source, 50000 photons.

| τ₀_half | mfp  | Kratos med\|x\| | Python med\|x\| | gap%  |
| ------- | ---- | ---------------:| ---------------:| -----:|
| 100     | 20   | 1.836           | 1.898           | 3.27% |
| 200     | 40   | 2.034           | 2.086           | 2.49% |
| 500     | 100  | 2.264           | 2.307           | 1.86% |
| 1000    | 200  | 2.446           | 2.464           | 0.72% |
| 2000    | 400  | 2.588           | 2.606           | 0.68% |
| 5000    | 1000 | 2.791           | 2.910           | 4.09% |
| 10000   | 2000 | 2.941           | 3.026           | 2.81% |

Agreement within 1-4% across τ₀=100-10000.  Gap is smallest (<1%) at
τ₀=1000-2000.

### R_IIA (ph_mode=1), a=0.01, unlimited scatter

| τ₀    | Kratos med\|x\| | Python med\|x\| | gap%   |
| ----- | ---------------:| ---------------:| ------:|
| 1000  | 2.787           | 2.792           | -0.18% |
| 10000 | 4.188           | 4.410           | -5.03% |

After the Voigt normalization fix, agreement at τ₀=1000 is excellent
(<0.2%).

### Single-scatter test (n_scat=1, a=0.5, τ₀_LC=1128.4)

| Code   | med\|x\| | mean\|x\| | n_escaped |
| ------ | --------:| ---------:| ---------:|
| Kratos | 0.5890   | 0.7374    | 5000      |
| Python | 0.4729   | 0.6097    | 5000      |
| Gap    | +24.5%   |           |           |

This was BEFORE the n_scat fix (par had n_scat=2).  After fix:
gap = -0.12%.

### Scaling test (a=0.01, unlimited scatter)

| τ₀     | aτ₀  | Kratos peak | Python peak | Neufeld peak | K/P   |
| ------ | ---- | -----------:| -----------:| ------------:| -----:|
| 1000   | 10   | 2.562       | 2.562       | 2.305        | 1.000 |
| 3000   | 30   | 3.062       | 2.938       | 3.325        | 1.043 |
| 10000  | 100  | 4.438       | 4.188       | 4.967        | 1.060 |
| 30000  | 300  | 5.438       | 5.812       | 7.163        | 0.935 |
| 100000 | 1000 | 7.188       | 9.312       | 10.700       | 0.772 |

At aτ₀=10-100, agreement is excellent (<6%).  At high aτ₀ (≥300),
both Kratos and Python fall below the Neufeld formula (expected:
finite slab effects).  At aτ₀=1000, the Kratos/Python gap grows due
to statistical noise from only 5000 photons at extreme τ.

---

## Summary of bugs and fixes

| #   | Bug                        | Symptom                   | Fix                                 | Commit    |
| --- | -------------------------- | ------------------------- | ----------------------------------- | --------- |
| 1   | Field/mesh grid mismatch   | 0 escaped photons         | `set_nearest()`, match grid extents | -         |
| 2   | `geo_loc_t::fix` overshoot | Photons stuck at boundary | Two-pass approach                   | `13dd8bd` |
| 3   | `vel +=` accumulation      | 8-11% R_IIA gap           | `vel = x_new * b_sca`               | `0910346` |
| 4   | `n_scat=2` in par file     | +24.5% single-scatter gap | Set `n_scat=1`                      | -         |
| 5   | Voigt peak-normalized      | +14.45% unlimited gap     | `voigt_profile * √π`                | -         |
| 6   | Half-slab τ bookkeeping    | constant 0.79× vs Neufeld | `mfp = 2τ/(√π L)`; Neufeld eq 2.24  | -         |

After all fixes: single-scatter gap -0.12%, unlimited-scatter gap
-1.31%, seed audit mean gap -0.68% ± 2.07%, wide-scaling sweep
(a=0.5) med|x| within ±3% of Neufeld eq. (2.24) at all aτ₀.

---

## Tools and scripts

| Script                       | Location               | Purpose                                                                        |
| ---------------------------- | ---------------------- | ------------------------------------------------------------------------------ |
| `test_scaling_wide.py`       | `usr_ext/line_rt/tests/` | Standalone Kratos regression: wide aτ₀ sweep, ph_modes 1/2/3, golden med\|x\|, PASS/FAIL (default WORKDIR `/tmp/line_rt_regress`) |
| `test_absorption.py`         | `tests/`               | Pure-absorption plane-parallel: f_esc vs E₂(τ/2)                               |
| `compare_escaped.py`         | `tests/archive/`       | (archived) Self-generating K-vs-P comparison                                   |
| `test_neufeld.py`            | `tests/archive/`       | (archived) Three-way: Kratos vs Python vs fiducial                             |
| `test_scaling.py`            | `tests/archive/`       | (archived) τ₀ scaling sweep (a=0.01, latent factor-2)                          |
| `test_ph_mode1_vs_python.py` | `tests/archive/`       | (archived) ph_mode=1 specific validation                                        |
| `mcrt.py`                    | `docs/reference_mcrt/` | Python reference MCRT (numba)                                                  |
| `plot_neufeld.py`            | `docs/reference_mcrt/` | Neufeld (1990) analytic solution                                               |
| `gen_voigt_table.py`         | `usr_ext/line_rt/`     | Generates `voigt_table_data.h`                                                 |

---

## Key source files

| File                                 | Role                                                 |
| ------------------------------------ | ---------------------------------------------------- |
| `usr_ext/line_rt/photon.h`           | Scattering physics (`scat`, `proc_geo`, `proc_phys`) |
| `usr_ext/line_rt/intg.h`             | Unified USampler (log-CDF, global/const mem) + Voigt tables |
| `usr_ext/line_rt/gen.h`              | Photon generation from binary                        |
| `usr_ext/line_rt/radiation.h`        | Field I/O, `init_cond`                               |
| `usr_ext/line_rt/block_data.h`       | `rad_t` struct, block I/O                            |
| `usr_ext/line_rt/pool.h`             | Escaped photon output                                |
| `usr_ext/line_rt/voigt_table_data.h` | Auto-generated Voigt table                           |
| `usr_ext/line_rt/gen_voigt_table.py` | Table generator script                               |

---

## Historical note

The file `attempt_record.md` in this directory is a 7702-line export
of a Kimi agent session (Jul 30) that attempted to debug the R_IIA
gap.  The agent investigated many hypotheses (USampler table, Voigt
profile, FP32/FP64, RNG) but never identified the two root causes
(n_scat misconfiguration and Voigt normalization).  The agent was
stopped at Turn 12.  The root causes were found by manual
single-scatter isolation testing on Jul 31.
