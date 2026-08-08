# Kratos Backend — LineRT Module

The C++/CUDA backend for line radiative transfer. Built on the Kratos
particle framework, with the `usr_ext/line_rt` user extension.

## Build

```bash
# CUDA (NVIDIA GPU, requires nvcc)
make USRDIR=usr_ext/line_rt -j8

# HIP-CPU (no GPU needed, uses g++)
make USRDIR=usr_ext/line_rt ARCH=HIPCPU -j8
# HIP (AMD GPU, requires hipcc/ROCm)
make USRDIR=usr_ext/line_rt ARCH=HIP -j8
```

The binary is produced at `bin/kratos`.

### Build options

| Option | Default | Values |
|--------|---------|--------|
| `USRDIR` | `usr` | `usr_ext/line_rt` (required for line_rt) |
| `ARCH` | `CUDA` | `CUDA`, `HIP`, `HIPCPU`, `MUSA` |
| `SM` | `sm_80` | GPU compute capability (e.g. `sm_70`, `sm_80`, `sm_90`) |
| `DEBUG` | `0` | `1` for debug build with `-g -O0` |
| `MPI` | `0` | `1` for MPI parallel I/O |

### HIP-CPU backend

The `HIPCPU` backend requires no GPU but needs:

1. **libtbb-dev**: `sudo apt install libtbb-dev`
2. **HIP-CPU runtime** — patched fork (the original ROCm/HIP-CPU does not
   compile with modern GCC):
   ```bash
   git clone https://github.com/wll745881210/HIP-CPU-vibe.git
   cd HIP-CPU-vibe && mkdir build && cd build
   cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local && make install
   ```

## Directory Structure

```
kratos/
├── src/                      # Core framework (extracted — no chemistry/dynamics/multigrid)
│   ├── comm/                 # MPI communication
│   ├── device/               # GPU device wrappers (cuda/hip/musa, #ifdef-guarded)
│   ├── io/                   # Binary I/O + argument parsing
│   ├── mesh/                 # Mesh, block, boundary, geometry
│   ├── modules/particle/     # Particle framework (base, radiation, evolve — no cic)
│   ├── user/                 # Problem generator stub
│   └── utilities/            # Math, types, data transfer
├── usr/
│   └── extension/algo/       # Header-only interpolation library (interp.h)
├── usr_ext/line_rt/          # LineRT user extension
│   ├── radiation.h           # Field I/O, init_cond (GPU kernel), ini_t tables
│   ├── photon.h              # Scattering physics (proc_geo, proc_phys, s_cam accumulation)
│   ├── photon_img.h          # Imaging photon (per-channel analytic RT)
│   ├── rad_img.h             # Imaging module (parasite of radiation_t)
│   ├── intg.h                # Integrator: USampler, R_IIA kernel, Voigt tables, camera
│   ├── gen.h                 # Photon generation
│   ├── pool.h / pool_img.*   # Output writing (escaped photons + imaging)
│   ├── block_data.h          # rad_t struct (fields, s_cam, imaging)
│   ├── usr.cpp               # Module enrollment
│   ├── tests/                # Standalone regression tests
│   └── ...
├── visual/
│   └── binary_io.py          # Binary I/O reader (for standalone tests)
└── Makefile
```

## Par File Format

Kratos reads a `.par` configuration file. Key sections:

```ini
[mesh]
x_min = -1.0 0 0              # CODE units (not CGS)
x_max =  1.0 1 1
n_cell_global = 64 16 2       # MUST be integers

[unit]
length  = 1.49598e13          # code unit → cm
time    = 1.0                 # code unit → s
density = 1.0                 # code unit → g/cm³

[line_rt]
field_file       = fields_cycle0.bin
field_fixed_file = fields_fixed.bin
photon_file      = photons_cycle0.bin
ph_mode          = 2          # 0=CFR, 1/2/3=R_IIA
b_sca            = 1.3369e-7  # CODE units
n_scat           = 10000
worker_mode      = 1
n_worker         = 32768

[imaging]
enabled         = 1
n_chan          = 32
dir_cam_theta   = 0.785
dir_cam_phi     = 0.0
v_chan_min      = -1.0e5
v_chan_max       = 1.0e5
```

Everything in `[mesh]` and `[line_rt]` is in **code units**, not CGS.
The `[unit]` section is documentation-only — Kratos does not auto-convert.

## GPU Memory Layout

| Table | Grid points | Bytes | Storage |
|-------|-------------|-------|---------|
| 2D Voigt (ph_mode 0/1) | 64×512 | 128 KiB | global |
| 1D Voigt (ph_mode 2) | 5,000 | 19.5 KiB | constant |
| USampler CDF (ph_mode 2) | 251×40 | 39.2 KiB | constant |
| R_IIA kernel | 200×200×40 | 6.1 MiB | global |

Total constant memory (ph_mode 2): 59.8 KiB of 64 KiB hardware limit.
See `pipeline/docs/PHYSICS.md` §4 for the full table.

## Standalone Tests

See `usr_ext/line_rt/tests/README.md` for the full test suite.

```bash
# Core validation (vs Neufeld + Python MC)
python3 usr_ext/line_rt/tests/test_absorption_scattering.py --kratos-root .

# Wide aτ₀ scaling (vs Neufeld)
python3 usr_ext/line_rt/tests/test_scaling_wide.py --kratos-root .

# Imaging double-peak scaling (vs Neufeld)
python3 usr_ext/line_rt/tests/test_scaling_image.py --kratos-root . --plots

# Thin-slab imaging spectrum (analytic)
python3 usr_ext/line_rt/tests/test_imaging_spectrum.py --kratos-root .

# Imaging normalization
python3 usr_ext/line_rt/tests/test_imaging_neufeld.py --kratos-root .
```

## Physics Reference

See `pipeline/docs/PHYSICS.md` for the authoritative physics specification:
- §2: Scattering modes (CFR vs R_IIA), Voigt profile
- §4: Cross sections, table sizes, GPU memory
- §12: Two-step imaging, R_IIA kernel definition, source function
