# line_rt_pipeline

Line radiative-transfer pipeline with self-consistent population
iteration, built on the [Kratos](https://github.com/...)
GPU Monte Carlo code.

See [docs/PHYSICS.md](docs/PHYSICS.md) for the physics tutorial and
[AGENTS.md](AGENTS.md) for the full developer reference.

## Installation

```bash
cd /path/to/line_rt_pipeline
pip install -e . --break-system-packages   # editable; live edits
```

This registers the `line-rt` console script and makes `import core`,
`import molecular` work from any directory.  Re-run only when
`pyproject.toml` changes (new deps, new entry points).

**Kratos binary.**  The pipeline shells out to the Kratos binary
(`bin/kratos`).  Its location is resolved at runtime by
`core/pipeline.py:resolve_kratos_bin()` in this order:

1. `kratos_root` kwarg: `LineRt(kratos_root=...)` / `--kratos-root`
2. `KRATOS_ROOT` environment variable
3. Default: `~/apps/kratos_line_rt`

If the binary is missing, a `FileNotFoundError` is raised with
instructions for all three methods.

**Running without install** also works.  Two options:

1. **CLI**: `python3 cli.py ...` from the repo root.
2. **Scripts / notebooks**: use `line_rt_bootstrap.py` - it adds the
   pipeline directory to `sys.path` and re-exports the public API:

   ```python
   import importlib.util, os
   _BOOT = os.path.expanduser(
       '/path/to/line_rt_pipeline/line_rt_bootstrap.py' )
   _spec = importlib.util.spec_from_file_location(
       'line_rt_bootstrap', _BOOT )
   lr = importlib.util.module_from_spec( _spec )
   _spec.loader.exec_module( lr )

   rt = lr.LineRt( ... )            # high-level orchestrator
   ti = lr.TransitionInfo( 'CO', 0 ) # species selection
   res = rt.run()
   ```

   Set the path in one place (the `_BOOT` line); no other
   `sys.path` manipulation needed.

## Three ways to use

### 1. Command line (batch runs)

```bash
# Group 2 (explicit opacity, no species data):
line-rt --mfp-i-sca-0 1e-13 --b-sca 1e5 --ph-mode 0 --n-photon 20000

# Group 1 (species-based, CO J=1-0):
line-rt --species CO --n-species 1e4 --temperature 100 --ph-mode 2

# Slab source with energetic flux:
line-rt --species CO --n-species 1e4 --temperature 100 \
    --source-type slab --source-x -5.0 --flux 1e-3 --wavelength 2.6e-2
```

Run `line-rt --help` for all flags, or `line-rt --list-species` to see
available molecules.

### 2. Python module (scripting / automation)

If installed (`pip install -e .`), import directly:

```python
from core.line_rt import LineRt
```

If NOT installed, use the bootstrap (see "Running without install"
above), then use `lr.LineRt` instead of `LineRt`.

**Group 2 - explicit opacity** (no species data needed):

```python
from core.line_rt import LineRt

rt = LineRt(
    n_cell          = ( 64, 2, 2 ),
    x_min           = ( -5, 0, 0 ), x_max = ( 5, 0.2, 0.2 ),
    b_sca           = 1e5,           # cm/s
    mfp_i_sca_0     = 1e-13,         # cm^-1
    ph_mode         = 0,
    n_cycles        = 3,
)
rt.set_boundary( 'fre fre per per per per' )
rt.add_source( n_photon = 50000, flux = 1e-3 )
results = rt.run()
```

**Group 1 - species-based** (LAMDA data + density + temperature):

```python
from core.line_rt           import LineRt
from molecular.transition_info import TransitionInfo

ti  = TransitionInfo( 'CO', 0 )            # CO J=1-0
rt  = LineRt(
    transition_info = ti,
    n_species       = 1e4,                  # cm^-3
    temperature     = 100.0,                # K
    ph_mode         = 2,
    n_cycles        = 3,
)
rt.add_source( n_photon = 50000, luminosity = 0.8 * 3.828e33 )
results = rt.run()
```

`LineRt` handles all I/O automatically: field binaries, par-file
templating, and subprocess calls to Kratos.  See
[docs/examples/](docs/examples/) for runnable example scripts.

### 3. Jupyter notebook (interactive)

```bash
jupyter lab ui/notebook.ipynb
```

### 4. Web dashboard (collaboration)

```bash
panel serve web/app.py --port 5006
```

## Embedded species data

20 species from the [LAMDA](https://home.strw.leidenuniv.nl/~moldata/)
database are shipped in `molecular/embedded/`:

```
CO  OH  OI  H2O  NH3  HCN  HCO+  CS  SiO  SO  SO2
H2CO  H2S  CH3OH  CN  NO  C2H  C3H2  N2H+  HNC
```

Additional species are auto-downloaded on first use to
`~/.line_rt_interface/lamda_cache/` (network access required; set
`HTTP_PROXY`/`HTTPS_PROXY` env vars if behind a proxy).

## Key features

- **Self-contained** - `binary_io.py` is vendored; no external Python
  path hacks needed.
- **Unit safety** - all quantities in CGS, validated at I/O boundaries.
- **Self-consistent MC iteration** - no approximate escape probability;
  full optical-depth treatment with MC -> population -> MC cycles.
- **Multi-level species** - LAMDA-based level populations with optional
  collisional rates.
- **GPU acceleration** - Kratos CUDA backend (ph_mode 0/1/2/3).
- **Validation** - regression tests against Neufeld (1990) analytic
  solutions; see `~/apps/kratos_line_rt/usr_ext/line_rt/tests/`.

## Implementation notes

### Binary I/O and field layout

Kratos stores field data in C++ row-major order: `cells[nz][ny][nx]`,
where `nx` varies fastest in memory.  The reader in `core/kratos_io.py`
reshapes the flat binary as `(nz, ny, nx)`, so
`excitation_flux[:n_cell_x]` directly yields the full x-profile at
`(z=0, y=0)` without manual reshaping.

### Headless environments

Example scripts use `matplotlib`.  For headless execution, add
`import matplotlib; matplotlib.use('Agg')` before importing
`matplotlib.pyplot`.

## References

- Schöier et al. (2005, A&A 432, 369) - LAMDA database
- Neufeld (1990, ApJ 350, 216) - analytic CFR solution used for
  validation
- Lucy (1999) - Monte Carlo radiative transfer methods

## License

MIT
