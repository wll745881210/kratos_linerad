# Line RT Interface

Interactive graphical interface for Monte Carlo line radiative transfer with self-consistent population number iteration.

See [docs/PHYSICS.md](docs/PHYSICS.md) for a tutorial on the underlying physics and the full unit conversion chain.

## Installation

```bash
# Python dependencies
pip install --break-system-packages numpy scipy matplotlib
pip install --break-system-packages ipywidgets    # for Jupyter interface
pip install --break-system-packages panel          # for web dashboard

# Install this package
cd /path/to/line_rt_pipeline
pip install -e .
```

## Three Ways to Use

### 1. Jupyter Notebook (research / interactive)

Launch JupyterLab and open the notebook:

```bash
cd /path/to/line_rt_pipeline
jupyter lab
# Open ui/notebook.ipynb
```

The notebook has 5 tabs:
- **Source** — specify photon source (point, parallel beam, custom)
- **Species** — select chemical species, view Einstein A and level data
- **Fields** — define spatial profiles (density, MFP, velocity) with preview
- **Iteration** — run MC → population → MC cycles with live progress
- **Output** — view spectra, flux maps, population maps, convergence

### 2. Python Module (scripting / automation)

**Mode 1 — direct MFP** (no species data needed):

```python
from linert import LineRT, SlabSource

rt = LineRT(
    source=SlabSource(x0=-5, n_photon=50000),
    x_min=(-5, 0, 0), x_max=(5, 0.2, 0.2),
    n_cell=(64, 2, 2),
    mfp_i_sca=100.0 / 1.496e14,   # τ₀ = 100 over 10 AU
    mfp_i_abs=0.0,
    n_photon=50000,
    n_step=10000, n_scat=100000,
    n_cycles=3,
)
result = rt.run()
```

**Mode 2 — physical medium** (species + density + temperature):

```python
from linert import LineRT, SlabSource
from molecular.lamda_format import load_lamda
import numpy as np

co = load_lamda(open('molecular/embedded/co.dat').read())

rt = LineRT(
    source=SlabSource(x0=-5, n_photon=50000),
    x_min=(-5, 0, 0), x_max=(5, 0.2, 0.2),
    n_cell=(64, 2, 2),
    species=co,
    n_total=1e4,           # total molecular density [cm⁻³]
    temperature=50.,        # gas temperature [K] (or array/callable)
    n_cycles=3,
)
result = rt.run()
```

`LineRT` handles all I/O automatically — no manual field writing, par templating, or subprocess calls.  See [examples/plane_parallel_example.py](https://github.com/username/line_rt/...) for the full example script.

### 3. Web Dashboard (sharing with collaborators)

```bash
panel serve web/app.py --port 5006
# Open http://localhost:5006 in browser
```

### 4. Command Line (batch runs)

```bash
python cli.py --source point,0,0,0,0.8,2.35e-4 --species CO --cycles 5
```

## Key Features

- **Unit safety** — all quantities in CGS, validated at I/O boundaries
- **LAMDA database** — embedded CO, OI, OH + auto-download for 57 more species
- **Self-consistent MC iteration** — no approximate escape probability; full optical depth treatment
- **Multi-level with optional collisions** — radiative-only or collisional-radiative equilibrium
- **Cartesian + spherical** — switchable coordinate systems

## References

- Schöier et al. (2005, A&A 432, 369) — LAMDA database
- Neufeld (1990, ApJ 350, 216) — analytic CFR solution used for validation
- Lucy (1999) — Monte Carlo radiative transfer methods

## License

MIT
