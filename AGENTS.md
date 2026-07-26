# AGENTS.md

Instructions for agentic sessions working on the `line_rt_pipeline` codebase.

---

## Project layout

| Directory | Purpose |
|-----------|---------|
| `molecular/` | Species data, cross sections, population solver |
| `core/` | Field functions, source generation, iterator, visualization |
| `pipeline/` | Kratos I/O, par-file management, orchestrator |
| `ui/` | Jupyter widget interface |
| `docs/` | PHYSICS.md (authoritative spec), examples |
| `~/apps/kratos_line_rt/` | Kratos build tree (symlinked to Seafile source) |
| `~/scratch/line_rt/` | **Runtime working directory** — all test runs happen here |

---

## Running Kratos

**ALWAYS run under `~/scratch/line_rt/`.** The Python pipeline writes field/photon binary files there, and Kratos reads them via the par file's `field_file` / `photon_file` entries.

Kratos requires a `.par` file. The canonical template lives at:

```
line_rt_pipeline/pipeline/line_rt_pipeline.par
```

Minimal invocation:

```bash
cd ~/scratch/line_rt
~/apps/kratos_line_rt/bin/kratos <par_file>
```

### Par-file essentials

The `[line_rt]` section must contain:

```ini
[line_rt]
field_file  = fields_cycle0.bin
photon_file = photons_cycle0.bin
ph_mode     = 0          # 0=CFR, 1=partial redistribution
b_sca       = 1.0        # Doppler b (scattering) — used for overlap integral
const_abs   = 1          # always 1 (absorption is wavelength-independent)
n_fld       = 1
num_rng     = 16381
```

**There is no `b_abs` parameter anymore.** Absorption MFP is purely user-provided (via `base_fields` in Python), never derived from the line-center cross-section formula.

### Unit system

The `[unit]` section converts CGS → Kratos code units:

```ini
[unit]
length  = 1.49598e13    # AU → cm
time    = 1.0
density = 1.0
```

Python pipeline uses pure CGS; Kratos converts internally.

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

### Usr-ext source files

| File | Role |
|------|------|
| `usr_ext/line_rt/radiation.h` | Field I/O, `init_cond`, module setup |
| `usr_ext/line_rt/photon.h` | `proc_geo` (scattering physics), `proc_phys` (excitation) |
| `usr_ext/line_rt/pool.h` | Escaped photon output writing |
| `usr_ext/line_rt/gen.h` | Photon generation from binary |
| `usr_ext/line_rt/intg.h` | Integrator parameters |
| `usr_ext/line_rt/block_data.h` | `rad_t` struct — all per-cell field data |
| `usr_ext/line_rt/line_rt.h` | Profile functions (b_sca only) |

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
Cycle 0:  LTE populations → make_fields() → write binary → run Kratos
Cycle 1+: read_output() → update_populations(F_ext) → make_fields() → write binary → run Kratos
```

Key functions:

| Function | File | Returns |
|----------|------|---------|
| `compute_opacity(pops, b_sca)` | `molecular/lamda_format.py` | `mfp_sca` only (absorption MFP is user-provided) |
| `update_populations(exc_flux, flx, pops, cycle, b_sca)` | `molecular/lamda_format.py` | Updated population dict |
| `make_fields(pops, step, cycle, base_fields)` | `molecular/lamda_format.py` | Field dict — includes `mfp_i_abs_0` only if in `base_fields` |
| `write_field_data(filename, fields, mesh)` | `pipeline/kratos_io.py` | Writes binary (no `b_abs_` prefix anymore) |
| `write_photon_data(filename, photons)` | `pipeline/kratos_io.py` | Writes photon binary |

### Field keys written to Kratos

| Key | Content |
|-----|---------|
| `mfp_i_sca_0_` | Inverse scattering MFP from `compute_opacity()` |
| `mfp_i_abs_0_` | Inverse absorption MFP from `base_fields` (user-provided) |
| `b_sca_` | Doppler b for scattering overlap integral |
| `vel_0_`, `vel_1_`, `vel_2_` | Bulk velocity (3 components) |
| `temp_` | Temperature (optional, diagnostic) |

---

## Example test invocation

```python
import sys; sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline')
from docs.examples.plane_parallel import *
```

Or run directly (generates plots):

```bash
cd ~/scratch/line_rt
python3 ~/Seafile/seafile_sync/code/line_rt_pipeline/docs/examples/plane_parallel.py
```

---

## Common pitfalls

1. **Don't derive absorption opacity from `cross_section()`.** `mfp_i_abs_0` must come from `base_fields`.
2. **Don't add `b_abs` back.** It was intentionally removed everywhere.
3. **Always run Kratos from `~/scratch/line_rt/`** where the binary field/photon files live.
4. **Always pass a `.par` file.** Kratos won't run without one.
5. **`compute_opacity()` returns only `mfp_sca`** — a single ndarray, not a tuple.
