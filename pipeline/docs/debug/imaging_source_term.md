# Imaging Source Term Bug

## Bug

The imaging pass (Step 2 of the two-step imaging, `photon_img.h`)
used the formula:

```
S = (alpha_s / alpha_t) * s_cam[i,k]
I = I * exp(-dtau) + S * (1 - exp(-dtau))
```

where `alpha_s = mfp_i_sca_0 * H(a, x_out)` is the frequency-dependent
line opacity at the **outgoing** frequency.  Since `s_cam` (the MC
accumulation in `photon.h:proc_phys`) already contains the R_IIA
redistribution kernel `R(x_out; x_pp, g)` — which itself has a
frequency profile — multiplying by `H(a, x_out)` introduces a **spurious
extra line-profile factor** at the outgoing frequency.  The resulting
imaging spectrum is a double-Gaussian `exp(-2*x^2)` in the thin-slab
limit, instead of the correct single-Gaussian `exp(-x^2)`.

## Root Cause

The scattering emissivity is:

```
j(v_out) = n_l * sigma(v_in) * integral[ R(v_out; v_in, g) * J(v_in) ] dv_in dOmega
```

where `sigma(v_in) = sigma_0 * H(a, x_in)` is the cross-section at the
**incoming** frequency (where the photon is absorbed), and `R` is the
redistribution kernel (probability of scattering from `v_in` to `v_out`).

The old s_cam accumulation stored `R * J / b` (without `sigma(v_in)`),
treating `s_cam` as a source function `S = j/alpha`.  The imaging then
multiplied by `alpha_s = mfp_s * H(a, x_out)` to recover the emissivity:

```
j = alpha_s * S = mfp_s * H(a, x_out) * R * J / b
```

This uses `sigma(v_out) = sigma_0 * H(a, x_out)` instead of the correct
`sigma(v_in) = sigma_0 * H(a, x_in)`.  The extra `H(a, x_out)` factor
produces a double-Gaussian in the thin-slab limit (where `R` and `H`
have the same Gaussian form).

## Fix

### Phase 1: s_cam accumulation (`photon.h:proc_phys`)

Include `prof_s = H(a, x_pp)` in the s_cam accumulation, making `s_cam` an
**emissivity** (not a source function):

```
s_cam[i,k] += base * R(x_out, x_pp, g) * prof_s
```

where `prof_s = H(a_voigt, x_pp)` is the Voigt profile at the photon's
incoming frequency, and `base = flx * corr / (4*pi * b_sca)`.

### Phase 2: imaging pass (`photon_img.h:proc_phys`)

Use the line-centre opacity scale `mfp_s` (NOT `alpha_s = mfp_s * H(a, x_out)`)
to convert s_cam to emissivity:

```
j = mfp_i_sca_0 * s_cam[i,k]
I = I * exp(-dtau) + (j / alpha_t) * (1 - exp(-dtau))
```

where `alpha_t = mfp_s * H(a, x_out) + mfp_i_abs_0` is the total extinction
(used for the optical depth `dtau` and the formal solution, but NOT for
the emissivity conversion).

This gives: `j = mfp_s * [base * R * H(a, x_in)] = sigma_0 * n_l * H(a, x_in) * R * J = sigma(v_in) * R * J`.
Correct.

### Phase 3: Voigt table sharing (`rad_img.h:init`)

The imaging integrator has `build_tables=false` (avoids const-pool
overflow).  Previously, `voigt_H()` fell back to `max(exp(-u^2), a/(sqrt(pi)*(u^2+a^2)))`,
which has a **derivative discontinuity** at the Gaussian-Lorentzian
crossover (~|u| ~ 2-3 for a=0.149).  This kink appeared in the imaging
spectrum after Phase 2 (which divides by `prof(k)`).

Fix: share the Voigt table pointers from the scattering integrator in
`rad_img_t::init()` (after `base_t::init()`):

- ph_mode 0/1: copy `voigt_interp` (2D global-mem table, shallow struct copy)
- ph_mode 2: copy `d_log_voigt_c` (1D const-mem table, pointer copy)

Safety: `finalize()` does not free `d_log_voigt_c` (const-mem, system-managed)
or `voigt_interp` (never freed).  Imaging's `free_dev_mem=false`, so finalize
frees nothing.  No double-free risk.

## Verification

### Thin-slab test (`test_imaging_spectrum.py`)

A monochromatic source (x_in=0) through an optically thin slab, camera
perpendicular (g=0).  For a->0, the R_IIA kernel at g=0 is
`R(x; 0, 0) = exp(-x^2)/sqrt(pi)`, and the Voigt profile is
`H(a, x) = exp(-x^2)`.  The correct imaging spectrum is:

```
I(x) proportional to R(x; 0, 0) = exp(-x^2)     (single Gaussian)
```

The old formula gave `I(x) proportional to R(x) * H(x) = exp(-2*x^2)` (double
Gaussian, wrong width by sqrt(2)).

Results (a=0.01, tau0=0.01, 100K photons, ph_mode=2):
- Normalisation: 2.2% relative error (PASS)
- Shape: 0.4% max relative error (PASS)
- Doppler shift: peak correctly tracks `v_chan = -v_bulk` (PASS)

### Escaped-photon cone test (reviewer's §8)

The reviewer ran 10^7 photons through a thin slab and measured
`<x^2>` for escaped photons within a 10-degree cone of the camera
direction:

- MC transport: `<x^2> = 0.504 +/- 0.018` (single Gaussian, correct)
- Old imaging chain: `<x^2> = 0.2513` (double Gaussian, wrong by factor 2)

This confirmed the MC transport is correct; only the imaging chain had the
spurious extra profile factor.

### Neufeld imaging ladder (`test_scaling_image.py`)

Thick-slab runs at 5 optical depths, comparing imaging peak position
`|x_peak|` to the Neufeld (1990) prediction `0.881 * (a*tau0)^(1/3)`:

| tau0 | a*tau0 | Neufeld | x_img | img/N | x_esc | esc/N | Status |
|------|--------|---------|-------|-------|-------|-------|--------|
| 200  | 30     | 2.731   | 2.50  | 0.914 | 2.73  | 0.998 | PASS   |
| 500  | 74     | 3.707   | 3.39  | 0.914 | 3.94  | 1.064 | PASS   |
| 2000 | 298    | 5.885   | 5.38  | 0.914 | 5.59  | 0.949 | PASS   |
| 8000 | 1192   | 9.341   | 9.85  | 1.055 | 9.32  | 0.997 | PASS   |
| 32000| 4768   | 14.828  | 15.64 | 1.055 | 15.36 | 1.036 | PASS   |

All 5 PASS (10% golden tolerance).  Before the fix (with the old
double-H formula and kinked Voigt fallback), the results were:
img/N = 0.773, 0.633, 0.914, 0.984, 1.055 (2/5 FAIL).

## Remaining Limitations

1. **Two systematic regimes**: `img/N` clusters around 0.914 (low tau0,
   not fully thermalised) and 1.055 (high tau0, sigma_0 over-estimation).
   The 0.914 under-prediction at low tau0 is because the s_cam includes
   backward-scattered photons (g < 0) that contribute at line centre,
   pulling the imaging peak inward.  The 1.055 over-prediction at high
   tau0 is because `mfp_s` (line-centre opacity) overestimates `sigma(v_in)`
   for photons at the Neufeld escape frequency where `H(a, x_in) < 1`.

2. **Thermal seed per-channel emissivity** (Group 1, with `emiss`):
   the emission seed `S = emiss/(mfp_s * sqrt(pi) * b)` is a source
   function (frequency-independent).  The imaging converts it via
   `j = mfp_s * S = emiss/(sqrt(pi) * b)` (line-centre emissivity, no
   frequency profile).  The correct per-channel thermal emissivity should
   be `j(v_k) = emiss * H(a, v_k/b) / (sqrt(pi) * b)`.  This affects
   Group 1 runs (with `emiss`); Group 2 runs (no `emiss`, scattering only)
   are correct.

3. **R_IIA analytic fence**: the `g > 0.99` fence for the near-forward
   scattering kernel uses the analytic Gaussian form.  With `n_riia_g = 40`
   (spacing 0.05), this catches only the last grid point on each side.
   Trilinear interpolation between the broad Gaussian (g=0.95) and the
   delta-spike (g=1.0) may introduce small artifacts.
