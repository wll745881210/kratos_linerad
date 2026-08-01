#!/usr/bin/env python3
"""
Pure absorption plane-parallel test.

A slab with no scattering (mfp_i_sca_0 = 0) and wavelength-independent
absorption (const_abs = 1, mfp_i_abs_0 = tau_abs / L_slab). An isotropic
midplane source emits monochromatic photons at line centre (x=0).

With no scattering, the spectrum stays monochromatic (x=0) -- so the
meaningful observable is the weighted escape fraction
    f_esc = Sum(proper_escaped) / N_total
since absorption only decays the photon weight (implicit absorption, no
photon kill). For isotropic midplane emission through a half-slab of
absorption optical depth tau_a = mfp_abs * L_slab/2 = tau_abs/2,
    f_esc = E_2(tau_a) = integral_0^1 exp(-tau_a/mu) dmu
(scipy.special.expn(2, tau_a)). Compares Kratos vs Python mcrt_slab vs
analytic E_2.

Usage
-----
  python tests/test_absorption.py
  python tests/test_absorption.py --tau-abs-list 0.3 1 3 10 --n 20000
"""
import argparse, os, subprocess, sys, tempfile
import numpy as np
from pathlib import Path
from scipy.special import expn

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline.kratos_io import write_field_data, write_photon_data, read_output
from docs.reference_mcrt.mcrt import run_mcrt

UNIT_L0 = 1.49597870691e13
UNIT_T0 = 1.0
KRATOS_BIN = os.path.expanduser('~/apps/kratos_line_rt/bin/kratos')
WORKDIR = '/tmp/line_rt'

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# ── Analytic ────────────────────────────────────────────────────────

def f_esc_analytic(tau_abs):
    """
    Escape fraction for isotropic midplane source, pure absorption.

    tau_abs = full-slab absorption optical depth; half-slab tau_a =
    tau_abs/2. f_esc = E_2(tau_a) = integral_0^1 exp(-tau_a/mu) dmu.
    """
    return expn(2, tau_abs / 2.0)


# ── Kratos input generation ─────────────────────────────────────────

PAR_TEMPLATE = """# Kratos pure-absorption test - auto-generated

[unit]
length  = {unit_l0:.6e}
time    = {unit_t0}
density = 1.0

[mesh]
x_min = {x_min:.6f} 0 0
x_max = {x_max:.6f} 1 1
n_cell_global = {nx} 2 2

[cycle]
prefix_output = test
n_cycle_lim   = 0
t_lim         = 600.0
t_output_next = 1e32
dt_output     = 1e32
final_output  = 1

[particle]
n_step = 5000000
n_scat = 0
output = 1
n_radiation = {n_radiation}

[line_rt]
field_file  = {field_file}
photon_file = {photon_file}
ph_mode     = 1
b_sca       = {b_sca_code:.10e}
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = 0.5

[boundary]
kinds = fre fre per per per per
"""


def generate_kratos_inputs(tau_abs, n_radiation, out_dir, tag,
                           n_cell=128, L_slab=1.49598e14, b_sca=1.0e5,
                           seed=42):
    L_slab_code = L_slab / UNIT_L0
    nx = n_cell
    dx_code = L_slab_code / nx
    half_code = L_slab_code / 2

    # Pure absorption: mfp_i_sca_0 = 0, mfp_i_abs_0 = tau_abs / L_slab (code).
    mfp_i_abs_0_code = tau_abs / L_slab * UNIT_L0
    b_sca_code = b_sca * UNIT_T0 / UNIT_L0

    n_tot = nx * 2 * 2
    fields = {
        'mfp_i_sca_0_': np.zeros(n_tot, dtype=np.float32),
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
    write_field_data(field_file, fields, mesh)

    par_path = os.path.join(out_dir, f'abs_{tag}.par')
    par_content = PAR_TEMPLATE.format(
        unit_l0=UNIT_L0, unit_t0=UNIT_T0,
        x_min=-half_code, x_max=half_code, nx=nx,
        n_radiation=n_radiation,
        field_file=os.path.basename(field_file),
        photon_file=f'photons_{tag}.bin',
        b_sca_code=b_sca_code,
    )
    with open(par_path, 'w') as fp:
        fp.write(par_content)

    photon_file = os.path.join(out_dir, f'photons_{tag}.bin')
    rng = np.random.default_rng(seed)
    ph = np.zeros((n_radiation, 9), dtype=np.float64)
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
    write_photon_data(photon_file, ph, n_col=9)

    return par_path


def run_kratos_one(tau_abs, n_radiation, out_dir, tag):
    print(f"  Kratos: tau_abs={tau_abs}, n={n_radiation}")
    par_path = generate_kratos_inputs(
        tau_abs, n_radiation, out_dir, tag)

    result = subprocess.run(
        [KRATOS_BIN, os.path.basename(par_path)],
        cwd=out_dir, capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        print(f"    FAILED: {result.stderr[-300:]}")
        return None

    out_files = sorted(Path(out_dir).glob('test_*.bin'))
    if not out_files:
        return None
    out = read_output(str(out_files[-1]))
    if 'photons' not in out or 'l' not in out['photons']:
        print("    No escaped photons")
        return None

    # Weighted escape fraction: sum(proper_escaped) / N_total.
    # proper per photon = 1/n_radiation, so total proper = 1.
    proper = out['photons']['l'].astype(np.float64)
    f_esc = float(np.sum(proper))
    n_esc = len(proper)
    print(f"    n_esc={n_esc}/{n_radiation},"
          f" f_esc(weighted)={f_esc:.6f}")
    return {'f_esc': f_esc, 'n_esc': n_esc}


def run_python_one(tau_abs, n_radiation):
    print(f"  Python: tau_abs={tau_abs}, n={n_radiation}")
    # Isotropic midplane source (same as Kratos), no scattering.
    L_slab = 1.49598e14
    n_cell = 128
    dx = L_slab / n_cell
    mesh = {
        'n_cell': np.array([n_cell, 2, 2], dtype=np.int32),
        'x_min': np.array([-L_slab / 2, 0.0, 0.0], dtype=np.float64),
        'dx': np.array([dx, L_slab / 2, L_slab / 2], dtype=np.float64),
    }
    mfp_a = tau_abs / L_slab
    rng = np.random.default_rng(42)
    ph = np.zeros((n_radiation, 9), dtype=np.float64)
    ph[:, 0] = 0.0
    ph[:, 1] = rng.uniform(0.0, L_slab / 2, n_radiation)
    ph[:, 2] = rng.uniform(0.0, L_slab / 2, n_radiation)
    mu = rng.uniform(-1.0, 1.0, n_radiation)
    phi = rng.uniform(0.0, 2.0 * np.pi, n_radiation)
    smu = np.sqrt(1.0 - mu * mu)
    ph[:, 3] = smu * np.cos(phi)
    ph[:, 4] = smu * np.sin(phi)
    ph[:, 5] = mu
    ph[:, 6] = 1.0 / n_radiation
    ph[:, 7] = 0.0
    ph[:, 8] = 0.0
    result = run_mcrt(
        mesh=mesh, photons=ph, b_sca=1.0e5,
        mfp_i_sca_0=0.0, mfp_i_abs_0=mfp_a,
        ph_mode=1, a_voigt=0.5, seed=42, parallel=True,
    )
    esc = result['escaped']
    proper = esc[:, 1].astype(np.float64)
    f_esc = float(np.sum(proper))
    n_esc = len(proper)
    print(f"    n_esc={n_esc}/{n_radiation},"
          f" f_esc(weighted)={f_esc:.6f}")
    return {'f_esc': f_esc, 'n_esc': n_esc}


def main():
    p = argparse.ArgumentParser(
        description='Pure absorption plane-parallel test')
    p.add_argument('--tau-abs-list', type=float, nargs='+',
                   default=[0.1, 0.3, 1.0, 3.0, 10.0, 20.0],
                   help='Full-slab absorption optical depth. Note: Kratos '
                        'uses FP32 photon weights, so f_esc below ~1e-7 '
                        'underflows; cap at tau_abs~20 for meaningful '
                        'comparison.')
    p.add_argument('--n', dest='n_radiation', type=int, default=20000)
    p.add_argument('--no-kratos', action='store_true')
    p.add_argument('--no-python', action='store_true')
    p.add_argument('--workdir', type=str, default=None,
                   help='output directory (default: auto under /tmp/line_rt)')
    args = p.parse_args()

    if args.workdir:
        out_dir = args.workdir
    else:
        os.makedirs('/tmp/line_rt', exist_ok=True)
        out_dir = tempfile.mkdtemp(prefix='abs_', dir='/tmp/line_rt')
    os.makedirs(out_dir, exist_ok=True)
    print(f"[test_absorption] Run directory: {out_dir}")

    results = []
    for tau_abs in args.tau_abs_list:
        f_an = f_esc_analytic(tau_abs)
        print(f"\n=== tau_abs={tau_abs},"
              f" tau_a(half)={tau_abs/2:.2f},"
              f" f_esc(E2)={f_an:.6e} ===")
        tag = f"t{tau_abs:.1f}"
        entry = {'tau_abs': tau_abs, 'f_analytic': f_an}

        if not args.no_kratos:
            for f in Path(out_dir).glob('test_0*.bin'):
                f.unlink()
            kres = run_kratos_one(tau_abs, args.n_radiation, out_dir, tag)
            if kres:
                entry['f_kratos'] = kres['f_esc']
                entry['n_kratos'] = kres['n_esc']

        if not args.no_python:
            pres = run_python_one(tau_abs, args.n_radiation)
            if pres:
                entry['f_python'] = pres['f_esc']
                entry['n_python'] = pres['n_esc']

        results.append(entry)

    # ── Plot: f_esc vs tau_abs ───────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 9),
                                   gridspec_kw={'height_ratios': [3, 1]})

    ta_fine = np.logspace(
        np.log10(min(args.tau_abs_list) * 0.7),
        np.log10(max(args.tau_abs_list) * 1.5), 200)
    ax1.plot(ta_fine, f_esc_analytic(ta_fine), 'k--', linewidth=2,
             label='Analytic: $E_2(\\tau_a/2)$')

    ta_arr = np.array([r['tau_abs'] for r in results])
    if 'f_kratos' in results[0]:
        fk = np.array([r.get('f_kratos', np.nan) for r in results])
        ax1.plot(ta_arr, fk, 'rs-', markersize=8, linewidth=1.5,
                 label='Kratos')
    if 'f_python' in results[0]:
        fp = np.array([r.get('f_python', np.nan) for r in results])
        ax1.plot(ta_arr, fp, 'b^--', markersize=8, linewidth=1.5,
                 label='Python')
    ax1.set_xscale('log')
    ax1.set_yscale('log')
    ax1.set_xlabel('$\\tau_{\\rm abs}$ (full-slab)', fontsize=14)
    ax1.set_ylabel('$f_{\\rm esc}$ (weighted)', fontsize=14)
    ax1.set_title('Pure absorption: escape fraction vs optical depth',
                  fontsize=14)
    ax1.legend(fontsize=12)
    ax1.grid(True, which='both', alpha=0.3)

    # Ratio panel
    if 'f_kratos' in results[0]:
        rk = np.array([r.get('f_kratos', np.nan) / r['f_analytic']
                       for r in results])
        ax2.plot(ta_arr, rk, 'rs-', markersize=8, label='Kratos / E2')
    if 'f_python' in results[0]:
        rp = np.array([r.get('f_python', np.nan) / r['f_analytic']
                       for r in results])
        ax2.plot(ta_arr, rp, 'b^--', markersize=8, label='Python / E2')
    ax2.axhline(1.0, color='k', linestyle=':', linewidth=1)
    ax2.set_xscale('log')
    ax2.set_xlabel('$\\tau_{\\rm abs}$ (full-slab)', fontsize=14)
    ax2.set_ylabel('ratio to $E_2$', fontsize=14)
    ax2.legend(fontsize=11)
    ax2.grid(True, which='both', alpha=0.3)

    fig.tight_layout()
    plot_path = os.path.join(out_dir, 'absorption_fesc_vs_tau.png')
    fig.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"\nSaved: {plot_path}")
    plt.close(fig)

    # ── Summary table ────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"{'tau_abs':>8} {'tau_a/2':>8} {'E2(tau_a/2)':>12}"
          f" {'Kratos':>12} {'Python':>12}"
          f" {'K/E2':>8} {'P/E2':>8}")
    print(f"{'-'*80}")
    for r in results:
        fk = r.get('f_kratos', np.nan)
        fp = r.get('f_python', np.nan)
        fa = r['f_analytic']
        print(f"{r['tau_abs']:8.2f} {r['tau_abs']/2:8.3f}"
              f" {fa:12.6e}"
              f" {fk:12.6e} {fp:12.6e}"
              f" {fk/fa:8.4f} {fp/fa:8.4f}")
    print(f"{'='*80}")

    return results


if __name__ == '__main__':
    main()
