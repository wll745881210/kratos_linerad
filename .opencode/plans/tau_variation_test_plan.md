# Tau Variation Test Plan (a=0) — for Kratos vs Python Reference Comparison

## Purpose
Quantify the escape-frequency distribution gap between Kratos (CUDA) and Python reference (mcrt.py) across τ₀ = 100…10000. Gap at τ₀=2000 is ~5.4% in median |x| (Kratos=2.375, Python=2.510). Test if gap scales with τ₀.

## Fixed Parameters (all runs)
| Parameter | Value | Notes |
|-----------|-------|-------|
| a (Voigt) | 0.0 | Pure Gaussian, ph_mode=0 |
| b_sca | 1.0e5 cm/s (CGS) → 6.6846e-09 (code) | Doppler width |
| L_slab | 1.49598e13 cm (1 AU) | unit_l0 = 1.49598e13 |
| L_half | 5.0 code | x ∈ [-5, 5] |
| unit_t0 | 1.0 s | |
| n_cell_y, n_cell_z | 2, 2 | periodic |
| boundary kinds | `fre fre per per per per` | x free, y/z periodic |
| n_photons | 50,000 | per run |
| source | midplane (x=0) | isotropic in half-space? |
| seed | 42 (Python) / Kratos RNG | |

## Tau Sweep Schedule

| τ₀ | mfp_i_sca_0 | n_cell_x | n_step (Kratos) |
|----|-------------|----------|-----------------|
| 100 | 20.0 | 32 | 5,000,000 |
| 200 | 40.0 | 32 | 5,000,000 |
| 500 | 100.0 | 32 | 5,000,000 |
| 1000 | 200.0 | 64 | 10,000,000 |
| 2000 | 400.0 | 64 | 20,000,000 |
| 5000 | 1000.0 | 128 | 50,000,000 |
| 10000 | 2000.0 | 256 | 50,000,000 |

**Note:** n_cell_x scaled to maintain ~1 cell per τ_unit at low τ, coarser at high τ (fixed max 256). n_step increased proportionally to τ₀ to allow enough scatterings.

## Execution

### Python Reference (mcrt.py) — Cell-Index Escape
```python
from docs.reference_mcrt.mcrt import mcrt_slab

res = mcrt_slab(
    n_cell=n_cell_x, L_slab=L_slab, tau0=tau0, tau_abs=0.0,
    b_sca=b_sca, n_photons=50000, ph_mode=0, a_voigt=0.0,
    seed=42, source='midplane', parallel=True
)
esc = res['escaped']  # [vel, proper, sigma] columns
vel = esc[:, 0]
x = vel / b_sca  # Doppler velocity → x_freq
med_abs_x = np.median(np.abs(x))
p_gt3 = np.mean(np.abs(x) > 3)
frac_esc = len(esc) / 50000
```

### Python Clone (transport_3d.py) — Position-Based Escape
```python
# My 3D tracer with xmin/xmax position escape
# Run with same parameters, compare both escape methods
```

### Kratos (CUDA, 1 thread/photon)
```bash
cd ~/scratch/line_rt
# Generate par file with correct mfp_i_sca_0_, b_sca_, n_cell_x
# Write field binary (fields_tauX.bin)
# Write photon binary (photons_tauX.bin) — 50000 isotropic from x=0
# Run: ~/apps/kratos_line_rt/bin/kratos a0_tauX.par
# Read output: photons_tauX.bin → vel column → x = vel / 6.6846e-09
```

## Output Metrics per Run
| Metric | Python Ref | Python Clone | Kratos |
|--------|------------|--------------|--------|
| frac_escaped | | | |
| med \|x\| | | | |
| P(\|x\| > 3) | | | |
| std(x) | | | |

## Gap Analysis
- Plot: Gap % (100*(Python-Kratos)/Python) vs τ₀
- If gap widens with τ₀ → boundary-handling error accumulates per crossing
- If gap constant → systematic physics difference (profile, RNG, precision)

## Saved For Later: a > 0 Extension
When ready, repeat with:
- a = 0.01, 0.1 (ph_mode=1, USampler R_IIA table)
- Add u_grid/xg_grid/C_grid from build_usampler()
- Compare Neufeld scaling: P(|x|>3) ∝ (aτ₀)^(-2/3) vs Kratos
