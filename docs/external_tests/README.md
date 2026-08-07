# External Tests

Comparative and integration tests for the `line_rt` pipeline, kept outside
the core test suite because they require large external data inputs or
comparison against other radiative transfer codes.

## Layout

```
docs/external_tests/
  README.md          ← this file
  ism/
    README.md        # ISM diffuse-cloud channel maps (data, units, results)
    read_ism.py      # Athena++ athdf reader → 128³ CGS grids
  skirt/
    README.md        # SKIRT install, config, run, timing extraction
    lya_slab.ski     # SKIRT Lyα slab configuration
    compare.py       # parse timings + plot escaped spectra
```

Notebooks stay in the working directories (`~/scratch/ism/ism_rt.ipynb`,
`~/scratch/skirt_tst/`), not in the pipeline repo.

## Test 1 — ISM diffuse-cloud channel maps

**Working dir:** `~/scratch/ism`  
**Notebook:** `~/scratch/ism/ism_rt.ipynb` (mirrors `~/scratch/ppd_rt/ppd_rt.ipynb`)

Loads the fiducial ISM MHD simulation (Yue et al. 2024, ApJ 973:37 —
Athena++, 128³, 0.04 pc box, 23-species thermochemistry) and produces
channel maps for:

| Molecule | Line | ν | Optical depth | Notes |
|----------|------|---|---------------|-------|
| OH | 18 cm Λ-doublet (1665.5 MHz) | 1.667 GHz | τ ~ 1 (thick) | ground state, always populated |
| CO | J=1→0 (115.271 GHz) | 115 GHz | τ ~ 0.05 (thin) | standard reference |

Both use `TransitionInfo.user_defined()` (2-level system) to avoid the full
LAMDA multi-level rate matrix. The 2-level LTE solver computes the lower-
level abundance automatically.

See `ism/README.md` for data provenance, unit conventions, and the full
optical-depth analysis table.

## Test 2 — SKIRT apple-to-apple speed test

**Working dir:** `~/scratch/skirt_tst`  
**SKIRT binary:** `~/scratch/skirt_tst/SKIRT9/build/SKIRT/main/skirt`

Compares our Kratos GPU pipeline against SKIRT 9 (CPU, 16 threads) for a
thick Lyα slab (τ₀ = 10⁶). Both codes use the same R_IIA partial
redistribution physics (SKIRT `VoigtProfile::sample` ≡ our USampler).

**Timing:** Kratos internal timer (`Duration = X s` from cycle.cpp:163,
excludes Python/IO overhead). SKIRT reports elapsed simulation time in its
log.

See `skirt/README.md` for install steps, configuration, and results.
