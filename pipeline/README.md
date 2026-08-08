# Python Pipeline — LineRT

The Python frontend for line radiative transfer: species data resolution,
population solver, Kratos I/O, visualization, and the `LineRt` orchestrator.

## Installation

```bash
cd pipeline
pip install -e . --break-system-packages
```

This registers the `line-rt` console script and makes `from line_rt import ...`
work from any directory. Re-run only when `pyproject.toml` changes.

### Setting `kratos_root`

The pipeline shells out to the Kratos binary. Set its location via:

1. `kratos_root` kwarg: `LineRt(kratos_root='../kratos')`
2. `KRATOS_ROOT` environment variable
3. `~/.config/kratos_linerad/paths.conf` (run `../scripts/install.sh`)
4. Monorepo auto-detect (`../kratos/bin/kratos` relative to this package)

For HPC/CI: `export KRATOS_ROOT=/path/to/kratos`

## Quick Start

```python
from line_rt import LineRt, TransitionInfo

# Group 1: species-based (LAMDA data)
ti = TransitionInfo(species='co', transition_idx=0)  # CO J=1→0
rt = LineRt(
    kratos_root='../kratos',
    transition_info=ti,
    n_species=1e-4, temperature=10.0,
    n_cell=(64, 16, 2), x_min=(-8, -2, 0), x_max=(8, 2, 0.2),
    unit_l0=1.49598e13,
    n_cycles=3, n_photon=100000,
)
rt.add_source(type='slab', position=-5, direction='+x',
              n_photon=100000, flux=1e6)
out = rt.run()
rt.plot_results()

# Group 2: direct fields (no species data)
rt = LineRt(
    kratos_root='../kratos',
    b_sca=1e-4, mfp_i_sca_0=0.01, mfp_i_abs_0=1e-12,
    n_cell=(64, 16, 2), x_min=(-8, -2, 0), x_max=(8, 2, 0.2),
    unit_l0=1.49598e13,
    ph_mode=2, n_cycles=1,
)
```

## CLI

```bash
line-rt --kratos-root ../kratos \
    --n-cell 64 16 2 --x-min -8 -2 0 --x-max 8 2 0.2 \
    --unit-l0 1.49598e13 \
    --b-sca 1e-4 --mfp-i-sca-0 0.01 --mfp-i-abs-0 1e-12 \
    --ph-mode 2 --n-cycles 3 --n-photon 100000 \
    --source slab --source-position -5 --source-direction +x \
    --source-flux 1e6
```

Run `line-rt --help` for all options.

## Visualization

| Method | Purpose |
|--------|---------|
| `rt.plot_input()` | Input fields (opacity, emissivity, velocity) |
| `rt.plot_results()` | Output fields (flux, excitation, spectrum) |
| `rt.plot_channel_maps(out)` | Velocity-channel images (cube) |
| `rt.plot_convergence(out)` | Population convergence per cycle |

## Key API

| Class/Function | Purpose |
|----------------|---------|
| `LineRt` | High-level orchestrator (`core/line_rt.py`) |
| `TransitionInfo` | Species/transition selection (`molecular/transition_info.py`) |
| `TransitionInfo.user_defined(...)` | Non-LAMDA transitions |
| `iterate()` | Low-level MC cycle loop (`core/iterator.py`) |

## Directory Structure

```
pipeline/
├── line_rt.py          # Public facade (re-exports LineRt, TransitionInfo)
├── cli.py              # CLI entrypoint
├── core/               # LineRt, iterator, pipeline, kratos_io, binary_io, visualization
├── molecular/          # Species data, LAMDA, population solver, transition_info
├── ui/                  # Jupyter ipywidgets interface
├── web/                 # Panel dashboard
├── docs/                # PHYSICS.md, METHODS.md, debug/, examples/
├── tests/               # pytest test suite
├── pyproject.toml
└── AGENTS.md            # Developer reference (pitfalls, conventions, architecture)
```

## Tests

```bash
# Pipeline tests
cd pipeline
python -m pytest tests/ -v

# Standalone Kratos tests (need kratos_root)
cd ../kratos
python3 usr_ext/line_rt/tests/test_absorption_scattering.py --kratos-root .
python3 usr_ext/line_rt/tests/test_scaling_wide.py --kratos-root .
python3 usr_ext/line_rt/tests/test_scaling_image.py --kratos-root . --plots
```

## Documentation

- [AGENTS.md](AGENTS.md) — Full developer reference (pitfalls, conventions)
- [PHYSICS.md](docs/PHYSICS.md) — Physics specification
- [METHODS.md](docs/METHODS.md) — Methods document
- [Examples](docs/examples/) — Plane-parallel, imaging, PPD
