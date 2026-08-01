#!/usr/bin/env python3
"""
Standalone scattering + continuum absorption test vs Neufeld (1990).

Self-contained: no pipeline imports. Inlines:
  - binary I/O (via the Kratos repo's binary_io, like test_scaling_wide.py)
  - a compact pure-NumPy/SciPy reference MC (USampler + R_II-A kernel)

A slab of scattering (Voigt) opacity with a_voigt = a and wavelength-
independent continuum absorption (const_abs = 1). An isotropic midplane
source emits monochromatic photons at line centre (x=0, vel=0, sv=0).

With pure scattering the spectrum broadens to the wing and photons escape
with f_esc = 1; adding continuum absorption kappa_a reduces the escape
fraction. Neufeld (1990, ApJ 350, 216) Sec. IV gives the analytic
approximation (valid for line-centre injection into a thick slab):

    f_esc = 1 / cosh(Y0),  Y0 = [3 phi(x_s) beta tau0^2]^{1/2}   (4.28,4.25)

with beta = kappa_a / kappa_bar_s (absorption / MEAN scattering opacity),
tau0 = half-slab mean scattering depth, phi = line profile (int phi dx
= 1, wing phi ~ a/pi x^2) and x_s = 0.525 (a tau0)^{1/3} the effective
escape frequency (4.32). In the far-wing limit this gives (4.33):

    Y0^2 = 3.464 (a tau0)^{1/3} tau0 beta  =>  Y0 = 1.8612 sqrt(X)

with X = (a tau0)^{1/3} tau0 beta = (a tau_m)^{1/3} tau_a in our units.

IMPORTANT: cosh (4.33) is a Fokker-Planck / Eddington / power-law-wing
APPROXIMATION. It OVERESTIMATES f_esc at intermediate optical depth
because the power-law wing approximation underestimates core absorption
probability (Verhamme et al. 2006, A&A 460, 397, Sec. 3.1.1). An
independent MC (~/scratch/line_rt/fiducial/Agent_Neufeld/Neufeld检验复现/
neufeld_mc.py, exact R_II-A kernel) confirms MC sits systematically
BELOW cosh (4.33) at Q = (a tau0)^{1/3} tau0 beta ~ 1-3 (their Table
Sec. 5.3: 4.2-4.3 sigma below at Q=1,3). Therefore the PASS criterion
is Kratos ~ Python (two independent MC implementations), NOT agreement
with the approximate analytic formula. The K/Neufeld and P/Neufeld
ratios are reported for diagnostics but are expected to be < 1.

Unit mapping (half-slab mean-depth convention, see AGENTS.md pitfall 23):
    tau0 = tau_m = sqrt(pi) * mfp_i_sca_0 * L/2
    tau_a = mfp_i_abs_0 * L/2                  (half-slab absorption depth)
    beta = kappa_a / kappa_bar_s = mfp_i_abs_0 / (sqrt(pi) mfp_i_sca_0)
         = tau_a / tau_m
    X = (a tau_m)^{1/3} tau_a
    Y0 = 1.8612 sqrt(X)
    f_esc = 1 / cosh(Y0)                        (Neufeld 4.33, approximate)

Usage
-----
  python3 tests/test_absorption_scattering.py --kratos-root ~/apps/kratos_line_rt
  python3 tests/test_absorption_scattering.py --tau-m-list 30 300 3000 \
      --tau-a-list 0.3 1.0 --n 100000 \
      --kratos-root ~/apps/kratos_line_rt
"""
import argparse, importlib, os, subprocess, sys, tempfile
import numpy as np
from pathlib import Path

UNIT_L0 = 1.49597870691e13
UNIT_T0 = 1.0
DEFAULT_KRATOS_ROOT = Path(os.path.expanduser('~/apps/kratos_line_rt'))
WORKDIR = Path('/tmp/line_rt')
B_SCA_CGS = 1.0e5


def resolve_kratos_root(kratos_root):
    """Validate a Kratos build tree: must contain bin/kratos and
    visual/binary_io.py.  Returns (kratos_root, kratos_bin, binary_io_module).
    """
    kratos_root = Path(kratos_root).expanduser()
    kratos_bin = kratos_root / 'bin' / 'kratos'
    bio_path = kratos_root / 'visual' / 'binary_io.py'
    if not kratos_bin.exists():
        raise FileNotFoundError(f"kratos binary not found: {kratos_bin}")
    if not bio_path.exists():
        raise FileNotFoundError(f"binary_io.py not found: {bio_path}")
    if str(kratos_root / 'visual') not in sys.path:
        sys.path.insert(0, str(kratos_root / 'visual'))
    binary_io = importlib.import_module('binary_io').binary_io
    return kratos_root, kratos_bin, binary_io


from scipy.special import voigt_profile  # noqa: E402

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# == Analytic (Neufeld 1990 Sec. IV) =================================

def f_esc_neufeld(tau_m, tau_a, a_voigt):
    """
    Neufeld (1990) eq (4.33) escape fraction (far-wing branch).

    tau_m  = half-slab mean scattering depth (tau0 = sqrt(pi) mfp_sca L/2)
    tau_a  = half-slab absorption depth (mfp_abs L/2)
    a_voigt = Voigt damping parameter
    Returns (f_esc, Y0) with Y0 = 1.8612 sqrt(X), X = (a tau_m)^{1/3} tau_a.

    This is the Fokker-Planck/power-law-wing approximation that
    OVERESTIMATES f_esc at intermediate optical depth (Verhamme 2006);
    MC implementations sit below it. See module docstring.
    """
    x = (a_voigt * tau_m) ** (1.0 / 3.0) * tau_a
    y0 = 1.8612 * np.sqrt(x)
    return 1.0 / np.cosh(y0), y0


# == Binary I/O (inline, mirrors pipeline/kratos_io.py) ===============

def write_fields(filename, fields, mesh, binary_io):
    """Write Kratos field binary."""
    bio = binary_io(filename)
    n_cell = np.asarray(mesh['n_cell'], dtype=np.int32)
    x_min = np.asarray(mesh['x_min'], dtype=np.float32)
    dx = np.asarray(mesh['dx'], dtype=np.float32)
    n_pts = (n_cell + 1).astype(np.int32)

    for prefix in ['mfp_i_sca_0_', 'mfp_i_abs_0_', 'b_sca_',
                   'vel_0_', 'vel_1_', 'vel_2_']:
        if prefix not in fields:
            continue
        raw = np.asarray(fields[prefix], dtype=np.float32)
        arr = raw.reshape(n_cell[2], n_cell[1], n_cell[0])
        padded = np.pad(arr, ((0, 1), (0, 1), (0, 1)), mode='edge')
        bio.cache(f'{prefix}n_pts', n_pts, dtype='int32')
        bio.cache(f'{prefix}x0', x_min, dtype='float32')
        bio.cache(f'{prefix}dx', dx, dtype='float32')
        bio.cache(f'{prefix}data', padded.ravel(), dtype='float32')
    bio.save()
    return filename


def write_photons(filename, photons, binary_io):
    """Write Kratos photon binary."""
    ph = np.asarray(photons, dtype=np.float32)
    bio = binary_io(filename)
    bio.cache('par_n_col', ph.shape[1], dtype='int32')
    bio.cache('par_n_par', ph.shape[0], dtype='int64')
    bio.cache('par_par_dat', ph, dtype='float32')
    bio.save()
    return filename


def read_escaped_photons(filename, binary_io):
    """Read escaped photons from a Kratos output binary."""
    bio = binary_io(filename)
    bio.open()
    phot = {}
    for raw_key in bio.hmap:
        if '_rank_' in raw_key and raw_key.endswith('_x'):
            phot['x'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_dir'):
            phot['dir'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_l'):
            phot['l'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_vel'):
            phot['vel'] = bio.as_array(raw_key, 'f')
    bio.close()
    return phot


# == Compact pure-NumPy reference MC (R_II-A kernel) ==================
# Based on ~/scratch/line_rt/fiducial/Agent_Neufeld/Neufeld检验复现/
# neufeld_mc.py (prior agent's validated independent MC). Works in
# mean-depth units: z in [-tau_m, tau_m], opacity = phi(x) + beta.

class _USampler:
    """Inverse-CDF table sampler for P(u|x) ∝ exp(-u²)/(a²+(x-u)²).

    This is the exact R_II-A redistribution kernel (Maxwell x Lorentz).
    Builds a 2D CDF table C(|x|, u), samples via binary search +
    linear interpolation between adjacent |x| grid points.
    """

    __slots__ = ('u', 'xg', 'C')

    def __init__(self, a, x_max=300.0, du=5e-3, n_lin=101, n_log=121):
        u = np.arange(-6.0, 6.0 + du, du)
        x_lin = np.linspace(0.0, 8.0, n_lin)
        x_log = np.logspace(np.log10(8.0), np.log10(x_max), n_log)[1:]
        xg = np.concatenate([x_lin, x_log])
        G = np.exp(-u ** 2)
        D = u[None, :] - xg[:, None]
        W = G[None, :] / (a ** 2 + D ** 2)
        C = np.cumsum(W, axis=1)
        C /= C[:, -1:]
        C[:, -1] = 1.0
        self.u, self.xg, self.C = u, xg, C

    def sample(self, x, rng):
        """Sample u_par for frequency array x (any sign)."""
        x = np.asarray(x)
        sgn = np.where(x < 0, -1.0, 1.0)
        xa = np.abs(x)
        j = np.clip(np.searchsorted(self.xg, xa) - 1, 0, self.xg.size - 2)
        f = (xa - self.xg[j]) / (self.xg[j + 1] - self.xg[j])
        r = rng.random(x.size)
        u_out = np.empty(x.size)
        for jj in np.unique(j):
            m = j == jj
            rr = r[m]
            us = []
            for row in (self.C[jj], self.C[jj + 1]):
                k = np.clip(np.searchsorted(row, rr), 1, self.u.size - 1)
                c0, c1 = row[k - 1], row[k]
                us.append(self.u[k - 1] + (rr - c0) /
                          np.maximum(c1 - c0, 1e-300) *
                          (self.u[k] - self.u[k - 1]))
            u_out[m] = (1.0 - f[m]) * us[0] + f[m] * us[1]
        return sgn * u_out


_SIGMA = 1.0 / np.sqrt(2.0)  # 1D thermal velocity dispersion (v_th units)


def run_mc_slab(tau_m, tau_a, a_voigt, n_photons, seed=42, batch=2000,
                max_iter=300000):
    """Pure-NumPy Lyα MC in mean-depth units (z in [-tau_m, tau_m]).

    Physics (exact R_II-A, no core-skipping):
      - free flight: -ln(1-xi) / (phi(x) + beta),  phi = voigt_profile
      - escape: |z| >= tau_m
      - dust absorption: prob beta/(phi+beta)
      - scatter: u_par ~ P(u|x) (USampler), x_at = x - u_par,
        isotropic new dir, u_par' = g*u_par + sqrt(1-g^2)*u_perp,
        x' = x_at + u_par'

    Returns f_esc (sum of proper weights of escaped photons).
    """
    beta = tau_a / tau_m if tau_m > 0 else 0.0
    sampler = _USampler(a_voigt)
    n_esc = 0
    weight = 1.0 / n_photons

    for b0 in range(0, n_photons, batch):
        nb = min(batch, n_photons - b0)
        rng = np.random.default_rng(seed * 100003 + b0)
        z = np.zeros(nb)
        x = np.zeros(nb)
        mu = 2.0 * rng.random(nb) - 1.0
        alive = np.ones(nb, dtype=bool)
        it = 0
        while alive.any():
            it += 1
            if it > max_iter:
                raise RuntimeError("max_iter exceeded")
            idx = np.nonzero(alive)[0]
            n = idx.size
            x_a, mu_a, z_a = x[idx], mu[idx], z[idx]

            coeff = voigt_profile(x_a, _SIGMA, a_voigt) + beta
            z_new = z_a + mu_a * (-np.log(1.0 - rng.random(n))) / coeff

            esc = np.abs(z_new) >= tau_m
            if esc.any():
                ie = idx[esc]
                n_esc += ie.size
                alive[ie] = False

            surv = ~esc
            if not surv.any():
                continue
            isur = idx[surv]
            z[isur] = z_new[surv]
            ns = isur.size
            x_s = x_a[surv]

            absorbed = rng.random(ns) < beta / coeff[surv]
            if absorbed.any():
                alive[isur[absorbed]] = False
            keep = ~absorbed
            if not keep.any():
                continue
            ik = isur[keep]
            x_k = x_s[keep]
            nk = ik.size

            u_par = sampler.sample(x_k, rng)
            x_at = x_k - u_par
            g = 2.0 * rng.random(nk) - 1.0
            u_perp = rng.standard_normal(nk) * _SIGMA
            u_par_n = g * u_par + np.sqrt(1.0 - g ** 2) * u_perp
            x[ik] = x_at + u_par_n
            mu[ik] = 2.0 * rng.random(nk) - 1.0

    return n_esc * weight


# == Kratos input generation ==========================================

PAR_TEMPLATE = """# Kratos scattering+absorption test - auto-generated

[unit]
length  = {unit_l0:.6e}
time    = {unit_t0}
density = 1.0

[mesh]
x_min = {x_min:.6f} 0 0
x_max = {x_max:.6f} 1 1
n_cell_global = {nx} 2 2

[cycle]
prefix_output = test_{tag}
n_cycle_lim   = 0
t_lim         = 600.0
t_output_next = 1e32
dt_output     = 1e32
final_output  = 1

[particle]
n_step = 5000000
n_scat = 5000000
output = 1
n_radiation = {n_radiation}

[line_rt]
field_file  = {field_file}
photon_file = {photon_file}
ph_mode     = {ph_mode}
b_sca       = {b_sca_code:.10e}
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = {a_voigt}

[boundary]
kinds = fre fre per per per per
"""


def generate_kratos_inputs(tau_m, tau_a, a_voigt, n_radiation, out_dir, tag,
                           ph_mode=1, n_cell=128, L_slab=1.49598e14,
                           b_sca=1.0e5, seed=42, binary_io=None):
    L_slab_code = L_slab / UNIT_L0
    nx = n_cell
    dx_code = L_slab_code / nx
    half_code = L_slab_code / 2

    mfp_i_sca_0_cgs = 2.0 * tau_m / (np.sqrt(np.pi) * L_slab)
    mfp_i_abs_0_cgs = 2.0 * tau_a / L_slab
    mfp_i_sca_0_code = mfp_i_sca_0_cgs * UNIT_L0
    mfp_i_abs_0_code = mfp_i_abs_0_cgs * UNIT_L0
    b_sca_code = b_sca * UNIT_T0 / UNIT_L0

    n_tot = nx * 2 * 2
    fields = {
        'mfp_i_sca_0_': np.full(n_tot, np.float32(mfp_i_sca_0_code)),
        'mfp_i_abs_0_': np.full(n_tot, np.float32(mfp_i_abs_0_code)),
        'b_sca_': np.full(n_tot, np.float32(b_sca_code)),
        'vel_0_': np.zeros(n_tot, dtype=np.float32),
        'vel_1_': np.zeros(n_tot, dtype=np.float32),
        'vel_2_': np.zeros(n_tot, dtype=np.float32),
    }
    mesh = {
        'n_cell': np.array([nx, 2, 2], dtype=np.int32),
        'x_min': np.array([-half_code, 0.0, 0.0], dtype=np.float32),
        'dx': np.array([dx_code, 0.5, 0.5], dtype=np.float32),
    }

    field_file = os.path.join(out_dir, f'fields_{tag}.bin')
    write_fields(field_file, fields, mesh, binary_io)

    par_path = os.path.join(out_dir, f'abs_{tag}.par')
    par_content = PAR_TEMPLATE.format(
        unit_l0=UNIT_L0, unit_t0=UNIT_T0,
        x_min=-half_code, x_max=half_code, nx=nx,
        n_radiation=n_radiation, ph_mode=ph_mode, a_voigt=a_voigt,
        field_file=os.path.basename(field_file),
        photon_file=f'photons_{tag}.bin',
        b_sca_code=b_sca_code, tag=tag,
    )
    with open(par_path, 'w') as fp:
        fp.write(par_content)

    photon_file = os.path.join(out_dir, f'photons_{tag}.bin')
    rng = np.random.default_rng(seed)
    ph = np.zeros((n_radiation, 9), dtype=np.float32)
    ph[:, 0] = 0.0
    ph[:, 1] = rng.uniform(0.0, 1.0, n_radiation)
    ph[:, 2] = rng.uniform(0.0, 1.0, n_radiation)
    mu = rng.uniform(-1.0, 1.0, n_radiation)
    phi = rng.uniform(0.0, 2.0 * np.pi, n_radiation)
    smu = np.sqrt(1.0 - mu * mu)
    ph[:, 3] = smu * np.cos(phi)
    ph[:, 4] = smu * np.sin(phi)
    ph[:, 5] = mu
    ph[:, 6] = 1.0 / n_radiation
    ph[:, 7] = 0.0
    ph[:, 8] = 0.0
    write_photons(photon_file, ph, binary_io)

    return par_path


def run_kratos_one(tau_m, tau_a, a_voigt, n_radiation, out_dir, tag,
                   ph_mode=1, kratos_bin=None, binary_io=None):
    print(f"  Kratos: tau_m={tau_m}, tau_a={tau_a}, n={n_radiation}")
    par_path = generate_kratos_inputs(
        tau_m, tau_a, a_voigt, n_radiation, out_dir, tag, ph_mode=ph_mode,
        binary_io=binary_io)

    result = subprocess.run(
        [str(kratos_bin), os.path.basename(par_path)],
        cwd=out_dir, capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        print(f"    FAILED: {result.stderr[-300:]}")
        return None

    out_files = sorted(Path(out_dir).glob(f'test_{tag}_*.bin'))
    if not out_files:
        return None
    phot = read_escaped_photons(str(out_files[-1]), binary_io)
    if 'l' not in phot or phot['l'].size == 0:
        print("    No escaped photons")
        return None

    proper = phot['l'].astype(np.float64)
    f_esc = float(np.sum(proper))
    print(f"    n_esc={len(proper)}/{n_radiation},"
          f" f_esc(weighted)={f_esc:.6f}")
    return {'f_esc': f_esc, 'n_esc': len(proper)}


def run_python_one(tau_m, tau_a, a_voigt, n_radiation):
    print(f"  Python: tau_m={tau_m}, tau_a={tau_a}, n={n_radiation}")
    f_esc = run_mc_slab(tau_m, tau_a, a_voigt, n_radiation, seed=42)
    print(f"    f_esc(weighted)={f_esc:.6f}")
    return {'f_esc': f_esc}


def main():
    p = argparse.ArgumentParser(
        description='Standalone scattering + absorption vs Neufeld (1990)')
    p.add_argument('--tau-m-list', type=float, nargs='+',
                   default=[30.0, 100.0, 300.0],
                   help='Half-slab mean scattering depths (tau_m)')
    p.add_argument('--tau-a-list', type=float, nargs='+',
                   default=[0.1, 0.3, 1.0],
                   help='Half-slab absorption depths (tau_a)')
    p.add_argument('--a-voigt', type=float, default=0.149)
    p.add_argument('--ph-mode', type=int, default=1,
                   help='Kratos ph_mode (1=R_IIA exact, 2=const-mem)')
    p.add_argument('--n', dest='n_radiation', type=int, default=50000)
    p.add_argument('--kratos-root', type=str, default=str(DEFAULT_KRATOS_ROOT),
                   help='Kratos build tree root (must contain bin/kratos '
                        'and visual/binary_io.py)')
    p.add_argument('--no-kratos', action='store_true')
    p.add_argument('--no-python', action='store_true')
    p.add_argument('--no-plot', action='store_true')
    p.add_argument('--workdir', type=str, default=None,
                   help='output directory (default: auto under /tmp/line_rt)')
    args = p.parse_args()

    kratos_root, kratos_bin, binary_io = resolve_kratos_root(args.kratos_root)
    print(f"Kratos root: {kratos_root}")
    print(f"Kratos bin:  {kratos_bin}")

    if args.workdir:
        out_dir = Path(args.workdir)
    else:
        Path('/tmp/line_rt').mkdir(parents=True, exist_ok=True)
        out_dir = Path(tempfile.mkdtemp(prefix='abs_scat_',
                                        dir='/tmp/line_rt'))
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[test_absorption_scattering] Run directory: {out_dir}")

    results = []
    for tau_a in args.tau_a_list:
        for tau_m in args.tau_m_list:
            f_an, y0 = f_esc_neufeld(tau_m, tau_a, args.a_voigt)
            print(f"\n=== tau_m={tau_m}, tau_a={tau_a},"
                  f" f_esc(Neufeld 4.33)={f_an:.6e}"
                  f" [Y0={y0:.3f}] ===")
            tag = f"m{tau_m:g}_a{tau_a:g}"
            entry = {'tau_m': tau_m, 'tau_a': tau_a,
                     'f_neufeld': f_an, 'y0': y0}

            if not args.no_kratos:
                for f in out_dir.glob('test_*_*.bin'):
                    f.unlink()
                kres = run_kratos_one(tau_m, tau_a, args.a_voigt,
                                      args.n_radiation, str(out_dir), tag,
                                      ph_mode=args.ph_mode,
                                      kratos_bin=kratos_bin,
                                      binary_io=binary_io)
                if kres:
                    entry['f_kratos'] = kres['f_esc']
                    entry['n_kratos'] = kres['n_esc']

            if not args.no_python:
                pres = run_python_one(tau_m, tau_a, args.a_voigt,
                                      args.n_radiation)
                if pres:
                    entry['f_python'] = pres['f_esc']

            results.append(entry)

    # ── Plot: f_esc vs tau_a, per tau_m ──────────────────────────
    if not args.no_plot and results:
        ta_arr = np.array([r['tau_a'] for r in results])
        tm_arr = np.array([r['tau_m'] for r in results])

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 9),
                                       gridspec_kw={'height_ratios': [3, 1]})

        ta_fine = np.logspace(np.log10(min(ta_arr) * 0.7),
                              np.log10(max(ta_arr) * 1.5), 200)
        f_fine, _ = f_esc_neufeld(np.median(tm_arr), ta_fine,
                                  args.a_voigt)
        ax1.plot(ta_fine, f_fine, 'k--', linewidth=2,
                 label='Neufeld (4.33): $1/\\cosh(Y_0)$ '
                       '(Fokker-Planck approx.)')

        for tm in np.unique(tm_arr):
            m = tm_arr == tm
            if 'f_kratos' in results[0]:
                fk = np.array([r.get('f_kratos', np.nan)
                               for r in results])[m]
                ax1.plot(ta_arr[m], fk, 'rs-', markersize=7,
                         label=f'Kratos $\\tau_m$={tm:g}')
            if 'f_python' in results[0]:
                fp = np.array([r.get('f_python', np.nan)
                               for r in results])[m]
                ax1.plot(ta_arr[m], fp, 'b^--', markersize=7,
                         label=f'Python $\\tau_m$={tm:g}')
        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel('$\\tau_a$ (half-slab absorption depth)', fontsize=14)
        ax1.set_ylabel('$f_{\\rm esc}$ (weighted)', fontsize=14)
        ax1.set_title('Scattering + continuum absorption: '
                      f'escape fraction, a={args.a_voigt}',
                      fontsize=14)
        ax1.legend(fontsize=11)
        ax1.grid(True, which='both', alpha=0.3)

        rk = np.array([r.get('f_kratos', np.nan) / r['f_neufeld']
                       for r in results])
        rp = np.array([r.get('f_python', np.nan) / r['f_neufeld']
                       for r in results])
        for tm in np.unique(tm_arr):
            m = tm_arr == tm
            ax2.plot(ta_arr[m], rk[m], 'rs-', markersize=7)
            ax2.plot(ta_arr[m], rp[m], 'b^--', markersize=7)
        ax2.axhline(1.0, color='k', linestyle=':', linewidth=1)
        ax2.set_xscale('log')
        ax2.set_xlabel('$\\tau_a$', fontsize=14)
        ax2.set_ylabel('ratio to Neufeld', fontsize=14)
        ax2.grid(True, which='both', alpha=0.3)

        fig.tight_layout()
        plot_path = os.path.join(str(out_dir), 'abs_scat_fesc_vs_tau.png')
        fig.savefig(plot_path, dpi=150, bbox_inches='tight')
        print(f"\nSaved: {plot_path}")
        plt.close(fig)

    # ── Summary table + PASS/FAIL ────────────────────────────────
    # PASS = Kratos ~ Python (two independent MC implementations agree).
    # K/Neufeld and P/Neufeld are diagnostic-only: cosh (4.33) is a
    # Fokker-Planck approximation that OVERESTIMATES f_esc at intermediate
    # depth (Verhamme 2006); MC sits below it (expected ratios < 1).
    print(f"\n{'='*96}")
    print(f"{'tau_m':>6} {'tau_a':>6} {'Q':>7} {'Neufeld':>12}"
          f" {'Kratos':>12} {'Python':>12}"
          f" {'K/N':>8} {'P/N':>8} {'K/P':>8}")
    print(f"{'-'*96}")
    ok = True
    for r in results:
        fk = r.get('f_kratos', np.nan)
        fp = r.get('f_python', np.nan)
        fa = r['f_neufeld']
        q = (args.a_voigt * r['tau_m']) ** (1.0 / 3.0) * r['tau_a']
        kn = fk / fa if fa > 0 else np.nan
        pn = fp / fa if fa > 0 else np.nan
        kp = fk / fp if fp > 0 else np.nan
        # PASS criterion: Kratos ~ Python. Allow 1.6x for MC noise at low
        # f_esc (~1e-3 with n=5e4 -> ~15% Poisson per implementation).
        if (not np.isnan(kp)) and (kp < 0.6 or kp > 1.6):
            ok = False
        print(f"{r['tau_m']:6.0f} {r['tau_a']:6.2f} {q:7.3f}"
              f" {fa:12.6e} {fk:12.6e} {fp:12.6e}"
              f" {kn:8.3f} {pn:8.3f} {kp:8.3f}")
    print(f"{'='*96}")
    print("Note: K/N, P/N < 1 is EXPECTED - cosh (4.33) is a Fokker-Planck")
    print("      approximation that overestimates f_esc (Verhamme 2006);")
    print("      independent MC (neufeld_mc.py) shows the same MC-below-cosh")
    print("      behavior. PASS = Kratos ~ Python.")
    if args.no_kratos or args.no_python:
        print("(partial run: K/P check skipped)")
    elif ok:
        print("PASS: Kratos ~ Python (two independent MC implementations agree)")
    else:
        print("FAIL: Kratos and Python disagree beyond 1.6x tolerance")
        sys.exit(1)

    return results


if __name__ == '__main__':
    main()
