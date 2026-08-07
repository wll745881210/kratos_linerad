# External Tests

Comparative and integration tests for the `line_rt` pipeline, kept outside
the core test suite because they require large external data inputs or
comparison against other radiative transfer codes.

## Layout

```
docs/external_tests/
  README.md          ← this file
  ism/
    README.md        # ISM diffuse-cloud channel maps (data, units, results)
    read_ism.py      # Athena++ athdf reader → 128³ CGS grids
  skirt/
    README.md        # SKIRT install, config, run, timing extraction
    lya_slab.ski     # SKIRT Lyα slab configuration (200-bin SED)
    run_comparison.py # timing + peak extraction script
```

Notebooks stay in the working directories (`~/scratch/ism/ism_rt.ipynb`,
`~/scratch/skirt_tst/`), not in the pipeline repo.

## Test 1 — ISM diffuse-cloud channel maps

**Working dir:** `~/scratch/ism`  
**Notebook:** `~/scratch/ism/ism_rt.ipynb` (mirrors `~/scratch/ppd_rt/ppd_rt.ipynb`)

Loads the fiducial ISM MHD simulation (Yue et al. 2024, ApJ 973:37 —
Athena++, 128³, 0.04 pc box, 23-species thermochemistry) and produces
channel maps for:

| Molecule | Line | ν | Optical depth | Notes |
|----------|------|---|---------------|-------|
| OH | 18 cm Λ-doublet (1665.5 MHz) | 1.667 GHz | τ ~ 1 (thick) | ground state, always populated |
| CO | J=1→0 (115.271 GHz) | 115 GHz | τ ~ 0.05 (thin) | standard reference |

Both use `TransitionInfo.user_defined()` (2-level system) to avoid the full
LAMDA multi-level rate matrix. The 2-level LTE solver computes the lower-
level abundance automatically.

See `ism/README.md` for data provenance, unit conventions, and the full
optical-depth analysis table.

## Test 2 — SKIRT apple-to-apple Lyα comparison

**Working dir:** `~/scratch/skirt_tst`  
**SKIRT binary:** `~/scratch/skirt_tst/SKIRT9/build/SKIRT/main/skirt`

Compares our Kratos GPU pipeline against SKIRT 9 (CPU, 16 threads) for a
thick Lyα slab. Both codes use the same R_IIA partial redistribution
physics (SKIRT `VoigtProfile::sample` ≡ our USampler), the same
isotropic volume source (`UniformBoxGeometry` ↔ `type='volume'`), the
same 32³ Cartesian grid, and 1×10⁵ photons.

### Configuration (apple-to-apple)

| Parameter | Our code | SKIRT |
|-----------|----------|-------|
| Species | Lyα (H I 2p→1s) | LyaNeutralHydrogenGasMix |
| T | 100 K | 100 K |
| τ₀ | 1000 | 1000 (n_H = 1.69×10¹⁹ m⁻³) |
| Box | 1 m ([-0.5, 0.5]³) | 1 m ([-0.5, 0.5]³) |
| Grid | 32³ Cartesian | 32³ Cartesian |
| Photons | 1×10⁵ | 1×10⁵ |
| Source | `type='volume'`, luminosity=10⁶ ph/s, σ=v_th | `UniformBoxGeometry` + `LyaGaussianSED` dispersion=v_th |
| Scattering | R_IIA (`ph_mode=2`, `a_voigt=4.73×10⁻³`) | R_IIA (`VoigtProfile::sample`, no acceleration) |
| Boundaries | free x, periodic y/z | (default) |

### Peak convergence

Escaped spectrum double-peak location (|x| = |v|/v_th):

| Source type | Our x_peak | SKIRT x_peak | Agreement | Neufeld |
|-------------|-----------|-------------|-----------|---------|
| Slab (one-sided) | 0.96 | 2.36 | 59% off | — |
| Slab (two-sided) | 0.38 | 2.36 | 84% off | — |
| **Volume (isotropic)** | **±2.63** | **±2.36** | **11% off** | 1.48 |

The volume source (matching SKIRT's `UniformBoxGeometry`) brings the
peaks to within 11%. Both codes give peaks higher than Neufeld's slab
prediction (1.48, mean-depth convention), consistent with the box
geometry allowing escape in 6 directions (not just 2 as in a slab).

### Speed tests (with and without imaging)

| Configuration | Kratos GPU (s) | SKIRT CPU (s) | Speedup |
|---------------|---------------|---------------|---------|
| τ₀=10³, no imaging | 0.14 | 6.2 | 44× |
| τ₀=10³, with imaging | 0.54 | 5.7 | 11× |
| τ₀=10⁴, no imaging | 0.55 | 5.7 | 10× |

Notes:
- **Kratos timing** = internal GPU timer (excludes Python I/O ~8 s).
- **SKIRT timing** = total run time (includes C++ setup).
- **Kratos imaging** = 2D channel maps (32×32 pixels × 32 velocity
  channels). Imaging overhead = 0.40 s (281%) due to default 32×32
  pixel grid (1024 rays × 32 channels × per-cell Voigt evaluation).
  Setting `img_resol=(8,8)` reduces this to 64 rays (requires fixing
  the par template `img_resol` key — currently silently dropped).
- **SKIRT instrument** = 1D SED (200 wavelength bins). Overhead
  negligible (5.7 vs 6.2 s for 200-bin vs 2-bin).
- At τ₀=10⁴, MCRT work increases 4× (0.14→0.55 s) but SKIRT time is
  unchanged (~5.7 s), suggesting SKIRT startup dominates.

See `skirt/README.md` for SKIRT install steps and `.ski` configuration
details.
