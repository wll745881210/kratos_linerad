# AGENTS.md

Instructions for agentic sessions working on the `line_rt_pipeline` codebase.

## Network

The pipeline downloads LAMDA species data on demand from
`https://home.strw.leidenuniv.nl/~moldata/`.  No proxy is hardcoded;
`requests` honours the standard `HTTP_PROXY` / `HTTPS_PROXY` environment
variables automatically.  If you are behind a proxy, set them before
running the pipeline:

```bash
export http_proxy=http://your-proxy:port
export https_proxy=http://your-proxy:port
```

---

## Installation

```bash
cd ~/Seafile/seafile_sync/code/line_rt_pipeline
pip install -e . --break-system-packages   # editable; live edits, no reinstall needed
```

This registers the `line-rt` console script and makes `from line_rt import ...` work from any CWD. Re-run only when `pyproject.toml` changes (new deps, new entry points).

**Kratos binary location** is resolved at runtime by `core/pipeline.py:resolve_kratos_bin()` in this order:
1. `kratos_root` kwarg: `LineRt(kratos_root=...)` / `iterate(kratos_root=...)` / `--kratos-root` CLI flag
2. `KRATOS_ROOT` environment variable

There is NO default - you must set one of the above. If neither is set, a `FileNotFoundError` is raised with instructions (Python, notebook `%env`, shell `export`).

**Running without install** also works: `python3 cli.py ...` from the repo root (the `cli.py` sys.path bootstrap was removed; Python's default CWD-on-path handles it). For scripts and notebooks, use `line_rt.py` (public facade at the repo root) via `importlib.util.spec_from_file_location()` - works with symlinks too:

```python
import importlib.util, os;
_PIPELINE = '/path/to/line_rt_pipeline/line_rt.py';
_spec = importlib.util.spec_from_file_location( 'line_rt', _PIPELINE );
lr = importlib.util.module_from_spec( _spec );
_spec.loader.exec_module( lr );

rt = lr.LineRt( kratos_root = '/path/to/kratos_line_rt', ... );
```

When installed, the same API is available as `from line_rt import LineRt, TransitionInfo`.

---

## Project layout

| Directory | Purpose |
|-----------|---------|
| `core/` | `LineRt` orchestrator, field functions, source generation, iterator, visualization, consistency checks, Kratos I/O (`kratos_io.py`), `binary_io.py` (vendored from kratos/visual), low-level `run_pipeline()` + par templates |
| `molecular/` | Species data (LAMDA), cross sections, population solver, LAMDA downloader |
| `ui/` | Jupyter ipywidgets interface |
| `web/` | Panel dashboard (`panel serve web/app.py`) |
| `cli.py` | CLI entrypoint (`line-rt` console script, registered in `pyproject.toml`) |
| `line_rt.py` | Public facade: re-exports `LineRt`, `TransitionInfo`, etc. Single import point for both installed and importlib loading. |
| `docs/archived_tests/` | Archived standalone test scripts (moved from `tests/`) |
| `docs/reference_mcrt/mcrt.py` | Reference Python MCRT (numba). ph_mode=1 uses USampler table-lookup R_IIA. `plot_neufeld.py` validates vs Neufeld (1990). |
| `~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_wide.py` | **Standalone Kratos regression test** (self-contained, no pipeline imports). Wide `aτ₀` sweep vs Neufeld eq (2.24) for ph_modes 1/2/3, golden med\|x\| table, PASS/FAIL exit code. Run: `python3 test_scaling_wide.py --kratos-root ~/apps/kratos_line_rt` |
| `~/apps/kratos_line_rt/` | Kratos build tree (symlinked to Seafile source) |
| `~/scratch/line_rt/` | Historical runtime dir; new runs default to per-run subdirs under `/dev/shm/line_rt/`. `fiducial/` subdir holds reference test records. |

---

## Architecture: two-level API

**High level — `LineRt` class** (`core/line_rt.py:25`): single-entry-point orchestrator. Configure geometry, sources via constructor + `add_source()`, then call `run()`. Handles mesh creation, field resolution, photon generation, consistency checks, and the full MC → population → MC cycle loop. This is what README examples and the CLI use.

**Species selection — `TransitionInfo`** (`molecular/transition_info.py`): pass `transition_info = ti` to the `LineRt` constructor to use the species-based (Group 1) configuration. `TransitionInfo` resolves the species data, transition index, molecular mass (built-in table), and auto-wavelength (`add_source()` defaults `wavelength` to the transition wavelength when given). Constructor: `TransitionInfo( species, transition_idx = 0, *, value = None, unit = None, freq_GHz = None, mol_mass = None )` — the transition can be picked by index, by `freq_GHz`, or by `value`+`unit` (`GHz`/`THz` for frequency, `cm`/`mm`/`um`/`nm`/`angstrom` for wavelength, `eV`/`erg` for photon energy; all converted to frequency and matched via `specify_transition()`). No `species`/`transition_idx`/`mol_mass` arguments on `LineRt` — mol_mass comes only from `TransitionInfo` (explicit arg or table; `MolecularMassError` if unknown).

**Low level — `iterate()`** (`core/iterator.py:16`): bare loop over writes→run→read→update. Takes raw arrays; no species resolution or source generation. `LineRt.run()` delegates to this.

---

## Running Kratos

**ALWAYS run under a per-run subdir of `/dev/shm/line_rt/`** (auto-created by the pipeline). The Python pipeline writes field/photon binary files there, and Kratos reads them via the par file's `field_file` / `photon_file` entries. The run directory is printed at startup (e.g. `[LineRt] Run directory: /dev/shm/line_rt/rt_20260801_120000`).

Kratos requires a `.par` file. The canonical template lives at:

```
line_rt_pipeline/core/line_rt_pipeline.par
```

Minimal invocation:

```bash
cd /dev/shm/line_rt/<run_dir>
~/apps/kratos_line_rt/bin/kratos <par_file>
```

### Par-file essentials

A minimal working par file (a=0 plane-parallel MCRT, ph_mode=0) is at:

```
pipeline/a0_test.par
```

It can be used as a template for simple MCRT validation runs. Copy it to
a per-run subdir of `/dev/shm/line_rt/` and edit `[mesh]`, `[line_rt]` `b_sca`,
and `field_file`/`photon_file` paths as needed.

The `[line_rt]` section must contain:

```ini
[line_rt]
field_file       = fields_cycle0.bin   # line-dependent (mfp_i_sca_0, mfp_i_abs_0)
field_fixed_file = fields_fixed.bin    # line-independent (b_sca, vel) - optional, falls back to field_file
photon_file      = photons_cycle0.bin
ph_mode          = 0          # 0=CFR (Gaussian), 1/2/3=R_IIA (USampler)
b_sca            = 1.0        # Doppler b (scattering) - used for overlap integral
const_abs        = 1          # always 1 (absorption is wavelength-independent)
n_fld            = 1
num_rng          = 16381
a_voigt          = 0.0        # Voigt damping parameter (0 = pure Gaussian)
```

**Field file split (Task 2):** Fields are split into two groups to prepare for multi-line problems:
- `field_file` (line-dependent): `mfp_i_sca_0`, `mfp_i_abs_0` - change per cycle as populations evolve and differ per transition.
- `field_fixed_file` (line-independent): `b_sca`, `vel_0..2` - depend only on the gas (bulk velocity, thermal temperature, molecular weight), fixed across lines. Written once per simulation.
- If `field_fixed_file` is omitted, Kratos falls back to reading `b_sca`/`vel` from `field_file` (backward compatibility).

**ph_mode values:**
- `0` – CFR: `Δv = −v·d̂`, `σ_ph = σ_th` (no random velocity)
- `1` – R_IIA: exact USampler kernel (log-CDF table, global mem) + 2D Voigt opacity table (global mem, 128 KiB)
- `2` – R_IIA: same USampler kernel, but tables in **constant memory**: coarse log-CDF USampler (251×40, `du=0.048`) + 1D log-space Voigt table (5000 pts, `u∈[0,50]`, built from the host-side scipy 2D table). Fastest exact mode.
- `3` – R_IIA: const-mem USampler only; scattering profile uses the approximate analytic `voigt_H` blend in `photon.h` (Gauss core + Lorentz wing crossover). Fastest overall but underestimates `med|x|` at low `aτ₀` (~0.77–0.94× Neufeld for `aτ₀=30–1192`); converges at high `aτ₀`.

All R_IIA modes (1/2/3) share the same scattering kernel (`g = dir_old·dir` directional correlation). Modes 1 and 2 agree to ~1–2% (`med|x|`); use `2` for production, `1` for debug (global-mem table). `ph_mode=2`/`3` use the constant-memory pool — **not freed** in `finalize` (`free_dev_mem=false`); the 60 KiB const pool is a bump allocator.

### `[cycle]` section (output control)

For single-run MCRT tests (one Kratos invocation = one output file), use this canonical pattern:

```ini
[cycle]
prefix_output  = test        # output filename prefix -> test_00000.bin
n_cycle_lim    = 0           # 0 or 1 (no difference with t_output_next=1e32)
t_lim          = 600.0       # simulation time limit
t_output_next  = 1e32        # disable time-based output (never triggers)
dt_output      = 1e32        # output interval (disabled by t_output_next)
final_output   = 1           # guarantee one output when the run finishes
```

- `t_output_next = 1e32` disables time-based output entirely, preventing an empty cycle-0 file. With `final_output = 1`, exactly ONE output file is produced: `{prefix_output}_00000.bin`.
- `prefix_output` sets the output filename prefix. Example: `prefix_output = aa` generates `aa_00000.bin`.
- Without `t_output_next = 1e32`, Kratos may emit an empty cycle-0 output before the real output at cycle-1.

**There is no `b_abs` parameter anymore.** Absorption MFP is purely user-provided (via `base_fields` in Python), never derived from the line-center cross-section formula.

### Unit system

**The par file MUST have everything in code units — except the `[unit]` section itself.**

```ini
[unit]
length  = 1.49598e13    # code unit to cm (CGS)
time    = 1.0            # code unit to second (CGS)
density = 1.0            # code unit to g/cm^3 (CGS)

[mesh]
x_min = -3.34 0 0        # CODE units (NOT CGS)
x_max = 3.34 1 1         # CODE units

[line_rt]
b_sca = 1.3369e-7        # CODE units (b_CGS × unit_t0 / unit_l0)
```

The `[unit]` section is for reference/documentation — Kratos does NOT automatically convert mesh coordinates or line_rt parameters. The Python pipeline converts everything to code units before writing the par file. Field binary coordinates (`x0`, `dx`) must also be in code units, matching `geo.x_cc()`.

---

## Compiling Kratos

```bash
cd ~/apps/kratos_line_rt

# Incremental build
make USRDIR=usr_ext/line_rt -j8

# Clean rebuild
make clean && make USRDIR=usr_ext/line_rt -j8
```

**Rules:**
- **Always specify `USRDIR=usr_ext/line_rt`.** Without it the default `USRDIR=usr` won't link the line_rt module.
- **Never compile in `~/Seafile/`.** Source lives there but object/bin files go to `~/apps/kratos_line_rt/` (symlinked).
- The binary is at `~/apps/kratos_line_rt/bin/kratos`.
- **`~/Seafile/seafile_sync/code/kratos/` and `~/Seafile/seafile_sync/code/kratos/usr_ext/` are SEPARATE git repos.** Git operations in one do NOT affect the other. Never checkout/commit in the wrong repo.

### Usr-ext source files

| File | Role |
|------|------|
| `usr_ext/line_rt/radiation.h` | Field I/O, `init_cond` (GPU kernel), `ini_t` (interp tables, `to_device`/`free_device`) |
| `usr_ext/line_rt/photon.h` | `proc_geo` (scattering physics), `proc_phys` (excitation) |
| `usr_ext/line_rt/pool.h` | Escaped photon output writing |
| `usr_ext/line_rt/gen.h` | Photon generation from binary |
| `usr_ext/line_rt/intg.h` | Integrator parameters, Voigt interpolation table |
| `usr_ext/line_rt/block_data.h` | `rad_t` struct, block I/O (`copy_input` blank, `copy_output` device->host) |
| `usr_ext/line_rt/line_rt.h` | Profile functions (b_sca only) |

### GPU field initialization (Task 1)

Field arrays (`mfp_i_sca_0`, `mfp_i_abs_0`, `b_sca`, `vel[3]`) are initialized on the **GPU** by sampling device-resident `interp_t` tables at cell centers, NOT on the CPU. The flow:

1. `ini_t::read()` loads `interp_t` tables from the field binary (host memory).
2. `ini_t::to_device(dev)` (called in `init()`, after `p_dev` is available) moves tables to device global memory.
3. `init_cond()` zeros device field arrays via `f_mset`, then launches `init_rad_fields_kernel` (2D grid: `n_th=(nx)`, `n_bl=(ny,nz)`) to sample tables at cell centers.
4. `finalize()` calls `ini_t::free_device(dev)` to release table memory after init is done.
5. **`block_data_t::copy_input` is intentionally blank** - prevents `copy_h2d()` from flushing GPU-initialized fields with uninitialized host garbage. Field copies happen only in `copy_output` (device->host).

---

## Physics reference

**PHYSICS.md (`docs/PHYSICS.md`) is the authoritative specification.** All implementations must comply with it. Key points:

- All quantities are in photon-number units (proper = photons/unit-time, not erg/s).
- Absorption is wavelength-independent — user provides `mfp_i_abs_0` directly.
- Only `b_sca` (Doppler b for scattering) appears in the overlap integral and profile.
- Cross section: `σ₀ = (g_u/g_l) × A_ul × c³ / (8 π^(3/2) ν³ b)`
- Per-lower-level excitation rate: `Γ = F_ext × σ₀` (where F_ext comes from Kratos).
- The overlap integral I is computed in Kratos `photon.h:proc_phys` using `b_sca`.

---

## Python pipeline workflow

```
Cycle 0:  LTE populations -> make_fields() -> write line + fixed binaries -> run Kratos
Cycle 1+: read_output() -> update_populations(F_ext) -> make_fields() -> write line binary -> run Kratos
```

(line-dependent `field_file` is written per cycle; line-independent `field_fixed_file` is written once at cycle 0.)

Key functions:

| Function | File | Returns |
|----------|------|---------|
| `compute_opacity(pops, b_sca, transition_idx)` | `molecular/lamda_format.py` | `mfp_sca` only (absorption MFP is user-provided) |
| `update_populations(exc_flux, flx, pops, cycle, dx, b_sca, T, colliders, transition_idx)` | `molecular/lamda_format.py` | Updated population dict |
| `make_fields(pops, step, cycle, base_fields, unit_l0, unit_t0, transition_idx)` | `molecular/lamda_format.py` | Field dict — includes `mfp_i_abs_0` only if in `base_fields` |
| `write_field_data(filename, fields, mesh, group='all')` | `core/kratos_io.py` | Writes binary; `group='line'` (mfp_i_*), `'fixed'` (b_sca, vel), or `'all'` |
| `write_photon_data(filename, photons)` | `core/kratos_io.py` | Writes photon binary |

### Field keys written to Kratos

**Split into two binary files (Task 2):**

| File | Key | Content |
|------|-----|---------|
| `field_file` (line-dependent, per cycle) | `mfp_i_sca_0_` | **Inverse** scattering MFP at line centre (σ₀ × n_lower) [code-l]⁻¹ |
| `field_file` | `mfp_i_abs_0_` | **Inverse** absorption MFP [code-l]⁻¹ |
| `field_fixed_file` (line-independent, once) | `b_sca_` | Doppler b for scattering overlap integral |
| `field_fixed_file` | `vel_0_`, `vel_1_`, `vel_2_` | Bulk velocity (3 components) |
| `field_fixed_file` | `temp_` | Temperature (optional, diagnostic) |

> **Suffix convention:** `_i` means "inverse" (reciprocal). ALL `mfp_i_*` values are inverse mean free paths (cm⁻¹), NOT actual mean free paths (cm). For τ₀ = 100 over length L: `mfp_i_sca_0 = 100/L`, not `L/100`.
>
> If `field_fixed_file` is omitted in the par file, Kratos falls back to reading `b_sca`/`vel` from `field_file` (backward compat).

---

## Example test invocation

```python
import sys; sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline')
from docs.examples.plane_parallel import *
```

Or run directly (generates plots):

```bash
cd /dev/shm/line_rt
python3 ~/Seafile/seafile_sync/code/line_rt_pipeline/docs/examples/plane_parallel_hl.py
```

Neufeld validation (Python reference MCRT):

```bash
cd /dev/shm/line_rt
python3 ~/Seafile/seafile_sync/code/line_rt_pipeline/docs/reference_mcrt/plot_neufeld.py [output_prefix]
```

Full research record: `~/scratch/line_rt/fiducial/neufeld_test.md`

---

## Common pitfalls

1. **Two-group validation rule.** `LineRt.run()` calls `check_consistency()` (`core/consistency.py:43`). You MUST provide either **Group 1** (via `transition_info` + n_species + temperature) or **Group 2** (b_sca + mfp_i_sca_0). Group 1 takes precedence. If both incomplete, `ConsistencyError` is raised. **Adding a new mode or parameter? Add it to `check_consistency()` too.**
2. **Don't derive absorption opacity from `cross_section()`.** `mfp_i_abs_0` must come from `base_fields`.
3. **Don't add `b_abs` back.** It was intentionally removed everywhere.
4. **Always run Kratos from a per-run subdir of `/dev/shm/line_rt/`** where the binary field/photon files live.
5. **Always pass a `.par` file.** Kratos won't run without one.
6. **`compute_opacity()` returns only `mfp_sca`** — a single ndarray, not a tuple.
7. **One excitation flux → one transition, not all levels.** `solve_populations()` applies F_ext × σ₀ only to the (lower↔upper) pair of the target transition.
8. **`dv_c` does not exist anymore.** Removed from photon struct, binary format, and all I/O. The photon binary columns are: x,y,z, dir_x,dir_y,dir_z, proper, [vel], [sv].  `write_photon_data()` accepts 7, 8, or 9 columns.
9. **Proper-weight FP32 scaling:** `write_photon_data()` scales `proper` by `1/proper_max` to fit FP32. It RETURNS the scale factor. Both `iterate()` and `run_pipeline()` MUST undo the scaling by multiplying flx and exc_flux by `1/scale_factor` after readback. Values in `output['flx']` and `output['exc_flux_flat']` are always in CGS.
10. **Photon binary columns 7 (vel) and 8 (sv, Gaussian σ) are velocities → need CGS→code conversion:** `× unit_t0/unit_l0` before writing, `÷ unit_t0/unit_l0` (= `× unit_l0/unit_t0`) on readback for escaped photons.
11. **Two distinct 3D data ordering conventions in Kratos:**
    - **OUTPUT fields** (flx, exc_flux read via `read_output()`): `(nz, ny, nx)` (z slowest, x fastest in C++ row-major). `slice_plot_2d()` must reshape accordingly and `.T` transpose slices for pcolormesh.
    - **INPUT field binaries** (`field_file`/`field_fixed_file`, read by `interp_t`): data is written in `(nz, ny, nx)` C-order (z slowest, x fastest) with `ijkl=0` flag. `interp_t` with `ijkl=false` indexes as `idx = iz*ny*nx + iy*nx + ix`, matching the `(nz, ny, nx)` layout directly. `write_field_data()` writes 3D `(nz, ny, nx)` arrays with `np.pad` + ravel, no transpose needed. **The Python pipeline uses 3D `(nz, ny, nx)` arrays everywhere** (field dicts, populations, exc_flux, flx); callables receive `(X, Y, Z)` tuples of 3D arrays.
12. **Boundary cells produce NaN in excitation_flux** — both `iterate()` and `run_pipeline()` filter NaN to 0 before population update.
13. **`gen.h:104-107`:** `par.sv` is the photon's Gaussian σ (NOT the Doppler b). The relation is `b = σ·√2`. Read from binary column 8 when `ncol_ph >= 9`; defaults to 0.f (monochromatic at line centre) when not provided. After first scatter, `sv` is reset to the thermal σ (= `b_sca / √2`). **Column layout:** 0-2=pos, 3-5=dir, 6=proper, 7=vel, 8=sv.
14. **`base_fields_cgs` must be kept separate** from the code-unit `fields` output to prevent double unit-conversion across cycles.
15. **Boundary `kinds` MUST specify all 6 faces, not 3.** Kratos expects 6 values: `-x, +x, -y, +y, -z, +z`. Writing only 3 leaves the remaining undefined, defaulting to periodic. **The par template default is now all-free** (`fre fre fre fre fre fre`). For plane-parallel slabs, use `par_overrides={'kinds': 'fre fre per per per per'}` or `rt.set_boundary("fre fre per per per per")`.
16. **Slab sources use `flux`, point sources use `luminosity`.** `add_source` enforces this: passing `luminosity` to a `slab` source or `flux` to a `point` source raises `ValueError`, and each type requires its own quantity (slab needs `flux`, point needs `luminosity`). Quantities default to **photon number** (`flux` in [photons cm⁻² s⁻¹], `luminosity` in [photons/s]); pass `units='energy'` for erg-based values (erg cm⁻² s⁻¹ / erg s⁻¹). With `units='energy'` the conversion uses the `transition_info` wavelength — there is NO `wavelength` argument on `add_source`, and `units='energy'` without a transition raises `ValueError`. The proper per packet = flux × source_area_cm² / n_photon. `LineRt.show_sources()` prints all registered sources.
16b. **`LineRt.plot_input()` plots configured input fields WITHOUT running Kratos.** It resolves `n_species`, `temperature` (Group 1), `mfp_i_sca_0`, `b_sca`, `mfp_i_abs_0`, and `vel_0..2` (both groups) at cell centres in CGS via `_plot_input_data()` and renders them with `default_plot`. Default field set: Group 1 → `[n_species, temperature, mfp_i_sca_0, b_sca, mfp_i_abs_0, vel_0, vel_1, vel_2]`; Group 2 → `[mfp_i_sca_0, b_sca, mfp_i_abs_0, vel_0..2]` (vel only when `vel` configured). Unconfigured fields show `(no data)` panels. No `check_consistency()` is run — plot whatever is configured. `LineRt.plot_results(out)` plots `run()` output via `default_plot` (wraps the old `_plot_results`). Velocity fields (`vel_*`) and uniformly non-positive data use a **linear** colormap in `default_plot` (`_LINEAR_FIELDS`), because `LogNorm` cannot handle negative/zero values; `_extract_field` converts `vel_*` cm/s → km/s like `b_sca`.
17. **Default boundaries are all-free.** Use `set_boundary(kinds)` on `LineRt` or `par_overrides={'kinds': ...}` in `iterate()` to configure boundaries for your geometry.
18. **Internal emission photons are recomputed each cycle — they do NOT accumulate.** `core/iterator.py` keeps the external `source_photons` array immutable and regenerates emission from the updated populations each cycle (`SpeciesData.generate_emission_photons()`), combining per cycle as `vstack([ext_source, emission_ph])`. The per-cycle photon count is therefore stable (external + fresh emission), NOT growing linearly. Padded/truncated to match the external source photon column count. Control with `n_emission_max` on `LineRt`.
19. **Regression tests: copy to temp directories, NEVER touch the trunk.** Before testing with historical versions (e.g. git-bisecting a regression), clone the repos to temp directories and work there. Never modify `~/apps/kratos_line_rt/` or `~/Seafile/seafile_sync/code/kratos/` or `~/Seafile/seafile_sync/code/line_rt_pipeline/` for A/B testing.

   Template:
   ```bash
   # Copy Kratos build tree (includes compiled binary, src/, usr_ext/)
   cp -a ~/apps/kratos_line_rt /tmp/regtest_kratos

   # Copy pipeline
   git clone ~/Seafile/seafile_sync/code/line_rt_pipeline /tmp/regtest_pipeline

   # Checkout historical versions in temp copies only
   cd /tmp/regtest_kratos/usr_ext && git checkout <old_commit>
   cd /tmp/regtest_pipeline && git checkout <old_commit>

   # Build the temp Kratos if usr_ext changed
   cd /tmp/regtest_kratos && make USRDIR=usr_ext/line_rt -j8

   # Run from temp dir, never from ~/scratch/line_rt
   mkdir /tmp/regtest_run
   cd /tmp/regtest_run
   /tmp/regtest_kratos/bin/kratos <par_file>

   # Cleanup when done
   rm -rf /tmp/regtest_kratos /tmp/regtest_pipeline /tmp/regtest_run
   ```

20. **CRITICAL: n_cell_global minimum is 2 in EVERY dimension. `n_cell=1` WILL silently fail — Kratos produces only particle output with no field data or escaped photons.** This is the #1 pitfall. Never use `n_cell_global = 1 2 2` or any dimension with 1 cell. Always `>=2` for each component. The mesh output `.bin` file is produced but contains zero flux fields, and `n_cell` comes back as `None` from `read_output()`. Purely a Kratos requirement; the Python reference MCRT can use n_cell=1 but Kratos cannot.
21. **`core/binary_io.py` is vendored** from `~/Seafile/seafile_sync/code/kratos/visual/binary_io.py`. The pipeline is now self-contained — no `sys.path` hack needed for I/O. If the Kratos `binary_io` upstream changes, re-copy it into `core/binary_io.py`.

    **Standalone regression tests** (`~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_wide.py`, `test_absorption_scattering.py`) are separate from the pipeline and use the **Kratos build tree's** `binary_io.py` (not the pipeline's vendored copy). There, never import `binary_io` at module top level.** Load it lazily inside a `resolve_kratos_root(kratos_root)` helper that (1) validates `<kratos-root>/bin/kratos` and `<kratos-root>/visual/binary_io.py` exist, (2) inserts `<kratos-root>/visual` into `sys.path`, and (3) returns `binary_io`. Use `importlib` so static checkers (pyright/Pylance) never flag `Import "binary_io" could not be resolved`:

    ```python
    import importlib
    ...
    binary_io = importlib.import_module('binary_io').binary_io
    ```

    A static `from binary_io import binary_io` triggers a false-positive LSP error (the module only resolves at runtime after `sys.path` is patched). Do NOT fix it with `# type: ignore` or LSP `extraPaths` — those are per-file/config hacks; `importlib` is the portable fix. See `usr_ext/line_rt/tests/README.md` (Troubleshooting) and the `--kratos-root` flag conventions there.

22. **Par file and field binary: everything in code units except `[unit]`.** Mesh coordinates (`x_min`, `x_max`), `b_sca`, and all field binary spatial grids (`x0`, `dx`) must be in code units — NOT CGS. The `[unit]` section is documentation-only; Kratos does NOT convert mesh or `[line_rt]` parameters. `geo.x_cc()` returns code units. Python converts CGS → code before writing: positions / `unit_l0`, velocities × `unit_t0/unit_l0`, inverse lengths × `unit_l0`.

    ```cpp
    // 1. Allocate host copy of the table (interp_t will own and free it)
    float *copy = (float*)std::malloc(sizeof(float) * n_total);
    std::memcpy(copy, static_table_data, sizeof(float) * n_total);
    
    // 2. Set up the grid (uniform or non-uniform)
    voigt_interp.setup(x0, dx, n, copy);
    
    // 3. Move data to device const/global memory (frees host copy)
    voigt_interp.to_const(*mod.p_dev);
    //  or: voigt_interp.to_device(*mod.p_dev);
    ```

    **Why malloc is required:** `setup()` takes a raw pointer without copying. `to_const()` / `to_device()` internally calls `std::free()` on that pointer to release the host copy after moving data to the device. **Never pass a static `const` array to `setup()`** — it will be passed to `free()` and cause undefined behavior.

    **Device-side access:** After `to_const()`, the table data lives in constant memory. The `interp_t` struct itself (x0, dx, n, dat pointer) is shallow-copied to the device when its parent struct is passed to a kernel. Calling `interp.object(x)` on device uses bilinear interpolation.

    **Reference files:**
    - `usr/extension/algo/interp.h` — the `interp_t` class (with `setup()`, `setup_non_uni()`, `to_const()`, `to_device()`, `operator()`)
    - `usr/extension/chem_therm/reaction/mol_cooling.h:26-31` — interp members in a device-accessible struct
    - `usr/extension/chem_therm/reaction/mol_cooling.cpp:25-34` — `set_intp` lambda: malloc → setup → to_const
    - `usr_ext/line_rt/intg.h:38-50` — our Voigt table (follows this pattern)

23. **τ-convention for Neufeld/Lyα validation: mean depth vs line-centre.** Both Kratos and Python use the raw-Hjerting opacity `κ(x) = mfp_i_sca_0 × H(a,x)` with `∫H(a,x)dx = √π`. The **half-slab mean depth** (the convention-independent quantity, = Neufeld's τ₀) is:

    ```
    τ_m = mfp_i_sca_0 × √π × L_slab / 2
    ```

    To run at a target mean depth `τ_m`: set `mfp_i_sca_0 = 2τ_m / (√π × L_slab)` (note the factor 2 for the half-slab). For `mcrt_slab(tau0=...)`: its `tau0` arg is `mfp × L_slab`, so pass `tau0 = 2τ_m / √π`.

    Compare against the **Neufeld original eq. (2.24)** in the mean-depth convention (peak `0.881(aτ₀)^(1/3)`), NOT the Verhamme (2006) line-centre transcription (peak `1.066(aτ_lc)^(1/3)`). The Verhamme form assumes `H(a,0)=1`; for `a ≳ 0.1` this fails (`H(0.5,0)=0.616`, a 1.62× error in τ). The relation `τ_N = √π τ_lc` is only valid for `H(a,0)=1`; the correct relation is `τ_N = √π τ_lc / H(a,0)`.

    See `docs/debug/debug.md` Bug 6 and `~/scratch/line_rt/fiducial/neufeld_test.md` §2.3/§6/§9 for the full convention saga.

24. **Periodic-boundary wrapping: `regulate` uses `<=` not `<`.** `particle_base.h:45` must use `if( x[a] <= bmap.xlim[0][a] )` (not strict `<`). When `proc_geo` snaps a photon to exactly `xlim[0][a]` (the lower face, e.g. `0.0`), `0.0 < 0.0` is false -> `regulate` doesn't wrap the position and returns false -> `g_l` not reloaded -> photon in wrong cell with wrong boundaries. This causes asymmetric flux maps (upper y-row higher than lower) with scattering enabled. See `docs/debug/debug.md` Bug 7.

25. **`interp_t` ijkl flag: write `ijkl=0` for `(nz,ny,nx)` data.** `write_field_data()` writes the `ijkl=0` flag so `interp_t` indexes as `idx = iz*ny*nx + iy*nx + ix` (z-slowest), matching the `(nz,ny,nx)` C-order data directly. If the flag is absent, `interp_t` defaults to `ijkl=true` (`idx = ix*ny*nz + iy*nz + iz`, x-slowest) which scrambles coordinate-dependent fields across axes (invisible for uniform fields). `interp_gen.py` (Kratos `visual/`) also writes `ijkl=0`. See `docs/debug/debug.md` Bug 8.

26. **`_cell_centers_cgs`: multiply the ENTIRE expression by `unit_l0`.** `cx = (x_min[0] + (np.arange(nx)+0.5)*dx[0]) * self._unit_l0` - NOT `cx = x_min[0] + (ix+0.5)*dx[0]*self._unit_l0` (which mixes code-unit `x_min` with CGS `dx*unit_l0`, making all coordinates positive). Callables receive `(X, Y, Z)` tuples of 3D `(nz,ny,nx)` arrays in CGS [cm]. See `docs/debug/debug.md` Bug 9.

27. **`n_scat=0` silently disables ALL scattering.** `photon.h:209` `if( n_scat > 0 && dtau_s > tau_remain )` gates scattering on the remaining-scatter budget. With `n_scat=0` (e.g. copied from a pure-absorption par), no scattering ever triggers - Kratos runs pure absorption. Always set `n_scat` ≥ 1 for scattering runs; the par templates use `n_scat=5000000` (`a0_test.par`) or `n_scat=10000` (`line_rt_pipeline.par`). See `docs/debug/debug.md` Bug 10.
