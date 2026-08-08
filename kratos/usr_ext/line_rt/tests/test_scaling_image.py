#!/usr/bin/env python3
"""
Standalone imaging + escape scaling test for the Kratos line_rt module.

Sweeps a range of Neufeld mean-depth optical depths and measures BOTH:
  1. Escaped photon spectrum  -> med|x| and x_peak (vs golden, Neufeld eq. 2.24)
  2. Imaging cube spectrum   -> |x_peak| of the double-peaked formal transfer

The test directly compares imaging peak vs escaped peak to study their
systematic difference (imaging peak < escaped peak, converging at high a*tau0).

Geometry (inherited from test_scaling_wide.py)
---------------------------------------------
  x_min = (-L/2, 0, 0),  x_max = (L/2, 1, 1)
  n_cell = (128, 2, 2),  L = 1 AU (code: L_code = 1.0)
  Photons: x=0 (midplane), random y/z in [0,1], isotropic dir,
           vel=0, sv=0, proper = 1/n
  mfp_i_sca_0 = 2*tau0 / (sqrt(pi) * L)         [code units]
  b_sca       = 1e5 * unit_t0 / unit_l0          [code units]
  a_voigt     = 0.149

Imaging
-------
  dir_cam = (+1, 0, 0)  (theta=pi/2, phi=0)
  n_chan = 64 (fixed; the bins widen with tau0 since v_chan scales
               as (a*tau0)**(1/3), smoothing MC noise at high depth)
  v_chan = adaptive (4.5x Neufeld peak, contains the escaped wing)

Usage
-----
  python3 usr_ext/line_rt/tests/test_scaling_image.py \\
      --kratos-root ~/apps/kratos_line_rt            # regression
  python3 usr_ext/line_rt/tests/test_scaling_image.py \\
      --kratos-root ~/apps/kratos_line_rt --plots     # + PNGs
  python3 usr_ext/line_rt/tests/test_scaling_image.py \\
      --kratos-root ~/apps/kratos_line_rt --measure   # print goldens

Exit code: 0 = all points within tolerance, 1 = any point outside.
"""
import argparse, importlib, os, shutil, subprocess, sys, tempfile
import numpy as np
from pathlib import Path

UNIT_L0 = 1.49597870691e13
UNIT_T0 = 1.0
DEFAULT_KRATOS_ROOT = Path(os.path.expanduser('~/apps/kratos_line_rt'))
WORKDIR = Path(tempfile.gettempdir()) / 'line_rt_img_scaling'
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


# Golden med|x| from test_scaling_wide.py (ph_mode=2)
GOLDEN_MED = {
    200: 3.1148,
    500: 4.0249,
    2000: 6.1476,
    8000: 9.7357,
    32000: 15.7114,
}

# Golden imaging |x_peak| (double-peak position).
# Placeholder zeros — run with --measure to fill in.
GOLDEN_IMG_PEAK = {
    200: 2.3046,
    500: 3.1278,
    2000: 6.0685,
    8000: 9.6331,
    32000: 15.2916,
}

GOLDEN_TOL = 0.10  # imaging peaks have more scatter than med|x|


# -- Analytic formulas (Neufeld 1990 eq. 2.24, mean-depth convention) --

def neufeld_peak(a_tau0):
    """Neufeld (1990) peak: |x_p| = 0.881 * (a*tau0)**(1/3)."""
    return 0.881 * a_tau0 ** (1.0 / 3.0)


def neufeld_J(x, a_tau0):
    """Neufeld (1990) emergent spectrum, eq. (2.24)."""
    xa = np.abs(np.asarray(x, dtype=np.float64))
    K = np.sqrt(np.pi ** 4 / 54.0)
    A = np.sqrt(6.0) / 24.0
    return A * xa * xa / (a_tau0 + 1e-35) / np.cosh(
        K * xa * xa * xa / (a_tau0 + 1e-35))


# -- Binary I/O (inline, using the repo's own binary_io) -------------

def write_fields(filename, fields, mesh, binary_io):
    """Write Kratos field binary (mirrors pipeline/kratos_io.py).

    Uses cell-centred nodes (n_pts = n_cell, x0 = x_min + 0.5*dx)
    matching the current interp_t convention (ijkl=0, no padding).
    """
    bio = binary_io(filename)
    n_cell = np.asarray(mesh['n_cell'], dtype=np.int32)
    x_min = np.asarray(mesh['x_min'], dtype=np.float32)
    dx = np.asarray(mesh['dx'], dtype=np.float32)
    n_pts = n_cell.copy()

    for prefix in ['mfp_i_sca_0_', 'mfp_i_abs_0_', 'b_sca_',
                   'vel_0_', 'vel_1_', 'vel_2_']:
        if prefix not in fields:
            continue
        raw = np.asarray(fields[prefix], dtype=np.float32)
        arr = raw.reshape(n_cell[2], n_cell[1], n_cell[0])
        bio.cache(f'{prefix}n_pts', n_pts, dtype='int32')
        bio.cache(f'{prefix}x0', x_min + 0.5 * dx, dtype='float32')
        bio.cache(f'{prefix}dx', dx, dtype='float32')
        bio.cache(f'{prefix}data', arr.ravel(), dtype='float32')
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


def read_output(filename, binary_io):
    """Read escaped photons + image cube from a Kratos output binary.

    Returns (phot_dict, img_dict).
    phot_dict: keys 'vel', 'l' (escaped photon arrays).
    img_dict:   keys 'i2d', 'l' (image pixel indices and cube values).
    """
    bio = binary_io(filename)
    bio.open()
    phot = {}
    img = {}
    for raw_key in bio.hmap:
        if '_rank_' in raw_key and raw_key.endswith('_vel'):
            phot['vel'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_l'):
            phot['l'] = bio.as_array(raw_key, 'f')
        elif raw_key.endswith('_i2d_img'):
            img['i2d'] = bio.as_array(raw_key, 'i')
        elif raw_key.endswith('_l_img'):
            img['l'] = bio.as_array(raw_key, 'f')
    bio.close()
    return phot, img


# -- Kratos input generation ----------------------------------------

def estimate_n_scatt(tau0, a_voigt):
    if a_voigt > 1e-6:
        return max(100, int(2.857 * tau0))
    else:
        return max(100, int(tau0 * tau0))


PAR_TEMPLATE = """# Kratos line_rt imaging scaling test - auto-generated

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
prefix_output = img_{tag}
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

[imaging]
enabled        = 1
n_chan         = {n_chan}
dir_cam_theta  = {dir_cam_theta:.10e}
dir_cam_phi    = {dir_cam_phi:.10e}
v_chan_min     = {v_chan_min:.10e}
v_chan_max     = {v_chan_max:.10e}
step_max       = 65535
"""


def generate_kratos_inputs(tau0_fid, a_voigt, n_radiation, out_dir, tag,
                           n_cell=128, L_slab=UNIT_L0,
                           t_lim=1800.0, seed=42, ph_mode=2, binary_io=None,
                           n_chan=32, v_chan_cgs=1e6):
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

    v2c = UNIT_T0 / UNIT_L0
    v_chan_min_code = -v_chan_cgs * v2c
    v_chan_max_code = v_chan_cgs * v2c

    par_path = os.path.join(out_dir, f'imaging_{tag}.par')
    par_content = PAR_TEMPLATE.format(
        unit_l0=UNIT_L0, unit_t0=UNIT_T0,
        x_min=-half_code, x_max=half_code, nx=nx,
        t_lim=t_lim, n_step=n_step, n_radiation=n_radiation,
        field_file=os.path.basename(field_file),
        photon_file=f'photons_{tag}.bin',
        b_sca_code=b_sca_code, a_voigt=a_voigt, ph_mode=ph_mode,
        seed_rng=seed, tag=tag,
        n_chan=n_chan,
        dir_cam_theta=np.pi / 2.0, dir_cam_phi=0.0,
        v_chan_min=v_chan_min_code, v_chan_max=v_chan_max_code,
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


# -- Imaging spectrum analysis --------------------------------------

def extract_imaging_spectrum(img, n_chan, v_chan_cgs):
    """Return (x_chan, I_avg) from the imaging cube (pixel-averaged).

    x_chan = channel velocity / b_sca (dimensionless frequency offset).
    I_avg  = mean over all pixels of the per-channel intensity.
    """
    l_flat = img.get('l')
    i2d = img.get('i2d')
    if l_flat is None or i2d is None:
        return None, None

    n_pix = i2d.shape[0] // 2
    n_chan_found = l_flat.size // max(n_pix, 1)
    if n_chan_found == 0 or l_flat.size != n_pix * n_chan_found:
        return None, None

    cube = l_flat.reshape(n_pix, n_chan_found).astype(np.float64)
    I_avg = np.mean(cube, axis=0)

    b_sca_code = B_SCA_CGS * UNIT_T0 / UNIT_L0
    v2c = UNIT_T0 / UNIT_L0
    dv = 2.0 * v_chan_cgs * v2c / n_chan_found
    vc = -v_chan_cgs * v2c + dv * (np.arange(n_chan_found) + 0.5)
    x_img = vc / b_sca_code

    return x_img, I_avg


def find_imaging_peak(x, I):
    """Find the |x| of the imaging double-peak.

    For a double-peaked spectrum (dip at x=0, peaks at +-x_peak),
    return the average |x_peak| of the two side peaks.

    If no clear double-peak (no dip at center), return the |x| of
    the global maximum.
    """
    I_abs = np.abs(I)
    I_max = np.max(I_abs)
    if I_max == 0:
        return 0.0

    I_center = np.interp(0.0, x, I_abs)
    has_dip = I_center < 0.8 * I_max

    if has_dip:
        pos_mask = x > 0
        neg_mask = x < 0
        if np.any(pos_mask) and np.any(neg_mask):
            x_pos = x[pos_mask]
            I_pos = I_abs[pos_mask]
            x_neg = x[neg_mask]
            I_neg = I_abs[neg_mask]

            peak_pos = x_pos[np.argmax(I_pos)] if len(I_pos) > 0 else 0.0
            peak_neg = x_neg[np.argmax(I_neg)] if len(I_neg) > 0 else 0.0
            return 0.5 * (abs(peak_pos) + abs(peak_neg))

    return abs(x[np.argmax(I_abs)])


# -- Run one configuration ------------------------------------------

def run_one(tau0_fid, a_voigt, n_radiation, out_dir, tag,
            ph_mode=2, kratos_bin=None, binary_io=None,
            n_chan=32, v_chan_cgs=1e6, t_lim=1800.0):
    """Run Kratos for one tau0, return dict with escaped + imaging results."""
    print(f"  Kratos: tau0={tau0_fid:.0f}, a={a_voigt}, n={n_radiation},"
          f" ph_mode={ph_mode}")

    par_path, n_step = generate_kratos_inputs(
        tau0_fid, a_voigt, n_radiation, out_dir, tag,
        ph_mode=ph_mode, binary_io=binary_io,
        n_chan=n_chan, v_chan_cgs=v_chan_cgs, t_lim=t_lim)

    result = subprocess.run(
        [str(kratos_bin), os.path.basename(par_path)],
        cwd=out_dir, capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        print(f"    FAILED: {result.stderr[-300:]}")
        return None

    out_files = sorted(Path(out_dir).glob(f'img_{tag}_*.bin'))
    if not out_files:
        print("    FAILED: no output file")
        return None

    phot, img = read_output(str(out_files[-1]), binary_io)

    # ---- Escaped spectrum ----
    b_sca_code = B_SCA_CGS * UNIT_T0 / UNIT_L0
    vel = phot.get('vel')
    x_freq = None
    if vel is not None and vel.size > 0:
        x_freq = vel.astype(np.float64) / b_sca_code
        abs_x = np.abs(x_freq)
        med_x = float(np.median(abs_x))
        bins = np.linspace(0, max(15, abs_x.max() * 1.1), 100)
        h, bc = np.histogram(abs_x, bins=bins, density=True)
        x_peak_esc = float(bc[np.argmax(h)])
        print(f"    ESCAPED: n_esc={len(x_freq)}, med|x|={med_x:.4f},"
              f" x_peak={x_peak_esc:.3f}")
    else:
        med_x = float('nan')
        x_peak_esc = float('nan')
        print("    ESCAPED: no photons")

    # ---- Imaging cube ----
    x_img, I_avg = extract_imaging_spectrum(img, n_chan, v_chan_cgs)
    if x_img is not None and I_avg is not None:
        x_peak_img = find_imaging_peak(x_img, I_avg)
        I0 = float(np.interp(0.0, x_img, np.abs(I_avg)))
        Imax = float(np.max(np.abs(I_avg)))
        ratio_0 = I0 / Imax if Imax > 0 else 0.0
        print(f"    IMAGING: x_peak={x_peak_img:.3f},"
              f" I(0)/I_max={ratio_0:.4f}")
    else:
        x_peak_img = float('nan')
        ratio_0 = float('nan')
        print("    IMAGING: no image data")

    return {
        'med_x': med_x,
        'x_peak_esc': x_peak_esc,
        'x_peak_img': x_peak_img,
        'n_esc': len(vel) if vel is not None else 0,
        'x_img': x_img,
        'I_avg': I_avg,
        'I0_ratio': ratio_0,
        'x_freq': x_freq if vel is not None else None,
    }


# -- Main -----------------------------------------------------------

def adaptive_v_chan(a_voigt, tau0, b_sca_cgs=B_SCA_CGS):
    """Channel half-range that covers the escaped wing (>=4.5x Neufeld peak).

    The escaped-photon distribution extends well beyond the Neufeld double
    peak (roughly to ~4x the peak at a*tau0 ~ 10^4).  A 3.0x multiplier left
    the tau0=1e5 imaging channels too narrow, so that rays/photons with
    |x| beyond the boundary bins piled up there.  4.5x contains the wing.
    """
    neuf = neufeld_peak(a_voigt * tau0)
    return max(1e5, 4.5 * neuf * b_sca_cgs)


def main():
    p = argparse.ArgumentParser(
        description='Standalone imaging+escape scaling test for Kratos line_rt')
    p.add_argument('--tau0-fid-list', type=float, nargs='+',
                   default=[200, 500, 2000, 8000, 32000],
                   help='Neufeld mean-depth tau0 values')
    p.add_argument('--a', dest='a_voigt', type=float, default=0.149,
                   help='Voigt a parameter (default 0.149)')
    p.add_argument('-n', dest='n_radiation', type=int, default=100000)
    p.add_argument('--ph-mode', type=int, default=2,
                   help='Kratos ph_mode (default 2)')
    p.add_argument('--n-chan', type=int, default=64)
    p.add_argument('--v-chan-cgs', type=float, default=0.0,
                   help='Channel velocity half-range [cm/s] '
                        '(default 0 = adaptive: 4.5x Neufeld peak)')
    p.add_argument('--seed-rng', type=int, default=42)
    p.add_argument('--t-lim', type=float, default=1800.0)
    p.add_argument('--kratos-root', type=str, default=str(DEFAULT_KRATOS_ROOT),
                   help='Kratos build tree root')
    p.add_argument('--workdir', type=str, default=str(WORKDIR))
    p.add_argument('--tol', type=float, default=GOLDEN_TOL,
                   help='regression tolerance on imaging |x_peak| (fraction)')
    p.add_argument('--plots', action='store_true')
    p.add_argument('--measure', action='store_true',
                   help='print golden values and exit (no regression)')
    p.add_argument('--keep-dir', action='store_true')
    args = p.parse_args()

    kratos_root, kratos_bin, binary_io = resolve_kratos_root(args.kratos_root)
    print(f"Kratos root: {kratos_root}")
    print(f"Kratos bin:  {kratos_bin}")

    workdir = os.path.expanduser(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix='line_rt_imgscal_', dir=workdir)
    print(f"Run dir: {run_dir}")

    try:
        measured = {}
        for tau0_fid in args.tau0_fid_list:
            a_tau0 = args.a_voigt * tau0_fid
            pred = neufeld_peak(a_tau0)
            print(f"\n=== tau0={tau0_fid:.0f}, a={args.a_voigt},"
                  f" a*tau0={a_tau0:.0f}, Neufeld peak={pred:.3f} ===")
            tag = f"tau{tau0_fid:.0f}_pm{args.ph_mode}"
            if args.v_chan_cgs > 0:
                vc = args.v_chan_cgs
                nc = args.n_chan
            else:
                # Fixed n_chan: v_chan scales as (a*tau0)**(1/3), so the
                # bins widen with tau0 -- smoothing MC noise at high depth
                # (fine bins expose single-bin spikes in the source fn).
                vc = adaptive_v_chan(args.a_voigt, tau0_fid)
                nc = args.n_chan
            print(f"    v_chan={vc:.3e} cm/s, n_chan={nc}")
            res = run_one(
                tau0_fid, args.a_voigt, args.n_radiation, run_dir, tag,
                ph_mode=args.ph_mode, kratos_bin=kratos_bin,
                binary_io=binary_io,
                n_chan=nc, v_chan_cgs=vc,
                t_lim=args.t_lim)
            measured[tau0_fid] = res

        if args.measure:
            print("\nGOLDEN_IMG_PEAK = {")
            for tau0_fid in args.tau0_fid_list:
                res = measured.get(tau0_fid)
                val = res['x_peak_img'] if res else float('nan')
                print(f"    {tau0_fid:.0f}: {val:.4f},")
            print("}")
            return 0

        # ---- Regression + comparison table ----
        n_fail = 0
        hdr = (f"{'tau0':>7} {'med|x|':>8} {'golden_m':>8}"
               f" {'x_esc':>7} {'x_img':>7} {'Neufeld':>8}"
               f" {'img/N':>6} {'esc/N':>6} {'img/esc':>8}  status")
        print(f"\n{hdr}")
        print('-' * len(hdr))
        for tau0_fid in args.tau0_fid_list:
            res = measured.get(tau0_fid)
            if res is None:
                print(f"{tau0_fid:7.0f} {'---':>8} {'---':>8}"
                      f" {'---':>7} {'---':>7} {'---':>8}"
                      f" {'---':>6} {'---':>6} {'---':>8}  FAIL")
                n_fail += 1
                continue

            a_tau0 = args.a_voigt * tau0_fid
            neuf = neufeld_peak(a_tau0)
            g_med = GOLDEN_MED.get(tau0_fid, float('nan'))
            g_img = GOLDEN_IMG_PEAK.get(tau0_fid, float('nan'))

            med = res['med_x']
            x_esc = res['x_peak_esc']
            x_img = res['x_peak_img']

            img_n = x_img / neuf if neuf > 0 else 0.0
            esc_n = x_esc / neuf if neuf > 0 else 0.0
            img_esc = x_img / x_esc if x_esc > 0 else 0.0

            # Regression: imaging peak vs golden (if golden > 0)
            ok = True
            if not np.isnan(g_img) and g_img > 0:
                ok = abs(x_img / g_img - 1.0) <= args.tol
            if not ok:
                n_fail += 1

            tag_str = 'PASS' if ok else 'FAIL'
            print(f"{tau0_fid:7.0f} {med:8.3f} {g_med:8.3f}"
                  f" {x_esc:7.2f} {x_img:7.2f} {neuf:8.3f}"
                  f" {img_n:6.3f} {esc_n:6.3f} {img_esc:8.3f}  {tag_str}")

        print('-' * len(hdr))
        print(f"{'PASS' if n_fail == 0 else f'{n_fail} FAILURES'}")

        if args.plots:
            make_plots(args, measured, run_dir)

        return 0 if n_fail == 0 else 1
    finally:
        if not args.keep_dir:
            shutil.rmtree(run_dir, ignore_errors=True)
            print(f"Removed: {run_dir}")


# -- Plots ----------------------------------------------------------

def make_plots(args, measured, run_dir):
    """Save scaling_image_peaks.png and scaling_image_spectra.png."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    tau0s = args.tau0_fid_list
    at_arr = np.array([args.a_voigt * t for t in tau0s])
    sort_idx = np.argsort(at_arr)
    at_fine = np.logspace(
        np.log10(max(at_arr.min(), 1)), np.log10(at_arr.max() * 1.5), 100)

    # ---- Peak scaling comparison ----
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(at_fine, neufeld_peak(at_fine), 'k--', linewidth=2,
            label='Neufeld: $0.881(a\\tau_0)^{1/3}$')

    med_vals = np.array([measured.get(t, {}).get('med_x', np.nan)
                         for t in tau0s])[sort_idx]
    esc_vals = np.array([measured.get(t, {}).get('x_peak_esc', np.nan)
                         for t in tau0s])[sort_idx]
    img_vals = np.array([measured.get(t, {}).get('x_peak_img', np.nan)
                         for t in tau0s])[sort_idx]

    ax.plot(at_arr[sort_idx], med_vals, 'bs-', markersize=8,
            linewidth=1.5, label='Escaped med$|x|$')
    ax.plot(at_arr[sort_idx], esc_vals, 'b^--', markersize=8,
            linewidth=1.5, label='Escaped $|x|_{\\rm peak}$')
    ax.plot(at_arr[sort_idx], img_vals, 'ro-', markersize=8,
            linewidth=1.5, label='Imaging $|x|_{\\rm peak}$')

    ax.set_xlabel('$a \\tau_0$ (mean-depth)')
    ax.set_ylabel('$|x|$')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.legend()
    plot1 = os.path.join(args.workdir, 'scaling_image_peaks.pdf')
    fig.savefig(plot1, bbox_inches='tight')
    print(f"Saved: {plot1}")
    plt.close(fig)

    # ---- Spectrum grid ----
    n_pts = len(tau0s)
    n_cols = min(3, n_pts)
    n_rows = (n_pts + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols,
                             figsize=(6 * n_cols, 4.5 * n_rows),
                             squeeze=False)
    try:
        for idx, tau0_fid in enumerate(tau0s):
            ax = axes[idx // n_cols][idx % n_cols]
            res = measured.get(tau0_fid)
            if res is None:
                ax.set_visible(False)
                continue

            a_tau0 = args.a_voigt * tau0_fid
            xp = neufeld_peak(a_tau0)

            # Data-driven x-range: cover the escaped wing so the histogram
            # does not pile up at the boundary bins.  Fall back to the
            # Neufeld scaling if the escaped data are unavailable.
            x_esc = res.get('x_freq')
            if x_esc is not None and len(x_esc) > 0:
                xlim = max(3.0 * xp, float(np.percentile(np.abs(x_esc), 99.9)))
            else:
                xlim = max(3.5 * (a_tau0 ** (1.0 / 3.0)), 3.0 * xp)
            xlim = float(xlim) * 1.05

            # Neufeld analytic
            bins = np.linspace(-xlim, xlim, 81)
            bc = 0.5 * (bins[:-1] + bins[1:])
            J = neufeld_J(bc, a_tau0)
            if J.max() > 0:
                J = J / J.max()
            ax.plot(bc, J, 'k:', linewidth=2, label='Neufeld $J(x)$')

            # Imaging spectrum
            if res.get('x_img') is not None and res.get('I_avg') is not None:
                x_img = res['x_img']
                I_img = np.abs(res['I_avg'])
                if I_img.max() > 0:
                    I_img = I_img / I_img.max()
                mask = np.abs(x_img) <= xlim
                ax.plot(x_img[mask], I_img[mask], 'b-', linewidth=1.5,
                        label='Imaging $I(x)$')

            # Escaped photon histogram
            if x_esc is not None:
                h_esc, edges = np.histogram(x_esc, bins=bins, density=True)
                bc_esc = 0.5 * (edges[:-1] + edges[1:])
                if h_esc.max() > 0:
                    h_esc = h_esc / h_esc.max()
                ax.plot(bc_esc, h_esc, 'g--', linewidth=1.5,
                        label='Escaped $F(x)$')

            # Analytic double-peak location only (one pair of dotted lines).
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
        plot2 = os.path.join(args.workdir, 'scaling_image_spectra.pdf')
        fig.savefig(plot2, bbox_inches='tight')
        print(f"Saved: {plot2}")
        plt.close(fig)
    finally:
        pass


if __name__ == '__main__':
    sys.exit(main())
