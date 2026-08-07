"""Paper-run for the ISM diffuse-cloud test: OH 18cm + CO J=1->0.

Identical physics to ~/scratch/ism/ism_rt.py (2-level LTE user_defined
transitions, ph_mode=2, n_step=5000, n_scat=1000, 64x64 px, face-on),
but with 5 velocity channels centred at v = -2,-1,0,+1,+2 km/s, and
saves the imaging cubes + run metadata for the publication figure
(make_ism_figures.py) and the manuscript text.

Outputs (in ~/scratch/ism/):
  ism_paper_cubes.npz  -- cube_oh, cube_co (n_pix,5) CGS, i2d, v_chan,
                          mesh geometry
  ism_paper_meta.json  -- wall-clock per species, transition parameters,
                          escaped-packet statistics
"""
import sys, os, json, time, importlib.util, numpy as np

PIPELINE = '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline/line_rt.py'
_spec = importlib.util.spec_from_file_location('line_rt', PIPELINE)
lr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lr)
sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline')
from molecular.transition_info import TransitionInfo
sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline/docs/external_tests/ism')
from read_ism import load_ism_data

OUT_NPZ  = os.path.expanduser('~/scratch/ism/ism_paper_cubes.npz')
OUT_META = os.path.expanduser('~/scratch/ism/ism_paper_meta.json')

# ============================================================
# 1. Load ISM simulation data
# ============================================================
print("Loading ISM data...")
g = load_ism_data()
print("  n_CO: mean=%.3e max=%.3e cm^-3" % (g['n_CO'].mean(), g['n_CO'].max()))
print("  n_OH: mean=%.3e max=%.3e cm^-3" % (g['n_OH'].mean(), g['n_OH'].max()))
print("  T:    mean=%.1f max=%.1f K" % (g['T'].mean(), g['T'].max()))
print("  vel0: std=%.3f km/s" % (g['vel0'].std()/1e5))

def n_oh_xyz(X, Y, Z): return g['n_OH']
def n_co_xyz(X, Y, Z): return g['n_CO']
def T_xyz(X, Y, Z):    return g['T']
def vel0_xyz(X, Y, Z): return g['vel0']
def vel1_xyz(X, Y, Z): return g['vel1']
def vel2_xyz(X, Y, Z): return g['vel2']

# 5 channels at v = -2,-1,0,+1,+2 km/s (cell-edges convention in the
# pipeline: v_k = v_min + k*dv with dv=(v_max-v_min)/(n_chan-1)).
n_chan = 5
v_span = 2e5   # cm/s = 2 km/s
img_kw = dict(n_chan=n_chan, v_chan=(-v_span, v_span),
              dir_cam=(0.0, 0.0), img_resol=(64, 64))

meta = {
    'n_chan': n_chan,
    'v_span_cgs': v_span,
    'img_resol': [64, 64],
    'dir_cam': [0.0, 0.0],
    'ph_mode': 2, 'n_step': 5000, 'n_scat': 1000,
    'mfp_i_abs_0': 1e-20,
    'grid': {'n_cell': [128, 128, 128],
             'x_min': [float(v) for v in g['x_min']],
             'x_max': [float(v) for v in g['x_max']],
             'unit_l0': float(g['unit_l0'])},
    'data_stats': {
        'n_CO_mean': float(g['n_CO'].mean()), 'n_CO_max': float(g['n_CO'].max()),
        'n_OH_mean': float(g['n_OH'].mean()), 'n_OH_max': float(g['n_OH'].max()),
        'T_mean': float(g['T'].mean()),       'T_max': float(g['T'].max()),
        'vel0_std_kms': float(g['vel0'].std()/1e5),
    },
    'species': {},
}

def run_species(tag, transition_info, n_species):
    print("\n=== %s ===" % tag)
    t0 = time.perf_counter()
    rt = lr.LineRt(
        kratos_root='/home/lilew/apps/kratos_line_rt',
        n_cell=(128, 128, 128),
        x_min=tuple(g['x_min']), x_max=tuple(g['x_max']),
        unit_l0=g['unit_l0'],
        transition_info=transition_info,
        n_species=n_species, temperature=T_xyz,
        vel=(vel0_xyz, vel1_xyz, vel2_xyz),
        mfp_i_abs_0=1e-20,
        ph_mode=2, n_step=5000, n_scat=1000,
        imaging=img_kw,
    )
    out = rt.run()
    wall = time.perf_counter() - t0
    img = out['image']
    cube = np.asarray(img['cube_cgs'])          # (n_pix, n_chan) CGS
    i2d  = np.asarray(img['i2d'])
    print("  cube: max=%.4e inf=%d  wall=%.1f s"
          % (cube.max(), np.isinf(cube).sum(), wall))

    # escaped-packet statistics (Monte Carlo pass)
    spec = out.get('spectrum', {})
    n_esc = None
    if spec and 'vel' in spec:
        n_esc = int(len(np.asarray(spec['vel']).ravel()))
    meta['species'][tag] = {
        'transition': tag,
        'wall_time_s': wall,
        'cube_max_cgs': float(cube.max()),
        'n_inf_pixels': int(np.isinf(cube).sum()),
        'n_escaped_packets': n_esc,
    }
    return cube, i2d, np.asarray(img.get('v_chan', (-v_span, v_span)),
                                 dtype=float)

# ============================================================
# 2. OH 18cm (optically thick, tau~1)
# ============================================================
ti_oh = TransitionInfo.user_defined(
    A_ul=8.632e-11, freq_GHz=1.66655,
    g_u=4.0, g_l=4.0, E_u_K=0.0556,
    mol_mass=17.0, species_name='OH')
cube_oh, i2d, v_chan = run_species('OH_18cm', ti_oh, n_oh_xyz)

# ============================================================
# 3. CO J=1->0 (optically thin, tau~0.05)
# ============================================================
ti_co = TransitionInfo.user_defined(
    A_ul=7.203e-8, freq_GHz=115.271,
    g_u=3.0, g_l=1.0, E_u_K=5.53,
    mol_mass=28.0, species_name='CO')
cube_co, i2d, v_chan = run_species('CO_J1-0', ti_co, n_co_xyz)

# ============================================================
# 4. Save
# ============================================================
np.savez(OUT_NPZ,
         cube_oh=cube_oh, cube_co=cube_co,
         i2d=i2d, v_chan=v_chan,
         n_cell=np.array([128, 128, 128]),
         x_min=g['x_min'], x_max=g['x_max'],
         unit_l0=np.array([g['unit_l0']]))
with open(OUT_META, 'w') as f:
    json.dump(meta, f, indent=2)
print("\nSaved %s" % OUT_NPZ)
print("Saved %s" % OUT_META)
print("Done.")
