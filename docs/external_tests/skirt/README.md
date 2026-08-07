# SKIRT 9 — Lyα Apple-to-Apple Comparison

Build and run instructions for the SKIRT 9 radiative transfer code, used
as an external benchmark for our Kratos GPU pipeline.

## Installation

```bash
# Clone SKIRT 9 (core + data resources)
cd ~/scratch/skirt_tst
git clone https://github.com/SKIRT/SKIRT9.git SKIRT9
cd SKIRT9

# Resource symlink (SKIRT expects a 'git' resource directory)
ln -sf . git

# Download resources (Core ~730 MB + AtomsMolecules ~2 MB)
# Full SKIRT resources are ~2 GB; only Core + AtomsMolecules needed for Lyα
git clone https://github.com/SKIRT/SKIRT9_data.git git

# Build (C++14, CMake, bundles CFITSIO + Voro++)
mkdir -p build/SKIRT/main && cd build
cmake ../.. -DCMAKE_POLICY_VERSION_MINIMUM=3.5
make -j16 skirt

# Binary: ~/scratch/skirt_tst/SKIRT9/build/SKIRT/main/skirt
```

## Running

```bash
cd ~/scratch/skirt_tst/run_fine
skirt lya_slab.ski
```

The `.ski` file is an XML hierarchy with root element
`<skirt-simulation-hierarchy type="MonteCarloSimulation" ...>`.

## Configuration (lya_slab.ski)

| Parameter | Value |
|-----------|-------|
| Simulation mode | `LyaExtinctionOnly` (Lyα transfer, no iteration) |
| Acceleration | `None` (apple-to-apple, no core-skipping) |
| Units | SI |
| Source | `UniformBoxGeometry` [-0.5, 0.5]³ m + `LyaGaussianSED` (dispersion = v_th = 1285 m/s) |
| Medium | `LyaNeutralHydrogenGasMix` (T = 100 K) |
| Grid | `CartesianSpatialGrid` 32³ |
| Instrument | `SEDInstrument` (200 wavelength bins, 1.21556–1.21578 × 10⁻⁷ m) |
| Photons | 1×10⁵ |

### Physical parameters

- Lyα wavelength: λ₀ = 1.21567 × 10⁻⁷ m (ν = 2.466 × 10¹⁵ Hz)
- Thermal velocity: v_th = √(2kT/m_p) = 1285 m/s (T = 100 K)
- Voigt damping: a = A_α / (4π ν₀) = 4.73 × 10⁻³
- σ₀ = (g_u/g_l) A_α c³ / (8π^(3/2) ν₀³ v_th) = 5.92 × 10⁻¹⁷ m²
- For τ₀ = 1000: n_H = τ₀ / (L σ₀) = 1.69 × 10¹⁹ m⁻³
- For τ₀ = 10⁴: n_H = 1.69 × 10²⁰ m⁻³

## Matching our code

Our pipeline `LineRt` configuration:

```python
rt = LineRt(
    kratos_root='~/apps/kratos_line_rt',
    n_cell=(32, 32, 32),
    x_min=(-0.5, -0.5, -0.5), x_max=(0.5, 0.5, 0.5),
    unit_l0=100.0,   # 1 m in cm
    unit_t0=1.0,
    b_sca=v_th,       # = 128486 cm/s
    mfp_i_sca_0=10.0, # = tau0 / L_cm
    mfp_i_abs_0=1e-12,
    ph_mode=2,         # R_IIA (const-mem USampler + 1D Voigt table)
    n_step=200000, n_scat=50000,
    worker_mode=True,  # server-worker photon scheduling
    a_voigt=4.73e-3,
)
rt.add_source(type='volume', luminosity=1e6, n_photon=100000, sigma=v_th)
rt.set_boundary('fre fre per per per per')
```

## Results

### Peak convergence

With the volume source (matching SKIRT's `UniformBoxGeometry`):

| Code | x_peak (+) | x_peak (-) | med\|x\| |
|------|-----------|-----------|---------|
| Our code (volume) | 2.625 | -2.625 | 2.669 |
| SKIRT (UniformBox) | 2.364 | -2.365 | — |
| Neufeld (slab, mean-depth) | 1.479 | — | — |

Agreement: 11%. Both codes give peaks higher than Neufeld's slab
prediction, consistent with the box geometry (6-direction escape vs
2-direction slab).

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
- Kratos MCRT scales sub-linearly at low counts (0.010 → 0.236 s,
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

**Hardware:** Kratos runs on NVIDIA RTX 3090 (82 SM, 24 GB VRAM).
SKIRT runs on CPU with 16 threads.

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

| Approach | Output bins | SNR / bin | Spectral SNR | Mechanism |
|----------|------------|-----------|-------------|-----------|
| Our imaging (2D × chan) | 32768 | 9.5 / pixel | 304 | s_cam MC (all ~3.2M segments) |
| SKIRT SED (1D) | 196 | 14.3 avg, 62.3 peak | 14.3 | Poisson (10⁵ escaped only) |

Our imaging achieves **20× higher spectral SNR** (304 vs 14.3) when
spatially averaged, because the s_cam source function uses ALL photon
segments (~3.2M, including trapped photons that scatter many times),
not just the 10⁵ escaped photons SKIRT counts. SKIRT has higher
per-bin SNR (fewer bins: 200 vs 32768) but produces 1D spectra only.
The trade-off: our imaging yields 2D spatial channel maps
(morphological information); SKIRT gives a 1D angle-averaged spectrum.
