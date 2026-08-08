#!/usr/bin/env python3
"""
Standalone regression test for the Kratos line_rt module.

Runs the Kratos binary alone (no Python reference MCRT, no pipeline
code) over a range of Neufeld mean-depth optical depths and compares
the emergent escape-frequency distribution against golden med|x|
values measured from the validated build.  The Neufeld (1990) peak
0.881 (a tau0)^(1/3) is printed as physics context.

tau convention (mean-depth, half-slab)
--------------------------------------
Both Kratos and the analytic solution use the raw-Hjerting opacity

    kappa(x) = mfp_i_sca_0 * H(a, x)        (Kratos photon.h)

with integral H(a, x) dx = sqrt(pi).  The half-slab mean depth is

    tau_m = mfp_i_sca_0 * sqrt(pi) * L_slab / 2 .

To run at a target Neufeld mean depth tau0_fid we set

    mfp_i_sca_0 = 2 * tau0_fid / (sqrt(pi) * L_slab) .

The Neufeld ORIGINAL eq. (2.24) is used (peak 0.881 (a tau0)^(1/3)),
which is convention-independent.  The Verhamme (2006) line-centre
transcription (peak 1.066 (a tau0_LC)^(1/3)) is NOT used: it assumes
H(a, 0) = 1, which fails for a >= 0.1.

Usage
-----
  python3 usr_ext/line_rt/tests/test_scaling_wide.py \
      --kratos-root ~/apps/kratos_line_rt            # regression
  python3 usr_ext/line_rt/tests/test_scaling_wide.py \
      --kratos-root ~/apps/kratos_line_rt --plots    # + PNGs
  python3 usr_ext/line_rt/tests/test_scaling_wide.py \
      --kratos-root ~/apps/kratos_line_rt --measure  # print goldens

Exit code: 0 = all points within tolerance, 1 = any point outside.

The --kratos-root must be a Kratos build tree containing both
bin/kratos (the binary) and visual/binary_io.py (the I/O module).

To update the golden values after a deliberate physics change:
run with --measure and paste the printed GOLDEN dict below.
"""
import argparse, importlib, os, shutil, subprocess, sys, tempfile
import numpy as np
from pathlib import Path

UNIT_L0 = 1.49597870691e13
UNIT_T0 = 1.0
DEFAULT_KRATOS_ROOT = Path(os.path.expanduser('~/apps/kratos_line_rt'))
WORKDIR = Path(tempfile.gettempdir()) / 'line_rt_regress'
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

# Golden med|x| per (tau0_fid, ph_mode).  Measured 2026-07-31 with the
# unified log-CDF USampler build: a = 0.149, n = 100000, seed_rng = 42,
# L_slab = 1.49598e14 cm, isotropic midplane source.
GOLDEN = {
    (200, 1): 3.1213,
    (200, 2): 3.1148,
    (200, 3): 2.0965,
    (500, 1): 4.0350,
    (500, 2): 4.0249,
    (500, 3): 3.0330,
    (2000, 1): 6.1552,
    (2000, 2): 6.1476,
    (2000, 3): 5.5094,
    (8000, 1): 9.7628,
    (8000, 2): 9.7357,
    (8000, 3): 8.9381,
    (32000, 1): 15.7006,
    (32000, 2): 15.7114,
    (32000, 3): 15.1140,
    (300, 1): 3.470,
    (300, 2): 3.489,
    (300, 3): 2.423,
    (1000, 1): 4.947,
    (1000, 2): 4.953,
    (1000, 3): 4.136,
    (3000, 1): 7.023,
    (3000, 2): 7.014,
    (3000, 3): 6.407,
    (10000, 1): 10.511,
    (10000, 2): 10.523,
    (10000, 3): 9.552,
    (30000, 1): 15.379,
    (30000, 2): 15.350,
    (30000, 3): 14.712,
    (100000, 1): 23.459,
    (100000, 2): 23.427,
    (100000, 3): 23.147,
}

GOLDEN_TOL = 0.05
# ph_mode=3 uses the approximate voigt_H blend (AGENTS.md: underestimates
# med|x| at low a*tau0, converges at high a*tau0).  Give it a looser band so
# the documented approximation does not trip the regression gate.
GOLDEN_TOL_PM3 = 0.10

# -- Analytic formulas (Neufeld 1990 eq. 2.24, mean-depth convention) --

def neufeld_peak(a_tau0):
    """Neufeld (1990) peak: |x_p| = 0.881 * (a*tau0)**(1/3)."""
    return 0.881 * a_tau0 ** (1.0 / 3.0)


def neufeld_J(x, a_tau0):
    """Neufeld (1990) emergent spectrum, eq. (2.24), mean-depth convention."""
    xa = np.abs(np.asarray(x, dtype=np.float64))
    K = np.sqrt(np.pi ** 4 / 54.0)
    A = np.sqrt(6.0) / 24.0
    return A * xa * xa / (a_tau0 + 1e-35) / np.cosh(
        K * xa * xa * xa / (a_tau0 + 1e-35))


# -- Binary I/O (inline, using the repo's own binary_io) -------------

def write_fields(filename, fields, mesh, binary_io):
    """Write Kratos field binary (mirrors pipeline/kratos_io.py)."""
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
    """Write Kratos photon binary (mirrors pipeline/kratos_io.py)."""
    ph = np.asarray(photons, dtype=np.float32)
    bio = binary_io(filename)
    bio.cache('par_n_col', ph.shape[1], dtype='int32')
    bio.cache('par_n_par', ph.shape[0], dtype='int64')
    bio.cache('par_par_dat', ph, dtype='float32')
    bio.save()
    return filename


def read_escaped_photons(filename, binary_io):
    """Read escaped photons from a Kratos output binary.

    Returns dict with keys 'x', 'dir', 'l', 'vel' (float32 arrays).
    """
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


# -- Kratos input generation ----------------------------------------

def estimate_n_scatt(tau0, a_voigt):
    if a_voigt > 1e-6:
        return max(100, int(2.857 * tau0))
    else:
        return max(100, int(tau0 * tau0))


PAR_TEMPLATE = """# Kratos line_rt standalone regression test - auto-generated

[unit]
length  = {unit_l0:.6e}
time    = {unit_t0}
density = 1.0

[device]
seed_rng = {seed_rng}

[mesh]
x_min = {x_min:.6f} 0 0
x_max = {x_max:.6f} 1 1
n_cell_global = {nx} 2 2

[cycle]
except_ferr   = 1
prefix_output = test_{tag}
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
ph_mode     = {ph_mode}
b_sca       = {b_sca_code:.10e}
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = {a_voigt}

[boundary]
kinds = fre fre per per per per
"""


def generate_kratos_inputs(tau0_fid, a_voigt, n_radiation, out_dir, tag,
                           n_cell=128, L_slab=1.49598e14,
                           t_lim=1800.0, seed=42, ph_mode=1, binary_io=None):
    """Generate Kratos field/photon/par files for mean depth tau0_fid."""
    L_slab_code = L_slab / UNIT_L0
    nx = n_cell
    dx_code = L_slab_code / nx
    half_code = L_slab_code / 2

    mfp_i_sca_0_code = (2.0 * tau0_fid) / (np.sqrt(np.pi) * L_slab) * UNIT_L0
    b_sca_code = B_SCA_CGS * UNIT_T0 / UNIT_L0

    n_tot = nx * 2 * 2
    fields = {
        'mfp_i_sca_0_': np.full(n_tot, np.float32(mfp_i_sca_0_code)),
        'mfp_i_abs_0_': np.zeros(n_tot, dtype=np.float32),
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

    n_sc_est = estimate_n_scatt(tau0_fid, a_voigt)
    n_step = max(n_radiation * n_sc_est * 3, 5000000)

    par_path = os.path.join(out_dir, f'neufeld_{tag}.par')
    par_content = PAR_TEMPLATE.format(
        unit_l0=UNIT_L0, unit_t0=UNIT_T0,
        x_min=-half_code, x_max=half_code, nx=nx,
        t_lim=t_lim, n_step=n_step, n_radiation=n_radiation,
        field_file=os.path.basename(field_file),
        photon_file=f'photons_{tag}.bin',
        b_sca_code=b_sca_code, a_voigt=a_voigt, ph_mode=ph_mode,
        seed_rng=seed, tag=tag,
    )
    with open(par_path, 'w') as fp:
        fp.write(par_content)

    photon_file = os.path.join(out_dir, f'photons_{tag}.bin')
    rng = np.random.default_rng(42)
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

    return par_path, n_step


def run_kratos_one(tau0_fid, a_voigt, n_radiation, out_dir, tag,
                   ph_mode=1, kratos_bin=None, binary_io=None):
    """Run Kratos for one (tau0, ph_mode) point, return med|x| and x_peak."""
    print(f"  Kratos: tau0_fid={tau0_fid:.1f}, a={a_voigt}, n={n_radiation},"
          f" ph_mode={ph_mode}")
    par_path, n_step = generate_kratos_inputs(
        tau0_fid, a_voigt, n_radiation, out_dir, tag, ph_mode=ph_mode,
        binary_io=binary_io)

    result = subprocess.run(
        [str(kratos_bin), os.path.basename(par_path)],
        cwd=out_dir, capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        print(f"    FAILED: {result.stderr[-300:]}")
        return None

    out_files = sorted(Path(out_dir).glob(f'test_{tag}_*.bin'))
    if not out_files:
        return None
    phot = read_escaped_photons(str(out_files[-1]), binary_io)
    vel = phot.get('vel')
    if vel is None or vel.size == 0:
        return None

    b_sca_code = B_SCA_CGS * UNIT_T0 / UNIT_L0
    x_freq = vel.astype(np.float64) / b_sca_code
    abs_x = np.abs(x_freq)
    if np.isnan(abs_x).any():
        print(f"    FAILED: {np.isnan(abs_x).sum()} NaN escaped velocities")
        return None

    bins = np.linspace(0, max(15, abs_x.max() * 1.1), 100)
    h, bc = np.histogram(abs_x, bins=bins, density=True)
    x_peak = bc[np.argmax(h)]
    med_x = float(np.median(abs_x))
    print(f"    n_esc={len(x_freq)}, x_peak={x_peak:.3f},"
          f" med|x|={med_x:.3f}, n_step={n_step}")
    return {'x_peak': x_peak, 'med_x': med_x, 'n_esc': len(x_freq)}


# -- Main ------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description='Standalone regression test for Kratos line_rt')
    p.add_argument('--tau0-fid-list', type=float, nargs='+',
                   default=[200, 500, 2000, 8000, 32000],
                   help='Neufeld mean-depth tau0 values')
    p.add_argument('--a', dest='a_voigt', type=float, default=0.149,
                   help='Voigt a parameter (default 0.149)')
    p.add_argument('--n', dest='n_radiation', type=int, default=100000)
    p.add_argument('--ph-mode-list', type=int, nargs='+', default=[1, 2, 3],
                   help='Kratos ph_mode values to test')
    p.add_argument('--tol', type=float, default=GOLDEN_TOL,
                   help='regression tolerance on med|x| (fraction)')
    p.add_argument('--seed-rng', type=int, default=42,
                   help='Kratos [device] seed_rng')
    p.add_argument('--kratos-root', type=str, default=str(DEFAULT_KRATOS_ROOT),
                   help='Kratos build tree root (must contain bin/kratos '
                        'and visual/binary_io.py)')
    p.add_argument('--workdir', type=str, default=str(WORKDIR),
                   help=f'parent dir for run dirs and plots'
                        f' (default: {WORKDIR})')
    p.add_argument('--plots', action='store_true',
                   help='also save scaling_wide_*.png plots')
    p.add_argument('--measure', action='store_true',
                   help='print golden med|x| values and exit')
    p.add_argument('--keep-dir', action='store_true',
                   help='keep the temporary run directory')
    args = p.parse_args()

    kratos_root, kratos_bin, binary_io = resolve_kratos_root(args.kratos_root)
    print(f"Kratos root: {kratos_root}")
    print(f"Kratos bin:  {kratos_bin}")

    workdir = os.path.expanduser(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix='line_rt_regress_', dir=workdir)
    print(f"Run dir: {run_dir}")

    try:
        measured = {}
        for tau0_fid in args.tau0_fid_list:
            a_tau0 = args.a_voigt * tau0_fid
            pred = neufeld_peak(a_tau0)
            print(f"\n=== tau0={tau0_fid:.0f} (mean-depth), a={args.a_voigt},"
                  f" a*tau0={a_tau0:.0f}, Neufeld peak={pred:.3f} ===")
            for pm in args.ph_mode_list:
                tag = f"fid{tau0_fid:.0f}_a{args.a_voigt}_pm{pm}"
                res = run_kratos_one(tau0_fid, args.a_voigt,
                                     args.n_radiation, run_dir, tag,
                                     ph_mode=pm, kratos_bin=kratos_bin,
                                     binary_io=binary_io)
                if res is None:
                    print(f"    {tag}: NO RESULT (run failed)")
                    measured[(tau0_fid, pm)] = None
                else:
                    measured[(tau0_fid, pm)] = res
                    if res['n_esc'] < 0.99 * args.n_radiation:
                        print(f"    WARNING: n_esc={res['n_esc']} < "
                              f"n_radiation={args.n_radiation}")

        if args.measure:
            print("\nGOLDEN = {")
            for tau0_fid in args.tau0_fid_list:
                for pm in args.ph_mode_list:
                    res = measured.get((tau0_fid, pm))
                    val = res['med_x'] if res else float('nan')
                    print(f"    ({tau0_fid}, {pm}): {val:.4f},")
            print("}")
            return 0

        # Regression comparison
        n_fail = 0
        print(f"\n{'tau0':>7} {'pm':>2} {'med|x|':>8} {'golden':>8}"
              f" {'ratio':>6} {'Neufeld':>8} {'med/N':>6}  status")
        print('-' * 65)
        for tau0_fid in args.tau0_fid_list:
            a_tau0 = args.a_voigt * tau0_fid
            pred = neufeld_peak(a_tau0)
            for pm in args.ph_mode_list:
                res = measured.get((tau0_fid, pm))
                golden = GOLDEN.get((tau0_fid, pm))
                if res is None or golden is None or np.isnan(golden):
                    print(f"{tau0_fid:7.0f} {pm:2d} {'---':>8} {'---':>8}"
                          f" {'---':>6} {pred:8.3f} {'---':>6}  NO GOLDEN")
                    n_fail += 1
                    continue
                ratio = res['med_x'] / golden
                tol = args.tol if pm != 3 else max(args.tol, GOLDEN_TOL_PM3)
                ok = abs(ratio - 1.0) <= tol
                n_fail += 0 if ok else 1
                print(f"{tau0_fid:7.0f} {pm:2d} {res['med_x']:8.3f}"
                      f" {golden:8.3f} {ratio:6.3f} {pred:8.3f}"
                      f" {res['med_x'] / pred:6.3f}"
                      f"  {'PASS' if ok else 'FAIL'}")

        print('-' * 65)
        print(f"{'PASS' if n_fail == 0 else f'{n_fail} FAILURES'}")

        if args.plots:
            make_plots(args, measured, run_dir, binary_io)

        return 0 if n_fail == 0 else 1
    finally:
        if not args.keep_dir:
            shutil.rmtree(run_dir, ignore_errors=True)
            print(f"Removed: {run_dir}")


def make_plots(args, measured, run_dir, binary_io):
    """Save scaling_wide_xpeak.png and scaling_wide_spectra.png."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    tau0s = args.tau0_fid_list
    at_arr = np.array([args.a_voigt * t for t in tau0s])
    sort_idx = np.argsort(at_arr)
    at_fine = np.logspace(
        np.log10(max(at_arr.min(), 1)), np.log10(at_arr.max() * 1.5), 100)

    pm_styles = {
        1: ('r', 's', '-'),
        2: ('b', '^', '--'),
        3: ('g', 'o', ':'),
    }

    # Peak scaling
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(at_fine, neufeld_peak(at_fine), 'k--', linewidth=2,
            label='Neufeld: $0.881(a\\tau_0)^{1/3}$')
    for pm in args.ph_mode_list:
        c, m, ls = pm_styles.get(pm, ('g', 'o', '-'))
        vals = np.array([measured.get((t, pm), {}).get('x_peak', np.nan)
                         for t in tau0s])[sort_idx]
        ax.plot(at_arr[sort_idx], vals, color=c, marker=m, linestyle=ls,
                markersize=8, linewidth=1.5, label=f'Kratos ph_mode={pm}')
    ax.set_xlabel('$a \\tau_0$ (mean-depth)')
    ax.set_ylabel('$|x|_{\\rm peak}$')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.legend()
    plot1 = os.path.join(WORKDIR, 'scaling_wide_xpeak.pdf')
    fig.savefig(plot1, bbox_inches='tight')
    print(f"Saved: {plot1}")
    plt.close(fig)

    # Spectrum grid with Neufeld overlay
    n_pts = len(tau0s)
    n_cols = min(3, n_pts)
    n_rows = (n_pts + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols,
                             figsize=(5.5 * n_cols, 4.5 * n_rows),
                             squeeze=False)
    try:
        for idx, tau0_fid in enumerate(tau0s):
            ax = axes[idx // n_cols][idx % n_cols]
            a_tau0 = args.a_voigt * tau0_fid
            xp = neufeld_peak(a_tau0)
            xlim = 3.5 * (a_tau0 ** (1.0 / 3.0))
            # Gather the escaped photons for all ph_modes first so the
            # x-range can be made data-driven (contain the wing) before
            # any histogram is computed.
            x_esc_all = []
            for pm in args.ph_mode_list:
                tag = f"fid{tau0_fid:.0f}_a{args.a_voigt}_pm{pm}"
                phot = read_escaped_photons(
                    str(Path(run_dir) / f'test_{tag}_00000.bin'),
                    binary_io)
                if 'vel' not in phot:
                    continue
                b_sca_code = B_SCA_CGS * UNIT_T0 / UNIT_L0
                x_freq = phot['vel'].astype(np.float64) / b_sca_code
                x_esc_all.append(x_freq)
            if x_esc_all:
                x_esc_concat = np.concatenate([np.abs(v) for v in x_esc_all])
                xlim = max(xlim, float(np.percentile(x_esc_concat, 99.9)))
            xlim = float(xlim) * 1.05
            bins = np.linspace(-xlim, xlim, 81)
            bc = 0.5 * (bins[:-1] + bins[1:])
            for pm, x_freq in zip(args.ph_mode_list, x_esc_all):
                c, m, ls = pm_styles.get(pm, ('g', 'o', '-'))
                h, _ = np.histogram(x_freq, bins=bins, density=True)
                if h.max() > 0:
                    h = h / h.max()
                ax.plot(bc, h, color=c, linestyle=ls, linewidth=1.5,
                        label=f'Kratos ph_mode={pm}')
            J = neufeld_J(bc, a_tau0)
            if J.max() > 0:
                J = J / J.max()
            ax.plot(bc, J, 'k:', linewidth=2, label='Neufeld analytic')
            for s in (1, -1):
                ax.axvline(s * xp, color='0.7', linestyle=':',
                           linewidth=0.8)
            ax.set_xlim(-xlim, xlim)
            ax.set_xlabel('$x$')
            ax.set_ylabel('Normalised intensity')
            ax.set_title(f'$\\tau_0={tau0_fid:.0f}$,'
                         f' $(a\\tau_0)^{{1/3}}={a_tau0 ** (1/3):.1f}$',
                         )
            if idx == 0:
                ax.legend()
            
        for idx in range(n_pts, n_rows * n_cols):
            axes[idx // n_cols][idx % n_cols].set_visible(False)
        fig.tight_layout()
        plot3 = os.path.join(WORKDIR, 'scaling_wide_spectra.pdf')
        fig.savefig(plot3, bbox_inches='tight')
        print(f"Saved: {plot3}")
        plt.close(fig)
    finally:
        pass


if __name__ == '__main__':
    sys.exit(main())
