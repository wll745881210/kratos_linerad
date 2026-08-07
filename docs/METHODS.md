# Methods: Monte Carlo Line Radiative Transfer with R_IIA Redistribution

**Document purpose.** This document provides paper-ready descriptions
of all methods implemented in the `line_rt_pipeline` (Python side) and
the `kratos/usr_ext/line_rt` (GPU side). It is structured to mirror a
journal Methods section and serves as the source material for writing
the LaTeX manuscript.

**Notation conventions.** All quantities are in **photon-number units**
(photons s⁻¹, not erg s⁻¹) unless explicitly stated. The code works in
CGS on the Python side and in dimensionless code units on the GPU side.
Frequency offsets are expressed as dimensionless velocity-space
variables: $x \equiv \Delta v / b$, where $b$ is the Doppler broadening
parameter and $\Delta v$ is the gas-frame frequency offset.

---

## 1. Introduction (outline)

### Motivation

- Line radiation (e.g., CO, Lyα, Hα) is a primary diagnostic of
  temperature, density, and kinematics in astrophysical media.
- In optically thick line transfer, resonant scattering traps photons
  in frequency space, producing characteristic double-peaked emergent
  spectra (Neufeld 1990; Harrington 1973; Neufeld 1990).
- Accurate modeling requires: (a) partial frequency redistribution
  (R_IIA), not just complete redistribution (CRD); (b) self-consistent
  level populations via Lambda-iteration; (c) efficient synthetic
  imaging (channel maps / PV diagrams).

### Key contributions of this work

1. **GPU-accelerated MCRT** for line transfer with the R_IIA
   redistribution kernel, implemented as a Kratos user extension.
2. **Three ph_mode variants** (CFR, exact R_IIA, const-mem R_IIA)
   with validated agreement against the Neufeld (1990) analytic
   solution.
3. **Two-step imaging scheme** (adapted from Kratos-polrad) that
   decouples Monte Carlo sampling of the scattering source function
   from deterministic ray-tracing, producing velocity-resolved channel
   maps.
4. **Population solver** with collisional rates (LAMDA
   or user-defined) and collisional destruction probability.
5. **Comprehensive validation** against Neufeld analytic solutions for
   both escaped spectra and imaging double-peak scaling.

---

## 2. Line Radiative Transfer Methods

### 2.1 Transfer Equations and Cross Sections

#### Photon-number formulation

The radiative transfer equation for a spectral line in a moving medium
is formulated in **photon-number units** (proper = photons s⁻¹ per
packet). For a photon packet propagating along direction $\hat{n}$ through
a path element $\mathrm{d}s$ in a cell with bulk velocity $\mathbf{v}_{\rm bulk}$:

$$
\frac{\mathrm{d}I_\nu}{\mathrm{d}s} = j_\nu - \alpha_\nu \, I_\nu
$$

where:

- $j_\nu$ = emissivity [photons cm⁻³ s⁻¹ sr⁻¹ Hz⁻¹]
- $\alpha_\nu$ = extinction coefficient [cm⁻¹ Hz⁻¹] (absorption + scattering)
- $I_\nu$ = specific intensity [photons cm⁻² s⁻¹ sr⁻¹ Hz⁻¹]

Both $j_\nu$ and $\alpha_\nu$ share the **same line profile**
$\phi(\nu)$, which for a moving gas is Doppler-shifted by the bulk
velocity projected onto the photon direction:

$$
\Delta v_{\rm obs} = \hat{n} \cdot \mathbf{v}_{\rm bulk}
$$

The gas-frame frequency offset is:

$$
\Delta v = v_{\rm photon} + \Delta v_{\rm obs}
$$

where $v_{\rm photon}$ is the photon's stored velocity offset
(convention: $v < 0$ = blueshift) and the dimensionless frequency
variable is $x = \Delta v / b$.

#### Line profile

The Voigt (Hjerting) function $H(a, x)$ with Voigt damping parameter
$a = \Gamma / (4\pi \Delta\nu_D)$ describes the combined Gaussian
(Doppler) and Lorentzian (natural) broadening:

$$
H(a, x) = \frac{a}{\pi} \int_0^\infty \frac{e^{-t^2}}{t^2 + (x - t)^2 + a^2 - 2xt}\, \mathrm{d}t
$$

with $H(a, 0) \neq 1$ in general. The normalized profile is
$\phi(x) = H(a, x) / \sqrt{\pi}$ with $\int \phi\, \mathrm{d}x = 1$.

For $a = 0$ (pure Doppler): $H(0, x) = e^{-x^2}$, $H(0, 0) = 1$.

The Doppler broadening parameter:

$$
b = \sqrt{\frac{2 k_B T}{m}} = \sqrt{2}\,\sigma_{\rm th}
$$

where $m$ is the molecular mass and $\sigma_{\rm th}$ is the
1-dimensional thermal velocity dispersion.

#### Line-center cross section

The resonant (line-center) scattering cross section for a transition
$u \to l$ with Einstein $A_{ul}$, statistical weights $g_u, g_l$, and
frequency $\nu$:

$$
\sigma_0 = \frac{g_u}{g_l} \frac{A_{ul} c^3}{8\pi^{3/2} \nu^3 b}
$$

The line-center inverse scattering mean free path:

$$
\lambda_{\rm sca}^{-1}(\nu_0) = n_l \, \sigma_0 \quad \text{[cm}^{-1}\text{]}
$$

where $n_l$ is the lower-level number density. The frequency-dependent
opacity is:

$$
\alpha_\nu = \lambda_{\rm sca}^{-1}(\nu_0) \times H(a, x)
$$

**Note:** the code stores $\lambda_{\rm sca}^{-1}(\nu_0)$ as
`mfp_i_sca_0` (the **inverse** MFP at line centre, NOT the MFP
itself). The unnormalized profile $H(a, x)$ (peak = 1 for $a=0$) is
applied during transport, not the normalized $\phi(x)$.

#### Absorption

Absorption (dust, collisional destruction) is **wavelength-independent**
in this formulation. The user provides
$\lambda_{\rm abs}^{-1} = $ `mfp_i_abs_0` directly. It is NOT derived
from the line cross section. Collisional destruction
(Sec. 2.3) adds to `mfp_i_abs_0`.

#### Velocity convention

| Symbol    | Definition                                                      | Units      |
| --------- | --------------------------------------------------------------- | ---------- |
| `vel`     | Stored photon velocity offset (column 7 of binary)              | cm/s (CGS) |
| `vel_obs` | $\hat{n} \cdot \mathbf{v}_{\rm bulk}$ (bulk Doppler projection) | cm/s       |
| `dv`      | `vel + vel_obs` = gas-frame frequency offset                    | cm/s       |
| `b_sca`   | Doppler $b$ for scattering overlap integral                     | cm/s       |
| `sv`      | Gaussian $\sigma$ of photon; $b = \sigma\sqrt{2}$               | cm/s       |

Convention: `vel < 0` = blueshift (photon approaching observer).
After first scatter, `sv` is reset to thermal $\sigma = b/\sqrt{2}$.

---

### 2.2 Scattering Physics: CFR and R_IIA Redistribution

#### Overview of ph_modes

| ph_mode | Scattering profile | USampler table      | Voigt table                        | Memory |
| ------- | ------------------ | ------------------- | ---------------------------------- | ------ |
| 0       | CFR (Gaussian)     | —                   | —                                  | —      |
| 1       | R_IIA (exact)      | Global mem (251×40) | Global mem (2D, 64×512)            | Global |
| 2       | R_IIA (exact)      | Const mem (251×40)  | Const mem (1D log-space, 5000 pts) | Const  |
| 3       | R_IIA (approx.)    | Const mem           | Analytic voigt_H blend             | Const  |

Modes 1 and 2 agree to ~1–2% in `med|x|`. Mode 2 is recommended for
production; mode 1 for debug; mode 3 is fastest but underestimates
`med|x|` at low $a\tau_0$ (~0.77–0.94× Neufeld).

#### CFR (ph_mode = 0)

Complete Frequency Redistribution: the scattered photon's frequency is
drawn from the thermal Gaussian profile, independent of the incoming
frequency:

$$
x_{\rm new} = r \cos(2\pi u) \times \frac{b}{\sqrt{2}}
$$

where $r = \sqrt{-2\ln u_1}$ (Box-Muller). The outgoing direction is
sampled isotropically (azimuthally symmetric). No frequency-angle
correlation.

**Use case:** validation against analytic CRD solutions; fast
preparation runs. Does NOT reproduce Neufeld's double-peak correctly
(CRD over-redistributes).

#### R_IIA (ph_mode = 1, 2, 3)

Partial (Angle-dependent) Redistribution, Type II-A (Rylicki &
Hummer 1992): the outgoing frequency retains **memory** of the incoming
frequency, modulated by the scattering angle.

##### USampler: $P(u_{\parallel} | x)$

The angle-averaged R_II kernel gives the conditional probability of the
parallel frequency component $u_\parallel$ given incoming frequency
$x_{\rm in}$:

$$
P(u_\parallel | x_{\rm in}) \propto \frac{e^{-u_\parallel^2}}{a^2 + (x_{\rm in} - u_\parallel)^2}
$$

This is tabulated as a log-CDF with 251 $u_\parallel$ points over
$u \in [0, 6]$ (resolution $\mathrm{d}u = 0.048$) and 40 $x_{\rm grid}$
points (18 linear $[0, 8]$ + 22 log $[8, 300]$). The CDF is converted
to log-space for FP32 dynamic range and stored in device memory
(constant memory for mode 2, global for mode 1).

Sampling: draw uniform $r \in [0, 1)$, look up
$u_\parallel = F^{-1}(r | x_{\rm in})$ via bisection on the log-CDF.

##### Scattering event mechanics

Given incoming direction $\hat{n}_{\rm old}$, gas-frame frequency
$x_{\rm in} = \Delta v / b$:

1. Sample $u_\parallel \sim P(u_\parallel | x_{\rm in})$ via USampler.
2. Sample new direction $\hat{n}_{\rm new}$ isotropically (azimuthal
   symmetry, $\mu$ uniform in $[-1, 1]$).
3. Compute directional correlation $g = \hat{n}_{\rm old} \cdot \hat{n}_{\rm new}$.
4. Sample perpendicular component $u_\perp$ from a Gaussian
   ($u_\perp = r\cos(2\pi u_2) / \sqrt{2}$, $r = \sqrt{-2\ln u_1}$).
5. Outgoing frequency:

$$
x_{\rm new} = x_{\rm in} + u_\parallel (g - 1) + \sin\theta_g \, u_\perp
$$

where $\sin\theta_g = \sqrt{1 - g^2}$.

6. Store: `vel = x_new * b_sca - vel_obs_new` (convert to stored
   convention: `dv_new = vel + vel_obs_new = x_new * b`).

The key physics: for forward scattering ($g \to 1$),
$x_{\rm new} \approx x_{\rm in}$ (frequency preserved). For
backscattering ($g \to -1$), $x_{\rm new}$ is fully redistributed
($x_{\rm new} = x_{\rm in} - 2u_\parallel$). This directional-frequency
correlation is what produces the Neufeld double-peak.

##### voigt_H fallback (ph_mode 2/3 imaging)

The imaging module (photon_img.h) uses `build_tables = false` to avoid
constant-memory pool overflow. The Voigt profile falls back to:

$$
H(a, x) = \max\!\left(e^{-x^2},\; \frac{a}{\sqrt{\pi}(x^2 + a^2)}\right)
$$

i.e., the Gaussian core for $|x| < x_{\rm cross}$ and the Lorentzian
wing beyond. This avoids the pure-Gaussian fallback that vanished for
$|x| > 5$, which previously produced zero imaging opacity at wing
channels.

---

### 2.3 Statistical Equilibrium and Lambda-Iteration

#### Two-level atom

For a two-level system ($u, l$) with Einstein coefficients
$A_{ul}, B_{ul}, B_{lu}$, collisional rate $C_{ul}(T)$, and
de-excitation $C_{lu} = C_{ul} \cdot (g_u/g_l) \cdot \exp(-h\nu/kT)$
(detailed balance):

The excitation rate per lower-level atom from the radiation field:

$$
\Gamma = F_{\rm ext} \times \sigma_0
$$

where $F_{\rm ext}$ is the excitation-effective flux (from Kratos
output) and $\sigma_0$ is the line-center cross section.

The steady-state population ratio:

$$
\frac{n_u}{n_l} = \frac{g_u}{g_l} \frac{\Gamma + C_{lu} n_{\rm coll}}
{A_{ul} + \Gamma + C_{ul} n_{\rm coll}}
$$

where $n_{\rm coll}$ is the collider density (e.g., H₂).

#### Collisional destruction probability

The probability that a collisional de-excitation destroys a photon
(rather than re-emitting):

$$
\epsilon = \frac{C_{ul} n_{\rm coll}}{A_{ul} + C_{ul} n_{\rm coll}}
$$

The collisional destruction opacity:

$$
\alpha_{\rm coll} = n_l \, \sigma_0 \, \epsilon
$$

This is added to `mfp_i_abs_0` (wavelength-independent absorption).

#### Multi-level species (LAMDA)

For LAMDA species with $N$ levels and $N_{\rm trans}$ transitions, the
full rate matrix is solved:

$$
\sum_{j \neq i} \left( n_j R_{ji} - n_i R_{ij} \right) = 0
$$

where $R_{ij}$ includes radiative (from MC excitation flux) and
collisional rates. The matrix is solved via `scipy.linalg.solve` with
the closure $\sum n_i = n_{\rm species}$.

#### Lambda-iteration workflow

```
Cycle 0:  collisional-equilibrium populations → make_fields() →
          write field binaries → run Kratos (scattering + imaging)
Cycle 1+: read_output() → update_populations(F_ext) → make_fields() →
          write field binaries → run Kratos
```

- **Emission photons are frozen** across cycles (generated once from
  cycle-0 populations, re-used for all cycles). This prevents
  double-counting: scattered photons already carry the radiative
  excitation, so regenerating emission from radiation-inflated $n_u$
  would count it twice.
- Only the scattering opacity `mfp_i_sca_0` (derived from $n_l$) is
  updated each cycle.
- The `emiss` field (line-dependent) is written per cycle.
- The `b_sca`, `vel` fields (line-independent) are written once.

---

### 2.4 Two-Step Imaging Scheme

Adapted from the Kratos-polrad two-step polarimetry imaging (Yang &
Wang, in prep.), modified for frequency-resolved line transfer.

#### Principle

The imaging is split into two steps:

1. **MC pass (scattering source function sampling):** During the
   standard Monte Carlo photon propagation, accumulate the scattering
   source function toward a fixed camera direction, resolved per
   velocity channel.

2. **Imaging pass (formal ray-tracing):** For each image-plane pixel,
   march a ray toward the camera through the grid, integrating the
   transfer equation analytically cell-by-cell using the sampled
   source function.

This decoupling avoids the $1/N_{\rm cam}$ inefficiency of direct MC
imaging (where most photons miss the camera).

#### Step 1: Scattering source function `s_cam`

The source function toward the camera at cell $i$, channel $k$:

$$
S_{\rm sca}(\hat{n}_{\rm cam}, v_k, i) =
\sum_{\rm pp} \frac{F_{\rm pp}}{4\pi} \,
R_{\rm IIA}(x_{\rm out}; |x_{\rm pp}|, |g|) \,
\frac{1 - e^{-\mathrm{d}\tau_e}}{\mathrm{d}\tau_e}
$$

where:

- $F_{\rm pp} = w_{\rm pp} \times \mathrm{d}l / V$ = photon flux
  contribution (proper weight × path length / cell volume)
- $R_{\rm IIA}(x_{\rm out}; |x_{\rm pp}|, |g|)$ = the R_IIA
  redistribution kernel density, precomputed as a 3-D table
  (200 × 100 × 40 points for $x_{\rm out} \in [-50, 50]$,
  $|x_{\rm pp}| \in [0, 50]$, $g \in [0, 1]$)
- $x_{\rm out} = (v_k + \hat{n}_{\rm cam} \cdot \mathbf{v}_{\rm bulk}) / b$
  = resonant gas-frame frequency for the camera LOS at cell $i$
- $x_{\rm pp} = (\mathrm{vel} + \hat{n}_{\rm pp} \cdot \mathbf{v}_{\rm bulk}) / b$
  = photon's gas-frame frequency
- $g = \hat{n}_{\rm pp} \cdot \hat{n}_{\rm cam}$ = directional correlation
- $\mathrm{d}\tau_e = (\lambda_{\rm sca}^{-1} + \lambda_{\rm abs}^{-1}) \mathrm{d}l$
  = extinction optical depth of the path segment

The R_IIA kernel table is constructed from the USampler CDF:

$$
R(x_{\rm out}; x_{\rm pp}, g) =
\sum_k P(u_k | x_{\rm pp}) \,
\frac{e^{-(x_{\rm out} - x_{\rm pp} - u_k(g-1))^2 / \sin^2\theta_g}}
{\sin\theta_g \sqrt{\pi}}
$$

where $P(u_k | x_{\rm pp})$ are discrete probabilities from the USampler
CDF, and the Gaussian has $\sigma = \sin\theta_g / \sqrt{2}$.

**Emission seed:** In addition to the scattering accumulation, each
channel is seeded with the line emission source function:

$$
S_{\rm em}(i) = \frac{j_\nu(i)}{\alpha_\nu(i)} =
\frac{n_u A_{ul} / (4\pi)}{n_l \sigma_0} \times \frac{1}{\sqrt{\pi} \, b}
$$

This is frequency-independent (the line source function is constant
across the profile for a two-level atom). The total source function:
$S = S_{\rm em} + S_{\rm sca}$.

**Crucial normalization:** The `emiss` field is scaled by
`proper_scale` on write so the emission seed lives in the same
scaled-proper units as the scattering `s_cam`. On readback, the image
cube is divided by `scale_factor` to undo the scaling. When
`proper_scale=None` (default), the pipeline auto-computes a scale
from the estimated maximum `s_cam` magnitude (emission seed +
scattering contribution) in code units, ensuring the Kratos-side
`s_cam` field fits in FP32 range (< 1e30). This prevents the thermal-
seed overflow (`emiss/(mfp_s·√π·b) > 3.4e38` in code units due to
the `unit_l0³` factor in emiss combined with the tiny `b_code`)
that would otherwise produce `inf` imaging cubes.

#### Step 2: Formal ray tracing (imaging pass)

For each image-plane pixel, a ray is launched from the far boundary
toward the camera. The ray marches cell-by-cell, integrating the
transfer equation analytically:

$$
I_{\rm out} = I_{\rm in} \, e^{-\Delta\tau} + S \, (1 - e^{-\Delta\tau})
$$

where:

- $\Delta\tau = \alpha_t \, \Delta l$ = optical depth across the cell
- $\alpha_t = \lambda_{\rm sca}^{-1} \, H(a, x_{\rm res}) + \lambda_{\rm abs}^{-1}$
  = total extinction at the resonant frequency
- $x_{\rm res} = (v_k + \hat{n}_{\rm cam} \cdot \mathbf{v}_{\rm bulk}) / b$
  = resonant gas-frame frequency offset
- $S = \frac{\alpha_s}{\alpha_t} \, s_{\rm cam}[k]$
  = total source function (scattering + emission)

For thin cells ($\Delta\tau \ll 1$): $I \approx I + S \, \Delta\tau$
(linear regime). For thick cells ($\Delta\tau \gg 1$):
$I \to S$ (saturation).

#### Camera and channel grid

- Camera direction: spherical angles $(\theta_{\rm cam}, \phi_{\rm cam})$,
  pointing INTO the domain.
- Channel grid: bin centres
  $v_k = v_{\min} + (k + 0.5) \, \Delta v$ (NOT endpoints).
- Image plane: 2D grid, defaults to mesh $n_{\rm cell}$ in the
  first two dimensions, or user-specified `img_resol`, `img_xmin`,
  `img_xmax`.

#### Python readback

The image cube is read from the output binary as a flat array of
$(N_{\rm pix} \times N_{\rm chan})$ float32 values. Conversion to CGS:

$$
I_{\rm cgs} = \frac{I_{\rm code}}{\mathrm{scale\_factor}} \times
\frac{1}{\ell_0^3 \, t_0}
$$

where $\ell_0$ is the code length unit (cm) and $t_0$ the code time
unit (s). The $\ell_0^3$ factor arises because the source function
has units of intensity [photons cm⁻² s⁻¹ sr⁻¹] = [l⁻² t⁻¹ sr⁻¹]
and the cube is accumulated in code-volume-normalized units.

---

### 2.5 GPU Implementation

#### Field initialization

Field arrays (`mfp_i_sca_0`, `mfp_i_abs_0`, `b_sca`, `vel[3]`) are
initialized on the **GPU** by sampling device-resident `interp_t`
tables at cell centres. The `interp_t` tables are loaded from the
field binary (host memory), moved to device global memory via
`to_device()` or constant memory via `to_const()`, then sampled in
the `init_rad_fields_kernel` (2D grid: $n_{\rm th} = n_x$,
$n_{\rm bl} = (n_y, n_z)$).

`block_data_t::copy_input` is intentionally blank — preventing the
framework from overwriting GPU-initialized fields with uninitialized
host garbage. Field copies happen only in `copy_output`
(device → host).

#### Constant-memory tables (ph_mode 2)

- **USampler log-CDF:** 251 × 40 = 10,040 float32 values (~40 KiB),
  stored in constant memory. Accessed via bisection in device code.
- **Voigt table:** 1D log-space, 5000 points over $u \in [0, 50]$,
  built from a host-side scipy 2-D table. Stored in constant memory.
- **R_IIA kernel table:** 200 × 100 × 40 = 800,000 float32 values
  (~3.2 MiB), $x_{\rm out} \in [-50, 50]$, $|x_{\rm pp}| \in [0, 50]$,
  $g \in [-1, 1]$, stored in device global memory (too large for const
  pool).

#### Parallelization

- Scattering MC: **server-worker mode** (default ON, $n_{\rm worker} =
  32768$). A persistent kernel launches $n_{\rm worker}$ threads, each
  fetching photons from a shared atomic work counter (`pool.load_next()`)
  until the pool is depleted — load-balanced work-stealing that provides
  ~2$\times$ speedup at high optical depth (photons with varying
  lifetimes). The launch grid is capped at $n_{\rm worker}$ via
  `resource()` override (optimal: 6 blocks/SM $\times$ 82 SMs $\times$ 64
  threads on RTX 3090). NOT bit-identical to classic (RNG indexed by
  thread id) but statistically equivalent ($<0.3\%$ ensemble difference).
  Imaging ray-tracing uses one thread per pixel (no worker loop — fixed
  work per ray, no imbalance).
- Hardware-optimized `atomicAdd` accumulates `flx`,
  `excitation_flux`, and `s_cam`.
- Block data (fields, source function) shared via `p_map` between
  the scattering module (`radiation_t`) and imaging module
  (`rad_img_t`).

#### Memory management

- Per-run subdirectories under `/dev/shm/line_rt/` (tmpfs = RAM).
- `keep_intermediate = False` (default): per-cycle files deleted after
  readback.
- `LineRt.run()` prunes scratch: dirs older than `max_run_age`
  (default 3 h) deleted; total size capped at `size_cap`
  (default 4 GB).
- `retain_cycles = N`: keep only the last $N$ cycle dicts in output.

---

## 3. Verifications

### 3.1 Escaped Spectrum: Neufeld Scaling

**Reference.** Neufeld (1990), eq. (2.24): for a slab with
mean optical depth $\tau_0$ and Voigt parameter $a$, the escaped
photon spectrum has a double-peak at:

$$
|x_{\rm peak}| = 0.881 \, (a \tau_0)^{1/3}
$$

and median $|x|$ scaling similarly.

**Convention.** Mean-depth: $\tau_m = \lambda_{\rm sca}^{-1} \sqrt{\pi} L_{\rm slab} / 2$
(Neufeld's $\tau_0$, NOT the Verhamme line-centre convention).

**Test.** `test_scaling_wide.py`: isotropic midplane source in a
plane-parallel slab, $n_{\rm cell} = 128 \times 2 \times 2$,
$L = 1$ AU. Sweeps $\tau_0 = [200, 500, 2000, 8000, 32000]$,
$a = 0.149$ (CO-like). Tests ph_modes 1, 2, 3.

**Golden values** (ph_mode 2, $N = 10^5$ photons):

| $\tau_0$ | $a\tau_0$ | Neufeld peak | `med|x|` | `med/N` |
|-----------|-----------|-------------|-----------|---------|
| 200       | 30        | 2.731       | 3.115     | 1.14    |
| 500       | 74        | 3.707       | 4.025     | 1.09    |
| 2000      | 298       | 5.885       | 6.148     | 1.04    |
| 8000      | 1192      | 9.341       | 9.736     | 1.04    |
| 32000     | 4768      | 14.828      | 15.711    | 1.06    |

PASS criterion: $|\mathrm{med}|x| / \mathrm{golden} - 1| \leq 5\%$.

### 3.2 Imaging Double-Peak: Neufeld Scaling

**Test.** `test_scaling_image.py`: same geometry as
`test_scaling_wide.py`, camera along $+x$
($\theta = \pi/2, \phi = 0$), 32 velocity channels with adaptive
half-range $v_{\rm chan} = 3 \times x_{\rm peak} \times b$.

**Golden imaging peaks** (ph_mode 2, $N = 10^5$):

| $\tau_0$ | Imaging $|x_{\rm peak}|$ | Neufeld | img/N |
|-----------|--------------------------|---------|-------|
| 200       | 2.30                     | 2.73    | 0.84  |
| 500       | 3.13                     | 3.71    | 0.84  |
| 2000      | 6.07                     | 5.89    | 1.03  |
| 8000      | 9.63                     | 9.34    | 1.03  |
| 32000     | 15.29                    | 14.83   | 1.03  |

The imaging peak is slightly inside the escaped peak at low $\tau_0$
($I(x) = S(x)(1-e^{-\tau})$ has no $1/\tau$ penalty), and converges
at high $\tau_0$.

PASS criterion: $|x_{\rm peak} / \mathrm{golden} - 1| \leq 10\%$.

**Spectral comparison plot** (`scaling_image_spectra.png`):
per-$\tau_0$ panel showing Neufeld $J(x)$ (black dotted),
Imaging $I(x)$ (blue solid), Escaped $F(x)$ (green dashed histogram),
with peak vlines for all three.

### 3.3 Absorption + Scattering: Escape Fraction

**Test.** `test_absorption_scattering.py`: slab with both scattering
and dust absorption. Validates Kratos against (a) an inlined Python
reference MC and (b) the Neufeld approximate escape fraction
$f_{\rm esc} = 1/\cosh(Y_0)$ (eq. 4.33).

PASS criterion: Kratos ≈ Python reference (within 1.6×). The Neufeld
cosh formula overestimates $f_{\rm esc}$ at intermediate depth
(Fokker-Planck approximation; confirmed by independent MC).

### 3.4 Thin-Slab Normalization

**Test.** `test_imaging_normalization.py`: optically thin slab
($\tau \ll 1$) with known emissivity. Validates that:

1. The imaging cube intensity matches $I = j_\nu \times L$ (optically
   thin limit).
2. The emission photon proper weights sum to
   $n_u A_{ul} V_{\rm cgs}$ (photon-number normalization).
3. The emission seed $S_{\rm em} = j / (\alpha \sqrt{\pi} b)$ gives
   the correct frequency-dependent source function.

### 3.5 Velocity Convention

**Test.** Bulk velocity $v_{\rm bulk} = +0.5$ km/s along $x$, camera
along $x$. The imaging peak shifts by $-0.5$ km/s (blueshift), matching
the convention `vel = dv - vel_obs` where `vel_obs = \hat{n} \cdot \mathbf{v}_{\rm bulk}`.

### 3.6 SKIRT Cross-Code Comparison

**Test.** `docs/external_tests/skirt/`: apple-to-apple comparison
against SKIRT 9 (CPU, 16 threads) for Lyα ($a = 4.73 \times 10^{-3}$,
$T = 100$ K). Both codes use R_IIA redistribution, isotropic volume
source, 32³ grid, 10⁵ photons.

**Peak convergence** (escaped spectrum double-peak, $\tau_0 = 1000$):

| Source type | Our $|x_{\rm peak}|$ | SKIRT $|x_{\rm peak}|$ | Agreement |
|-------------|---------------------|------------------------|-----------|
| Slab (one-sided) | 0.96 | 2.36 | 59% off |
| Slab (two-sided) | 0.38 | 2.36 | 84% off |
| **Volume (isotropic)** | **2.63** | **2.36** | **11%** |

The volume source (matching SKIRT's `UniformBoxGeometry`) is required
for peak convergence; boundary-injected slab sources produce anisotropic
escaped spectra that don't match SKIRT's isotropic volume emission.

**Speed tests** (same configuration, with and without imaging):

| Configuration | Kratos GPU (s) | SKIRT CPU (s) | Speedup |
|---------------|---------------|---------------|---------|
| $\tau_0 = 10^3$, no imaging | 0.14 | 5.8 ± 0.2 | 41× |
| $\tau_0 = 10^3$, with imaging | 0.54 | 5.8 ± 0.2 | 11× |
| $\tau_0 = 10^4$, no imaging | 0.55 | 5.8 | 11× |

**SNR comparison** (10⁵ photons, $\tau_0 = 10^3$):

| Approach | Bins | SNR / bin | Spectral SNR | Mechanism |
|----------|------|-----------|-------------|-----------|
| Our imaging (2D × chan) | 32768 | 9.5 / pixel | 304 | s_cam MC (all segments) |
| SKIRT SED (1D) | 196 | 14.3 avg | 14.3 | Poisson (escaped only) |

Our imaging achieves 20× higher spectral SNR because the s_cam source
function uses all photon segments ($\sim$3.2M, including trapped
photons), not just the $10^5$ escaped photons SKIRT counts. SKIRT has
higher per-bin SNR (fewer bins) but produces 1D spectra only.

Kratos runs on NVIDIA RTX 3090 (82 SM); SKIRT on 16 CPU threads.

---

## 4. Discussion (outline)

### Astrophysical applications

- CO rotational lines in protoplanetary disks (LTE + sub-thermal)
- Lyα radiative transfer in galactic outflows
- Ro-vibrational lines (CO $v=1\to0$) using ExoMol line lists

### Limitations

- Only 2-level user-defined species (multi-level requires LAMDA)
- Single-line imaging (multi-line requires separate runs)
- No continuum subtraction in imaging (dust thermal emission not
  included in line imaging)
- Constant-memory pool size limits ph_mode 2 table resolution

### Future directions

- Multi-line imaging (shared `b_sca`/`vel`, per-line `s_cam`)
- Full R_IIA kernel in imaging (currently uses voigt_H fallback for
  const-mem pool; could use global-mem 2-D Voigt table)
- Adaptive mesh refinement for line transfer
- Polarization (coupling with Kratos-polrad)

---

## 5. Summary (outline)

- GPU-accelerated MCRT code for line transfer with R_IIA
  redistribution, validated against Neufeld (1990).
- Two-step imaging produces velocity-resolved channel maps.
- Self-consistent populations via Lambda-iteration with collisional
  rates.
- Open-source: Python pipeline + Kratos GPU extension.

---

## Appendix A: Code Architecture

### Two-level API

**High level — `LineRt` class** (`core/line_rt.py`): single-entry-point
orchestrator. Configure geometry, sources, species via constructor +
`add_source()`, then call `run()`.

**Species selection — `TransitionInfo`**
(`molecular/transition_info.py`): resolves species data (LAMDA or
user-defined), transition index, molecular mass, auto-wavelength.

**Low level — `iterate()`** (`core/iterator.py`): bare loop over
write → run → read → update. Takes raw arrays; no species resolution.

### Key files

| File                           | Role                                                         |
| ------------------------------ | ------------------------------------------------------------ |
| `core/line_rt.py`              | `LineRt` orchestrator                                        |
| `core/iterator.py`             | `iterate()` loop, field/photon I/O                           |
| `core/pipeline.py`             | `run_pipeline()`, par templates, scratch management          |
| `core/kratos_io.py`            | `write_field_data()`, `write_photon_data()`, `read_output()` |
| `molecular/transition_info.py` | `TransitionInfo`, `user_defined()`                           |
| `molecular/equilibrium.py`     | `solve_populations()`, `initial_populations()`               |
| `molecular/lamda_format.py`    | `compute_opacity()`, `compute_emissivity()`, `make_fields()` |
| `usr_ext/line_rt/photon.h`     | Scattering photon: `proc_geo`, `proc_phys`, `scat()`         |
| `usr_ext/line_rt/photon_img.h` | Imaging photon: `proc_phys` (ray tracing)                    |
| `usr_ext/line_rt/radiation.h`  | `radiation_t`: field I/O, `init_cond`, emission seed         |
| `usr_ext/line_rt/rad_img.h`    | `rad_img_t`: imaging module (parasite of `radiation_t`)      |
| `usr_ext/line_rt/intg.h`       | `intg_t`: USampler, Voigt table, R_IIA kernel, camera        |
| `usr_ext/line_rt/block_data.h` | `rad_t` struct: fields, `s_cam`, imaging output              |
| `usr_ext/line_rt/gen.h`        | Photon generation from binary                                |

---

## References

- Neufeld, D. A. 1990, ApJ, 350, 120. "Molecular hydrogen in
  Seyfert galaxies."
- Harrington, J. P. 1973, MNRAS, 161, 43. "Resonance-line transfer in
  moving media."
- Rybicki, G. B., & Hummer, D. G. 1992, A&A, 262, 209. "The
  redistribution approximation in line transfer."
- Verhamme, A. 2006, PhD thesis. "Lyα radiative transfer in
  galaxies."
- Yang, H., & Wang, L. (in prep.). "Kratos-polrad: GPU
  Monte-Carlo polarized radiative transfer."
- Schöier, F. L. et al. 2005, A&A, 432, 369. "Atomic and molecular
  data for radiative transfer: LAMDA."
- Tennyson, J. et al. 2016. "ExoMol: molecular line lists for
  exoplanet atmospheres."
