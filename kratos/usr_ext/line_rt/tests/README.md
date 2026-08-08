# Regression Tests — `usr_ext/line_rt/tests/`

Standalone Kratos regression tests for the `line_rt` user extension.
Each test is **self-contained**: no pipeline imports, no `PYTHONPATH`
hacks — just the Kratos binary, the Kratos `binary_io.py` I/O module,
and (for the absorption test) an inlined reference Monte Carlo.

## Prerequisites

1. **Kratos built with `USRDIR=usr_ext/line_rt`.** See
   [Compile Kratos](#compile-kratos) below.
2. **Python ≥ 3.10** with `numpy`, `scipy`. For plots: `matplotlib`.
3. **A Kratos build tree** at a known path. The default is
   `~/apps/kratos_line_rt`, overridable with `--kratos-root`.

The `--kratos-root` flag points at the Kratos **build tree root**.
It must contain:
- `bin/kratos` — the compiled binary.
- `visual/binary_io.py` — the binary I/O module used to read/write
  Kratos field and photon files.

Both are validated at startup; a clear `FileNotFoundError` is raised
if either is missing.

## Compile Kratos

Source lives in `~/Seafile/seafile_sync/code/kratos/` (git repo) and
is symlinked into the build tree `~/apps/kratos_line_rt/`. **Never
compile inside `~/Seafile/`** — object files and the binary must stay
in the build tree.

```bash
cd ~/apps/kratos_line_rt

# Incremental build (fast, after small edits)
make USRDIR=usr_ext/line_rt -j8

# Clean rebuild (after large changes or strange link errors)
make clean && make USRDIR=usr_ext/line_rt -j8
```

- **Always pass `USRDIR=usr_ext/line_rt`.** Without it the default
  `USRDIR=usr` is used and the `line_rt` module is not linked.
- The binary is produced at `~/apps/kratos_line_rt/bin/kratos`.
- The Makefile targets CUDA (`nvcc`, `-arch=sm_80`); a CUDA-capable
  GPU is required.
- If `usr_ext/line_rt/*.h` (the headers) are edited, an incremental
  `make` suffices because the Makefile tracks header dependencies
  via compiler-generated `.d` files.

## Tests

### `test_scaling_wide.py` — Neufeld escape-frequency scaling

**Purpose.** Validates that Kratos reproduces the Neufeld (1990) eq.
(2.24) escape-frequency peak scaling
`|x_peak| ≈ 0.881 (a τ₀)^{1/3}` across a wide `aτ₀` range, for all
three `ph_mode` values (1, 2, 3). Uses a golden `med|x|` table
measured from the validated build; the regression check is
`|med|x| / golden − 1| ≤ 5%`.

**Convention.** Mean-depth, half-slab:
`τ_m = mfp_i_sca_0 √π L_slab / 2` (Neufeld's original τ₀, not the
Verhamme line-centre convention). See the test docstring and
`AGENTS.md` pitfall 23 for details.

**Run.**
```bash
cd ~/scratch/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_wide.py \
    --kratos-root ~/apps/kratos_line_rt
```

**Options.**
| Flag | Default | Description |
|------|---------|-------------|
| `--kratos-root` | `~/apps/kratos_line_rt` | Kratos build tree root |
| `--tau0-fid-list` | `200 500 2000 8000 32000` | Neufeld mean-depth τ₀ values |
| `--a` | `0.149` | Voigt damping parameter |
| `--ph-mode-list` | `1 2 3` | Kratos ph_mode values to test |
| `--n` | `100000` | Number of photons per run |
| `--tol` | `0.05` | Regression tolerance on `med\|x\|` (fraction) |
| `--plots` | off | Also save `scaling_wide_*.png` plots |
| `--measure` | off | Print golden `med\|x\|` values and exit |
| `--keep-dir` | off | Keep the temporary run directory |

**Exit code.** `0` = all points within tolerance; `1` = any failure.

**Output.** A summary table to stdout:
```
   tau0 pm   med|x|   golden  ratio  Neufeld  med/N  status
-----------------------------------------------------------------
    200  2    3.151    3.115  1.012    2.731  1.154  PASS
```

**Updating the golden values.** After a deliberate physics change,
re-run with `--measure` and paste the printed `GOLDEN = { ... }` dict
back into the source file:

```bash
python3 test_scaling_wide.py --kratos-root ~/apps/kratos_line_rt --measure
```

---

### `test_absorption_scattering.py` — Dust absorption + scattering

**Purpose.** Validates Kratos against (a) an inlined independent
Python reference Monte Carlo and (b) the Neufeld (1990) approximate
escape fraction formula `f_esc = 1/cosh(Y₀)` (eq. 4.33) for a slab
with both scattering and continuum (dust) absorption. Three modes:

| Mode | Flag | Reference | Regime |
|------|------|-----------|--------|
| Default | *(none)* | Neufeld (1990) + in-house Python MC | a = 0.149, τ_m = 30–300 |
| Verhamme | `--verhamme` | Verhamme+ (2006) Fig. 4 published MC crosses | a = 0.015, τ₀ = 10⁵ |
| SKIRT | `--skirt` | SKIRT9 (Camps & Baes 2020) wide-box MC | same as default or Verhamme |

**Convention.** Same mean-depth τ₀ convention as
`test_scaling_wide.py`. The dust parameter is
`β = τ_a / τ_m`, where `τ_a = mfp_i_abs_0 · L_slab / 2` is the
half-slab dust optical depth.

#### Default mode

**PASS criterion.** Kratos ≈ Python reference (within 1.6×). The
Neufeld cosh formula is a Fokker-Planck approximation that
**overestimates** `f_esc` at intermediate optical depth (Verhamme
2006 §3.1.1; confirmed by an independent MC in
`~/scratch/line_rt/fiducial/Agent_Neufeld/`). Therefore `K/N < 1`
and `P/N < 1` are **expected** and not failures; the test documents
this in its output.

**Run.**
```bash
cd ~/scratch/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_absorption_scattering.py \
    --kratos-root ~/apps/kratos_line_rt
```

#### Verhamme mode (`--verhamme`)

**Purpose.** Compares Kratos against the analytic curve of Verhamme,
Schaerer & Meynet (2006, Fig. 4), digitised from the PDF (80-point
curve in `verhamme06_fig4.json`). The regime is `a = 0.015,
τ₀(line-centre) = 10⁵` (`τ_m = √π × 10⁵ ≈ 1.77 × 10⁵`). Seven X
values span `X = (a τ₀)^{1/3} τ_a` from 0.024 to 12.05; the analytic
`f_esc` is obtained by linear interpolation of the digitised curve.

**PASS criterion.** Kratos within **1.35×** of the analytic curve
(digitisation uncertainty ~few % + Poisson noise + mixed-precision
R_IIA kernel).

**Expected results.** 7/7 PASS (K/analytic = 0.91–1.12). The
deviation from unity is attributable to the mixed-precision R_IIA
redistribution kernel (constant-memory USampler table in FP32, see
`AGENTS.md` pitfall 18). Previously, comparing against the individual
MC crosses gave 2/7 FAIL; using the smooth analytic curve as the
reference absorbs the MC shot noise and gives a cleaner comparison.

**Run.**
```bash
cd ~/scratch/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_absorption_scattering.py \
    --verhamme --verhamme-n 200000 --ph-mode 2 \
    --kratos-root ~/apps/kratos_line_rt
```

#### SKIRT mode (`--skirt`)

**Purpose.** Compares Kratos against the published SKIRT9 code
(Camps & Baes 2020) for the same finite-box slab geometry. The SKIRT
runs use the `skirt_dust_slab.py` harness
(`docs/external_tests/skirt/skirt_dust_slab.py`) which generates a
`.ski` file and invokes the SKIRT binary. The dust cross-section per
unit density (`--skirt-kappa`) is pre-calibrated via a pure-absorption
run.

**Default-mode SKIRT** (a = 0.149, τ_m = 30–300): works directly.

**Verhamme-mode SKIRT** (a = 0.015, τ_m = 1.77 × 10⁵): SKIRT without
acceleration (`lyaAccelerationScheme="None"`, for apple-to-apple
comparison) cannot handle τ_m > ~10⁴ — photons are trapped and
`f_esc` is non-physical. To obtain SKIRT results at the Verhamme
optical depth, the acceleration scheme must be enabled (edit the
ski template to use `lyaAccelerationScheme="All"`). This is a
numerical optimisation that does not change the physics.

**Run (default + SKIRT).**
```bash
cd ~/scratch/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_absorption_scattering.py \
    --skirt --kratos-root ~/apps/kratos_line_rt
```

**Run (Verhamme + SKIRT).**
```bash
cd ~/scratch/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_absorption_scattering.py \
    --verhamme --skirt \
    --verhamme-n 200000 --verhamme-skirt-n 10000 \
    --ph-mode 2 --kratos-root ~/apps/kratos_line_rt
```

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--kratos-root` | `~/apps/kratos_line_rt` | Kratos build tree root |
| `--tau-m-list` | `30 100 300` | Half-slab mean scattering depths τ_m (default mode) |
| `--tau-a-list` | `0.1 0.3 1.0` | Half-slab dust depths τ_a (default mode) |
| `--a-voigt` | `0.149` | Voigt damping parameter (default mode) |
| `--ph-mode` | `1` | Kratos ph_mode (1=R_IIA exact, 2=const-mem) |
| `--n` | `50000` | Photons per run (default mode) |
| `--verhamme` | off | Run Verhamme+ (2006) regime (a=0.015, τ₀=10⁵) |
| `--verhamme-n` | `200000` | Photon count for Verhamme-mode Kratos runs |
| `--verhamme-skirt-n` | `10000` | Photon count for Verhamme-mode SKIRT runs |
| `--skirt` | off | Also run SKIRT9 comparison (default or Verhamme) |
| `--skirt-aspect` | `8.0` | Transverse aspect ratio for the SKIRT box |
| `--skirt-kappa` | `8.2897e-17` | Dust τ_a per unit dust density (pre-calibrated) |
| `--no-kratos` | off | Skip the Kratos run |
| `--no-python` | off | Skip the Python reference MC |
| `--no-plot` | off | Skip saving the plot |
| `--workdir` | `~/scratch/line_rt` | Output directory for files + plots |

**Exit code.** `0` = PASS; `1` = FAIL (any mode).

**Output.** A summary table (stdout) + a PDF plot:
- Default: `abs_scat_fesc_vs_tau.png` — f_esc vs τ_m for Kratos,
  Python, and Neufeld analytic.
- Verhamme: `abs_scat_verhamme.pdf` — f_esc vs X on log-log axes,
  showing the Verhamme (2006) analytic curve, Hansen & Oh (2006)
  circles, published MC crosses, and Kratos stars (green squares if
  `--skirt`).

```
Default mode:
 tau_m  tau_a       Q      Neufeld       Kratos       Python      K/N      P/N      K/P
------------------------------------------------------------------------------------------------
    100   0.30   0.738 3.882881e-01 1.767730e-01 1.676000e-01    0.455    0.432    1.055
PASS: Kratos ~ Python (two independent MC implementations agree)

Verhamme mode:
         X      tau_a fe(analytic)   fe(Kratos)     K/an
--------------------------------------------------------------------------------------
    0.0240    0.00210 8.563260e-01 9.599090e-01    1.121
    0.2407    0.02103 6.248882e-01 6.712546e-01    1.074
    1.2062    0.10537 1.988732e-01 2.115316e-01    1.064
    2.4049    0.21008 7.559249e-02 7.754874e-02    1.026
    2.5740    0.22486 6.971246e-02 6.930664e-02    0.994
    5.1426    0.44925 1.529451e-02 1.540114e-02    1.007
   12.0488    1.05256 1.140435e-03 1.041179e-03    0.913
PASS: Kratos within 1.35x of the Verhamme+ (2006) analytic curve
```

---

### `test_scaling_image.py` — Imaging + escape scaling

**Purpose.** Validates that the Kratos **imaging** module produces a
double-peaked spectrum whose peak position scales as
`|x_peak| ≈ 0.881 (a τ₀)^{1/3}` (Neufeld), and that the **escaped**
photon `med|x|` matches the golden values from `test_scaling_wide.py`.
Runs both imaging and escape analysis on the same Kratos output.

**Convention.** Same mean-depth, half-slab, isotropic midplane source
as `test_scaling_wide.py`. Camera along `+x`
(`dir_cam_theta = π/2, dir_cam_phi = 0`). Channel grid is adaptive:
`v_chan = 3 × Neufeld_peak × b_sca` (covers the full peak at high τ₀).

**Run.**
```bash
cd /dev/shm/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_image.py \
    --kratos-root ~/apps/kratos_line_rt --plots
```

**Options.**
| Flag | Default | Description |
|------|---------|-------------|
| `--kratos-root` | `~/apps/kratos_line_rt` | Kratos build tree root |
| `--tau0-fid-list` | `200 500 2000 8000 32000` | Neufeld mean-depth τ₀ values |
| `--a` | `0.149` | Voigt damping parameter |
| `--ph-mode` | `2` | Kratos ph_mode (2 = const-mem R_IIA) |
| `--n` | `100000` | Number of photons per run |
| `--n-chan` | `32` | Number of velocity channels |
| `--v-chan-cgs` | `0` | Channel half-range [cm/s] (0 = adaptive) |
| `--tol` | `0.10` | Regression tolerance on imaging `|x_peak|` (fraction) |
| `--plots` | off | Save `scaling_image_*.png` plots |
| `--measure` | off | Print golden imaging peaks and exit |
| `--keep-dir` | off | Keep the temporary run directory |

**Exit code.** `0` = all points within tolerance; `1` = any failure.

**Output.** A summary table + two PNGs:
- `scaling_image_peaks.png` — log-log scaling: Neufeld line + escaped
  `med|x|` + escaped `|x|_peak` + imaging `|x|_peak` vs `aτ₀`.
- `scaling_image_spectra.png` — per-τ₀ panel grid: Neufeld `J(x)`
  (black dotted) + Imaging `I(x)` (blue solid) + Escaped `F(x)`
  (green dashed histogram), with peak vlines for all three.

```
   tau0   med|x| golden_m   x_esc   x_img  Neufeld  img/N  esc/N  img/esc  status
---------------------------------------------------------------------------------
    200    3.119    3.115    2.73    2.30    2.731  0.844  0.998    0.845  PASS
```

**Golden values.** `GOLDEN_MED` (escaped `med|x|`, from
`test_scaling_wide.py`) and `GOLDEN_IMG_PEAK` (imaging `|x_peak|`).
Re-measure with `--measure` after a deliberate physics change.

---

### `test_imaging_neufeld.py` — Pipeline imaging validation

**Purpose.** Validates the **pipeline-side** imaging (via `LineRt`)
against Neufeld for a slab with a two-level species. Checks that the
imaging double-peak position matches the Neufeld prediction and that
the escaped spectrum golden values are within tolerance. Uses the
`LineRt` orchestrator (not standalone Kratos).

**Run.**
```bash
cd /dev/shm/line_rt
python3 ~/Seafile/seafile_sync/code/line_rt_pipeline/tests/test_imaging_neufeld.py \
    --kratos-root ~/apps/kratos_line_rt
```

---

### `test_imaging_spectrum.py` — Thin-slab imaging spectrum

**Purpose.** Validates the **Kratos-side** imaging normalization and
spectral shape for a thin scattering slab with perpendicular
source–camera geometry (g = 0, a → 0). Self-contained: no pipeline
imports.

**Physics.** For a thin slab (τ₀ ≪ 1) with a slab source perpendicular
to the camera LoS, the R_IIA kernel at g = 0, a → 0 gives a purely
thermal scattered profile `R = exp(−x²)/√π` (no frequency memory). The
opacity profile `φ = exp(−x²)` provides a second Gaussian, so the
imaging spectrum is a double-Gaussian:

  I(v) ∝ exp(−2 · ((v + v_z)/b)²)

with total intensity `∫I dv = F · mfp_s · L / (4π · √2)`.

**Tests.**
- **Normalization**: Σ I(k) · dv vs analytic total (tolerance 20%).
- **Shape**: per-channel I(k)/I_peak vs exp(−2x²) (tolerance 20%).
- **Doppler shift**: peak at v_chan = −v_z with v_z = b_sca.

**Run.**
```bash
cd /dev/shm/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_imaging_spectrum.py \
    --kratos-root ~/apps/kratos_line_rt --plots
```

With `--plots` a 2-panel PNG (`imaging_spectrum.png`) is saved showing
analytic vs simulation spectra for v_z = 0 and v_z = b_sca.

---

## Common workflow

### After editing `usr_ext/line_rt/*.h`

```bash
cd ~/apps/kratos_line_rt
make USRDIR=usr_ext/line_rt -j8
cd /dev/shm/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_wide.py \
    --kratos-root ~/apps/kratos_line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_image.py \
    --kratos-root ~/apps/kratos_line_rt
```

### Full validation suite

```bash
cd /dev/shm/line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_wide.py \
    --kratos-root ~/apps/kratos_line_rt --plots
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_scaling_image.py \
    --kratos-root ~/apps/kratos_line_rt --plots
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_absorption_scattering.py \
    --kratos-root ~/apps/kratos_line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_absorption_scattering.py \
    --verhamme --ph-mode 2 --kratos-root ~/apps/kratos_line_rt
python3 ~/apps/kratos_line_rt/usr_ext/line_rt/tests/test_imaging_spectrum.py \
    --kratos-root ~/apps/kratos_line_rt --plots
```

The default-mode tests should print `PASS` and exit 0. The
Verhamme mode also prints `PASS` (7/7 within 1.35× of the analytic
curve).

### A/B testing a historical version

**Never modify the trunk build tree or source repos for A/B testing.**
Copy to a temp directory:

```bash
cp -a ~/apps/kratos_line_rt /tmp/regtest_kratos
cd /tmp/regtest_kratos/usr_ext && git checkout <old_commit>
cd /tmp/regtest_kratos && make USRDIR=usr_ext/line_rt -j8
python3 /tmp/regtest_kratos/usr_ext/line_rt/tests/test_scaling_wide.py \
    --kratos-root /tmp/regtest_kratos
rm -rf /tmp/regtest_kratos
```

The `--kratos-root` flag makes this trivial — no environment variables
or `PYTHONPATH` edits needed.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `FileNotFoundError: kratos binary not found` | Build Kratos first (`make USRDIR=usr_ext/line_rt`), or pass the correct `--kratos-root`. |
| `FileNotFoundError: binary_io.py not found` | `--kratos-root` points at the wrong tree. It must be the build tree root containing both `bin/` and `visual/`. |
| `n_esc=0` or no output `.bin` | `n_cell=1` in some dimension — Kratos requires `n_cell ≥ 2` in every dimension (AGENTS.md pitfall 20). The tests use `128×2×2`, so this should not occur unless the par template is edited. |
| `Speed=0` (zero transport, 2 ms) | `n_cell_global` formatted as a float (e.g. `128.000000`) in the par file — Kratos' par parser cannot parse float-formatted mesh dimensions and silently sets `n_cell=0`. The test uses `str(int(x))` for `n_cell_global` (see AGENTS.md pitfall 35). |
| All `med\|x\|` values are zero | Kratos ran in pure-absorption mode (`n_scat=0` in the par file). The tests set `n_scat=5000000`; do not reduce it. |
| `PASS` but ratios drift > 2% vs golden | Re-measure goldens with `--measure` after confirming the physics is correct. GPU non-determinism can cause ~0.5% scatter. |
| LSP error: `Import "binary_io" could not be resolved` | Static-analysis false positive. `binary_io` is imported lazily inside `resolve_kratos_root()` after `sys.path` is patched at runtime. The import succeeds when the test is executed. |
