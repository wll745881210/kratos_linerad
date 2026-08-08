# Kratos LineRT

A GPU-accelerated Monte Carlo radiative transfer pipeline for molecular and
atomic line emission, featuring exact R_IIA frequency redistribution,
two-step imaging, and a Python API.

## Architecture

The system has two parts:

| Part | Directory | Language | Purpose |
|------|-----------|----------|---------|
| **Kratos backend** | `kratos/` | C++/CUDA/HIP | GPU Monte Carlo transport + imaging |
| **Python pipeline** | `pipeline/` | Python | Species data, population solver, I/O, visualization |

## Quick Start

### 1. Build the Kratos backend

```bash
cd kratos
make USRDIR=usr_ext/line_rt -j8              # CUDA (NVIDIA, default)
# make USRDIR=usr_ext/line_rt ARCH=HIP -j8         # HIP (AMD ROCm GPUs)
# make USRDIR=usr_ext/line_rt ARCH=HIPCPU -j8       # CPU-only (no GPU needed)
```

This produces `kratos/bin/kratos`.

The code supports three backends:

| `ARCH` | Compiler | Target | Notes |
|--------|----------|--------|-------|
| `CUDA` (default) | `nvcc` | NVIDIA GPU (sm_80) | Pass `SM=sm_70` etc. for other architectures |
| `HIP` | `hipcc` | AMD ROCm GPU | Requires ROCm toolkit |
| `HIPCPU` | `g++` | CPU (multi-threaded) | Requires libtbb-dev + HIP-CPU runtime (see below) |

All device-specific code is `#ifdef`-guarded, so the same source compiles under
any backend without modification.

### HIP-CPU requirements

The `HIPCPU` backend (no GPU) requires:

1. **libtbb-dev** — Intel Threading Building Blocks:
   ```bash
   sudo apt install libtbb-dev
   ```

2. **HIP-CPU runtime** — a patched fork that works with modern GCC and libtbb-dev:
   ```bash
   git clone https://github.com/wll745881210/HIP-CPU-vibe.git
   cd HIP-CPU-vibe
   mkdir build && cd build
   cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local
   make install
   ```
   > **Note:** The original [ROCm/HIP-CPU](https://github.com/ROCm/HIP-CPU) does
   > not compile with recent GCC or libtbb-dev. Use the patched fork above.

### 2. Install the Python pipeline

```bash
cd pipeline
pip install -e . --break-system-packages
```

### 3. Run a simulation

```python
from line_rt import LineRt

rt = LineRt(
    kratos_root='../kratos',            # path to the kratos/ directory
    n_cell=(64, 16, 2),
    x_min=(-8, -2, 0), x_max=(8, 2, 0.2),  # CODE units (NOT CGS)
    unit_l0=1.49598e13,                  # length: 1 code unit = 1 AU in cm
    b_sca=1e-4,                          # Doppler b for scattering [cm/s] (CGS)
    mfp_i_sca_0=0.01,                    # inverse scattering MFP at line centre [cm^-1] (CGS)
    mfp_i_abs_0=1e-12,                   # inverse absorption MFP [cm^-1] (CGS)
    ph_mode=2,                           # R_IIA frequency redistribution (production)
    n_step=20000, n_scat=10000,
    n_cycles=3,
)
rt.add_source(type='slab', position=-5, direction='+x',  # position in CGS [cm]
              n_photon=100000, flux=1e6)                   # flux in CGS [photons cm^-2 s^-1]
out = rt.run()
rt.plot_results()
```

> **Unit convention:** The Python pipeline accepts **CGS** inputs for all
> physical quantities (densities, velocities, opacities, source positions,
> fluxes) — **except** `x_min`/`x_max` which are in **code units**
> (multiples of `unit_l0`). The Kratos backend operates in **code units**
> internally; the pipeline handles all conversions.
> See **[PHYSICS.md](pipeline/docs/PHYSICS.md)** for the full specification
> (§1: units, §3: cross sections, §12: imaging).

**Key parameters:**

| Parameter | Unit | Description |
|-----------|------|-------------|
| `unit_l0` | cm | Length: 1 code unit → this many cm (e.g. `1.49598e13` = 1 AU) |
| `b_sca` | cm/s | Doppler b-parameter for scattering (thermal + turbulent broadening) |
| `mfp_i_sca_0` | cm⁻¹ | Inverse scattering mean free path at line centre (τ₀ = × slab length) |
| `mfp_i_abs_0` | cm⁻¹ | Inverse absorption mean free path (dust/continuum destruction) |
| `n_species` | cm⁻³ | Species number density (lower-level population; used in Group 1) |

## Prerequisites

- **CUDA toolkit** (NVIDIA GPU builds), **ROCm toolkit** (AMD GPU builds), or **libtbb-dev + HIP-CPU** (CPU builds)
- **Python 3.10+** with `numpy`, `scipy`, `matplotlib`
- **NVIDIA GPU** (compute capability ≥ 7.0, e.g. RTX 3090) **or AMD GPU** (ROCm, e.g. MI250X) **or CPU**

## Setting `kratos_root`

The pipeline needs to find the `kratos` binary. It searches in this order:

1. `kratos_root` kwarg or `--kratos-root` CLI flag
2. `KRATOS_ROOT` environment variable
3. `~/.config/kratos_linerad/paths.conf` (written by `scripts/install.sh`)
4. Monorepo auto-detect (`../kratos/bin/kratos` relative to the pipeline package)

For HPC/CI: `export KRATOS_ROOT=/path/to/kratos`

## Documentation

- [Pipeline README](pipeline/README.md) — Python API, CLI, visualization
- [Kratos README](kratos/README.md) — Build, par file format, tests
- [Physics specification](pipeline/docs/PHYSICS.md) — Full physics reference
- [Methods](pipeline/docs/METHODS.md) — Methods document for publication

## License

See `LICENSE`.

## Citation

If you use this code in a publication, please cite:
(citation to be added)
