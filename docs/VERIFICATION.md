# Verification: Line RT Pipeline Validation Suite

**Document purpose.** This document provides paper-ready descriptions
of all validation tests, their methodology, golden values, and
results. It serves as source material for the paper's Verifications
section.

---

## 1. Test Suite Overview

The line RT pipeline is validated through a multi-layered test suite:

| Test | Location | Validates | Reference |
|------|----------|-----------|-----------|
| Escaped spectrum scaling | `kratos/usr_ext/line_rt/tests/test_scaling_wide.py` | R_IIA redistribution, Neufeld `med|x|` | Neufeld (1990) eq. 2.24 |
| Imaging double-peak scaling | `kratos/usr_ext/line_rt/tests/test_scaling_image.py` | Imaging `s_cam`, formal ray tracing | Neufeld (1990) eq. 2.24 |
| Absorption + scattering | `kratos/usr_ext/line_rt/tests/test_absorption_scattering.py` | Dust absorption + line scattering | Python reference MCRT |
| Thin-slab normalization | `line_rt_pipeline/tests/test_imaging_normalization.py` | Emission seed, photon weights, `i_conv` | Analytic $I = j L$ |
| Pipeline imaging (Neufeld) | `line_rt_pipeline/tests/test_imaging_neufeld.py` | Full pipeline imaging vs Neufeld | Neufeld (1990) |
| Emission weights | `line_rt_pipeline/tests/test_emission_weights.py` | Photon-number normalization, `vel` convention | $n_u A_{ul} V$ |
| Collisional rates | `line_rt_pipeline/tests/test_equilibrium.py` | Level populations, collisional equilibrium | Statistical equilibrium |
| Source types | `line_rt_pipeline/tests/test_add_source.py` | Slab/point sources, `vel_range`, `r_random` | Unit tests |

All tests are standalone (no pipeline imports for Kratos-side tests;
pipeline tests use the installed package).

---

## 2. Escaped Spectrum: Neufeld Scaling

### 2.1 Test: `test_scaling_wide.py`

**Purpose.** Validate that the R_IIA redistribution kernel produces the
correct escaped-photon spectrum scaling with optical depth, as
predicted by Neufeld (1990) eq. (2.24).

**Geometry.** Plane-parallel slab, $n_{\rm cell} = 128 \times 2 \times 2$,
$L = 1$ AU (code units). Isotropic midplane source at $x = 0$
(emitting in $\pm x$). Free $x$-boundaries, periodic $y, z$.

**Parameters.**
- $a = 0.149$ (Voigt damping, CO-like)
- $b = 10^5$ cm/s (Doppler, giving $T \approx 1684$ K for CO)
- $\tau_0 \in [200, 500, 2000, 8000, 32000]$ (mean-depth convention)
- $N_{\rm photon} = 10^5$ per $\tau_0$
- ph_modes: 1 (global-mem R_IIA), 2 (const-mem R_IIA), 3 (approx.)

**Convention.** Mean-depth $\tau_m = \lambda_{\rm sca}^{-1} \sqrt{\pi} L / 2$
(Neufeld's $\tau_0$). NOT the Verhamme (2006) line-centre convention
(which assumes $H(a,0)=1$ and fails for $a \gtrsim 0.1$).

**Neufeld prediction.** Peak at $|x_{\rm peak}| = 0.881 (a\tau_0)^{1/3}$.

**Golden values** (ph_mode 2, $N = 10^5$, PASS within 5%):

| $\tau_0$ | $a\tau_0$ | Neufeld peak | `med|x|` | `med/N` | PASS |
|-----------|-----------|-------------|-----------|---------|------|
| 200       | 30        | 2.731       | 3.115     | 1.14    | ✓    |
| 500       | 74        | 3.707       | 4.025     | 1.09    | ✓    |
| 2000      | 298       | 5.885       | 6.148     | 1.04    | ✓    |
| 8000      | 1192      | 9.341       | 9.736     | 1.04    | ✓    |
| 32000     | 4768      | 14.828      | 15.711    | 1.06    | ✓    |

**Mode comparison.** Modes 1 and 2 agree to ~1–2% in `med|x|`.
Mode 3 underestimates at low $a\tau_0$ (0.77–0.94× Neufeld for
$a\tau_0 = 30$–$1192$), converging at high $a\tau_0$.

**PASS criterion.** $|{\rm med}|x| / {\rm golden} - 1| \leq 5\%$.
Exit code 0 = all pass.

**Output.** `scaling_wide_med.png` (log-log: Neufeld line + data points
per ph_mode), `scaling_wide_hist.png` (per-$\tau_0$ histograms).

---

## 3. Imaging Double-Peak: Neufeld Scaling

### 3.1 Test: `test_scaling_image.py`

**Purpose.** Validate that the two-step imaging scheme produces
velocity-resolved channel maps whose double-peak scales with
$(a\tau_0)^{1/3}$, consistent with Neufeld.

**Geometry.** Same as `test_scaling_wide.py` (isotropic midplane
source, plane-parallel slab).

**Camera.** Along $+x$ ($\theta = \pi/2, \phi = 0$),
$n_{\rm chan} = 32$, adaptive half-range
$v_{\rm chan} = \max(10^5, 3 \times x_{\rm peak} \times b)$ cm/s.

**Golden values** (ph_mode 2, $N = 10^5$):

| $\tau_0$ | Imaging $|x_{\rm peak}|$ | Neufeld | img/N | PASS |
|-----------|--------------------------|---------|-------|------|
| 200       | 2.30                     | 2.73    | 0.84  | ✓    |
| 500       | 3.13                     | 3.71    | 0.84  | ✓    |
| 2000      | 6.07                     | 5.89    | 1.03  | ✓    |
| 8000      | 9.63                     | 9.34    | 1.03  | ✓    |
| 32000     | 15.29                    | 14.83   | 1.03  | ✓    |

**PASS criterion.** $|x_{\rm peak} / {\rm golden} - 1| \leq 10\%$.

**Physics note.** At low $\tau_0$, the imaging peak is slightly inside
the Neufeld prediction because $I(x) = S(x)(1 - e^{-\tau})$ has no
$1/\tau$ penalty (unlike the escaped spectrum $F(x) \propto S(x)/\tau$).
The imaging peak converges to Neufeld at high $\tau_0$ where both
saturate.

**Output.** `scaling_image_peaks.png` (log-log scaling plot:
Neufeld line + escaped med + escaped peak + imaging peak),
`scaling_image_spectra.png` (per-$\tau_0$ panels: Neufeld $J(x)$ dotted
+ Imaging $I(x)$ solid + Escaped $F(x)$ dashed histogram + peak vlines).

---

## 4. Absorption + Scattering

### 4.1 Test: `test_absorption_scattering.py`

**Purpose.** Validate Kratos line RT when both scattering and dust
absorption are present, against a Python reference MCRT.

**Geometry.** Plane-parallel slab with varying scattering and
absorption optical depths.

**Validation.**
1. Kratos vs inlined Python reference MCRT (numba-accelerated).
2. Neufeld approximate escape fraction
   $f_{\rm esc} = 1/\cosh(Y_0)$ (eq. 4.33), where $Y_0$ is the
   Sobolev-type optical depth parameter.

**Result.** Kratos agrees with the Python reference within ~1.6×.
The Neufeld cosh formula overestimates $f_{\rm esc}$ at intermediate
depth — this is expected (the Fokker-Planck approximation underlying
the cosh formula breaks down when $a\tau_0$ is not large).

---

## 5. Thin-Slab Normalization

### 5.1 Test: `test_imaging_normalization.py`

**Purpose.** Validate the imaging normalization (emission seed, photon
weights, `i_conv` conversion factor) in the optically thin limit where
$I = j_\nu \times L$.

**Three tests:**

1. **Thin slab (emission-only):** $I(x) = j_\nu \phi(x) L$.
   Expected: `cube_cgs / expected = 1.0 ± 0.1%`.
2. **Scattering slab:** external continuum source through thin slab.
   Expected: `cube_cgs` matches the scattering source function.
3. **Absorbing slab:** slab with finite absorption. Expected: `cube_cgs`
   matches $I = S (1 - e^{-\tau})$.

**Key formulas validated:**
- Emission photon proper weights: $\sum w_{\rm pp} = n_u A_{ul} V_{\rm cgs}$
- Emission seed: $S_{\rm em} = j / (\alpha \sqrt{\pi} b)$
- Image cube CGS conversion: $I_{\rm cgs} = I_{\rm code} / (\ell_0^3 t_0)$

---

## 6. Velocity Convention

### 6.1 Test: Doppler Shift in Imaging

**Setup.** Bulk velocity $v_{\rm bulk} = +0.5$ km/s along $x$.
Camera along $+x$ ($\theta = \pi/2, \phi = 0$).

**Convention.**
- `vel_obs = \hat{n} \cdot \mathbf{v}_{\rm bulk} = +0.5` km/s
- `dv = vel + vel_obs` (gas-frame offset)
- Resonant frequency for camera: `dv_cam = v_chan + vel_obs`
- Peak at `dv_cam = 0` → `v_chan = -0.5` km/s (blueshift)

**Result.** Imaging peak shifts from channel 15/16 (v ≈ 0) to
channel 12 (v ≈ −4.5 × 10⁴ cm/s), matching the expected
−5 × 10⁴ cm/s shift within one channel width (±1.3 × 10⁴ cm/s).

---

## 7. Collisional Rates and Populations

### 7.1 Test: `test_equilibrium.py`

**Purpose.** Validate the statistical equilibrium solver and
collisional rate handling.

**Tests:**
1. Two-level atom: LTE populations at given $T$, $n_{\rm coll}$.
   Expected: $n_u/n_l = (g_u/g_l) \exp(-h\nu/kT)$.
2. Multi-level (LAMDA CO): collisional equilibrium with H₂.
   Expected: populations match LAMDA reference at low density (critical
   density check).
3. Collisional destruction: $\epsilon = C n / (A + C n)$ added to
   `mfp_i_abs_0`.
4. User-defined collision rates: `TransitionInfo.user_defined(collision_rates=...)`.

---

## 8. Emission Photon Weights

### 8.1 Test: `test_emission_weights.py`

**Purpose.** Validate that emission photons carry photon-number
proper weights (photons/s, not energy-weighted).

**Tests:**
1. Sum of proper weights = $n_u A_{ul} V_{\rm cgs}$ (exactly).
2. `vel = vel_draw - v_bulk \cdot \hat{n}` (thermal draw minus bulk
   Doppler projection). Gas-frame: `dv = vel + vel_obs = vel_draw`.
3. Emissivity = $n_u A_{ul} / (4\pi)$ (photon-number, NOT energy).

---

## 9. Python Reference MCRT

### 9.1 `docs/reference_mcrt/mcrt.py`

A standalone numba-accelerated Python MCRT code for validation:
- 1D plane-parallel geometry (x-only)
- ph_mode 1: USampler table-lookup R_IIA
- No bulk velocity (static medium)
- Validates against Neufeld (1990) via `plot_neufeld.py`

**Use case:** Independent cross-check of Kratos R_IIA implementation.
The reference MCRT uses the same USampler CDF but a different code
path (Python + numba vs CUDA).

---

## 10. Reproducibility

### Running the full suite

```bash
# Kratos-side tests (standalone, from ~/apps/kratos_line_rt)
cd ~/apps/kratos_line_rt/usr_ext/line_rt/tests
python3 test_scaling_wide.py --kratos-root ~/apps/kratos_line_rt
python3 test_scaling_image.py --kratos-root ~/apps/kratos_line_rt --plots

# Pipeline tests (installed package)
cd ~/Seafile/seafile_sync/code/line_rt_pipeline
python3 -m pytest tests/ -v

# Neufeld reference (Python MCRT)
cd /dev/shm/line_rt
python3 ~/Seafile/seafile_sync/code/line_rt_pipeline/docs/reference_mcrt/plot_neufeld.py
```

### Golden value files

Golden values are embedded in the test scripts as Python dictionaries.
Updates require a `--measure` run to re-measure, followed by manual
verification against Neufeld predictions before updating the golden
table.
