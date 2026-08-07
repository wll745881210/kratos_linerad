# ISM Diffuse-Cloud Channel Maps

## Data provenance

- **Simulation:** Yue et al. 2024, ApJ 973:37 — 3D MHD nonequilibrium
  thermochemistry, Athena++, 23-species network.
- **Domain:** (0.04 pc)³, periodic BCs, 128³ root grid (uniform, all
  level-0 meshblocks, 8³ = 512 blocks × 16³ = 128³).
- **Irradiation:** ISRF 0.3 G0, cosmic ray ionization.
- **Data files** (in `~/scratch/ism/run_fid/`):
  - `tm.out2.00200.athdf` — hydro variables (156 vars: T, H2, CO, OH, …)
  - `tm.out1.00200.athdf` — primitive variables (27 vars: rho, vel1-3, …)

## Units

| Symbol | Value | Note |
|--------|-------|------|
| l0 | parsec (3.086e18 cm) | length unit |
| t0 | year (3.156e7 s) | time unit |
| rho0 | m_p | density unit |
| V_UNIT | l0/t0 ≈ 9.78e5 km/s | velocity unit (pc/yr) |

Species abundances are stored as [particle cm⁻³] directly.

## Optical-depth analysis (T = 75 K, L = 0.04 pc = 1.234e17 cm)

σ₀ ∝ ν⁻³, so low-frequency lines are far thicker. τ_*pk is the
realistic peak column through a dense sightline (~10 cells at 30% of max).

| Species | Line | ν | σ₀ [cm²] | τ_mean | τ_*pk |
|---------|------|---|---------|--------|-------|
| **OH** | 18 cm (1665.5 MHz) | 1.667 GHz | 3.7e-13 | 0.27 | ~1.2 |
| OH | 119 μm | 2.52 THz | 2.7e-13 | 0.19 | ~0.86 |
| CH | 3.3 mm (532 GHz) | 532 GHz | 1.3e-13 | 0.51 | ~0.13 |
| **CO** | J=1→0 (115.271 GHz) | 115 GHz | 4.1e-15 | 0.014 | ~0.05 |
| H | 21 cm | 1.42 GHz | 1.6e-17 | 7.9 | ~2.5 |

OH 18 cm is the only molecular line reaching τ ≈ 1 in this diffuse box.
CO J=1→0 is optically thin (τ ≈ 0.05).

## Transition setup (2-level user_defined)

Both species use `TransitionInfo.user_defined()` to create a 2-level
system, avoiding the full LAMDA multi-level rate matrix:

```python
# OH 18cm ground-state Λ-doublet
ti_oh = TransitionInfo.user_defined(
    A_ul=8.632e-11, freq_GHz=1.66655,
    g_u=4.0, g_l=4.0, E_u_K=0.0556,  # Λ-doublet splitting
    mol_mass=17.0, species_name='OH')

# CO J=1→0
ti_co = TransitionInfo.user_defined(
    A_ul=7.203e-8, freq_GHz=115.271,
    g_u=3.0, g_l=1.0, E_u_K=5.53,   # J=1 rotational energy
    mol_mass=28.0, species_name='CO')
```

The 2-level LTE solver computes n_lower = n_species · g_l / (g_l + g_u·exp(-dE/T))
automatically. At T = 50–100 K, both transitions are well-populated.

## Reader (`read_ism.py`)

Stitches 512 meshblocks into 128³ arrays using `LogicalLocations`
(block (i,j,k) → array[k*16:(k+1)*16, j*16:(j+1)*16, i*16:(i+1)*16]).

Returns CGS grids: `n_CO`, `n_OH`, `n_H2`, `T`, `vel0`, `vel1`, `vel2`.
