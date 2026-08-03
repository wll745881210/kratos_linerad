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

This registers the `line-rt` console script and makes `from line_rt import ...`
work from any directory.  Re-run only when `pyproject.toml` changes (new deps,
new entry points).

**Kratos binary.**  The pipeline shells out to the Kratos binary
(`bin/kratos`).  Its location is NOT hardcoded - set it via one of:

1. `kratos_root` kwarg: `LineRt(kratos_root=...)` / `--kratos-root`
2. `KRATOS_ROOT` environment variable

If neither is set, a `FileNotFoundError` is raised with instructions.

**Running without install.**  Use `line_rt.py` (a public facade at the
repo root) via `importlib` - works with symlinks too:

```python
import importlib.util, os
_PIPELINE = os.path.expanduser(
    '/path/to/line_rt_pipeline/line_rt.py' )
_spec = importlib.util.spec_from_file_location( 'line_rt', _PIPELINE )
line_rt = importlib.util.module_from_spec( _spec )
_spec.loader.exec_module( line_rt )

rt = line_rt.LineRt( kratos_root = '/path/to/kratos_line_rt', ... )
ti = line_rt.TransitionInfo( 'CO', 0 )
res = rt.run()
```

Set the path in one place (the `_PIPELINE` line); no `sys.path`
manipulation needed.  When installed, the same API is available as
`from line_rt import LineRt, TransitionInfo`.

## Three ways to use

### 1. Command line (batch runs)

```bash
# Group 2 (explicit opacity, no species data):
line-rt --mfp-i-sca-0 1e-13 --b-sca 1e5 --ph-mode 0 --n-photon 20000

# Group 1 (species-based, CO J=1-0):
line-rt --species CO --n-species 1e4 --temperature 100 --ph-mode 2

# Slab source with energetic flux:
line-rt --species CO --n-species 1e4 --temperature 100 \
    --source-type slab --source-x -5.0 --flux 1e-3 --source-units energy
```

Run `line-rt --help` for all flags, or `line-rt --list-species` to see
available molecules.

### 2. Python module (scripting / automation)

If installed (`pip install -e .`), import from `line_rt`:

```python
from line_rt import LineRt
```

If NOT installed, use `importlib` (see "Running without install"
above), then use `line_rt.LineRt` instead of `LineRt`.

**Group 2 - explicit opacity** (no species data needed):

```python
from line_rt import LineRt

rt = LineRt(
    n_cell          = ( 64, 2, 2 ),
    x_min           = ( -5, 0, 0 ), x_max = ( 5, 0.2, 0.2 ),
    b_sca           = 1e5,           # cm/s
    mfp_i_sca_0     = 1e-13,         # cm^-1
    ph_mode         = 0,
    n_cycles        = 3,
    kratos_root     = '/path/to/kratos_line_rt',
)
rt.set_boundary( 'fre fre per per per per' )
rt.add_source( n_photon = 50000, flux = 1e-3 )
rt.show_sources()
rt.plot_input()                     # verify input fields before running
results = rt.run()
```

**Continuum-style sources** — randomize each packet's initial velocity
shift (injected at a random frequency offset, emulating a broad
continuum) with `vel_range`:

```python
# uniform over [-1e5, +1e5] cm/s, added on top of vel_offset
rt.add_source( type = 'slab', flux = 1e-3,
               vel_offset = 0.0, vel_range = ( -1e5, 1e5 ) )

# Gaussian (truncated to the interval), width vel_sigma
rt.add_source( type = 'point', luminosity = 1e30,
               vel_range = ( -3e5, 3e5 ),
               vel_pdf = 'gaussian', vel_sigma = 1e5 )

# arbitrary (possibly unnormalized) PDF: integrated to a normalized CDF,
# sampled by inverse transform
rt.add_source( type = 'slab', flux = 1e-3,
               vel_range = ( -2e5, 2e5 ),
               vel_pdf = lambda v: np.exp( -( v / 1e5 ) ** 2 ) )
```

`vel_range = None` (default) keeps the current behaviour: every photon
gets exactly `vel_offset`.

**Extended point source** — spread each packet's initial position
uniformly (volume-weighted) over a sphere of radius `r_random` [cm]
centred on `position`:

```python
rt.add_source( type = 'point', luminosity = 1e30, position = ( 0, 0, 0 ),
               r_random = 1.5e13 )   # emission within R=1.5e13 cm
```

`r_random = 0.0` (default) keeps all photons exactly at `position`.
`r_random > 0` is rejected for slab sources.

**Group 1 - species-based** (LAMDA data + density + temperature):

```python
from line_rt import LineRt, TransitionInfo

ti  = TransitionInfo( 'CO', 0 )            # CO J=1-0
rt  = LineRt(
    transition_info = ti,
    n_species       = 1e4,                  # cm^-3
    temperature     = 100.0,                # K
    ph_mode         = 2,
    n_cycles        = 3,
    kratos_root     = '/path/to/kratos_line_rt',
)
rt.add_source( n_photon = 50000, luminosity = 0.8 * 3.828e33 )
results = rt.run()

# Energetic (erg-based) slab flux - wavelength taken from the transition:
rt.add_source( n_photon = 50000, flux = 1e-3, units = 'energy' )
```

**Transition not in the LAMDA database?** Build a species-based Group 1
configuration from physical transition parameters with
`TransitionInfo.user_defined( )`:

```python
ti = TransitionInfo.user_defined(
    A_ul       = 1.0e-6,          # Einstein A [s^-1]
    freq_GHz   = 115.271,         # or value + unit (wavelength/energy)
    g_u        = 3,  g_l = 1,     # degeneracies (default 1/1)
    species_name = 'CO',          # resolves the molecular mass
)                                # unknown name -> pass mol_mass
rt = LineRt( transition_info = ti, n_species = 1e4, temperature = 100.0 )
```

The species is built as a 2-level system; `E_u/K` defaults to the photon
energy `h·ν/k_B` (pass `E_u_K` to override).  Everything downstream
(σ₀, Doppler b, populations, MCRT) works identically to a LAMDA species.


Flux/luminosity default to **photon number**; pass `units='energy'`
for erg-based quantities (the wavelength is taken from
`transition_info`, so no `wavelength` argument is needed).  `flux` is
only valid for `type='slab'`, `luminosity` only for `type='point'` —
passing the wrong pair raises `ValueError`.  `rt.show_sources()`
prints a summary of all registered sources.

**Emission-only runs** — a species (Group 1) works without any
`add_source()`: cycle 0 is seeded with internal emission photons
generated from the initial LTE populations, and later cycles regenerate
emission from the updated populations.  Initial populations are ALWAYS
thermalised to LTE at the gas temperature (`SpeciesData.initial_populations(n_species, T=...)`),
even when external sources are present, so cycle-0 opacity and
emissivity are physically consistent.

`rt.plot_input()` (interface mirrors `default_plot`) plots slices of
the configured input fields — `n_species`, `temperature` (Group 1),
`mfp_i_sca_0`, `b_sca`, `mfp_i_abs_0`, and `vel_0..2` (both groups) —
resolved at cell centres **without running Kratos**, so you can verify
the input before a run.  Unconfigured fields appear as `(no data)`
panels.  After a run, `rt.plot_results( )` plots the run output via
`default_plot` — the `run()` return value is cached in `rt._results`,
so the `out` argument is optional (`rt.plot_results( out )` still
works if you want to plot a specific results dict).

**Imaging (two-step)** — pass `imaging=` to the `LineRt` constructor to
produce a position–velocity cube on the final MC cycle (scattering
source function sampling + non-scattering ray tracing; physics in
`docs/PHYSICS.md` §12):

```python
rt = LineRt(
    transition_info = ti,
    n_species       = 1e4,  temperature = 100.0,
    n_cycles        = 3,
    kratos_root     = '/path/to/kratos_line_rt',
    imaging = {
        'dir_cam': ( 0.5, 0.0 ),   # (theta, phi) [rad], LOS INTO the domain
        'n_chan':  64,             # velocity channels
        'v_chan':  ( -1e6, 1e6 ),  # [cm/s]
    },
)
out = rt.run()
out['image']              # {'cube': (n_pix, n_chan) CGS, 'i2d', 'v_chan', ...}
rt.plot_channel_maps()    # shared-log-scale single-channel spatial maps
```

The image cube is `out['image']['cube']` (erg cm⁻² s⁻¹ sr⁻¹ per pixel
per channel); `rt.plot_channel_maps()` renders a grid of channel maps
with a shared logarithmic scale (≤ 4 dex, values below the lower limit
saturated).  See `docs/examples/imaging_hl.py` for a runnable example.

`LineRt` handles all I/O automatically: field binaries, par-file
templating, and subprocess calls to Kratos.  See
[docs/examples/](docs/examples/) for runnable example scripts.

### Memory management

Per-cycle binaries live in the run directory under `/dev/shm/line_rt/`
(a tmpfs mount — so on-disk files consume **RAM**), and every cycle's
full float64 flux/population arrays are held in the returned `results`
list.  For long multi-cycle runs this can exhaust memory.  Several knobs
bound both:

- **`keep_intermediate=False`** (default for `LineRt` / `iterate()` /
  `run_pipeline()` / CLI; pass `--keep-intermediate` to keep files):
  each cycle's `fields_cycleN.bin`, `photons_cycleN.bin`,
  `cycleN.par`, `cycleN.txt`, and `cycleN_00000.bin` are deleted as soon
  as their data has been read back into RAM.  The fixed fields file and
  the final cycle's output are always kept.  When using `LineRt` with an
  auto-created run directory, `run()` additionally removes the whole
  directory afterwards — including on a crashed/interrupted run (an
  explicit `path=` is never touched).
- **`max_run_age` / `size_cap`** (constructor / `--max-run-age` /
  `--size-cap`): before starting each auto-created run, `run()` prunes
  the scratch root — deleting `rt_*` run dirs older than `max_run_age`
  (default 3 hours) and, if the total size of `rt_*` dirs exceeds
  `size_cap` (default 4 GB), removing the oldest dirs until under the
  cap.  Pass `0` to disable either.
- **`retain_cycles=N`** (constructor / `iterate()` / `run_pipeline()` /
  `--retain-cycles`): only the last `N` cycle dicts are kept in
  `out['results']`; older cycles are dropped to bound Python-side RAM.
  Default `None` keeps every cycle.

Stored output fields (`flx`, `exc_flux_flat`) are always `float32` —
Kratos produces float32 field binaries, so nothing is lost while halving
storage relative to float64.

### Escaped photons and proper weights

Each cycle's `results` dict carries the escaped photons under
`results[i]['photons']` with keys `x` (positions, CGS cm), `dir`
(unit direction vectors), `vel` (CGS cm/s), and **`proper`** — the
surviving photon weight in photons/s per packet (CGS).  `proper` is what
matters for photon statistics: scattered/absorbed photons contribute
proportionally less, and `sum(proper)` is the total escaped photon
luminosity.  The `run()` output `spectrum` (`{'vel': ..., 'n': ...}`) is
proper-weighted, so the emergent histogram reflects photon statistics
rather than raw packet counts.  (The old key `'l'` is retained as a
deprecated alias for `'proper'` — it was a weight all along, never a
path length.)

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
- **Two-step imaging** - position-velocity cubes via scattering-source-
  function sampling + non-scattering ray tracing (Kratos-polrad method);
  see `LineRt(imaging=...)` and `docs/PHYSICS.md` §12.
- **Multi-level species** - LAMDA-based level populations with optional
  collisional rates.
- **GPU acceleration** - Kratos CUDA/HIP/MUSA backend
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
- Li et al. (2015, ApJS 216, 15) - ExoMol `Li2015` hot line list for CO
  (ro-vibrational X¹Σ⁺ lines with per-line Einstein A). Download:
  `https://exomol.com/db/CO/12C-16O/Li2015/`
  (`12C-16O__Li2015.trans.bz2` = `i f A[s⁻¹] ν[cm⁻¹]`;
  `12C-16O__Li2015.states.bz2` = `idx E[cm⁻¹] g J v e`).
- Neufeld (1990, ApJ 350, 216) - analytic CFR solution used for
  validation
- Lucy (1999) - Monte Carlo radiative transfer methods

## License

MIT
