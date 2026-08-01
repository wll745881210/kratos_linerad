# Test B — Compare ph_mode=1 vs ph_mode=2

**Pipeline commit:** `b9dda65`
**Kratos usr_ext:** `d335aef` (gen.h sv=sigma)

## Purpose

Isolate whether the Neufeld failure is in the new Voigt table / R_IIA code (ph_mode=1 only) or fundamental (both modes).

ph_mode=2 uses the old Gaussian CFR + analytic Voigt and SHOULD match old behavior.

## Setup

- `mfp_i_sca_0 = tau0 / L_slab`, `mfp_i_abs_0 = 0` (pure scattering)
- `b_sca = 1e5`, `a_voigt = 0.01`, `L_slab = 1 AU`
- `n_source = 20000`, `n_cell = (55, 2, 2)`
- tau0 ∈ {10, 100, 1000}

## Results

| tau0 | f_esc(1) | f_esc(2) | hwhm(1) | hwhm(2) | x_pred |
|------|----------|----------|---------|---------|--------|
| 10   | 1.0000   | 1.0000   | 0.75    | 1.26    | 0.41   |
| 100  | 1.0000   | 1.0000   | 0.94    | 1.60    | 0.88   |
| 1000 | 1.0000   | 1.0000   | 1.64    | 2.39    | 1.90   |

**f_esc = 1.0 is expected** for pure scattering — all photons eventually escape.

**HWHM increases with τ₀** for both modes → scattering IS happening. The velocity distribution broadens as expected for higher optical depth.

**ph_mode=2 gives larger HWHM** than ph_mode=1 at all τ₀, indicating different redistribution physics (ph_mode=1 keeps wing-coherent photons, producing narrower spectra).

## Conclusion

**Both modes show qualitatively similar behavior** — scattering works but doesn't match Neufeld (1990) scaling quantitatively. The bug is NOT isolated to the ph_mode=1 Voigt table / R_IIA code. The root cause is fundamental (gen.h sv init, b_sca scaling, or other changes common to both modes).

Note: Neufeld predicts x_peak ≈ 0.41, 0.88, 1.90 for these τ₀. Neither mode matches — ph_mode=2 overshoots, ph_mode=1 undershoots.
