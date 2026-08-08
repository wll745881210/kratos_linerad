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

For ro-vibrational lines NOT in LAMDA, see the ExoMol line lists
(e.g. `Li2015` for CO at `https://exomol.com/db/CO/12C-16O/Li2015/`,
`.trans.bz2` = `i f A[s⁻¹] ν[cm⁻¹]`, `.states.bz2` = `idx E[cm⁻¹] g J v e`)
to fill `TransitionInfo.user_defined()`.

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
| `tests/archived_tests/` | Archived standalone test scripts (moved from `docs/archived_tests/`) |
| `docs/reference_mcrt/mcrt.py` | Reference Python MCRT (numba). ph_mode=1 uses USampler table-lookup R_IIA. `plot_neufeld.py` validates vs Neufeld (1990). |
| `~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_wide.py` | **Standalone Kratos regression test** (self-contained, no pipeline imports). Wide `aτ₀` sweep vs Neufeld eq (2.24) for ph_modes 1/2/3, golden med\|x\| table, PASS/FAIL exit code. Run: `python3 test_scaling_wide.py --kratos-root ~/apps/kratos_line_rt` |
| `~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_imaging_neufeld.py` | **Standalone imaging test** (inherits `test_scaling_wide.py` geometry). Validates imaging double-peak scaling vs Neufeld for ph_mode=2. Also runs escaped spectrum golden check. Run: `python3 test_imaging_neufeld.py --kratos-root ~/apps/kratos_line_rt` |
| `~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_image.py` | **Standalone imaging+escape scaling test** (self-contained). Sweeps `aτ₀`, compares imaging double-peak and escaped `med|x|`/`|x|_peak` vs Neufeld. Adaptive v_chan (3× Neufeld peak). Spectra PNG: Neufeld `J(x)` + Imaging `I(x)` + Escaped `F(x)` histogram with peak vlines. Run: `python3 test_scaling_image.py --kratos-root ~/apps/kratos_line_rt --plots` |
| `~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_absorption_scattering.py` | **Standalone absorption+scattering test** (self-contained). Three modes: (1) default vs Neufeld cosh(4.33) + in-house Python MCRT (K/P PASS 1.01–1.06); (2) `--verhamme` vs Verhamme+ (2006) Fig. 4 published MC crosses (7 digitized points, a=0.015, τ₀=1e5); (3) `--skirt` vs SKIRT9 wide-box (Camps & Baes 2020). Uses `VERHAMME_HANDOFF.md` for status. Run: `python3 test_absorption_scattering.py --kratos-root ~/apps/kratos_line_rt` |
| `~/apps/kratos_line_rt/` | Kratos build tree (symlinked to Seafile source) |
| `~/scratch/line_rt/` | Historical runtime dir; new runs default to per-run subdirs under `/dev/shm/line_rt/`. `fiducial/` subdir holds reference test records. |

---

## Architecture: two-level API

**High level — `LineRt` class** (`core/line_rt.py:25`): single-entry-point orchestrator. Configure geometry, sources via constructor + `add_source()`, then call `run()`. Handles mesh creation, field resolution, photon generation, consistency checks, and the full MC → population → MC cycle loop. This is what README examples and the CLI use.

**Species selection — `TransitionInfo`** (`molecular/transition_info.py`): pass `transition_info = ti` to the `LineRt` constructor to use the species-based (Group 1) configuration. `TransitionInfo` resolves the species data, transition index, molecular mass (built-in table), and auto-wavelength (`add_source()` defaults `wavelength` to the transition wavelength when given). Constructor: `TransitionInfo( species, transition_idx = 0, *, value = None, unit = None, freq_GHz = None, mol_mass = None )` — the transition can be picked by index, by `freq_GHz`, or by `value`+`unit` (`GHz`/`THz` for frequency, `cm`/`mm`/`um`/`nm`/`angstrom` for wavelength, `eV`/`erg` for photon energy; all converted to frequency and matched via `specify_transition()`). No `species`/`transition_idx`/`mol_mass` arguments on `LineRt` — mol_mass comes only from `TransitionInfo` (explicit arg or table; `MolecularMassError` if unknown). **For a transition NOT in the LAMDA database** (online or embedded), use the classmethod `TransitionInfo.user_defined( A_ul, freq_GHz = None, value = None, unit = None, g_u = 1.0, g_l = 1.0, E_u_K = None, mol_mass = None, species_name = 'user_defined' )` — it builds a synthetic 2-level `SpeciesData` from physical transition parameters and returns a fully functional `TransitionInfo` (mass resolved from `species_name` via the built-in table, or explicit `mol_mass`; `E_u_K` defaults to `h·ν/k_B`). Only 2-level species are supported. **Collision rates** can be supplied via `collision_rates={'H2': {'rate': ..., 'density': ...}}` where each value is a float [cm^3/s] or callable `f(T)`. The collider **density** is supplied via `LineRt(colliders={'H2': ...})`, NOT in `user_defined`. The old `molecular/synthetic_molecule.py:make_synthetic_2level()` is deprecated in its favour.

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
field_file       = fields_cycle0.bin   # line-dependent (mfp_i_sca_0, mfp_i_abs_0, emiss)
field_fixed_file = fields_fixed.bin    # line-independent (b_sca, vel) - optional, falls back to field_file
photon_file      = photons_cycle0.bin
ph_mode          = 0          # 0=CFR (Gaussian), 1/2/3=R_IIA (USampler)
b_sca            = 1.0        # Doppler b (scattering) - used for overlap integral
const_abs        = 1          # always 1 (absorption is wavelength-independent)
n_fld            = 1
num_rng          = 16381
a_voigt          = 0.0        # Voigt damping parameter (0 = pure Gaussian)
proper_min_frac  = 0          # proper-weight culling threshold (0 = disabled)
worker_mode      = 1          # 1 = server-worker photon scheduling (default ON)
n_worker         = 32768      # worker count (0 = auto: min(n_par, 65536))
```

**Field file split (Task 2):** Fields are split into two groups to prepare for multi-line problems:
- `field_file` (line-dependent): `mfp_i_sca_0`, `mfp_i_abs_0`, `emiss` - change per cycle as populations evolve and differ per transition.
- `field_fixed_file` (line-independent): `b_sca`, `vel_0..2` - depend only on the gas (bulk velocity, thermal temperature, molecular weight), fixed across lines. Written once per simulation.
- If `field_fixed_file` is omitted, Kratos falls back to reading `b_sca`/`vel` from `field_file` (backward compatibility).

**Imaging (two-step, runs on the FINAL cycle only):** the `[imaging]` section controls the camera + channel grid. When `enabled=0` (default) the s_cam field is neither allocated nor initialised — non-imaging runs are unaffected. The imaging uses the full **R_IIA kernel** (precomputed 3-D table, `intg.h:build_riia_kernel`) for the scattering source function toward the camera, correctly capturing the angle–frequency correlation (see `docs/PHYSICS.md` §12.2, §12.6).

```ini
[imaging]
enabled        = 1           # 1 = run the imaging pass on the final cycle
n_chan         = 32          # number of velocity channels
dir_cam_theta  = 0.785       # camera LOS polar angle [rad] (pointing INTO the domain)
dir_cam_phi    = 0.0         # camera LOS azimuth [rad]
v_chan_min     = -1.0e5      # channel grid lower edge [CODE units, × unit_t0/unit_l0]
v_chan_max     = 1.0e5       # channel grid upper edge [CODE units]
img_xmin       = ...         # optional image-plane lower corner [code units]
img_xmax       = ...         # optional image-plane upper corner [code units]
img_resol      = 64 64       # optional image resolution (pixels)
step_max       = 65535       # ray-march step budget (imaging module)
```

Physics and units are documented in `docs/PHYSICS.md` §12.

**ph_mode values:**
- `0` – CFR: `Δv = −v·d̂`, `σ_ph = σ_th` (no random velocity)
- `1` – R_IIA: exact USampler kernel (log-CDF table, global mem) + 2D Voigt opacity table (global mem, 128 KiB)
- `2` – R_IIA: same USampler kernel, but tables in **constant memory**: coarse log-CDF USampler (251×40, `du=0.048`) + 1D log-space Voigt table (5000 pts, `u∈[0,50]`, built from the host-side scipy 2D table). Fastest exact mode.
- `3` – R_IIA: const-mem USampler only; scattering profile uses the approximate analytic `voigt_H` blend in `photon.h` (Gauss core + Lorentz wing crossover). Fastest overall but underestimates `med|x|` at low `aτ₀` (~0.77–0.94× Neufeld for `aτ₀=30–1192`); converges at high `aτ₀`.

All R_IIA modes (1/2/3) share the same scattering kernel (`g = dir_old·dir` directional correlation). The USampler conditional is `P(u|x) ∝ exp(−u²)/(a²+(x−u)²)` (`n_u=251`, `u∈[−6,6]`, `du=0.048`, `n_xg=40`, `xg∈[0,300]` mixed linear+log). The R_IIA kernel density `R(Δ; x_pp, g) = Σ_k pdf[k]·Gauss(y_k; σ=sin_g/√2)` is precomputed as a 200×200×40 table (`Δ=x_out−x_pp∈[−10,10]`, `|x_pp|∈[0,120]`, `g∈[−1,1]`, with analytic asymptotic for `|x_pp|≥120`), used in imaging source-function accumulation (see `docs/PHYSICS.md` §12.2 for the full definition). Modes 1 and 2 agree to ~1–2% (`med|x|`); use `2` for production, `1` for debug (global-mem table). `ph_mode=2`/`3` use the constant-memory pool — **not freed** in `finalize` (`free_dev_mem=false`); the 60 KiB const pool is a bump allocator.

**Photon features (Kratos-side, all in `usr_ext/line_rt`):**
- `proper_min_frac` (default 0 = off): proper-weight culling. Each photon stores `proper_0` (its weight at creation, set in `gen.h`); in `photon.h:proc_step()` a photon is culled (`dest.todo = to_rm`) once `proper < proper_min_frac * proper_0`. Useful for heavily absorbing media. Exposed as `LineRt(proper_min_frac=...)`.
- `worker_mode` (default **True**, `n_worker=32768`): server-worker photon scheduling. `pool.h:pol_t` / `pool_img.h:pol_img_t` carry a device `work_counter` (reset each step in `pre_proc`); `intg.h:operator()` branches to a persistent `while(true)` loop that calls `pool.load_next()` (atomic increment) until the pool is depleted, instead of one short kernel per photon. Provides ~2× speedup at high optical depth (load-balanced work-stealing). NOT bit-identical to classic (RNG indexed by thread id, not pool index) but statistically equivalent (ensemble med|x| matches to <0.3%). `rad_img_t::init()` sets `itg.worker_mode=false` so imaging ray-tracing never uses the worker loop (one fixed ray per pixel, no load imbalance). Exposed as `LineRt(worker_mode=..., n_worker=...)`. The launch grid is capped at `n_worker` threads via `resource()` override in `intg.h`; optimal ~32768 (6 blocks/SM × 82 SMs × 64 threads on RTX 3090).
- `x_last_scat`: every photon records its last-scattering position (initialised to its creation position in `gen.h`, updated in `photon.h:scat()`). Written to escaped-photon output under `_x_last_scat`; the pipeline readback exposes it as `out[...]['photons']['x_last_scat']` (CGS, × `unit_l0` like `x`). Only escaped photons carry it.
- **Do NOT modify the particle trunk** (`src/modules/particle/` excluding `radiation/`) for these — it is generic and also serves dark-matter particles. All overrides live in `usr_ext/line_rt` (`pool.h`, `pool_img.h`, `intg.h`, `photon.h`, `gen.h`).

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
| `usr_ext/line_rt/radiation.h` | Field I/O, `init_cond` (GPU kernel), `ini_t` (interp tables, `to_device`/`free_device`), imaging emissivity seed (`s_cam = emiss/(mfp_i_sca_0·√π·b_sca)`) |
| `usr_ext/line_rt/photon.h` | `proc_geo` (scattering physics), `proc_phys` (excitation + s_cam scattering accumulation via R_IIA kernel) |
| `usr_ext/line_rt/photon_img.h` | `line_img_t` imaging photon: per-channel analytic RT integration, pixel ray setup |
| `usr_ext/line_rt/rad_img.h` | `rad_img_t` imaging module (parasite of `radiation_t`), `enabled` gate |
| `usr_ext/line_rt/pool_img.h` / `.cpp` | `pol_img_t` imaging output writing (`_dir_img`, `_x_img`, `_i2d_img`, `_l_img`) |
| `usr_ext/line_rt/photon_gen_img.h` / `.cpp` | `gen_img_t` pixel generation (one ray per image-plane pixel) |
| `usr_ext/line_rt/pool.h` | Escaped photon output writing |
| `usr_ext/line_rt/gen.h` | Photon generation from binary |
| `usr_ext/line_rt/intg.h` | Integrator parameters, camera (`dir_cam`, `q_cam`), channel grid (`d_v_chan`), Voigt interpolation table, R_IIA kernel table (`build_riia_kernel`, 200×200×40, device global mem) |
| `usr_ext/line_rt/block_data.h` | `rad_t` struct (incl. `s_cam`, `emiss`, `imaging`, `n_chan`), block I/O (`copy_input` blank, `copy_output` device->host) |
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
Cycle 0:  initial (collisional-equilibrium) populations -> make_fields() -> write line + fixed binaries -> run Kratos
Cycle 1+: read_output() -> update_populations(F_ext) -> make_fields() -> write line binary -> run Kratos
```

(line-dependent `field_file` is written per cycle; line-independent `field_fixed_file` is written once at cycle 0.)

Key functions:

| Function | File | Returns |
|----------|------|---------|
| `compute_opacity(pops, b_sca, transition_idx)` | `molecular/lamda_format.py` | `mfp_sca` only (absorption MFP is user-provided) |
| `compute_emissivity(populations, transition_idx, temperature)` | `molecular/lamda_format.py` | Photon-number volume emissivity `n_u·A_ul/(4π)` [photons cm⁻³ s⁻¹ sr⁻¹] |
| `destruction_opacity(pops, transition_idx, b_sca, T, colliders)` | `molecular/lamda_format.py` | Collisional destruction `n_l·σ₀·ε` [cm⁻¹] (ε=C·n/(A+C·n)); added to `mfp_i_abs_0` |
| `update_populations(exc_flux, flx, pops, cycle, dx, b_sca, T, colliders, transition_idx)` | `molecular/lamda_format.py` | Updated population dict |
| `make_fields(pops, step, cycle, base_fields, unit_l0, unit_t0, transition_idx)` | `molecular/lamda_format.py` | Field dict — includes `mfp_i_abs_0` only if in `base_fields`, plus `emiss` when `transition_idx` given |
| `write_field_data(filename, fields, mesh, group='all')` | `core/kratos_io.py` | Writes binary; `group='line'` (mfp_i_*, emiss), `'fixed'` (b_sca, vel), or `'all'` |
| `write_photon_data(filename, photons)` | `core/kratos_io.py` | Writes photon binary |

### Field keys written to Kratos

**Split into two binary files (Task 2):**

| File | Key | Content |
|------|-----|---------|
| `field_file` (line-dependent, per cycle) | `mfp_i_sca_0_` | **Inverse** scattering MFP at line centre (σ₀ × n_lower) [code-l]⁻¹ |
| `field_file` | `mfp_i_abs_0_` | **Inverse** absorption MFP [code-l]⁻¹ |
| `field_file` | `emiss_` | Photon-number emissivity `n_u·A_ul/(4π)` [code units]; rescaled by `proper_scale` for the imaging emissivity seed (optional, only written when a transition is used) |
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
8. **`dv_c` does not exist anymore.** Removed from photon struct, binary format, and all I/O. The photon binary columns are: x,y,z, dir_x,dir_y,dir_z, proper, [vel], [sv].  `write_photon_data()` accepts 7, 8, or 9 columns. Escaped-photon readback (`read_output()`) exposes the weight under key `'proper'` (with `'l'` as a deprecated alias); it is a photon-number weight (photons/s per packet, CGS after `iterate()` conversion), NOT a path length — use it for photon statistics and proper-weighted spectra (`LineRt.run()` output `'spectrum'` is proper-weighted).
9. **Proper-weight FP32 scaling:** `write_photon_data()` scales `proper` to fit FP32 and RETURNS the scale factor. A user-supplied `proper_scale` (default **None = auto**) is applied first (photon weights × `proper_scale`); if the scaled `proper_max` still exceeds `1e38`, an automatic `1/proper_max` rescale follows, and the two factors are combined into the returned scale. Both `iterate()` and `run_pipeline()` MUST undo the scaling by multiplying flx and exc_flux by `1/scale_factor` after readback, and escaped-photon `proper` weights are divided by `1/scale_factor` the same way (they are photon weights, NOT path lengths — never multiply by `unit_l0`). Values in `output['flx']` and `output['exc_flux_flat']` are always in CGS. Since Kratos MCRT is linear in photon weights, rescaling all propers by a constant leaves all fields unchanged after the read-back division. **When `proper_scale=None` (default)**, `iterate()` auto-computes a scale from the estimated max `s_cam` magnitude (emission seed `emiss/(mfp_s·√π·b)` + scattering contribution `n_ph·max_proper·max_dsi/(4π·√π·b)` in code units) so the Kratos-side `s_cam` field fits in FP32 range (< 1e30, margin below 3.4e38). This prevents the thermal-seed overflow that produces `inf` imaging cubes. Set `proper_scale=1.0` to disable auto-scaling, or a small value (e.g. `1e-30` for YSO-scale fluxes, or `--proper-scale 1e-30` on the CLI) for manual control. `write_photon_data()` copies its input (never mutates the caller's array).
10. **Photon binary columns 7 (vel) and 8 (sv, Gaussian σ) are velocities → need CGS→code conversion:** `× unit_t0/unit_l0` before writing, `÷ unit_t0/unit_l0` (= `× unit_l0/unit_t0`) on readback for escaped photons.
11. **Two distinct 3D data ordering conventions in Kratos:**
    - **OUTPUT fields** (flx, exc_flux read via `read_output()`): `(nz, ny, nx)` (z slowest, x fastest in C++ row-major). `slice_plot_2d()` must reshape accordingly and `.T` transpose slices for pcolormesh.
    - **INPUT field binaries** (`field_file`/`field_fixed_file`, read by `interp_t`): data is written in `(nz, ny, nx)` C-order (z slowest, x fastest) with `ijkl=0` flag. `interp_t` with `ijkl=false` indexes as `idx = iz*ny*nx + iy*nx + ix`, matching the `(nz, ny, nx)` layout directly. `write_field_data()` writes 3D `(nz, ny, nx)` arrays at cell-centred nodes (`n_pts = n_cell`, `x0 = x_min + 0.5*dx`, no padding) and ravels them directly, no transpose needed. **The Python pipeline uses 3D `(nz, ny, nx)` arrays everywhere** (field dicts, populations, exc_flux, flx); callables receive `(X, Y, Z)` tuples of 3D arrays.
12. **Boundary cells produce NaN in excitation_flux** — both `iterate()` and `run_pipeline()` filter NaN to 0 before population update.
13. **`gen.h:104-107`:** `par.sv` is the photon's Gaussian σ (NOT the Doppler b). The relation is `b = σ·√2`. Read from binary column 8 when `ncol_ph >= 9`; defaults to 0.f (monochromatic at line centre) when not provided. After first scatter, `sv` is reset to the thermal σ (= `b_sca / √2`). **Column layout:** 0-2=pos, 3-5=dir, 6=proper, 7=vel, 8=sv.
14. **`base_fields_cgs` must be kept separate** from the code-unit `fields` output to prevent double unit-conversion across cycles.
15. **Boundary `kinds` MUST specify all 6 faces, not 3.** Kratos expects 6 values: `-x, +x, -y, +y, -z, +z`. Writing only 3 leaves the remaining undefined, defaulting to periodic. **The par template default is now all-free** (`fre fre fre fre fre fre`). For plane-parallel slabs, use `par_overrides={'kinds': 'fre fre per per per per'}` or `rt.set_boundary("fre fre per per per per")`.
16. **Slab sources use `flux`, point/volume sources use `luminosity`.** `add_source` enforces this: passing `luminosity` to a `slab` source or `flux` to a `point`/`volume` source raises `ValueError`, and each type requires its own quantity (slab needs `flux`, point/volume needs `luminosity`). Quantities default to **photon number** (`flux` in [photons cm⁻² s⁻¹], `luminosity` in [photons/s]); pass `units='energy'` for erg-based values (erg cm⁻² s⁻¹ / erg s⁻¹). With `units='energy'` the conversion uses the `transition_info` wavelength — there is NO `wavelength` argument on `add_source`, and `units='energy'` without a transition raises `ValueError`. The proper per packet = flux × source_area_cm² / n_photon (slab) or luminosity / n_photon (point/volume). `LineRt.show_sources()` prints all registered sources. Point sources accept `r_random` (default 0.0, [cm]) to draw each packet's initial position uniformly (volume-weighted) over a sphere of that radius centred on `position` — rejected for slab and volume sources (`ValueError`), and `r_random < 0` raises. **Volume sources** (`type='volume'`) generate photons at random uniform positions throughout the mesh volume with isotropic directions, using `luminosity` [photons/s]. Matches SKIRT's `UniformBoxGeometry` source for apple-to-apple Lyα comparisons.

**Randomized initial velocity shifts** (continuum injection): pass `vel_range=(v_lo, v_hi)` [cm/s, CGS] to `add_source` to give each generated photon a random velocity offset drawn from `vel_pdf` over that interval (added on top of `vel_offset`); `vel_range=None` (default) keeps every photon at exactly `vel_offset`. `vel_pdf` is `'uniform'` (default), `'gaussian'` (centred on the interval midpoint, width `vel_sigma`, truncated to the interval), or a user callable `f(v)` giving an arbitrary — possibly **unnormalized** — PDF, which is numerically integrated to a CDF, normalized, and sampled by inverse transform (`_sample_vel()` in `core/line_rt.py`). `'gaussian'` requires `vel_sigma>0`; `v_lo<=v_hi` is enforced; a callable that integrates to zero raises `ValueError` at generation time. Fully Python-side (writes photon-binary column 7 `vel`); no Kratos change.
16b. **`LineRt.plot_input()` plots configured input fields WITHOUT running Kratos.** It resolves `n_species`, `temperature` (Group 1), `mfp_i_sca_0`, `b_sca`, `mfp_i_abs_0`, and `vel_0..2` (both groups) at cell centres in CGS via `_plot_input_data()` and renders them with `default_plot`. Default field set: Group 1 → `[n_species, temperature, mfp_i_sca_0, b_sca, mfp_i_abs_0, vel_0, vel_1, vel_2]`; Group 2 → `[mfp_i_sca_0, b_sca, mfp_i_abs_0, vel_0..2]` (vel only when `vel` configured). Unconfigured fields show `(no data)` panels. No `check_consistency()` is run — plot whatever is configured. `LineRt.plot_results( out = None )` plots `run()` output via `default_plot` (wraps the old `_plot_results`). `run()` caches its return value in `self._results`, so `plot_results()` can be called with no argument; pass `out` explicitly to plot a different results dict. Velocity fields (`vel_*`) and uniformly non-positive data use a **linear** colormap in `default_plot` (`_LINEAR_FIELDS`), because `LogNorm` cannot handle negative/zero values; `_extract_field` converts `vel_*` cm/s → km/s like `b_sca`.
17. **Default boundaries are all-free.** Use `set_boundary(kinds)` on `LineRt` or `par_overrides={'kinds': ...}` in `iterate()` to configure boundaries for your geometry.
18. **Internal emission photons are FROZEN across cycles (anti-double-counting).** `core/iterator.py` generates emission photons ONCE from the cycle-0 populations and re-uses them for every subsequent cycle. Only the scattering opacity `mfp_i_sca_0` (derived from the evolving lower-level population n_lower) is updated each cycle. This avoids double-counting: scattered photons already carry the radiative excitation (absorption + re-emission), so regenerating new emission from radiation-inflated n_u would count it twice. The per-cycle photon count is stable (external + frozen emission). Control with `n_emission_max` on `LineRt`.
18b. **Initial populations: collisional-only thermalization (NO blackbody/T_rad term).** `SpeciesData.initial_populations(n_species, T=None, colliders=None)` calls `solve_populations` at zero external flux when a temperature is provided: with colliders the gas relaxes to collisional equilibrium at the gas temperature (cycle-0 opacity and emissivity consistent); WITHOUT colliders there is no excitation mechanism, so the upper level stays empty (all-in-ground-state -> zero emissivity -> zero emission photons). `core/iterator.py` passes the `temp` field (and `colliders`, default None) from `base_fields_cgs` unconditionally. With no temperature, it falls back to all-in-ground-state. Emission-only mode (no `add_source()`) works: cycle 0 is seeded with internal emission from the cycle-0 populations; `check_consistency` no longer errors on a species without sources (it only errors if BOTH sources and species are missing). **Colliders** (`LineRt(colliders={'H2': {'density': ...}})` -> `iterate(..., colliders=...)` -> `solve_populations`) are fully wired: densities may be floats or callables. Collisional de-excitation rates come from LAMDA (full download, not the stripped embedded files) or from `TransitionInfo.user_defined(collision_rates={'H2': ...})`, where the value is a float or callable `f(T)`. The collider **density** (spatial field) is supplied separately via `LineRt(colliders={'H2': ...})`, NOT in `user_defined`. The collisional destruction probability eps = C*n/(A+C*n) adds `n_l*sigma_0*eps` to `mfp_i_abs_0` via `SpeciesData.destruction_opacity()`.
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

26. **Field binary nodes are CELL-CENTERED, not vertex/node-based.** `write_field_data()` writes the interp_t grid at cell centres: `n_pts = n_cell`, `x0 = x_min + 0.5*dx`, and the data array is the field values at cell centres **without padding**. Kratos `init_rad_fields_kernel` samples the table at `geo.x_cc(i)` (cell centres), which then coincide with the nodes and return the exact stored value. **Do NOT** use the old vertex scheme (`n_pts = n_cell+1`, `x0 = x_min`, edge-padded array): it stored cell-centre values at vertex positions, producing a half-cell shift plus a high-side duplicate node that broke mirror symmetry for spatially-varying fields (a 3× x+/x- flux imbalance for a symmetric medium; see `docs/debug/debug.md` Bug 11). The field binary must cover the mesh domain; out-of-range sampling returns the `set_fill(0)` value (silent zero opacity).

27. **`_cell_centers_cgs`: multiply the ENTIRE expression by `unit_l0`.** `cx = (x_min[0] + (np.arange(nx)+0.5)*dx[0]) * self._unit_l0` - NOT `cx = x_min[0] + (ix+0.5)*dx[0]*self._unit_l0` (which mixes code-unit `x_min` with CGS `dx*unit_l0`, making all coordinates positive). Callables receive `(X, Y, Z)` tuples of 3D `(nz,ny,nx)` arrays in CGS [cm]. See `docs/debug/debug.md` Bug 9.

28. **`n_scat=0` silently disables ALL scattering.** `photon.h:209` `if( n_scat > 0 && dtau_s > tau_remain )` gates scattering on the remaining-scatter budget. With `n_scat=0` (e.g. copied from a pure-absorption par), no scattering ever triggers - Kratos runs pure absorption. Always set `n_scat` ≥ 1 for scattering runs; the par templates use `n_scat=5000000` (`a0_test.par`) or `n_scat=10000` (`line_rt_pipeline.par`). See `docs/debug/debug.md` Bug 10.

29. **Memory: /dev/shm is tmpfs = RAM; results hold every cycle's arrays.** Per-cycle binaries (`fields_cycleN.bin`, `photons_cycleN.bin`, `cycleN_00000.bin`, `cycleN.par`, `cycleN.txt`) accumulate in the run dir under `/dev/shm/line_rt/` — plus the returned `results` list keeps every cycle's full arrays. **Defaults are now memory-friendly**: `keep_intermediate=False` by default (`LineRt` / `iterate(...)` / `run_pipeline(...)` / CLI), so each cycle's files are deleted as soon as their data is read back into RAM (fixed fields + final cycle kept), and `LineRt.run()` with an auto-created run dir removes the whole directory afterwards — including on a **crashed/interrupted run** (the cleanup is `try/except`-guarded). An explicit `path=` is never touched. Use `keep_intermediate=True` (`--keep-intermediate`) to keep every per-cycle file. In addition, before every auto-created run `LineRt.run()` prunes the scratch root: `rt_*` dirs older than `max_run_age` (default 3 h) are deleted, and if the total size of `rt_*` dirs exceeds `size_cap` (default 4 GB) the oldest dirs are removed until under the cap. Both are configurable: `LineRt(max_run_age=..., size_cap=...)`, `--max-run-age <sec>` / `--size-cap <bytes>` on the CLI (pass 0 to disable either); `prune_scratch(max_run_age, size_cap, base)` in `core/pipeline.py` runs the logic standalone. Use `retain_cycles=N` (`LineRt(retain_cycles=N)` / `--retain-cycles`) to keep only the last N cycle dicts in `out['results']`. Stored output fields (`flx`, `exc_flux_flat`) are float32 (Kratos already produces float32 binaries; nothing is lost vs float64).

30. **Imaging: `emiss` field must be scaled by `proper_scale` (NOT `/ proper_scale`).** `core/iterator.py` rescales the emiss field by `× proper_scale` on write so the emission seed (`s_cam = emiss/(mfp_i_sca_0·√π·b_sca)`) lives in the same scaled-proper units as the scattering s_cam (photon propers in the binary are already multiplied by `proper_scale`). The `√π·b_sca` factor converts the frequency-integrated source function to the frequency-dependent `S(v)=j(v)/α(v)`. The old `/ proper_scale` double-rescaling overflowed FP32 → `inf` emiss → NaN/inf imaging cube → spurious corner peak. Readback divides the cube by `scale_factor` and converts to CGS intensity (`÷ unit_l0³`, `l³` because `I(v)` has units [ph cm⁻³ sr⁻¹]; `unit_t0` cancels in the source-function ratio). When `proper_scale=None` (default), the scale is auto-computed (see pitfall 9) to prevent the emission-seed FP32 overflow. See `docs/PHYSICS.md` §12.

31. **Imaging: pass `x_min`/`x_max` in CODE units to `LineRt`.** `_cell_centers_cgs` multiplies the mesh coords by `unit_l0`, so passing CGS (e.g. `-5*AU`) makes all callable inputs ~1e13× too large — field callables return their fallback everywhere (constant mfp, zero emiss) → zero image. Use plain code units (`x_min=(-5,-5,-5)`) and give `unit_l0=AU` separately.
32. **Imaging: voigt_H Lorentzian fallback** (RESOLVED): the imaging integrator has `build_tables=false` (const-memory pool overflow, see pitfall 18). The `voigt_H` fallback blends Gaussian core with Lorentzian wing: `H = max(exp(−u²), a/(√π·(u²+a²)))`. The old pure-Gaussian fallback vanished for `u > 5` → zero imaging opacity at wing channels → zero image. See `docs/PHYSICS.md` §12.4.
33. **Imaging: channel grid bin centres** (RESOLVED): the channel grid now uses bin centres `v_chan[k] = v_min + (k+0.5)·dv` (not linspace endpoints). The endpoint convention caused a half-bin shift vs the test's bin-centre convention.
34. **Imaging: s_cam corr clamping** (RESOLVED): `(1−e^−dτ_e)/dτ_e` was clamped by `max(dτ_e, 1)` (37% suppression for thin cells). Fixed to `max(dτ_e, 1e-10f)`.
35. **Standalone test par files: `n_cell_global` MUST be formatted as INTEGERS, not floats.** The Kratos par parser cannot parse `128.000000` as an integer — it silently produces `n_cell=0` → no mesh blocks → no photons inside any block → `Speed=0` (zero transport). Use `str(int(x))` for `n_cell_global`, `%.6f` for `x_min`/`x_max`. See `usr_ext/line_rt/tests/test_absorption_scattering.py:generate_kratos_inputs()` (`fmt3i` lambda). This was the root cause of the Verhamme-mode zero-transport blocker (VERHAMME_HANDOFF.md §2).
