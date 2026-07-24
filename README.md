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

```python
from core.source import point_source, make_cartesian_mesh, Lsun
from core.fields import uniform_field
from core.iterator import iterate
from molecular.lamda_fetcher import fetch_species
import numpy as np

mesh = make_cartesian_mesh((32, 8, 8), (-5, 0, 0), (5, 3.14, 6.28))
photons = point_source(L=0.8 * Lsun, lam=2.35e-4, pos=(0, 0, 0), n_ph=50000)

n_tot = mesh['n_tot']
fields = {
    'mfp_i_sca_0': np.ones(n_tot) * 0.1,
    'mfp_i_abs_0': np.ones(n_tot) * 0.001,
    'b_sca': np.ones(n_tot) * 1e5,
    'b_abs': np.ones(n_tot) * 1e5,
    'vel_0': np.ones(n_tot) * 1e5,
    'vel_1': np.zeros(n_tot),
    'vel_2': np.zeros(n_tot),
}

species = fetch_species('CO')
results, populations = iterate(photons, species, fields, mesh, n_cycles=5)
```

See [docs/examples/plane_parallel.py](docs/examples/plane_parallel.py) for a complete end-to-end example.

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
