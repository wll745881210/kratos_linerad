# Physics of Monte Carlo Line Radiative Transfer

> Derived from `notes.tm`. This document serves as the **authoritative physics specification** for all implementations (Kratos C++ and Python pipeline). All quantities below are in **photon-number units** — "luminosity" means photon number per unit time, NOT energy luminosity.

---

## 1. Conventions

### 1.1 Unit Systems

| System | Used by | Convention |
|--------|---------|-----------|
| CGS | Python pipeline (inputs/outputs) | All external quantities; spatial coordinates in cm; velocities in cm/s |
| Code units | Python→Kratos (write); Kratos internal (read) | Python converts CGS → code units before writing field/photon binary files. Kratos treats all quantities as code units internally with no further conversion. |
| Dimensions | This document | `[l]` = length, `[t]` = time, `[m]` = mass, `[n]` = photon number (dimensionless, kept as "counting" unit) |

#### Code-unit conversion (Python side)

```
l_code   = l_cgs   / unit_l0           # length
v_code   = v_cgs   × unit_t0 / unit_l0  # velocity
mfp_code = mfp_cgs × unit_l0            # inverse length (1/l)
```

`unit_l0` [cm per code-length] and `unit_t0` [s per code-time] are explicit parameters passed to the pipeline. The same factors appear in Kratos's `[unit]` par file section for spatial coordinates.

#### Suffix convention: `_i` = "inverse" (reciprocal)

All fields and variables whose names end in `_i` represent **inverse (1/x) quantities**, most commonly inverse mean free paths:

| Field | Meaning | Unit |
|-------|---------|------|
| `mfp_i_sca_0` | **Inverse** scattering MFP at line centre = σ₀ × n_lower | [l]⁻¹ |
| `mfp_i_abs_0` | **Inverse** absorption MFP = α | [l]⁻¹ |

Do **not** feed actual mean free paths (cm) into these fields. Always provide the inverse: `1 / MFP_cm`. For example, to achieve τ₀ = 100 over a slab of length L = 10 cm → `mfp_i_sca_0 = 100 / L = 10 cm⁻¹` (NOT `L / 100 = 0.1 cm`).

This convention mirrors the naming in `notes.tm` where `λ_sca,0⁻¹` and `λ_abs⁻¹` denote the reciprocal mean free paths.


### 1.2 Velocity Space

- "Velocity" ≡ Doppler velocity shift: Δv = Δλ/λ₀ = −Δν/ν₀
- Δv > 0 for redshifts (longer wavelengths)
- All profile quantities (σ_ph, σ_th, b) are in velocity units [l][t]⁻¹

---

## 2. Photon Packets

Each photon packet represents many photons evolved over a unit time period.

### 2.1 Packet Parameters

| Symbol | Name | Dimension | Meaning |
|--------|------|-----------|---------|
| ℒ | proper | `[n][t]⁻¹` | Photon number luminosity of this packet (photons per unit time) |
| Δv | vel | `[l][t]⁻¹` | Doppler velocity centroid of the packet's Gaussian profile |
| σ_ph | sv | `[l][t]⁻¹` | Dispersion of the Gaussian velocity profile |
| **d̂** | dir | dimensionless | Normalized direction unit vector |
| **x** | x | `[l]` | Spatial position vector |

### 2.2 Velocity-Space Distribution

The per-unit-velocity photon-number distribution for a packet:

```
dℒ/dv = ℒ / (√(2π) σ_ph) × exp(−(v − Δv)² / (2 σ_ph²))
```

---

## 3. Flux Accumulation in Kratos

### 3.1 Total Flux `F` (field: `flx`)

When a photon packet with proper ℒ traverses a cell of volume V with intra-cell path length δl:

```
δF = ℒ × δl / V
```

Dimension: `[n][l]⁻²[t]⁻¹` — photon number fluence per unit area per unit time.

Summed over all photon crossings through the cell.

### 3.2 Overlap Integral I

The convolution of the photon's Gaussian profile with the thermal Gaussian absorption profile:

```
I = exp(−(Δv + v∥)² / (2(σ_ph² + σ_th²))) / √(1 + σ_ph²/σ_th²)
```

where:
- σ_th = thermal Doppler dispersion of the gas: σ_th = √(k_B T / μ)
- v∥ = **v** · **d̂** = bulk velocity projected along photon direction
- Δv = photon packet's velocity centroid (Δv > 0 = redshift)

The argument is Δv + v∥ (NOT Δv − v∥). Reason: transforming to the gas rest frame, the photon's velocity offset is Δv_gas = Δv_lab + v_bulk·d̂. The thermal absorption profile is centered at line center (v=0) in the gas frame, so the overlap integral evaluates the photon at Δv_gas.

In Kratos code (with b = √2 σ_th, sv ≈ σ_ph):

```
s2_sca = b² + 2·sv²                   // 2(σ_th² + σ_ph²)
dv    = vel + vel_obs                  // Δv + v_bulk·d̂ (gas-frame offset)
prof_s = exp(−dv² / s2_sca)
I     = prof_s × b / √(s2_sca)        // normalized overlap integral
```

### 3.3 Excitation-Effective Flux `F_ext` (field: `excitation_flux`)

```
δF_ext = I × δF = I × ℒ × δl / V
```

Dimension: `[n][l]⁻²[t]⁻¹` — photon number fluence per unit area per unit time, overlap-weighted.

This is the quantity Kratos outputs for the population solver. It already incorporates the Gaussian convolution — no further velocity-space integration is needed on the Python side.

### 3.4 Relationship

```
F_ext = I × F    (per-path-segment; summed over all photons)
```

---

## 4. Scattering (Kratos Transport)

### 4.1 Optical Depth Along Path

The remaining scattering optical depth τ_rem is initialized from an exponential distribution (mean = 1). At each cell crossing with path length δl:

```
δτ_rem = I × λ_sca,0⁻¹ × δl
```

where `λ_sca,0⁻¹ = σ₀ × n_lower` is the inverse line-center scattering mean free path. The overlap integral I encapsulates the velocity-space profile mismatch.

### 4.2 Scattering Event Location

If `τ_rem' = τ_rem − δτ_rem > 0`: no scattering in this cell; continue propagation.
If `τ_rem' ≤ 0`: linear interpolation to find scattering point within the cell at fractional distance `τ_rem / δτ_rem`.

### 4.3 Absorption (Real)

Along the path, the photon proper weight is reduced by absorption:

```
ℒ' = ℒ × exp(−δl × λ_abs⁻¹)
```

for pure continuum absorption (wavelength-independent), where `λ_abs⁻¹` [l]⁻¹ is the inverse absorption mean free path.

### 4.4 Scattering Event Mechanics (Re-emission)

When a scattering event occurs:

1. **Direction**: isotropic — uniform in cosθ ∈ [−1, 1] and φ ∈ [0, 2π]
2. **Velocity centroid**: `Δv = −v_bulk · d̂` (blueshift: gas moving along photon direction gives negative Δv)

The reason: in the gas rest frame, the re-emitted photon is at line center (Δv_gas = 0). Transforming back to the lab frame: Δv_lab = −v_bulk · d̂. When v_bulk · d̂ > 0 (gas moves with photon), the photon is blueshifted (Δv < 0).
3. **Profile dispersion**: `σ_ph = σ_th` (photon thermalizes to local gas temperature)
4. **New τ_rem**: generated from exponential distribution

This is the "coherent redistribution / complete frequency redistribution" (ph_mode=0) case.

**R_IIA modes (ph_mode = 1/2/3):** the re-emitted frequency is drawn
from the angle-averaged redistribution kernel
`P(u|x) ∝ exp(−u²) / (a² + (x−u)²)` — the conditional distribution of the
atom's parallel velocity `u` given incoming dimensionless frequency `x`
(Maxwellian atom velocity weighted by the Lorentzian absorption profile).
This is sampled via an inverse-CDF table lookup (USampler), with
directional correlation `g = dir_old·dir` (see §12.2 for the full R_IIA
kernel density definition used in imaging). All three modes share the same
kernel and table; they differ only in where the tables live and how the
Voigt opacity is evaluated:

| ph_mode | USampler table | Voigt opacity | Notes |
|---------|----------------|---------------|-------|
| 0 | — (CFR, Gaussian kick) | 2D table, global mem | σ_ph = σ_th |
| 1 | global mem (freed) | 2D table, global mem (128 KiB) | debug |
| 2 | constant mem (251×40, log-CDF) | 1D log-space table, const mem (5000 pts) | production |
| 3 | constant mem | approximate `voigt_H` blend (photon.h) | fastest; underestimates med\|x\| at low aτ₀ |

**Table sizes and GPU memory layout:**

| Table | Grid points | Bytes | ph_mode 1 (global) | ph_mode 2 (const) |
|-------|-------------|-------|-------------------|-------------------|
| 2D Voigt (`voigt_interp`) | 64×512 = 32,768 | 128 KiB | global (`to_device`) | host-only (removed from device) |
| 1D Voigt (`d_log_voigt_c`) | 5,000 | 19.5 KiB | — | const (`malloc_const`) |
| USampler CDF (`d_cdf`) | 251×40 = 10,040 | 39.2 KiB | global (`malloc_device`) | const (`malloc_const`) |
| USampler xg (`d_xg`) | 40 | 160 B | global | const |
| R_IIA kernel (`d_riia`) | 200×200×40 = 1,600,000 | 6.1 MiB | global | global (unchanged) |
| **Total const-mem** | — | — | — | **59.8 KiB** (of 64 KiB HW limit) |

The `free_dev_mem` flag (set at `init()`: `true` for ph1, `false` for ph2)
controls whether `build_usampler()` uses `malloc_device` (global) or
`malloc_const` + `f_cc` (const). The 2D Voigt table (128 KiB) is the largest
saving in ph_mode 2: it is replaced by a run-specific 1D slice (19.5 KiB)
pre-sampled at the fixed `a_voigt`, collapsing the `a` dimension entirely.
The R_IIA kernel (6.1 MiB) is too large for constant memory (~157× the 64 KiB
limit) and stays in global memory in all modes.

See `docs/debug/debug.md` "Jul 31 afternoon session" for the
validation numbers (a=0.149, Neufeld eq. 2.24) and the Humlicek
W4 / TG2006 evaluation.

---

## 5. Cross Sections

### 5.1 Line-Center Cross Section σ₀

From the Einstein A coefficient and temperature-dependent Doppler width:

**Given oscillator strength f** (Draine 2011, eq. 6.39):

```
σ(v) = √π e² f λ₀ / (m_e c √2 σ_th) × exp(−v²/(2σ_th²))
σ₀   = √π e² f λ₀ / (m_e c √2 σ_th)                         [l]²
```

**Given Einstein A** (using Draine 2011, eq. 6.20: A = (8π² e² ν² / (m_e c³)) × (g_l/g_u) × f):

```
σ₀ = (g_u/g_l) × A_ul × c³ / (8 π^(3/2) ν³ b)               [l]²
```

where:
- b = √2 σ_th = Doppler b-parameter [l][t]⁻¹
- σ_th = √(k_B T / μ) = thermal dispersion [l][t]⁻¹
- g_u, g_l = statistical weights of upper/lower levels (g = 2J + 1)

### 5.2 Scattering Inverse Mean Free Path

```
λ_sca,0⁻¹ = σ₀ × n_lower                                    [l]⁻¹
```

where n_lower [l]⁻³ is the number density of particles on the lower level of the transition.

### 5.3 Numerical Constants

```
e  = 4.80321 × 10⁻¹⁰ g^(1/2) cm^(3/2) s⁻¹   (CGS electron charge)
m_e = 9.10938 × 10⁻²⁸ g
c  = 2.99792 × 10¹⁰ cm/s
k_B = 1.38065 × 10⁻¹⁶ erg/K
√π = 1.77245
π^(3/2) = 5.56833
```

---

## 6. Population Calculation (Python Side)

> **Proposition: excitation maps to transitions, not levels.**
> Kratos outputs one excitation flux field per transition (configured by `n_fld`). Each excitation flux is the overlap-integrated fluence **F_ext** for that specific transition. The population solver applies this F_ext only to the transition's (lower ↔ upper) pair — not to all levels. It is physically inconsistent to spread a single-transition's F_ext across multiple levels.

### 6.1 Photon Excitation Rate

The Kratos output `F_ext` (overlap-weighted excitation flux) is used to compute the per-lower-level-particle excitation rate:

```
Γ = F_ext × σ₀                                            [t]⁻¹
```

Dimension check: `[n][l]⁻²[t]⁻¹ × [l]² = [t]⁻¹` (with [n] treated as dimensionless counting unit).

**No additional optical depth factor is applied** — Kratos already tracked absorption and the overlap integral during MC transport.

### 6.2 Statistical Equilibrium (2-Level System)

For levels g (ground, index 0) and e (excited, index 1):

**Rate balance:** the lower level is depopulated by photon excitation
(Γ) and by induced absorption from the thermal radiation background
(R_abs); the upper level is depopulated by spontaneous decay (A_ul)
and by stimulated emission from the background (R_stim).

The thermal Planck background at temperature T enters through the
Bose-Einstein occupation number:

```
x = 1 / (exp(hν / k_B T) - 1)          (dimensionless)

R_abs  = (g_u / g_l) × x × A_ul        [t]⁻¹   (induced absorption)
R_stim = x × A_ul                       [t]⁻¹   (stimulated emission)
```

where ν is the transition frequency, h the Planck constant, k_B the
Boltzmann constant, and g_u, g_l the statistical weights.

The population ratio is:

```
n_e / n_total = (Γ + R_abs) / (A_ul + R_stim + Γ + R_abs)   (dimensionless)
```

**Limiting behaviour:**

- **Zero external flux (Γ = 0):** reduces to the Boltzmann
  distribution n_e/n_total = R_abs / (A_ul + R_stim + R_abs),
  i.e. n_e/n_g = (g_u/g_l) × exp(−hν / k_B T).  At high T the
  Boltzmann factor → 1 and n_e/n_total → g_u / (g_u + g_l).

- **Strong external flux (Γ ≫ A_ul):** n_e/n_total → 1 (all
  particles pumped to the upper level), regardless of temperature.

- **No thermal background (T = 0 or T = None):** R_abs = R_stim = 0,
  giving n_e/n_total = Γ / (A_ul + Γ).

**Consistency with MCRT opacity:** the MCRT uses σ₀ × n_lower (no
stimulated-emission correction in the opacity).  The Γ term therefore
does NOT include a (g_l/g_u) × Γ stimulated-emission contribution.
Adding one would cap n_e/n_total at g_u/(g_u + g_l) < 1 even for
arbitrarily strong flux, contradicting the opacity model.

With collisions (collisional de-excitation rate C_ul, excitation rate
C_lu = (g_u/g_l) × exp(−hν/k_B T) × C_ul by detailed balance):

```
n_e / n_total = (Γ + R_abs + C_lu) / (A_ul + R_stim + C_ul + Γ + R_abs)
```

### 6.2b Collisional Destruction Probability

When collisional de-excitation is active, a fraction of the absorbed line
photons are **destroyed** (thermalised) rather than re-emitted.  The
destruction probability is:

```
ε = C_ul × n_coll / (A_ul + C_ul × n_coll)
```

where `C_ul` [cm³ s⁻¹] is the collisional de-excitation rate coefficient
(interpolated from LAMDA tables or user-supplied) and `n_coll` [cm⁻³] is
the collider number density.  This adds an effective absorption opacity:

```
mfp_i_abs_line = n_lower × σ₀ × ε       [cm⁻¹]
```

to the user-provided `mfp_i_abs_0`.  The total effective absorption MFP
inverse is `mfp_i_abs_eff = mfp_i_abs_user + mfp_i_abs_line`, computed
per-cell from the local temperature and collider density
(`SpeciesData.destruction_opacity()` in `molecular/lamda_format.py`).
At high collider density (n_coll ≫ n_cr = A_ul/C_ul), ε → 1 and the line
becomes pure absorption (thermalised).  At low density (n_coll ≪ n_cr),
ε → 0 and the line is pure scattering.

### 6.3 Multi-Level Statistical Equilibrium

Linear system for N levels:
- For each pair i ≠ j: M[i,j] = R_rad[j→i] + R_col[j→i](T)
  - R_rad includes spontaneous (A_ul), induced absorption (R_abs),
    and stimulated emission (R_stim) from the Planck background at T
- Diagonal: M[i,i] = −Σ_{j≠i} M[j,i]
- Replace last row with Σ_i n_i = n_total
- Solve: M · n = b

---

## 7. Iteration Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                      PYTHON SIDE                             │
│                                                              │
│  Cycle 0: initial populations (LTE if species data exists)  │
│         -> generate emission photons (FROZEN across cycles) │
│         → compute λ_sca,0⁻¹ (CGS)                            │
│         → convert CGS → code units (×unit_l0, ×t0/l0)        │
│         → write binary field + photon files (code units)     │
│                          │                                    │
│                          ▼                                    │
│                      KRATOS SIDE  (code units)                │
│                                                               │
│  Read fields + photons (all in code units)                    │
│  MC transport: accumulate F = ℒ×δl/V, F_ext = I × F          │
│  Write F and F_ext (per-cell, code units) to output binary    │
│                          │                                    │
│                          ▼                                    │
│                      PYTHON SIDE                              │
│                                                               │
│  Cycle 1+:                                                    │
│    Read F_ext from Kratos output (code units)                 │
│    Undo proper scaling: F_ext_cgs = F_ext_code               │
│         × scale_factor / (unit_l0² × unit_t0)                 │
│    Compute Γ = F_ext_cgs × σ₀ (CGS, [t]⁻¹)                   │
│    Solve populations per transition-pair (not per-level)      │
│    Filter NaN → 0 in boundary cells                           │
│    Update λ_sca,0⁻¹, convert CGS → code, write binaries       │
│                          │                                    │
│                          ▼                                    │
│                      KRATOS SIDE ...                          │
│                                                              │
│  Repeat until convergence or max cycles                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Fields Provided to Kratos by Python

**All fields are written in Kratos code units.** The Python pipeline converts CGS → code units before writing:

| Python conversion | CGS → code unit factor |
|-------------------|-----------------------|
| `mfp_i_sca_0`, `mfp_i_abs_0` | × `unit_l0` |
| `b_sca`, `vel` | × `unit_t0 / unit_l0` |

The field table below shows fields with their **code-unit** dimensions:

| Field Name | Symbol | Dimension | Content |
|-----------|--------|-----------|---------|
| `mfp_i_sca_0_` | λ_sca,0⁻¹ | [l]⁻¹ | Inverse line-center scattering MFP |
| `mfp_i_abs_0_` | λ_abs⁻¹ | [l]⁻¹ | Inverse absorption MFP |
| `b_sca_` | b_sca | [l][t]⁻¹ | Doppler b for scattering profile |
| `vel_0_`, `vel_1_`, `vel_2_` | **v** | [l][t]⁻¹ | Bulk velocity (3 components) |

Optional additional fields (for diagnostics):
| `temp_` | T | K | Gas temperature (not used by Kratos) |

---

## 9. Fields Read from Kratos by Python

**Kratos outputs fields in code units.** The Python pipeline converts back to CGS, also undoing the proper-weight FP32 scaling factor:

| Conversion | Code → CGS factor |
|-----------|-------------------|
| `flx`, `excitation_flux` | × `scale_factor` ÷ (`unit_l0²` × `unit_t0`) |

where `scale_factor` is the scaling factor returned by `write_photon_data()` (user `proper_scale`, possibly combined with the automatic FP32 fallback).

| Field Name | Symbol | Code-unit Dimension | Content |
|-----------|--------|---------------------|---------|
| `flx_` | F | `[n][l]⁻²[t]⁻¹` | Total photon number fluence |
| `excitation_flux_` | F_ext | `[n][l]⁻²[t]⁻¹` | Overlap-weighted excitation flux |

For the population solver, only `excitation_flux_` is needed. `flx_` is for diagnostics.

---

## 10. Source Photon Packet Generation

### 10.1 External Sources

**Isotropic point source**: user specifies photon-number luminosity L_phot [n][t]⁻¹.

```
L_phot = L_erg / hν
proper_per_packet = L_phot / N_packets       [n][t]⁻¹
```

Directions: uniform in cosθ ∈ [−1,1], φ ∈ [0,2π].

With `r_random = R` [cm] (default 0), each packet's initial position is
drawn uniformly (volume-weighted) over the sphere of radius R centred on
`position`: `r = R·u^(1/3)` with u ∈ U(0,1), then an independent
isotropic unit vector.  This gives E[r³] = R³/2 (E[r] = 3R/4) and
approaches the ideal point source as R → 0.  Rejected for slab sources.

**Plane-parallel extended (slab) source**: user specifies photon number flux F_phot [n][l]⁻²[t]⁻¹.

For a slab face with area A = (y_max − y_min) × (z_max − z_min) in physical units (cm²):

```
total_rate = F_phot × A                         [n][t]⁻¹
proper_per_packet = total_rate / N_packets       [n][t]⁻¹
```

All photons have the same initial direction d̂ (uniform across the face). Sum of packet proper weights per unit area perpendicular to d̂ equals F_phot.

**Units selection (`LineRt.add_source`)**: quantities default to photon
number.  Passing `units='energy'` treats the input as erg-based and
converts via the transition wavelength λ:

```
F_phot = F_erg / (h c / λ)          [slab; flux in erg cm⁻² s⁻¹]
L_phot = L_erg / (h c / λ)          [point; luminosity in erg/s]
```

The wavelength is always taken from `transition_info` (no user-supplied
`wavelength` argument exists).  `units='energy'` therefore requires a
transition to be configured.

### 10.2 Internal Sources (cell emission)

Each cell with upper-level particle density n_u [l]⁻³ produces photon-number
emissivity (per steradian):

```
j = n_u × A_ul / (4π)              [n][l]⁻³[t]⁻¹[sr]⁻¹  (photon-number)
```

The total photon production rate per cell is `4π × j × V_cell`, and the
proper weight per packet is:

```
L_cell   = n_u × A_ul × V_cell_cgs          [n][t]⁻¹ (photon number luminosity)
proper   = L_cell / N_packets_cell          [n][t]⁻¹ (photons per unit time)
```

where `V_cell_cgs = dx·dy·dz × unit_l0³` is the **CGS** cell volume (the
mesh `dx` is in code units).  This is consistent with external sources,
whose proper weights are also in [n][t]⁻¹ (photon number per unit time).

**Anti-double-counting policy.**  Emission photons are generated **once**
from the LTE (cycle-0) populations and **frozen** across all subsequent
cycles.  Only the scattering opacity `mfp_i_sca_0` (derived from the
lower-level population n_lower) is updated each cycle.  This avoids
double-counting the radiative excitation: scattered photons already carry
the absorption + re-emission of the radiation field, so regenerating new
emission from the radiation-inflated n_u would count it twice.

**Velocity shift.**  Each emission photon is created at line centre in the
gas rest frame.  The stored `vel` includes the bulk Doppler shift:

```
vel = vel_thermal_draw − v_bulk · dir      (thermal draw minus projected bulk velocity)
```

so that `dv = vel + vel_obs = vel + dir·v_bulk` recovers the thermal draw
in the emitting cell's rest frame.

---

## 11. Unit Conversion: CGS ↔ Kratos Code Units

### 11.1 Code Unit Specification

Defined in the `[unit]` section of the Kratos parameter file. The Python pipeline converts all quantities from CGS to code units BEFORE writing field/photon files. Kratos internally works entirely in code units except where `_cgs` suffixes mark explicit CGS quantities.

### 11.2 Photon Proper-Weight Scaling for FP32

Photon `proper` values can be very large (e.g., ~10⁴⁴ for astronomical luminosities). The Python writer (`write_photon_data()`) applies two rescale stages and **returns the combined scale factor**:

1. **User / auto rescale** — every photon weight is multiplied by `proper_scale`. When `proper_scale=None` (default), the pipeline auto-computes a scale from the estimated maximum `s_cam` magnitude in code units, considering both the **emission seed** (`emiss/(mfp_s·√π·b)`) and the **scattering contribution** (`n_ph·max_proper·max_dsi/(4π·√π·b)`), so that the Kratos-side `s_cam` field fits in FP32 range (< 1e30, margin below 3.4e38). This prevents the thermal-seed overflow that produces `inf` imaging cubes. Set `proper_scale=1.0` to disable auto-scaling, or a small value (< 1) for manual control. Passed as `proper_scale=` to `iterate()`/`run_pipeline()`, `LineRt(proper_scale=...)`, or `--proper-scale` on the CLI. Because Kratos MCRT is linear in photon weights, a constant rescale leaves all fields unchanged after the read-back division.
2. **FP32 fallback** — if the scaled `proper_max` still exceeds `1e38`, all weights are further scaled by `1/proper_max`.

`write_photon_data()` copies its input (never mutates the caller's array).

On readback, the pipeline MUST undo this scaling on Kratos outputs that carry the proper weight:

```
flx_cgs    = flx_code    × scale_factor / (unit_l0² × unit_t0)
F_ext_cgs  = F_ext_code  × scale_factor / (unit_l0² × unit_t0)
proper_escaped_cgs = proper_written / scale_factor
```

Both `iterate()` (low-level) and `run_pipeline()` (high-level) handle this automatically. The `results` dict returned to the user always contains CGS-scaled flux quantities. Escaped-photon `proper` weights are divided by `scale_factor` only (no `unit_l0` — they are photon-number weights, NOT path lengths); they appear in `results[i]['photons']['proper']` (CGS photons/s per packet, absorption-attenuated), with `'l'` retained as a deprecated alias.

### 11.3 Volume Consistency

Python-side cell volumes used for internal source luminosity must match Kratos cell volumes (i.e., use the same mesh specification). The Python pipeline computes `V_cell = dx × dy × dz` from the mesh definition passed to `make_cartesian_mesh()`.

---

## 12. Imaging (Two-Step: Scattering Source Function + Ray Tracing)

Imaging produces a position–velocity cube `I(pixel, channel)` = the
specific intensity reaching a distant observer, using the Kratos-polrad
two-step method (Yang & Wang 2025, §2.3 + Appendix A; adapted from the
polarization-specific `usr_ext/pol_rad` to scalar line RT).

### 12.1 Principle

Direct MC imaging is hopelessly expensive: the camera subtends a tiny
solid angle and multiple scattering randomises directions. Because RT is
linear, the contribution of scattered photons to a *fixed* viewing
direction can instead be accumulated **on the grid during the scattering
MC**, then a separate **non-scattering ray tracing** integrates the
transfer equation along camera rays — a post-processing step that can be
repeated for any viewing angle/camera at negligible cost.

The imaging is enabled by setting `imaging` in the `LineRt` constructor
(`core/line_rt.py`) or the `[imaging]` par section. It runs only on the
**final** MC cycle. When disabled, the s_cam field is not initialised,
allocated, or written — existing (non-imaging) runs are unaffected.

### 12.2 Step 1 — Scattering source function `s_cam`

The per-cell, per-channel field `s_cam` (Kratos `rad_t.s_cam`,
`n_int = n_chan`) carries the **total source function toward the camera
direction** — the emission seed and the scattering contribution are
folded together (populations enter only through the emission/absorption
profile weights, not as a separate `n_u·A_ul` term).

**Emissivity seed** (`radiation.h:init_rad_fields_kernel`).  On GPU init
the field is seeded with the line source function from the local emissivity:

```
S_emiss = emiss / (mfp_i_sca_0 · √π · b_sca)   (emiss from the field binary, code units)
```

The `√π · b_sca` factor converts the frequency-integrated source function
(`emiss/mfp_i_sca_0`, integrated over the line profile) to the
frequency-dependent source function `S(v) = j(v)/α(v)`, which is
frequency-independent for a two-level atom with CRD.
This is applied to **every channel equally**.
The per-channel selectivity comes only from the opacity profile in the
imaging pass (§12.4).  `emiss` is the **photon-number** volume emissivity
`n_u·A_ul/(4π)` [n][l]⁻³[t]⁻¹[sr]⁻¹ computed by
`molecular/lamda_format.py:compute_emissivity()` and written to the line
field file (`fields_cycleN.bin`, key `emiss_`) by `make_fields()`.

**Scattering accumulation** (`photon.h:proc_phys`).  During the MC, each
path segment in cell `i` also adds the packet's contribution to the
scattering source function toward the camera:

```
base = flx · (1 − e^−dτ_e) / dτ_e · (1/4π) / b_sca    (flx = proper·dl/V)
for channel k:
    dv_cam  = v_chan[k] + dir_cam·v_bulk(i)          (gas-frame offset
                                                      toward the camera)
    x_out   = dv_cam / b_sca
    x_in    = (vel + vel_obs) / b_sca               (photon's gas-frame
                                                      incoming freq)
    # Note: the code variable is named "x_pp" but is actually x_in
    # (gas-frame, NOT atom-frame); see §12.2 Convention B.
    g_dot   = dir_photon · dir_cam                  (directional correlation)
    prof_s  = H(a_voigt, x_in)                       (Voigt profile at the
                                                      photon's INCOMING freq)
    R       = R_IIA_kernel(x_out, |x_in|, g_dot)  (precomputed 3-D table)
    s_cam[i,k] += base · R · prof_s
```

Here `dτ_e = dl·(mfp_i_sca_0 + mfp_i_abs_0)` is the total extinction along
the segment (at the photon's own frequency, using the unnormalised line
opacity `mfp_i_sca_0`), and the `(1−e^−dτ_e)/dτ_e` factor is the
escape-probability-per-unit-length that weights the segment by the chance
the packet scatters within the cell.

The `prof_s = H(a, x_in)` factor is the Voigt profile evaluated at the
photon's **incoming** gas-frame frequency `x_in = (vel + vel_obs)/b_sca`.
Note: the code variable is named `x_pp` but is actually `x_in` (gas-frame,
not atom-frame); this follows Convention B (Dijkstra 2017 Saas-Fee), where
the kick is `Δ = x_out − x_in` with Gaussian center `u_∥(g−1)` — see §12.2.
Including it makes `s_cam` an **emissivity** (`j = σ(v_in) × R × J`), not a source
function.  The imaging pass (§12.4) multiplies by `mfp_s` (line-centre
opacity scale `σ₀ × n_l`) to recover the full emissivity
`j = σ₀ × H(a, x_in) × R × J = σ(v_in) × R × J`.  The opacity is at the
**incoming** frequency (where the photon is absorbed), not the outgoing
frequency — this avoids the spurious extra line-profile factor
`H(a, x_out)` that would produce a double-Gaussian spectrum
(see `docs/debug/imaging_source_term.md`).

The **R_IIA kernel** `R(x_out; x_in, g)` is the full angle-dependent
frequency redistribution kernel density, precomputed at startup as a 3-D
table (`intg.h:build_riia_kernel`, 200×200×40 = 1.6 M floats in device
global memory) from the USampler CDF.  The table is parametrised in
`Δ = x_out − x_in` (not `x_out` directly), which halves the table
size while providing 6× finer resolution in the dynamically relevant
range.  An analytic asymptotic is used for `|x_in| ≥ 120` where the
USampler CDF has converged.

> **Convention B** (Dijkstra 2017, Saas-Fee Eq. 71): the kernel is
> expressed in the **gas-frame** incoming frequency `x_in` (fixed per
> photon), with kick `Δ = x_out − x_in` and Gaussian center
> `u_∥(g−1)`.  This conserves the outgoing frequency `x_out` (verified:
> `∫R dΔ = 1`, `⟨x_out⟩ = x_in`).  The alternative Convention A
> (atom-frame `x_pp` with center `u_∥g`) conserves the atom-frame
> frequency instead — physically wrong as a redistribution kernel.

#### Definition of the R_IIA kernel

**Step 1 — USampler** (angle-averaged R_II conditional,
`intg.h:build_usampler`).  The conditional distribution of the atom's
parallel velocity `u` given incoming dimensionless frequency `x` is:

```
P(u | x) ∝ exp(−u²) / (a² + (x − u)²)
```

where `u` and `x` are in Doppler-width units (`v_th = √(2kT/m)`), and `a`
is the Voigt damping parameter.  This is the standard R_II redistribution
kernel conditional — the Maxwellian atom velocity distribution weighted by
the Lorentzian absorption profile.  The USampler tabulates the CDF of
`P(u|x)` on a grid of `n_u = 251` points spanning `u ∈ [−6, +6]`
(`Δu = 0.048`), for `n_xg = 40` values of `|x|` on a mixed linear+log
grid spanning `[0, 300]` (18 linear points `[0, 8]` + 22 log points
`[8, 300]`).  The CDF is stored as `log(CDF)` in float32 for smooth tail
interpolation.  `a_eff = max(a_voigt, 1e-6)` avoids NaN at `a = 0`.

**Step 2 — R_IIA kernel density** (`intg.h:build_riia_kernel`).  The full
angle-dependent kernel is the marginalisation of the sampling distribution
over the perpendicular velocity component.  The table is parametrised in
`Δ = x_out − x_in` (Convention B).  For each `(|x_in|, g, Δ)`:

```
R(Δ; x_in, g) = Σ_k  pdf[k] × Gauss( y_k ; σ = sin_g / √2 )

    y_k    = Δ − u_k × (g − 1)
    sin_g  = √( max(1 − g², 0) )       (clamped to ≥ 1e-3)
    pdf[k] = CDF[k] − CDF[k−1]          (discrete probabilities from the
                                         USampler CDF row at |x_in|)
    Gauss(y; σ) = exp(−y² / sin_g²) / (sin_g √π)
```

The table covers `Δ ∈ [−10, +10]` (200 points), `|x_in| ∈ [0, 120]`
(200 points), `g ∈ [−1, +1]` (40 points), total 1.6 M float32 values.
Device-side lookup (`intg.h:riia_kernel`) uses trilinear interpolation with
edge clamping (no extrapolation).  **Symmetry:**
`R(Δ; −x_in, g) = R(−Δ; x_in, g)` — the table stores only `|x_in| ≥ 0`;
the sign is restored at lookup time via `sgn = sign(x_in)`,
`t_Δ = (x_out − x_in) × sgn`.

**Asymptotic for `|x_in| ≥ 120`:** the USampler CDF converges to
`pdf_∞ ∝ exp(−u²)` (independent of `x_in` and `a`), giving the
analytic kernel:

```
R_∞(Δ; g) = exp( −Δ² / ((g−1)² + sin²_g) ) / ( √π × √((g−1)² + sin²_g) )
```

which is used directly (no table lookup).  The kernel returns 0 for
`|Δ| > 10` (negligible).

**Normalisation:** `∫ R dx_out = 1` by construction (`Σ pdf = 1` from the
CDF, `∫ Gauss = 1`).  The `1/b_sca` factor in the `s_cam` accumulation
converts from dimensionless `x` to velocity-space density.

**Relationship to photon scattering:** the code has two paths using the
same USampler table:

- **Sampling path** (actual photon scattering, `photon.h:scat()`): draws
  `u_par` from `P(u|x_freq)` via inverse-CDF lookup (`intg.h:sample_upar`),
  then `x_new = x_freq + u_par×(g−1) + sin_g×u_perp` where
  `u_perp ~ N(0, 1/√2)` (Box–Muller).  This produces a single random
  outgoing frequency per scattering event.
- **Density path** (imaging source function, `photon.h:proc_phys`):
  evaluates the kernel density `R(x_out; x_in, g)` via trilinear
  interpolation of the precomputed table.  This gives the probability
  density of scattering into each camera channel, marginalised over the
  perpendicular velocity — the analytic integral of the sampling kernel.

**Emission seed vs scattering**: the emission seed (`emiss/(mfp_s·√π·b)`,
§12.2 above) is a **source function** `S = j/α` (frequency-independent for a
two-level atom).  The imaging pass converts it to emissivity via
`j = mfp_s × S` (line-centre opacity scale; see §12.4).  The scattering
accumulation (`base·R·prof_s/b`) is already an emissivity (includes
`σ(v_in) = σ₀ × H(a, x_in)`).  Both contribute to the same `s_cam` field,
and the imaging pass applies the same `j = mfp_s × s_cam` formula uniformly.

In the optically thin limit the emission seed dominates (no scattering);
in thick slabs the scattering accumulation captures the multiple-scattering
source function that builds up the characteristic double-peaked surface
distribution (§12.6).

### 12.3 Camera and channel grid

**Camera** (Kratos `intg.h`, par section `[imaging]`):
`dir_cam_theta` / `dir_cam_phi` [rad] define the line of sight **pointing
into the domain** (imaging photons march along `+dir_cam`):

```
dir_cam = (sinθ·cosφ, sinθ·sinφ, cosθ)
```

The camera-frame image plane (LOS = +z, pixel centres at z=0) is rotated
into the domain frame by the quaternion `q_cam` (minimal rotation from
+z to `dir_cam`).  `LineRt(imaging={'dir_cam': (θ, φ)})` accepts the
spherical pair, or a 3-vector (Cartesian, normalised internally).

**Image plane** (Kratos `intg.h`, `img_x0`/`img_dx`/`img_n`): a flat grid
of `img_resol = (n_x, n_y)` pixels covering the first two mesh dimensions
(`x_min`..`x_max`), centred on cell centres, at camera-frame z=0.  One
thread per pixel; each pixel emits a parallel ray along `dir_cam`.

**Velocity channels** (`n_chan`, `v_chan_min`/`v_chan_max` [cm/s, CGS]):
the channel grid uses **bin centres**, `v_chan[k] = v_min + (k+0.5)·dv`
with `dv = (v_max − v_min)/n_chan`.  Python converts CGS→code
(`× unit_t0/unit_l0`) before writing the par file.  The bin-centre
convention (rather than linspace endpoints) matches the test
infrastructure and avoids edge aliasing when `n_chan` is small.

### 12.4 Step 2 — Non-scattering ray tracing (imaging pass)

A second module (`rad_img_t` + `photon_img.h:line_img_t`, enrolled as a
parasite of `radiation_t` in `usr.cpp`) integrates the transfer equation
along each camera ray, cell by cell, with the **analytic** solution of
`dI/dτ = −I + S` per cell (`S` assumed constant over the cell):

```
per channel k, per path segment:
    dv_cam  = v_chan[k] + dir_cam·v_bulk(i)
    prof    = φ(dv_cam / b_sca)                       (Gaussian or Voigt)
    α_t     = mfp_i_sca_0 · prof + mfp_i_abs_0        (total extinction)
    dτ      = α_t · dl_seg
    e^−dτ   = exp(−dτ)
    j       = mfp_i_sca_0 · s_cam[i,k]               (emissivity; s_cam already
                                                       includes H(a, x_in))
    I[k]    = I[k]·e^−dτ + (j/α_t)·(1 − e^−dτ)      (analytic cell update)
```

The emissivity `j = mfp_s × s_cam` uses the line-centre opacity scale
`mfp_s = σ₀ × n_l` (NOT the frequency-dependent `α_s = mfp_s × H(a, x_out)`).
This is correct because `s_cam` already includes `prof_s = H(a, x_in)` in
the MC accumulation (§12.2), so
`j = mfp_s × [base × R × H(a, x_in)] = σ₀ × n_l × H(a, x_in) × R × J = σ(v_in) × R × J`.
Using `α_s = mfp_s × H(a, x_out)` instead would introduce a spurious
extra `H(a, x_out)` factor, producing a double-Gaussian spectrum in the
thin-slab limit (see `docs/debug/imaging_source_term.md`).
For Group 1 (emiss present) the emission seed is a source function
`S = emiss/(mfp_s × √π × b)`; `j = mfp_s × S` converts it to the
line-centre emissivity `emiss/(√π × b)`.

The imaging photon has `n_scat = 1` (never scatters); `proc_geo` is the
pure geometric move.  Rays start at the far box boundary along `−dir_cam`
(`x = x0 − dl_min·dir·0.9999`) and march through the domain to the camera
plane.  Output (binary keys `_dir_img`, `_x_img`, `_i2d_img`, `_l_img`)
is read back by `kratos_io.read_output()` into `result['image']`.

**Voigt profile in the imaging pass**: the imaging integrator
(`rad_img_t`'s `intg_t`) sets `build_tables=false` to avoid re-building
the USampler/Voigt tables into constant memory (pool overflow, see
pitfall 18).  Instead, the Voigt table pointers are **shared from the
scattering integrator** in `rad_img_t::init()`: for ph_mode 0/1 the 2-D
global-mem table (`voigt_interp`) is shallow-copied; for ph_mode 2 the
1-D const-mem table (`d_log_voigt_c`) pointer is copied.  This gives the
imaging pass access to the same smooth tabulated Voigt profile as the
scattering pass, avoiding the derivative discontinuity of the analytic
`max(exp(−u²), a/(√π·(u²+a²)))` fallback that was used in earlier versions.

**Units**: the imaging output inherits the scaled-proper convention.
Both the scattering part (accumulated from the scaled photon propers) and
the emission seed must live in the same scaled units, so the `emiss` field
is rescaled by `proper_scale` on write (`core/iterator.py`) and the cube
is divided by `scale_factor` on readback, then converted to CGS
intensity (`÷ unit_l0³`; `unit_t0` cancels in the source-function
ratio).  When `proper_scale=None` (default), the scale is auto-computed
(see §11.2) to prevent the emission-seed FP32 overflow.  The cube in
the results dict is `image['cube_cgs']` in **photon-number** surface
brightness [photons cm⁻² s⁻¹ sr⁻¹].  The `l³` (not `l²`) reflects that
the imaging intensity `I(v)` has units [ph cm⁻³ sr⁻¹] = [ph cm⁻² s⁻¹
sr⁻¹ per (cm/s)], i.e. the velocity-channel width is in cm/s.

### 12.5 Python API

```python
rt = LineRt(..., imaging = {
    'dir_cam': (0.5, 0.0),       # (theta, phi) rad, or 3-vector
    'n_chan': 64,
    'v_chan': (-1e6, 1e6),       # [cm/s] channel range
    'img_resol': (nx, ny),       # optional image resolution
    'img_xmin': ... ,            # optional (code units)
    'img_xmax': ... ,
})
out = rt.run(...)
out['image']                     # {'cube': (n_pix, n_chan) CGS,
                                 #  'i2d': (n_pix, 2), 'v_chan': (v_lo, v_hi), ...}
rt.plot_channel_maps()           # shared-log-scale channel maps
```

### 12.6 Validation

The imaging module has been validated against Neufeld (1990) eq. (2.24)
for a plane-parallel scattering slab with isotropic midplane injection
(inheriting the `test_scaling_wide.py` geometry):

**Escaped photon spectrum** (angle-averaged emergent `med|x|`):

| τ₀ (mean) | golden `med|x|` | measured | ratio | PASS |
|-----------|----------------|----------|-------|------|
| 200       | 3.115          | 3.111    | 1.002 | ✓    |
| 500       | 4.025          | 4.027    | 1.000 | ✓    |
| 2000      | 6.148          | 6.149    | 1.000 | ✓    |
| 8000      | 9.736          | 9.753    | 1.002 | ✓    |

All within 0.3% of the golden values (tolerance 5%).

**Imaging spectrum** (formal transfer cube `I(x)`):

| τ₀   | imaging peak ±x | Neufeld peak | I(0)/I_max | dip shape      |
|------|------------------|-------------|------------|----------------|
| 200  | ±2.19            | 2.73        | 0.304      | clear double-peak |
| 2000 | ±5.31            | 5.89        | 0.220      | broad U-shape  |
| 8000 | ±9.06            | 9.34        | 0.200      | broad U-shape  |

The imaging double-peak **moves outward** with increasing τ₀, following
the Neufeld `(a·τ₀)^(1/3)` scaling.  The peak position is slightly below
the Neufeld value (by 10–20%) because the imaging source function
includes contributions from all depths (not just the exit surface where
the Neufeld formula applies).  The centre dip deepens for optically thin
slabs (τ₀=200: I(0)/I_max = 0.30) and flattens for thick slabs
(τ₀=8000: I(0)/I_max = 0.20) as the interior single-peaked source
function contributes more.

**Thin-slab normalization** (`tests/test_imaging_normalization.py`):
for an optically thin, non-absorbing slab with a uniform source, the
imaging cube matches the analytic `I = j·L` to within 0.01%.  Three
configurations tested: (1) emission only (Group 1), (2)
scattering of an external slab source (Group 2), (3) absorbing medium.
All pass.

**Standalone test**: `~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_imaging_neufeld.py`
inherits `test_scaling_wide.py`'s geometry (isotropic midplane source,
128×2×2 mesh, L=1 AU) and adds the `[imaging]` section.  Run:
```bash
cd ~/apps/kratos_line_rt/usr_ext/line_rt/tests
python3 test_imaging_neufeld.py --kratos-root ~/apps/kratos_line_rt
```

---

## 13. Collisional Rates and Destruction Probability

### 13.1 LAMDA collision data

LAMDA files contain collisional de-excitation rate coefficients C_ul(T)
[cm³ s⁻¹] for each collision partner (e.g. pH2, oH2, e, H, He).  The full
LAMDA files are downloaded on demand by `molecular/lamda_fetcher.py`
(cache -> download -> embedded fallback).  The embedded species files
are **stripped** (no collision partners) and serve only as a last-resort
fallback when the network is unavailable.

For a 2-level `TransitionInfo.user_defined()` species, the user can supply
collision **rate coefficients** via the `collision_rates` parameter, and
the collider **number density** via `LineRt(colliders=...)`:

```python
#  Rate coefficients (molecular property) in user_defined:
ti = TransitionInfo.user_defined(
    A_ul = 18.17, freq_GHz = 63302.467,
    g_u = 15, g_l = 17, species_name = 'CO',
    collision_rates = {
        'H2': 3e-12,                        # float [cm^3 s^-1] or callable f(T)
    },
)

#  Number density (spatial field) in LineRt:
rt = LineRt(
    transition_info = ti,
    colliders = { 'H2': 1e6 },              # float [cm^-3] or callable f(X,Y,Z)
    ...,
)
```

- **`collision_rates`** (in `user_defined`): a flat dict mapping partner
  name to a rate coefficient - a number (constant C_ul [cm³ s⁻¹]) or a
  callable `f(T) -> float`.  Callables are evaluated directly at the
  local gas temperature at runtime (no fixed grid; the user controls
  the valid T range).
- **`colliders`** (in `LineRt`): a flat dict mapping partner name to a
  number density [cm⁻³] - a float or a callable `f(X, Y, Z)` over the 3D
  mesh (same interface as `n_species`).

This separation keeps molecular data (rates) in `TransitionInfo` and
spatial fields (densities) in `LineRt`, matching the existing pattern
where `n_species` and `temperature` are also `LineRt` spatial fields.

### 13.2 Collisional destruction (§6.2b)

The destruction probability ε = C_ul·n_coll / (A_ul + C_ul·n_coll)
converts a fraction ε of the line scattering opacity into true absorption.
This is computed per-cell by `SpeciesData.destruction_opacity()` and added
to the user-provided `mfp_i_abs_0` in `core/iterator.py`.  The effective
absorption MFP inverse is:

```
mfp_i_abs_eff = mfp_i_abs_user + n_lower × σ₀ × ε
```

### 13.3 Ro-vibrational lines (not in LAMDA)

LAMDA contains only pure rotational data (v=0).  For ro-vibrational
transitions (e.g. CO P(8) v=1->0 at 4.736 µm), collisional de-excitation
rates must be obtained from external sources:
- **ExoMol** (`exomol.com`): line lists + state files
- **BASECOL** (`basecol.vamdc.org`): collisional rate database
- **Literature**: Song et al. 2015, Thi et al. 2013

Supply them via the `collision_rates` parameter of
`TransitionInfo.user_defined()`.

### 13.4 Critical density

The critical density n_cr = A_ul / C_ul separates LTE (n_coll ≫ n_cr,
ε -> 1, line thermalised) from subthermal (n_coll ≪ n_cr, ε -> 0, pure
scattering).  For high-J or ro-vibrational transitions, n_cr is typically
10⁹-10¹² cm⁻³, so PPD surface layers (n ~ 10⁶-10⁸) are subthermally
excited and collisions must be included for accurate populations.

---

## Appendix A: Common Implementation Bugs

1. **Confusing excitation_flux with dust absorption**: excitation_flux MUST be I × F (overlap-weighted fluence), NOT dfab (dust-absorbed energy)
2. **Wrong cross-section formula**: use σ₀ = (g_u/g_l) × A × c³ / (8 π^(3/2) ν³ b), NOT c²/(2 ν³ b √π)
3. **Double-counting optical depth**: F_ext already includes Kratos MC transport — do not apply additional (1−exp(−τ)) on the Python side
4. **Missing overlap integral in F_ext**: without I-weighting, F_ext = F (just total flux), missing the velocity-space overlap effect
5. **Wrong proper units**: proper must be in [n][t]⁻¹ (photons per unit time), NOT erg/s
6. **Wrong excitation rate formula**: Γ = F_ext × σ₀ (NOT F_ext / n_l or F_ext / n_total)
7. **Missing fields**: b_sca and velocity vectors must be provided to Kratos via the field binary file; mfp_i_abs_0 is user-provided, not auto-derived from cross_section
8. **Applying F_ext to all levels**: excitation flux maps to ONE transition — only update the (lower↔upper) pair's population, not all levels
9. **Forgetting to undo FP32 proper scaling**: Kratos fluxes inherit the proper weight scaling factor; reader MUST multiply flx and excitation_flux by the `scale_factor` returned by `write_photon_data()` after readback (handled by `iterate()` and `run_pipeline()`)
 10. **Photon velocity code→CGS conversion**: escaped photon velocities are in code units and must be converted to CGS (× `unit_l0/unit_t0`) for plots and diagnostics
 11. **Treating escaped-photon `proper` as a path length**: Kratos writes the photon weight (`proper`) under the binary key `_l`; the reader must NOT multiply it by `unit_l0`. Escaped weights are divided by `scale_factor` only, and exposed as `'proper'` (with `'l'` as a deprecated alias)
 12. **Boundary kinds with 3 faces**: Kratos expects 6 boundary kinds (−x,+x,−y,+y,−z,+z). Specifying only 3 leaves the remaining faces undefined, defaulting to periodic and causing photon wrap-around artifacts
 13. **Periodic boundary corner bug**: the framework's `geo_loc_t::fix` can produce zero-width cells when photons cross periodic boundaries in two dimensions simultaneously; fixed by adding a convergence loop and cell-index updates in `particle_base.h`
  14. **Imaging: emiss field units (emission seed)**: `emiss` must be in the SAME scaled-proper units as the scattering s_cam. Photon propers in the binary are already multiplied by `proper_scale`, so the `emiss` field must also be multiplied by `proper_scale` on write (`core/iterator.py`) — NOT divided. The old `/ proper_scale` double-rescaling overflowed FP32 (emiss ~1e52 → `inf` → NaN/inf imaging cube → spurious corner peak). Both parts are then divided by `scale_factor` on readback. When `proper_scale=None` (default), the auto-computed scale (see §11.2) prevents this overflow automatically.
 15. **Imaging: v_chan must be CGS→code converted**: the channel grid is written to the par file in code units (`× unit_t0/unit_l0`). Writing CGS cm/s leaves `dv_cam/b` ~1e14 → profile exactly 0 → zero image.
 16. **Imaging: s_cam zeroing when disabled**: non-imaging runs must NOT initialise/allocate s_cam. The allocation is gated on `rad.imaging && rad.n_chan>0` in `block_data_t::setup()`; `pre_proc` zeroing is gated on `rad.imaging`. When imaging is disabled, `rad_img_t` skips `save()` (else it segfaults on the uninitialised pool).
  17. **Imaging: emission seed must survive MC zeroing**: the scattering integrator's `pre_proc` zeroes `s_cam` each step; the emission seed is applied in `init_rad_fields_kernel` and must be preserved across MC steps — the scattering `intg_t` sets `zero_s_cam=false` when imaging is enabled.
 18. **Imaging: duplicate intg_t kernels**: both `radiation_t` and `rad_img_t` enroll `intg_t`; the framework warns 'Duplicate entry kernels'. Harmless (runtime uses the first registered). The imaging integrator sets `build_tables=false` to avoid re-building the USampler/Voigt tables into const memory (pool overflow).
 19. **Imaging: pool init ordering**: `pol_img_t::init` runs before `intg_t::init` in the module init sequence, so it cannot read `n_chan` from the integrator — it reads it directly from the par (`args.get('imaging','n_chan',0)`).
 20. **Emission photons must be photon-number, not energy**: `compute_emissivity()` returns `n_u·A_ul/(4π)` [photons cm⁻³ s⁻¹ sr⁻¹], NOT `n_u·A_ul·h·ν/(4π)` [erg]. The pipeline works entirely in photon-number units; including the `h·ν` factor makes emission photon weights ~10⁵⁶× too small and inconsistent with external sources.
 21. **Emission photons must be frozen across cycles (anti-double-counting)**: emission photons are generated ONCE from the cycle-0 populations and re-used every cycle. Only `mfp_i_sca_0` (from n_lower) is updated. Regenerating emission from radiation-inflated n_u would double-count the radiative excitation already carried by scattered photons.
 22. **Emission photon vel must include bulk Doppler shift**: `vel = thermal_draw − v_bulk·dir` (not just `thermal_draw`), so that `dv = vel + vel_obs` recovers the thermal draw in the gas rest frame.
 23. **LAMDA embedded files are stripped**: the embedded species files in `molecular/embedded/` have NO collision partners (stripped for size). `fetch_species()` prefers the downloaded full LAMDA file (cache -> download -> embedded fallback).
 24. **LAMDA collision rates array shape**: after parsing, `collision_partners[i]['rates']` has shape `(n_trans, n_temps)` - rate-only columns (trans#/upper/lower are stripped). The `trans_indices` array holds the 0-based `[upper, lower]` pairs separately.
 25. **Collisional destruction opacity**: when colliders are configured, `mfp_i_abs_0` must include the line destruction term `n_lower·σ₀·ε` where `ε = C_ul·n_coll/(A_ul+C_ul·n_coll)`. Without it, subthermally excited lines are treated as pure scattering (no thermalisation).
  26. **Imaging: s_cam normalization** (RESOLVED): the earlier CRD-like approximation used the normalised profile `φ_norm = exp(−u²)/(√π·b)` in the scattering accumulation, while the emissivity seed used the unnormalised profile (peak=1). This has been replaced by the full **R_IIA kernel** `R(x_out; x_in, g)` (precomputed 3-D table, Convention B: gas-frame `x_in` with `(g−1)` center), which correctly captures the angle–frequency correlation and is normalised in the dimensionless variable (`∫R dx = 1`). Both the emission seed and scattering accumulation now produce the same source function `S = j/α` for a two-level atom in LTE. The `1/b_sca` factor (replacing the old `1/(√π·b_sca)`) converts from dimensionless `x` to velocity-space density.
  27. **Imaging: voigt_H Lorentzian fallback** (RESOLVED): when the imaging integrator has `build_tables=false` (to avoid const-memory pool overflow), `voigt_H` falls back to a Gaussian-core + Lorentzian-wing blend `H = max(exp(−u²), a/(√π·(u²+a²)))`. The earlier pure-Gaussian fallback vanished for `u > 5`, making the imaging opacity zero at wing channels and producing a zero image. The Lorentzian wing is essential for the broad double-peaked imaging spectrum.
  28. **Imaging: channel grid bin centres** (RESOLVED): the channel grid now uses bin centres `v_chan[k] = v_min + (k+0.5)·dv` (not linspace endpoints `v_min + k·(v_max−v_min)/(n_chan−1)`). The endpoint convention caused a half-bin shift and edge aliasing when comparing to the test's bin-centre convention.
  29. **Imaging: s_cam corr clamping** (RESOLVED): the escape-probability correction `(1−e^−dτ_e)/dτ_e` was clamped by `dτ_e = max(dτ_e, 1)`, suppressing s_cam by 37% for thin cells (dτ_e ≪ 1). Fixed to `max(dτ_e, 1e-10f)` (only prevents division by zero).

---

## Appendix B: Kratos Implementation Details

### B.1 Overlap Integral and Flux Accumulation

The overlap integral I is computed in `photon.h:proc_phys` using code-unit quantities:

```cpp
const auto dv  = vel + vel_obs;              // Δv + v_ph·d̂ (gas-frame offset)
const auto b   = *prx.rad.b_sca.at(i);      // Doppler b (code units)
const auto s2  = b * b + 2.f * sv * sv;     // 2(σ_th² + σ_ph²)
const auto I   = expf(-dv*dv / s2) * b / sqrtf(s2);
```

The total flux `flx` and excitation flux `excitation_flux` are accumulated together:

```cpp
const auto flx = proper * dsi;               // δF = ℒ × δl / V
atomicAdd(prx.rad.flx.at(i), flx);
atomicAdd(prx.rad.excitation_flux.at(i), flx * I);  // δF_ext = I × δF
```

All values are in Kratos code units — Python converts CGS↔code at the I/O boundary.

### B.2 Scattering

At scattering (`photon.h:proc_geo`), for `ph_mode=0` (CFR):

```cpp
vel = -(dir[0]*v_cc[0] + dir[1]*v_cc[1] + dir[2]*v_cc[2]);  // Δv = −v_bulk·d̂
sv  = b / sqrtf(2.f);                                          // σ_ph = σ_th
```

The combined velocity offset in the gas frame is: Δv_gas = (−v·d̂) + (v·d̂) = 0 — the photon is at line center.

For `ph_mode=1/2/3` (R_IIA), the frequency is instead sampled from
the USampler table (`intg.h:sample_upar`), which draws `u` from
`P(u|x) ∝ exp(−u²)/(a²+(x−u)²)`; `vel = u·b_sca` and the scattering
direction is correlated with the incoming direction
(`g = dir_old·dir`). ph_mode=3 uses the approximate `voigt_H` blend
for the opacity profile; ph_modes 1/2 use the tabulated Voigt.

### B.3 Absorption

Absorption is wavelength-independent (`const_abs=1`), using only the user-provided `mfp_i_abs_0`:

```cpp
const auto mfp_i_a = mfp_i_a_0_cgs * itg.unit.l0;  // in code units
const auto tau_abs = dsi * mfp_i_a;
proper *= expf(-tau_abs);
```

### B.4 Photon Binary Format

Photon binary uses 7, 8, or 9 columns per packet:
```
x[3] | dir[3] | proper | [vel] | [sv]
```
- Column 7 (`vel`) = bulk velocity offset (code units). Optional; default 0.
- Column 8 (`sv`) = Gaussian σ of the photon's frequency distribution (code units). `b = σ·√2`. After first scatter, reset to thermal σ = `b_sca / √2`. Optional; default 0 (monochromatic at line centre).

`write_photon_data()` accepts 7, 8, or 9 columns. Kratos `gen.h` reads `ncol_ph` and uses columns 7/8 only when present.

### B.5 Ray Output Binary Format

When `ray_output=1` is set in the `[line_rt]` section of the par file, Kratos writes two additional per-cell fields to the standard output binary (same `.bin` file as the block/grid data):

```
block_N|rad_ray_flx_field      — float32[n_cell]  per-cell flux F        (code units)
block_N|rad_ray_exc_flux_field — float32[n_cell]  per-cell excitation flux F_ext (code units)
```

These are identical to `rad_flx_field` and `rad_excitation_flux_field` — written at the same time, containing the same accumulated per-cycle values. The ray fields serve as a parallel, independently-verifiable copy for diagnostic purposes.

**Python readback:** `kratos_io.read_output()` returns these as `result['ray_flx']` and `result['ray_exc_flux']` (1D float64 arrays, n_tot elements in (nz, ny, nx) order — identical layout to the standard `flx` and `excitation_flux` keys).

**Use case:** Enable end-to-end verification of the flux accumulation physics by comparing the standard and ray output fields.

**Note:** The `ray_id` parameter is read from the par file but not currently used in the output logic - all cells are always written when `ray_output=1`.
