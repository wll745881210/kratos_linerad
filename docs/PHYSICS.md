# Physics Behind Line Radiative Transfer

> A tutorial on the physics implemented in this package, written for users who want to understand what the code computes and why.

---

## 1. The Problem

Consider a cloud of gas and dust illuminated by a central star. Photons travel outward, interact with gas molecules (scattering in spectral lines), and are absorbed by dust grains. The gas can be excited by absorbing line photons, and excited molecules spontaneously decay, emitting new line photons. The problem is **nonlinear**: where the gas is excited changes its opacity, which changes where photons travel and are absorbed.

This package solves the full coupled problem iteratively:
- **Monte Carlo (MC) transport**: tracks individual photon packets through the medium
- **Population update**: from the MC absorption results, computes the excited-state populations
- **Opacity update**: from the updated populations, recomputes the scattering and absorption coefficients
- **Repeat** until convergence

---

## 2. The Unit Chain: From Source Luminosity to Photon Proper

### 2.1 Physical Quantities

All quantities use **CGS units**:

| Symbol | Quantity | Units |
|--------|----------|-------|
| `L` | Source luminosity | erg/s |
| `λ` | Wavelength | cm |
| `h` | Planck constant | erg·s |
| `c` | Speed of light | cm/s |
| `ν` | Frequency = c/λ | Hz (s⁻¹) |
| `E_ph` = hν | Photon energy | erg |

### 2.2 Source → Photon Number Rate

A source emitting luminosity `L` at wavelength `λ` emits:

```
ṅ = L / (hν)     [photons/s]
```

Example: a 0.8 L☉ source at λ = 2.35 μm:
```
L = 0.8 × 3.828 × 10³³ = 3.06 × 10³³ erg/s
ν = 2.998 × 10¹⁰ / 2.35 × 10⁻⁴ = 1.28 × 10¹⁴ s⁻¹
E_ph = 6.626 × 10⁻²⁷ × 1.28 × 10¹⁴ = 8.45 × 10⁻¹³ erg
ṅ = 3.06 × 10³³ / 8.45 × 10⁻¹³ ≈ 3.6 × 10⁴⁵ ph/s
```

### 2.3 Photon Proper Weight

We cannot simulate 3.6×10⁴⁵ photons. Instead, we simulate `N_MC` Monte Carlo "packets" (typically 10⁴–10⁶), each representing many real photons. The **proper weight** `w` of each packet is:

```
w = ṅ / N_MC     [dimensionless; photon count per packet]
```

This `w` is stored as column 6 in the photon binary and is the fundamental quantity connecting the MC simulation to physical photon fluxes.

### 2.4 MC Transport → Absorbed Flux

During MC transport (in Kratos), each photon packet deposits proper weight into every cell it traverses:

```
Flux registered in cell i:
  flx[i] = Σ_photons (w × dl / V_i)      [photon path-length / cm³]

Absorbed flux in cell i:
  fab[i] = Σ_photons (w × (1-e^{-τ_abs}) / V_i)    [absorbed photons / cm³]
```

where `dl` is the path length through the cell, `τ_abs` is the absorption optical depth along that segment, and `V_i` is the cell volume in cm³.

**This is the key insight**: `fab[i]` is the "answer" from the MC — it already accounts for all geometric dilution, optical depth effects, velocity gradients, and scattering. No approximate escape probability is needed.

---

## 3. Population Number Calculation

### 3.1 Why We Need Populations

The line scattering opacity depends on how many molecules are in the **lower state** of the transition. In a two-level system:

```
mfp_i_sca = n_lower × σ_center × Z⁻¹
```

where `σ_center` is the line-center cross-section (cm²) and `Z` is the partition function fraction. If the lower state is depleted by excitation to the upper state, the scattering opacity drops — this is the feedback loop that the iteration resolves.

### 3.2 Two-Level Case (No Collisions)

For a simple two-level system with ground state `g` and excited state `e`:

**Per cell**, the MC tells us how many photons were absorbed:

```
fab_e = fab[i]                          # excited-state feeding rate from MC
```

The excited state population fraction is:

```
f_exc = fab_e / n_total_eff             # fraction excited
f_exc = clamp(f_exc, 0, 0.9999)         # never exceed total density
```

Then:

```
n_e = f_exc × n_total                   # excited number density
n_g = n_total - n_e                     # ground number density
```

This is the **radiative-only** case — the excited state population is directly proportional to the MC-measured absorption rate.

### 3.3 Multi-Level with Collisions

When collisional data are available (from LAMDA), we solve the full statistical equilibrium for each cell. The master equation for level `i` is:

```
d(n_i)/dt = 0 = Σ_{j≠i} [n_j × (R_rad[j→i] + R_col[j→i](T))]
               - n_i × Σ_{j≠i} [R_rad[i→j] + R_col[i→j](T)]
```

plus the normalization constraint: `Σ_i n_i = n_total`.

Where:
- **R_rad[j→i]**: radiative transition rate from MC — computed from `fab_i` (the number of photons absorbed into level `i`)
- **R_col[j→i](T)**: collisional (de-)excitation rate = `n_collider × q_ji(T)`, where `q_ji(T)` is the rate coefficient from the LAMDA database, interpolated to temperature `T`

This is a linear system `M·n = 0` with the last row replaced by `Σn_i = n_total`, solved via `numpy.linalg.solve`.

### 3.4 Why No Escape Probability (β)

Traditional treatments of optically thick line transfer use an escape probability `β(τ)` to approximate the effective radiative decay rate:

```
A_eff = A × β(τ)
```

where β < 1 when τ > 1, accounting for the fact that emitted line photons are trapped and re-absorbed locally.

**We do NOT use β.** Instead, the Monte Carlo transport iteratively converges to the self-consistent solution:

1. MC tracks photons through the current opacity field (which depends on populations)
2. MC records exactly where photons are absorbed (`fab[i]`)
3. Populations are updated from `fab`
4. Opacity is recomputed from updated populations
5. MC runs again with updated opacity

Because the MC already accounts for all optical depth effects (multiple scattering, frequency redistribution, velocity gradients), repeating this cycle converges the populations to the correct values without any β approximation. **β is an approximate substitute for full MC iteration; we do the iteration directly.**

---

## 4. Iteration Convergence

The iteration process:

```
Cycle 0:   Initial populations (n_e = n_g = n_total/2, or LTE)
           → Run MC → get fab₀

Cycle 1:   n₁ = f(fab₀)  → Update opacities → Run MC → get fab₁

Cycle 2:   n₂ = f(fab₁)  → Update opacities → Run MC → get fab₂

...

Converged: max|n_k - n_{k-1}| < ε
```

Convergence is typically achieved in 3-5 cycles for moderate optical depths (τ₀ ≤ 100). The convergence metric is the maximum absolute change in any population:

```
Δ_n(k) = max_i |n_i(k) - n_i(k-1)| / n_total
```

which should be plotted as a function of cycle number (see `plot_convergence()` in `core/visualize.py`).

---

## 5. Opacity From Populations

Once populations are updated, the scattering and absorption mean free paths are:

**Line scattering** (for transition i→j, lower level i):
```
σ_center = λ³ × A_ij / (8 × π¹·⁵ × b)      # line-center cross-section [cm²]
b = √(2 × k_B × T / m_molecule)             # Doppler width [cm/s]
Z_i = g_i × exp(-E_i / (k_B × T)) / Z(T)    # partition function fraction
mfp_i_sca = n_i × σ_center × Z_i            # inverse scattering MFP [cm⁻¹]
```

**Dust absorption** (continuum):
```
mfp_i_abs = n_dust × σ_dust                  # inverse absorption MFP [cm⁻¹]
```

where `σ_dust` is the dust absorption cross-section at the line wavelength.

---

## 6. Output: From Internal Units to Observables

### 6.1 Emergent Spectrum

Escaped photons carry their velocity (line-of-sight velocity shift in cm/s) and proper weight. The spectrum is:

```
I(v) dv = Σ_{photons with v ∈ [v, v+dv]} w_photon
```

The velocity axis can be converted to wavelength:
```
Δλ = λ × v/c
```

### 6.2 Flux Maps

The flux field `flx[i]` recorded by Kratos gives the spatial distribution of radiation intensity. For a given slice:

```
J(r, θ) ∝ flx_slice(r, θ)    # mean intensity proxy
F(r, θ) ∝ flux weighted by direction cosines  # net flux (future work)
```

### 6.3 Effective Flux to Observer

To compute the observable flux at distance `D`:

```
F_ν(observer) = (1 / D²) × Σ_{escaped photons toward observer} w × (hν)
              = (1 / D²) × N_escaped(μ) × ⟨w⟩ × hν
```

---

## 7. Coordinate Systems

### Cartesian (current Kratos line_rt backend)

Suitable for plane-parallel slabs, Cartesian boxes. Mesh defined by `n_cell = (nx, ny, nz)` and bounds `x_min, x_max`.

### Spherical (supported in fields.py)

Suitable for disk/wind geometries. Mesh defined by `(r_face, θ_face, φ_face)` in cm and radians. Field generators include `spherical_power_law` and analytic disk profiles. Kratos supports spherical coordinates through its `geometry/` module; switching requires changing the `.par` file.

---

## 8. Key References

- **Monte Carlo line transfer**: Auer (1968), Lucy (1999)
- **Neufeld CFR solution**: Neufeld (1990, ApJ, 350, 216) — analytic solution for a plane-parallel slab with coherent frequency redistribution
- **LAMDA database**: Schöier et al. (2005, A&A, 432, 369)
- **Dust absorption**: Draine (2011, "Physics of the Interstellar and Intergalactic Medium")
