# Test C — Escape spectrum vs tau0

**Pipeline commit:** `b9dda65`
**Kratos usr_ext:** `d335aef` (gen.h sv=sigma)

## Purpose

Verify that the velocity distribution depends on tau0 (the real concern behind "f_esc=1.0 for all tau0").

## Setup

- `mfp_i_sca_0 = tau0 / L_slab`, `mfp_i_abs_0 = 0` (pure scattering)
- `b_sca = 1e5`, `a_voigt = 0.01`, `ph_mode = 2` (old Gaussian CFR)
- `n_source = 20000-50000`, `n_cell = (55, 2, 2)`
- tau0 ∈ {10, 30, 100, 300, 1000, 3000, 10000}

## Results

| tau0 | n_esc | HWHM | x_pred | ratio |
|------|-------|------|--------|-------|
| 10   | 20000 | 1.21 | 0.41   | 2.97  |
| 30   | 20000 | 1.42 | 0.59   | 2.41  |
| 100  | 20000 | 1.63 | 0.88   | 1.86  |
| 300  | 20000 | 1.93 | 1.27   | 1.52  |
| 1000 | 30000 | 2.39 | 1.90   | 1.26  |
| 3000 | 50000 | 2.80 | 2.73   | 1.02  |
| 10000| 50000 | 3.20 | 4.08   | 0.78  |

**HWHM growth exponent β (per tau0-decade):** 0.11–0.17 (Neufeld predicts 1/3 ≈ 0.333).

## Key finding

- At low τ₀: HWHM **overshoots** Neufeld (ratio > 1) — photons escape too easily
- At high τ₀: HWHM **undershoots** Neufeld (ratio < 1) — insufficient trapping
- The spectrum grows too slowly with τ₀ (β ≈ 0.15 vs expected 1/3)
- This is the same failure seen in neufeld_test.py

## Conclusion

Spectra DO depend on τ₀ (HWHM increases monotonically), confirming scattering is working. But the HWHM vs τ₀ scaling is wrong — photons appear to escape too easily at low τ₀ and too slowly at high τ₀, suggesting the effective trap is weaker than Neufeld's model.
