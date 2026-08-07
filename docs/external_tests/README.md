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

> **Analytic value:** Neufeld (1990) eq. (2.24) for a plane-parallel
> slab gives $|x_{\rm peak}| = 0.881\,(a\tau_0)^{1/3}$. With $a = 4.73
> \times 10^{-3}$, $\tau_0 = 1000$: $a\tau_0 = 4.73$, so
> $|x_{\rm peak}| = 0.881 \times 4.73^{1/3} = 0.881 \times 1.679 =
> \mathbf{1.48}$. This is the mean-depth (half-slab) convention; the
> box geometry allows escape in 6 directions (not 2), producing
> higher peaks in both codes.

### Speed tests

#### Photon scaling (τ₀ = 10³, 32³ grid, volume source)

| Photons | Kratos MCRT (s) | Kratos overhead (s) | Kratos total (s) | SKIRT MCRT (s) | SKIRT overhead (s) | SKIRT total (s) | MCRT speedup | Total speedup |
|---------|----------------|---------------------|------------------|----------------|---------------------|-----------------|---------------|----------------|
| 1×10³   | 0.010          | 8.7                 | 8.7              | 0.10           | 0.00                | 0.10            | 10×           | 0.01×          |
| 1×10⁴   | 0.012          | 8.4                 | 8.4              | 0.60           | 0.02                | 0.62            | 50×           | 0.07×          |
| 1×10⁵   | 0.033          | 8.7                 | 8.7              | 5.80           | 0.06                | 5.86            | 176×          | 0.7×           |
| 1×10⁶   | 0.236          | 9.2                 | 9.4              | 57.30          | 0.04                | 57.34           | **243×**      | **6.1×**       |

**Overhead breakdown:**

- **Kratos overhead** (~8.5 s, constant) = Python pipeline I/O: field
  binary write, photon binary write, par file generation, Kratos
  subprocess launch, output binary readback. Does not scale with
  photon count. The Kratos internal GPU timer (`Duration = X s` in
  `cycle.cpp:163`) captures only the MCRT kernel time.
- **SKIRT overhead** (~0.05 s) = process startup (shared library
  loading, `.ski` parsing, grid construction). SKIRT's
  `Finished setup in 0.0 s` confirms grid construction is negligible.
  The `Finished the run in X s` is essentially all MCRT.

**Key observations:**

- SKIRT scales linearly (0.10 → 57.3 s, ~570× for 1000× photons). At
  10⁶ photons, SKIRT is >99.9% MCRT — overhead fully dwarfed.
- Kratos MCRT also scales sub-linearly at low counts (0.010 → 0.236 s,
  ~24× for 1000× photons, due to GPU kernel launch overhead at small
  payloads) but approaches linearity at 10⁵+.
- At 10⁶ photons, Kratos MCRT is only 2.5% of wall time — the Python
  I/O bottleneck dominates the end-to-end comparison.
- **Pure MCRT speedup: 243×** at 10⁶ photons. This reflects the
  GPU (RTX 3090, 82 SM) vs CPU (16 threads) throughput for photon
  transport + R_IIA scattering.
- **Wall speedup: 6.1×** at 10⁶ photons, capped by the ~9 s Python
  I/O. To dwarf this overhead, ~4×10⁷ photons are needed (MCRT ~10 s),
  but SKIRT at that count would take ~37 min.

### SNR comparison

**Definitions:**
- **SNR per bin** = signal / noise. For MC estimates, noise ≈ √N_eff
  where N_eff = effective number of independent samples in the bin.
- **Spectral SNR** = per-bin SNR × √N_pixels (noise averages down
  by √N when combining N independent pixels spatially).
- For our imaging: N_eff ≈ (total photon path segments) /
  (output bins). With ~3.2M segments / 32768 bins (32² × 32) ≈ 98,
  per-pixel SNR ≈ √98 ≈ 9.9. Spectral SNR = 9.9 × √1024 ≈ 304.
- For SKIRT SED: N_eff = escaped photon count per wavelength bin
  (Poisson). With 10⁵ photons / 196 bins ≈ 510 avg, SNR ≈ √510 ≈ 22.6.
  Measured 14.3 avg (non-uniform distribution) to 62.3 peak (line
  center, more photons).

| Approach | Output bins | SNR per bin | Spectral SNR | Mechanism |
|----------|------------|-------------|-------------|-----------|
| Our imaging (2D × chan) | 32768 | 9.5 / pixel | 304 | s_cam MC estimate (all ~3.2M segments, incl. trapped photons) |
| SKIRT SED (1D spectrum) | 196 | 14.3 avg, 62.3 peak | 14.3 | Poisson counting (10⁵ escaped photons only) |

Our imaging achieves **20× higher spectral SNR** (304 vs 14.3) when
spatially averaged, because the s_cam source function uses ALL photon
segments (~3.2M, including trapped photons that scatter many times),
not just the 10⁵ escaped photons SKIRT counts. However, SKIRT has
higher per-bin SNR because it produces fewer bins (200 vs 32768). The
trade-off: our imaging yields 2D spatial channel maps (morphological
information); SKIRT gives a 1D angle-averaged spectrum only.

See `skirt/README.md` for SKIRT install steps and `.ski` configuration
details.
