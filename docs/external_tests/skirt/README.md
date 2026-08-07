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

| Configuration | Kratos GPU (s) | SKIRT CPU (s) | Speedup |
|---------------|---------------|---------------|---------|
| τ₀=10³, no imaging | 0.14 | 5.8 ± 0.2 | 41× |
| τ₀=10³, with imaging | 0.54 | 5.8 ± 0.2 | 11× |
| τ₀=10⁴, no imaging | 0.55 | 5.8 | 11× |

**Hardware:** Kratos runs on NVIDIA RTX 3090 (82 SM, 24 GB VRAM).
SKIRT runs on CPU with 16 threads.

**Timing notes:**
- Kratos timing = internal GPU timer (from `cycle.cpp:163`,
  `Duration = X s`), excludes Python/IO overhead (~8 s wall).
- SKIRT timing = total run time (3 repeats, mean ± std). The SED
  instrument overhead is negligible (5.8 ± 0.2 s for both 2-bin and
  200-bin SED — the instrument just bins escaping photons, O(N)).
- Kratos imaging overhead (0.40 s) is from the default 32×32 pixel
  grid (1024 rays × 32 channels). The `img_resol=(8,8)` override
  (64 rays) is silently dropped by `write_par_file` because
  `img_resol` is commented out in the par template.
- At τ₀=10⁴, Kratos MCRT time increases 4× (0.14→0.55 s) while
  SKIRT stays at ~5.8 s, suggesting SKIRT startup dominates at these
  scales.

### SNR comparison

| Approach | Output bins | SNR / bin | Spectral SNR | Mechanism |
|----------|------------|-----------|-------------|-----------|
| Our imaging (2D × chan) | 32768 | 9.5 / pixel | 304 | s_cam MC (all segments) |
| SKIRT SED (1D) | 196 | 14.3 avg, 62.3 peak | 14.3 | Poisson (escaped only) |

Our imaging achieves **20× higher spectral SNR** (304 vs 14.3) when
spatially averaged, because the s_cam source function uses ALL photon
segments (~3.2M, including trapped photons that scatter many times),
not just the 10⁵ escaped photons SKIRT counts. SKIRT has higher
per-bin SNR (fewer bins: 200 vs 32768) but produces 1D spectra only.
The trade-off: our imaging yields 2D spatial channel maps
(morphological information); SKIRT gives a 1D angle-averaged spectrum.
