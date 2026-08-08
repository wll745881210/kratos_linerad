#!/usr/bin/env python3
"""
Standalone imaging + escape test for the Kratos line_rt module.

Inherits the geometry of test_scaling_wide.py (isotropic midplane
source, Neufeld mean-depth convention) and adds an imaging pass
(camera along +x) to compare BOTH:

  1. Escaped photon spectrum  -> med|x| vs golden (Neufeld eq. 2.24)
  2. Imaging cube spectrum    -> I(x) shape (formal transfer)

Geometry (same as test_scaling_wide.py)
---------------------------------------
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
  n_chan = 32,  v_chan = ±1e6 cm/s  (±10 b)

Usage
-----
  python3 usr_ext/line_rt/tests/test_imaging_neufeld.py \\
      --kratos-root ~/apps/kratos_line_rt
  python3 usr_ext/line_rt/tests/test_imaging_neufeld.py \\
      --kratos-root ~/apps/kratos_line_rt --plots
"""
import argparse, importlib, os, shutil, subprocess, sys, tempfile
import numpy as np
from pathlib import Path

UNIT_L0 = 1.49597870691e13
UNIT_T0 = 1.0
DEFAULT_KRATOS_ROOT = Path(os.path.expanduser('~/apps/kratos_line_rt'))
WORKDIR = Path(tempfile.gettempdir()) / 'line_rt_imaging'
B_SCA_CGS = 1.0e5


def resolve_kratos_root(kratos_root):
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
GOLDEN_TOL = 0.05


def neufeld_peak(a_tau0):
    return 0.881 * a_tau0 ** (1.0 / 3.0)


def neufeld_J(x, a_tau0):
    xa = np.abs(np.asarray(x, dtype=np.float64))
    K = np.sqrt(np.pi ** 4 / 54.0)
    A = np.sqrt(6.0) / 24.0
    return A * xa * xa / (a_tau0 + 1e-35) / np.cosh(
        K * xa * xa * xa / (a_tau0 + 1e-35))


# -- Binary I/O (same as test_scaling_wide.py) ----------------------

def write_fields(filename, fields, mesh, binary_io):
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
    ph = np.asarray(photons, dtype=np.float32)
    bio = binary_io(filename)
    bio.cache('par_n_col', ph.shape[1], dtype='int32')
    bio.cache('par_n_par', ph.shape[0], dtype='int64')
    bio.cache('par_par_dat', ph, dtype='float32')
    bio.save()
    return filename


def read_output(filename, binary_io):
    """Read escaped photons + image cube from Kratos output."""
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


PAR_TEMPLATE = """# Kratos line_rt imaging test - auto-generated

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

    # Channel velocities in code units
    v2c = UNIT_T0 / UNIT_L0
    v_chan_min_code = -v_chan_cgs * v2c
    v_chan_max_code = v_chan_cgs * v2c

    # Camera along +x: theta=pi/2, phi=0
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
    ph[:, 0] = 0.0  # midplane
    ph[:, 1] = rng.uniform(0.0, 1.0, n_radiation)
    ph[:, 2] = rng.uniform(0.0, 1.0, n_radiation)
    mu = rng.uniform(-1.0, 1.0, n_radiation)
    phi = rng.uniform(0.0, 2.0 * np.pi, n_radiation)
    smu = np.sqrt(1.0 - mu * mu)
    ph[:, 3] = smu * np.cos(phi)
    ph[:, 4] = smu * np.sin(phi)
    ph[:, 5] = mu
    ph[:, 6] = 1.0 / n_radiation
    ph[:, 7] = 0.0  # vel = 0 (line centre)
    ph[:, 8] = 0.0  # sv = 0 (monochromatic)
    write_photons(photon_file, ph, binary_io)

    return par_path, n_step


def run_one(tau0_fid, a_voigt, n_radiation, out_dir, tag,
           ph_mode=2, kratos_bin=None, binary_io=None,
           n_chan=32, v_chan_cgs=1e6, t_lim=1800.0):
    print(f"  Kratos: tau0={tau0_fid:.0f}, a={a_voigt}, n={n_radiation},"
          f" ph_mode={ph_mode}, n_chan={n_chan}")

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
    vel = phot.get('vel')
    b_sca_code = B_SCA_CGS * UNIT_T0 / UNIT_L0
    if vel is not None and vel.size > 0:
        x_freq = vel.astype(np.float64) / b_sca_code
        abs_x = np.abs(x_freq)
        med_x = float(np.median(abs_x))
        bins = np.linspace(0, max(15, abs_x.max() * 1.1), 100)
        h, bc = np.histogram(abs_x, bins=bins, density=True)
        x_peak_esc = bc[np.argmax(h)]
        print(f"    ESCAPED: n_esc={len(x_freq)}, med|x|={med_x:.4f},"
              f" x_peak={x_peak_esc:.3f}")
    else:
        med_x = float('nan')
        x_peak_esc = float('nan')
        print("    ESCAPED: no photons")

    # ---- Imaging cube ----
    l_flat = img.get('l')
    i2d = img.get('i2d')
    if l_flat is not None and i2d is not None:
        n_pix = i2d.shape[0] // 2
        n_chan_found = l_flat.size // max(n_pix, 1)
        if n_chan_found > 0 and l_flat.size == n_pix * n_chan_found:
            cube = l_flat.reshape(n_pix, n_chan_found).astype(np.float64)
            I_avg = np.mean(cube, axis=0)
            v2c = UNIT_T0 / UNIT_L0
            dv = 2.0 * v_chan_cgs * v2c / n_chan_found
            vc = -v_chan_cgs * v2c + dv * (np.arange(n_chan_found) + 0.5)
            x_img = vc / b_sca_code
            I_peak = x_img[np.argmax(np.abs(I_avg))]
            I0 = np.interp(0.0, x_img, np.abs(I_avg))
            Imax = np.max(np.abs(I_avg))
            print(f"    IMAGING: n_pix={n_pix}, n_chan={n_chan_found},"
                  f" x_peak={I_peak:.3f}, I(0)/I_max={I0/Imax:.4f}")
        else:
            print(f"    IMAGING: cube shape mismatch"
                  f" (n_pix={n_pix}, l_size={l_flat.size})")
            I_avg = None
            x_img = None
    else:
        print("    IMAGING: no image data")
        I_avg = None
        x_img = None

    return {
        'med_x': med_x, 'x_peak_esc': x_peak_esc, 'n_esc': len(x_freq),
        'I_avg': I_avg, 'x_img': x_img,
    }


def main():
    p = argparse.ArgumentParser(
        description='Standalone imaging + escape test for Kratos line_rt')
    p.add_argument('--tau0', type=float, default=2000.0)
    p.add_argument('--a', dest='a_voigt', type=float, default=0.149)
    p.add_argument('-n', dest='n_radiation', type=int, default=100000)
    p.add_argument('--ph-mode', type=int, default=2)
    p.add_argument('--n-chan', type=int, default=32)
    p.add_argument('--v-chan-cgs', type=float, default=1e6,
                   help='Channel velocity half-range [cm/s] (default 1e6)')
    p.add_argument('--seed-rng', type=int, default=42)
    p.add_argument('--t-lim', type=float, default=1800.0)
    p.add_argument('--kratos-root', type=str, default=str(DEFAULT_KRATOS_ROOT))
    p.add_argument('--workdir', type=str, default=str(WORKDIR))
    p.add_argument('--keep-dir', action='store_true')
    p.add_argument('--plots', action='store_true')
    args = p.parse_args()

    kratos_root, kratos_bin, binary_io = resolve_kratos_root(args.kratos_root)
    print(f"Kratos root: {kratos_root}")
    print(f"Kratos bin:  {kratos_bin}")

    workdir = os.path.expanduser(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix='line_rt_img_', dir=workdir)
    print(f"Run dir: {run_dir}")

    try:
        a_tau0 = args.a_voigt * args.tau0
        pred = neufeld_peak(a_tau0)
        golden = GOLDEN_MED.get(int(args.tau0))
        print(f"\n=== tau0={args.tau0:.0f}, a={args.a_voigt},"
              f" a*tau0={a_tau0:.0f}, Neufeld peak={pred:.3f} ===")
        tag = f"tau{args.tau0:.0f}_pm{args.ph_mode}"
        res = run_one(
            args.tau0, args.a_voigt, args.n_radiation, run_dir, tag,
            ph_mode=args.ph_mode, kratos_bin=kratos_bin, binary_io=binary_io,
            n_chan=args.n_chan, v_chan_cgs=args.v_chan_cgs,
            t_lim=args.t_lim)

        if res is None:
            print("NO RESULT")
            return 1

        # Regression: escaped med|x| vs golden
        print(f"\n--- Regression ---")
        if golden is not None:
            ratio = res['med_x'] / golden
            ok = abs(ratio - 1.0) <= GOLDEN_TOL
            print(f"  med|x| = {res['med_x']:.4f}  golden = {golden:.4f}"
                  f"  ratio = {ratio:.4f}  {'PASS' if ok else 'FAIL'}")
        else:
            print(f"  med|x| = {res['med_x']:.4f}  (no golden for tau0={args.tau0:.0f})")

        # Neufeld comparison
        print(f"  med|x|/Neufeld_peak = {res['med_x'] / pred:.4f}")
        print(f"  x_peak_esc = {res['x_peak_esc']:.3f}  Neufeld peak = {pred:.3f}")

        # Imaging summary
        if res['I_avg'] is not None:
            I = np.abs(res['I_avg'])
            x = res['x_img']
            # Find where I drops to 1% of max
            idx_1pct = np.where(I >= 0.01 * I.max())[0]
            if len(idx_1pct) > 0:
                x_range = x[idx_1pct[-1]] - x[idx_1pct[0]]
                print(f"\n--- Imaging ---")
                print(f"  I_max = {I.max():.4e}")
                print(f"  I(0) = {np.interp(0, x, I):.4e}")
                print(f"  I(0)/I_max = {np.interp(0, x, I) / I.max():.4f}")
                print(f"  1% width: x=[{x[idx_1pct[0]]:.2f},"
                      f" {x[idx_1pct[-1]]:.2f}],"
                      f" width={x_range:.2f}")
                # Flatness in the thick regime (tau > 3)
                thick = np.where(x >= 0)[0]
                if len(thick) > 1:
                    I_thick = I[thick]
                    I_thick_nz = I_thick[I_thick > 0]
                    if len(I_thick_nz) > 1:
                        flatness = float(I_thick_nz.max() / I_thick_nz.min())
                        print(f"  S flatness (x>=0, I>0): {flatness:.2f}")

        if args.plots and res['I_avg'] is not None:
            make_plots(args, res, run_dir)

        return 0
    finally:
        if not args.keep_dir:
            shutil.rmtree(run_dir, ignore_errors=True)
            print(f"Removed: {run_dir}")


def make_plots(args, res, run_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    b_sca_code = B_SCA_CGS * UNIT_T0 / UNIT_L0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Escaped spectrum
    a_tau0 = args.a_voigt * args.tau0
    xp = neufeld_peak(a_tau0)
    xlim = 3.5 * (a_tau0 ** (1.0 / 3.0))
    # We don't have the raw escaped velocities here, just med_x
    ax1.axvline(res['med_x'], color='b', linestyle='--', label=f'med|x|={res["med_x"]:.2f}')
    ax1.axvline(xp, color='gray', linestyle=':', label=f'Neufeld peak={xp:.2f}')
    x_fine = np.linspace(-xlim, xlim, 200)
    J = neufeld_J(x_fine, a_tau0)
    norm = np.trapezoid(J, x_fine)
    if norm > 0:
        J /= norm
    ax1.plot(x_fine, J, 'k-', linewidth=2, label='Neufeld J(x)')
    ax1.set_xlabel('x')
    ax1.set_ylabel('P(x)')
    ax1.set_title(f'Escaped spectrum (med|x|={res["med_x"]:.2f})')
    ax1.legend()
    ax1.set_xlim(-xlim, xlim)
    ax1.grid(True, alpha=0.3)

    # Imaging spectrum
    x = res['x_img']
    I = np.abs(res['I_avg'])
    ax2.plot(x, I, 'b-', linewidth=2, label='Imaging I(x)')
    ax2.set_xlabel('x')
    ax2.set_ylabel('I(x)')
    ax2.set_title('Imaging cube (formal transfer)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    if I.max() > 0:
        ax2.set_ylim(0, I.max() * 1.3)

    fig.suptitle(f'tau0={args.tau0:.0f}, a={args.a_voigt},'
                 f' a*tau0={a_tau0:.0f}, ph_mode={args.ph_mode}',
                 fontsize=13)
    plot_path = os.path.join(args.workdir, 'imaging_neufeld.png')
    fig.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {plot_path}")
    plt.close(fig)


if __name__ == '__main__':
    sys.exit(main())
