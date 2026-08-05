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
from the angle-averaged redistribution kernel `P(u|x) ∝ exp(−u²) / (a² + (x−u)²)`
via an inverse-CDF table lookup (USampler), with directional
correlation `g = dir_old·dir`. All three modes share the same kernel
and table; they differ only in where the tables live and how the
Voigt opacity is evaluated:

| ph_mode | USampler table | Voigt opacity | Notes |
|---------|----------------|---------------|-------|
| 0 | — (CFR, Gaussian kick) | 2D table, global mem | σ_ph = σ_th |
| 1 | global mem (freed) | 2D table, global mem (128 KiB) | debug |
| 2 | constant mem (251×40, log-CDF) | 1D log-space table, const mem (5000 pts) | production |
| 3 | constant mem | approximate `voigt_H` blend (photon.h) | fastest; underestimates med\|x\| at low aτ₀ |

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

1. **User rescale** — every photon weight is multiplied by `proper_scale` (default 1.0 = no-op). Passed as `proper_scale=` to `iterate()`/`run_pipeline()`, `LineRt(proper_scale=...)`, or `--proper-scale` on the CLI. Because Kratos MCRT is linear in photon weights, a constant rescale leaves all fields unchanged after the read-back division — use `proper_scale < 1` when the physical flux would overflow the FP32 output fields (≥ 3.4e38) even though no single photon does.
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
**final** MC cycle. When disabled, the st_cam field is not initialised,
allocated, or written — existing (non-imaging) runs are unaffected.

### 12.2 Step 1 — Scattering source function `st_cam`

The per-cell, per-channel field `st_cam` (Kratos `rad_t.st_cam`,
`n_int = n_chan`) carries the **total source function toward the camera
direction** — the thermal emission and the scattering contribution are
folded together (populations enter only through the emission/absorption
profile weights, not as a separate `n_u·A_ul` term).

**Thermal seed** (`radiation.h:init_rad_fields_kernel`).  On GPU init
the field is seeded with the line source function from the local emissivity:

```
S_th = emiss / mfp_i_sca_0        (emiss from the field binary, code units)
```

This is frequency-independent and applied to **every channel equally**.
The per-channel selectivity comes only from the opacity profile in the
imaging pass (§12.4).  `emiss` is the **photon-number** volume emissivity
`n_u·A_ul/(4π)` [n][l]⁻³[t]⁻¹[sr]⁻¹ computed by
`molecular/lamda_format.py:compute_emissivity()` and written to the line
field file (`fields_cycleN.bin`, key `emiss_`) by `make_fields()`.

**Scattering accumulation** (`photon.h:proc_phys`).  During the MC, each
path segment in cell `i` also adds the packet's contribution to the
scattering source function toward the camera:

```
base = flx · (1 − e^−dτ_e) / dτ_e · (1/4π)         (flx = proper·dl/V)
for channel k:
    dv_cam  = v_chan[k] + dir_cam·v_bulk(i)          (gas-frame offset
                                                     toward the camera)
    prof_cam = φ(dv_cam / b_sca)                    (Gaussian or Voigt)
    st_cam[i,k] += base · prof_cam / (√π · b_sca)
```

Here `dτ_e = dl·(mfp_i_sca_0·φ_pp + mfp_i_abs_0)` is the extinction along
the segment using the packet's *own* frequency offset (φ_pp), and the
`(1−e^−dτ_e)/dτ_e` factor is the escape-probability-per-unit-length that
weights the segment by the chance the packet scatters within the cell.
This implements the CRD-like approximation of the R_IIA kernel toward
the fixed camera direction (only the emission-profile factor `φ(dv_cam)`
is angle-selective; the full angle–frequency correlation of R_IIA is not
reproduced).  The `√π·b_sca` normalisation makes `∫φ dv = √π·b`, matching
the Hjerting convention used elsewhere in the code.

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
the channel grid uses **cell edges**, `v_chan[k] = v_min + k·dv` with
`dv = (v_max − v_min)/(n_chan − 1)`.  Python converts CGS→code
(`× unit_t0/unit_l0`) before writing the par file.

### 12.4 Step 2 — Non-scattering ray tracing (imaging pass)

A second module (`rad_img_t` + `photon_img.h:line_img_t`, enrolled as a
parasite of `radiation_t` in `usr.cpp`) integrates the transfer equation
along each camera ray, cell by cell, with the **analytic** solution of
`dI/dτ = −I + S` per cell (`S` assumed constant over the cell):

```
per channel k, per path segment:
    dv_cam  = v_chan[k] + dir_cam·v_bulk(i)
    prof    = φ(dv_cam / b_sca)                       (Gaussian or Voigt)
    α_s     = mfp_i_sca_0 · prof                      (line opacity)
    α_t     = α_s + mfp_i_abs_0                       (total extinction)
    dτ      = α_t · dl_seg
    e^−dτ   = exp(−dτ)
    S       = (α_s / α_t) · st_cam[i,k]               (source fn toward camera)
    I[k]    = I[k]·e^−dτ + S·(1 − e^−dτ)              (analytic cell update)
```

The imaging photon has `n_scat = 1` (never scatters); `proc_geo` is the
pure geometric move.  Rays start at the far box boundary along `−dir_cam`
(`x = x0 − dl_min·dir·0.9999`) and march through the domain to the camera
plane.  Output (binary keys `_dir_img`, `_x_img`, `_i2d_img`, `_l_img`)
is read back by `kratos_io.read_output()` into `result['image']`.

**Units**: the imaging output inherits the scaled-proper convention.
Both the scattering part (accumulated from the scaled photon propers) and
the thermal seed must live in the same scaled units, so the `emiss` field
is rescaled by `proper_scale` on write (`core/iterator.py`) and the cube
is divided by `scale_factor` on readback, then converted to CGS
intensity (`÷ unit_l0²·unit_t0`).  The cube in the results dict is
`image['cube']` in **photon-number** surface brightness
[photons cm⁻² s⁻¹ sr⁻¹].

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
        'H2': { 'rate': 3e-12 },           # float [cm^3 s^-1] or callable f(T)
    },
)

#  Number density (spatial field) in LineRt:
rt = LineRt(
    transition_info = ti,
    colliders = { 'H2': { 'density': 1e6 } },   # float [cm^-3] or callable f(X,Y,Z)
    ...,
)
```

- **`rate`** (in `user_defined`): a number (constant) or a callable
  `f(T) -> float` giving the de-excitation rate coefficient at
  temperature T [K].  Callables are sampled on a 13-point grid (10-5000 K)
  and linearly interpolated at runtime.
- **`density`** (in `LineRt`): collider number density [cm⁻³], as a float
  or a callable `f(X, Y, Z)` over the 3D mesh (same interface as
  `n_species`).

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
 14. **Imaging: emiss field units (thermal seed)**: `emiss` must be in the SAME scaled-proper units as the scattering st_cam. Photon propers in the binary are already multiplied by `proper_scale`, so the `emiss` field must also be multiplied by `proper_scale` on write (`core/iterator.py`) — NOT divided. The old `/ proper_scale` double-rescaling overflowed FP32 (emiss ~1e52 → `inf` → NaN/inf imaging cube → spurious corner peak). Both parts are then divided by `scale_factor` on readback.
 15. **Imaging: v_chan must be CGS→code converted**: the channel grid is written to the par file in code units (`× unit_t0/unit_l0`). Writing CGS cm/s leaves `dv_cam/b` ~1e14 → profile exactly 0 → zero image.
 16. **Imaging: st_cam zeroing when disabled**: non-imaging runs must NOT initialise/allocate st_cam. The allocation is gated on `rad.imaging && rad.n_chan>0` in `block_data_t::setup()`; `pre_proc` zeroing is gated on `rad.imaging`. When imaging is disabled, `rad_img_t` skips `save()` (else it segfaults on the uninitialised pool).
 17. **Imaging: thermal seed must survive MC zeroing**: the scattering integrator's `pre_proc` zeroes `st_cam` each step; the thermal seed is applied in `init_rad_fields_kernel` and must be preserved across MC steps — the scattering `intg_t` sets `zero_st_cam=false` when imaging is enabled.
 18. **Imaging: duplicate intg_t kernels**: both `radiation_t` and `rad_img_t` enroll `intg_t`; the framework warns 'Duplicate entry kernels'. Harmless (runtime uses the first registered). The imaging integrator sets `build_tables=false` to avoid re-building the USampler/Voigt tables into const memory (pool overflow).
 19. **Imaging: pool init ordering**: `pol_img_t::init` runs before `intg_t::init` in the module init sequence, so it cannot read `n_chan` from the integrator — it reads it directly from the par (`args.get('imaging','n_chan',0)`).
 20. **Emission photons must be photon-number, not energy**: `compute_emissivity()` returns `n_u·A_ul/(4π)` [photons cm⁻³ s⁻¹ sr⁻¹], NOT `n_u·A_ul·h·ν/(4π)` [erg]. The pipeline works entirely in photon-number units; including the `h·ν` factor makes emission photon weights ~10⁵⁶× too small and inconsistent with external sources.
 21. **Emission photons must be frozen across cycles (anti-double-counting)**: emission photons are generated ONCE from LTE populations and re-used every cycle. Only `mfp_i_sca_0` (from n_lower) is updated. Regenerating emission from radiation-inflated n_u would double-count the radiative excitation already carried by scattered photons.
 22. **Emission photon vel must include bulk Doppler shift**: `vel = thermal_draw − v_bulk·dir` (not just `thermal_draw`), so that `dv = vel + vel_obs` recovers the thermal draw in the gas rest frame.
 23. **LAMDA embedded files are stripped**: the embedded species files in `molecular/embedded/` have NO collision partners (stripped for size). `fetch_species()` prefers the downloaded full LAMDA file (cache -> download -> embedded fallback).
 24. **LAMDA collision rates array shape**: after parsing, `collision_partners[i]['rates']` has shape `(n_trans, n_temps)` - rate-only columns (trans#/upper/lower are stripped). The `trans_indices` array holds the 0-based `[upper, lower]` pairs separately.
 25. **Collisional destruction opacity**: when colliders are configured, `mfp_i_abs_0` must include the line destruction term `n_lower·σ₀·ε` where `ε = C_ul·n_coll/(A_ul+C_ul·n_coll)`. Without it, subthermally excited lines are treated as pure scattering (no thermalisation).
 26. **Imaging: scattering st_cam vs thermal seed normalization mismatch** (KNOWN, pending fix): the scattering accumulation uses the NORMALIZED profile `φ_norm = exp(−u²)/(√π·b)` (with `inv_norm = 1/(√π·b)`), while the thermal seed uses the UNNORMALIZED profile (peak=1). This makes the scattering contribution ~1/(√π·b)× larger than the thermal, so in the optically-thin limit the scattering st_cam dominates and the imaging cube deviates from the analytic `I = j·φ·L`. The convention must be unified.

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
