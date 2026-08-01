#!/usr/bin/env python3
"""
Neufeld test: Kratos ph_mode=1 vs Python reference MCRT vs fiducial.

Compares the escape-frequency distribution of a uniform plane-parallel
slab with midplane source against:
(a) pipeline mcrt_slab()  (docs/reference_mcrt/mcrt.py)
(b) fiducial neufeld_mc   (~/scratch/line_rt/fiducial/Agent_Neufeld/...)
(c) Kratos ph_mode=1
(d) Neufeld (1990) analytic formula, both τ conventions

Units
-----
- Dimensionless frequency x = (nu-nu0)/Delta_nu_D = vel / b_sca.
- mcrt_slab() and Kratos use line-centre tau0 convention.
- neufeld_mc (fiducial) uses Neufeld mean-depth tau convention:
    tau_fid = sqrt(pi) * tau0_LC.

Usage
-----
# Compare all three MCRT codes:
  python tests/test_neufeld.py --tau0 10000 --a 0.01 --n 5000 --fiducial

# Kratos + pipeline + analytic formula:
  python tests/test_neufeld.py --tau0 56419 --a 0.01 --n 50000 --ref-neufeld

# Fiducial only (fast test):
  python tests/test_neufeld.py --tau0 10000 --a 0.5 --n 5000 --no-kratos \
    --no-python --fiducial
"""

import argparse, os, subprocess, sys
import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline.kratos_io import write_field_data, write_photon_data, read_output
from docs.reference_mcrt.mcrt import mcrt_slab

UNIT_L0 = 1.49597870691e13
UNIT_T0 = 1.0
KRATOS_BIN = os.path.expanduser('~/apps/kratos_line_rt/bin/kratos')
WORKDIR = os.path.expanduser('~/scratch/line_rt')

FIDUCIAL_PATH = os.path.expanduser(
    '~/scratch/line_rt/fiducial/Agent_Neufeld/'
    'Neufeld检验复现/neufeld_mc.py')
sys.path.insert(0, str(Path(FIDUCIAL_PATH).parent))

PAR_TEMPLATE = """# Kratos Neufeld test — auto-generated

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
t_lim         = {t_lim}
t_output_next = 1e32
dt_output     = 1e32
final_output  = 1

[particle]
n_step = {n_step}
n_scat = {n_step}
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
a_voigt     = {a_voigt}

[boundary]
kinds = fre fre per per per per
"""


def estimate_n_scatt(tau0, a_voigt):
    if a_voigt > 1e-6:
        return max(100, int(2.857 * tau0))
    else:
        return max(100, int(tau0 * tau0))


def generate_kratos_inputs(args, out_dir):
    L_slab_code = args.L_slab / UNIT_L0
    nx = args.n_cell
    dx_code = L_slab_code / nx
    half_code = L_slab_code / 2

    mfp_i_sca_0_code = args.tau0 / args.L_slab * UNIT_L0
    b_sca_code = args.b_sca * UNIT_T0 / UNIT_L0

    n_tot = nx * 2 * 2
    fields = {
        'mfp_i_sca_0_': np.full(n_tot, np.float32(mfp_i_sca_0_code)),
        'mfp_i_abs_0_': np.zeros(n_tot, dtype=np.float32),
        'b_sca_': np.full(n_tot, np.float32(b_sca_code)),
        'vel_0_': np.zeros(n_tot, dtype=np.float32),
        'vel_1_': np.zeros(n_tot, dtype=np.float32),
        'vel_2_': np.zeros(n_tot, dtype=np.float32),
    }
    # Field mesh MUST coincide with the par mesh (y,z in [0,1], 2 cells):
    # Kratos samples the field interpolant at par-mesh cell centres.
    mesh = {
        'n_cell': np.array([nx, 2, 2], dtype=np.int32),
        'x_min': np.array([-half_code, 0.0, 0.0], dtype=np.float32),
        'dx': np.array([dx_code, 0.5, 0.5], dtype=np.float32),
    }

    field_file = os.path.join(out_dir, 'fields_neufeld.bin')
    write_field_data(field_file, fields, mesh)

    n_sc_est = estimate_n_scatt(args.tau0, args.a_voigt)
    n_step = max(args.n_radiation * n_sc_est * 3, 5000000)

    par_path = os.path.join(out_dir, 'neufeld.par')
    par_content = PAR_TEMPLATE.format(
        unit_l0=UNIT_L0, unit_t0=UNIT_T0,
        x_min=-half_code, x_max=half_code, nx=nx,
        t_lim=args.t_lim,
        n_step=n_step, n_radiation=args.n_radiation,
        field_file=os.path.basename(field_file),
        photon_file='photons_neufeld.bin',
        b_sca_code=b_sca_code, a_voigt=args.a_voigt,
    )
    with open(par_path, 'w') as fp:
        fp.write(par_content)

    photon_file = os.path.join(out_dir, 'photons_neufeld.bin')
    rng = np.random.default_rng(args.seed)
    ph = np.zeros((args.n_radiation, 9), dtype=np.float64)
    ph[:, 0] = 0.0
    ph[:, 1] = rng.uniform(0.0, 1.0, args.n_radiation)
    ph[:, 2] = rng.uniform(0.0, 1.0, args.n_radiation)
    # Isotropic midplane source (match Python ref and fiducial)
    mu = rng.uniform(-1.0, 1.0, args.n_radiation)
    phi = rng.uniform(0.0, 2.0 * np.pi, args.n_radiation)
    smu = np.sqrt(1.0 - mu * mu)
    ph[:, 3] = smu * np.cos(phi)
    ph[:, 4] = smu * np.sin(phi)
    ph[:, 5] = mu
    ph[:, 6] = 1.0 / args.n_radiation
    ph[:, 7] = 0.0
    ph[:, 8] = 0.0
    write_photon_data(photon_file, ph, n_col=9)

    print(f"  n_step={n_step}, n_rad={args.n_radiation}, nx={nx}")
    print(f"  Est. scatters/photon: {n_sc_est}")
    return par_path


def run_kratos(par_path, out_dir, b_sca, n_radiation):
    result = subprocess.run(
        [KRATOS_BIN, os.path.basename(par_path)],
        cwd=out_dir, capture_output=True, text=True, timeout=600,
    )
    print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
    if result.returncode != 0:
        print("Kratos stderr:", result.stderr[-500:])
        return None
    out_files = sorted(Path(out_dir).glob('test_*.bin'))
    if not out_files:
        return None
    out = read_output(str(out_files[-1]))
    if 'photons' not in out or out['photons'].get('vel', np.array([])).size == 0:
        return None
    b_sca_code = b_sca * UNIT_T0 / UNIT_L0
    ph = out['photons']
    vel = ph['vel'].astype(np.float64)
    x_freq = vel / b_sca_code
    if np.all(np.abs(x_freq) < 1e-6):
        raise RuntimeError(
            "All escaped photons have x=0 — no scattering occurred. "
            "Likely field/mesh mismatch: Kratos samples the field binary "
            "at par-mesh cell centres; the field grid must coincide with "
            "the par mesh (check field x_min/dx/n_cell vs [mesh] section).")
    print(f"Escaped photons: {len(x_freq)} / {n_radiation}")
    return {'x_freq': x_freq, 'n_esc': len(x_freq)}


def run_python_ref(args):
    print(f"\n--- mcrt_slab() (ph_mode=1, n={args.n_radiation}) ---")
    result = mcrt_slab(
        n_cell=args.n_cell, L_slab=args.L_slab,
        tau0=args.tau0, tau_abs=0.0, b_sca=args.b_sca,
        n_photons=args.n_radiation, ph_mode=1,
        a_voigt=args.a_voigt, seed=args.seed,
        parallel=True, source='midplane',
    )
    esc = result['escaped']
    x_freq = esc[:, 0].astype(np.float64) / args.b_sca
    print(f"Escaped: {len(x_freq)} / {args.n_radiation}")
    return {'x_freq': x_freq, 'n_esc': len(x_freq)}


def run_fiducial(args):
    """
    Run fiducial neufeld_mc.run_mc().
    Uses Neufeld mean-depth tau convention: tau_fid = sqrt(pi) * tau0_LC.
    """
    try:
        sys.path.insert(0, str(Path(FIDUCIAL_PATH).parent))
        from neufeld_mc import run_mc
    except ImportError:
        print(f"Fiducial not importable: {FIDUCIAL_PATH}")
        return None
    tau_fid = np.sqrt(np.pi) * args.tau0
    at_fid = args.a_voigt * tau_fid
    print(f"\n--- Fiducial run_mc (a={args.a_voigt}, tau_fid={tau_fid:.0f},"
          f" a*tau_fid={at_fid:.0f}) ---")
    res = run_mc(
        N=args.n_radiation, tau0=tau_fid, a=args.a_voigt,
        beta=0.0, seed=args.seed,
    )
    n_esc = int(res['N'] * res['f_esc'])
    # Reconstruct individual x_freq values from histogram
    x_cen = res['x_cen']
    hist = res['hist']
    x_freq = np.repeat(x_cen, hist.astype(int))
    rng = np.random.default_rng(args.seed + 999)
    x_freq += rng.uniform(-res['dx'] / 2, res['dx'] / 2, len(x_freq))
    print(f"Escaped: {n_esc} / {int(res['N'])},"
          f" <N_scatt>={res['mean_Nscatt']:.1f}")
    return {
        'x_freq': x_freq, 'n_esc': n_esc,
        'mean_Nscatt': res['mean_Nscatt'],
        'tau_fid': tau_fid,
    }


# ── Neufeld analytic formulas (both conventions) ────────────────────

def neufeld_J_lc(x, a_tau0):
    """
    Neufeld emergent spectrum, line-centre tau0 convention.
    Verhamme+2006 Eq (20). Peak at |x| = 1.07*(a*tau0)^(1/3).
    """
    xa = np.abs(np.asarray(x, dtype=np.float64))
    K = np.sqrt(np.pi ** 3 / 54.0)
    A = np.sqrt(6.0 / np.pi)
    return A * xa * xa / np.cosh(K * xa * xa * xa / (a_tau0 + 1e-35))


def neufeld_J_fid(x, a, tau_fid):
    """
    Neufeld (1990) Eq (2.24), mean-depth tau convention.
    Peak at |x| = 0.881*(a*tau_fid)^(1/3).
    """
    xa = np.abs(np.asarray(x, dtype=np.float64))
    arg = np.sqrt(np.pi ** 4 / 54.0) * xa * xa * xa / (a * tau_fid + 1e-35)
    out = np.where(arg < 700.0,
                   (np.sqrt(6.0) / 24.0) * xa * xa / (a * tau_fid)
                   / np.cosh(arg), 0.0)
    return out


# ── Stats ───────────────────────────────────────────────────────────

def print_stats(label, data):
    x = np.abs(data['x_freq'])
    print(f"  {label}: n={data['n_esc']},"
          f" med|x|={np.median(x):.4f},"
          f" mean|x|={np.mean(x):.4f}, P(|x|>3)={np.mean(x > 3):.4f}")


def compare_neufeld(data, a_tau0, nbins=80):
    x = data['x_freq']
    bins = np.linspace(-10, 10, nbins + 1)
    h, _ = np.histogram(x, bins=bins, density=True)
    bc = 0.5 * (bins[:-1] + bins[1:])
    J = neufeld_J_lc(bc, a_tau0)
    norm = np.trapz(J, bc)
    if float(norm) > 0:
        J /= norm
    chi2 = np.sum((h - J) ** 2 / (np.abs(J) + 1e-10)) / nbins
    x_pred = 1.07 * a_tau0 ** (1.0 / 3.0)
    x_obs = bc[np.argmax(h)]
    return {'chi2': chi2, 'x_pred': x_pred, 'x_obs': x_obs}


def main():
    p = argparse.ArgumentParser(description='Neufeld test suite')
    p.add_argument('--tau0', type=float, default=10000,
                   help='Line-centre tau0')
    p.add_argument('--a', dest='a_voigt', type=float, default=0.01)
    p.add_argument('--n', dest='n_radiation', type=int, default=5000)
    p.add_argument('--L-slab', type=float, default=1.49598e14)
    p.add_argument('--b-sca', type=float, default=1.0e5)
    p.add_argument('--n-cell', type=int, default=128)
    p.add_argument('--t-lim', type=float, default=600.0)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--no-kratos', action='store_true')
    p.add_argument('--no-python', action='store_true')
    p.add_argument('--fiducial', action='store_true',
                   help='Run fiducial neufeld_mc comparison')
    p.add_argument('--ref-neufeld', action='store_true',
                   help='Compare vs analytic formula')
    args = p.parse_args()

    a_tau0_lc = args.a_voigt * args.tau0
    tau_fid = np.sqrt(np.pi) * args.tau0
    a_tau0_fid = args.a_voigt * tau_fid

    print(f"a={args.a_voigt}, tau0_LC={args.tau0}, a*tau0_LC={a_tau0_lc:.1f}")
    print(f"tau_fid={tau_fid:.0f}, a*tau0_fid={a_tau0_fid:.1f}")
    print(f"L_slab={args.L_slab:.3e} cm, nx={args.n_cell}")

    results = {}

    if not args.no_kratos:
        print("\n=== Kratos ===")
        os.makedirs(WORKDIR, exist_ok=True)
        par_path = generate_kratos_inputs(args, WORKDIR)
        kres = run_kratos(par_path, WORKDIR, args.b_sca, args.n_radiation)
        if kres is not None:
            results['Kratos'] = kres
            print_stats('Kratos', kres)

    if not args.no_python:
        pres = run_python_ref(args)
        if pres is not None:
            results['Pipeline mcrt'] = pres
            print_stats('Pipeline mcrt', pres)

    if args.fiducial:
        fres = run_fiducial(args)
        if fres is not None:
            results['Fiducial'] = fres
            print_stats('Fiducial', fres)
            print(f"    <N_scatt> = {fres['mean_Nscatt']:.0f}")

    if len(results) >= 2:
        print("\n=== Direct comparison ===")
        names = list(results.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                nx_i = np.abs(results[names[i]]['x_freq'])
                nx_j = np.abs(results[names[j]]['x_freq'])
                g = (np.median(nx_i) / np.median(nx_j) - 1) * 100
                print(f"  med|x|: {names[i]} vs {names[j]}: gap={g:.2f}%")

    if args.ref_neufeld:
        print("\n=== Analytic comparison (LC tau convention) ===")
        for name, data in results.items():
            nc = compare_neufeld(data, a_tau0_lc)
            print(f"  {name}: x_peak={nc['x_obs']:.3f}"
                  f" (pred=1.07*(aτ₀)^(1/3)={nc['x_pred']:.3f}),"
                  f" chi2/N={nc['chi2']:.4f}")

    return results


if __name__ == '__main__':
    main()
