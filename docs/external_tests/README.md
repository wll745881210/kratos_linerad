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

### Speed tests

#### Photon scaling (τ₀ = 10³, 32³ grid, volume source)

| Photons | Kratos MCRT (s) | Kratos wall (s) | SKIRT (s) | MCRT speedup | Wall speedup |
|---------|----------------|-----------------|-----------|--------------|--------------|
| 1×10⁵   | 0.033          | 8.7             | 5.8       | 176×         | 0.7×         |
| 1×10⁶   | 0.236          | 9.4             | 56.3      | **239×**     | **6.0×**     |

**Interpretation:**

- **SKIRT** scales linearly (5.8 → 56.3 s, ~10× for 10× photons). At
  10⁶ photons, SKIRT is ~90% MCRT — its ~5.7 s C++ startup overhead
  is dwarfed.
- **Kratos MCRT** also scales linearly (0.033 → 0.236 s, ~7× for 10×
  photons). However, the Python pipeline I/O overhead (~8.7 s: field
  binary write, photon binary write, par file, output readback) is
  constant regardless of photon count. At 10⁶ photons, MCRT is only
  2.5% of the wall time — the Python I/O dominates.
- **Pure MCRT speedup** (excluding Python I/O): **239×** at 10⁶
  photons. This reflects the GPU vs CPU throughput for the actual
  photon transport + R_IIA scattering.
- **Wall speedup** (end-to-end, including Python I/O): **6.0×** at
  10⁶ photons. The Python I/O bottleneck caps the practical speedup.
- To dwarf the Python I/O for Kratos (MCRT >> 8.7 s), ~4×10⁷ photons
  are needed (MCRT ~10 s). But SKIRT at 4×10⁷ would take ~37 min,
  making the benchmark impractical.

#### Configuration variants (1×10⁵ photons, τ₀ = 10³)

| Configuration | Kratos MCRT (s) | SKIRT (s) | Speedup (MCRT) |
|---------------|----------------|-----------|----------------|
| No imaging    | 0.033          | 5.8       | 176×           |
| With imaging  | 0.39           | 5.8       | 15×            |
| τ₀ = 10⁴     | 0.55           | 5.8       | 11×            |

Notes:
- **Kratos timing** = internal GPU timer (from `cycle.cpp:163`,
  `Duration = X s`), excludes Python I/O (~8.7 s wall).
- **SKIRT timing** = total run time (3 repeats, mean ± std). The SED
  instrument overhead is negligible (5.8 ± 0.2 s for both 2-bin and
  200-bin SED).
- **Kratos imaging** = 2D channel maps (32×32 pixels × 32 velocity
  channels). Imaging overhead = 0.36 s due to default 32×32 pixel
  grid (1024 rays × 32 channels × per-cell Voigt evaluation).
- At τ₀=10⁴, Kratos MCRT increases 17× (0.033→0.55 s) while SKIRT
  stays at ~5.8 s (overhead-dominated, 10⁵ photons).

### SNR comparison

| Approach | Output bins | SNR per bin | Spectral SNR | Mechanism |
|----------|------------|-------------|-------------|-----------|
| Our imaging (2D × chan) | 32768 | 9.5 / pixel | 304 | s_cam MC estimate (all segments) |
| SKIRT SED (1D spectrum) | 196 | 14.3 avg, 62.3 peak | 14.3 | Poisson counting (escaped only) |

Our imaging achieves **20× higher spectral SNR** (304 vs 14.3) when
spatially averaged, because the s_cam source function uses ALL photon
segments (~3.2M, including trapped photons that scatter many times),
not just the 10⁵ escaped photons SKIRT counts. However, SKIRT has
higher per-bin SNR because it produces fewer bins (200 vs 32768). The
trade-off: our imaging yields 2D spatial channel maps (morphological
information); SKIRT gives a 1D angle-averaged spectrum only.

See `skirt/README.md` for SKIRT install steps and `.ski` configuration
details.
