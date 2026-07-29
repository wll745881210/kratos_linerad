"""ph_mode=1 (Voigt) comparison: Kratos vs Python reference MCRT."""
import subprocess, sys, os, math, json, shutil
import numpy as np

sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline')
sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/kratos/visual')

from pipeline.kratos_io import write_field_data, write_photon_data, read_output

np.random.seed(42)

# --- Parameters ---
A_VOIGT = 0.01
B_SCA_CGS = 1e5
L_HALF = 5.0
TAU0_HALF = 500  # total tau0=1000
MFP_I_SCA_0 = TAU0_HALF / L_HALF
N_CELL = 64
N_PHOTONS = 5000
N_STEP = int(5e6)

# Units
UNIT_L0 = 1.49597870691e13  # code → CGS
UNIT_T0 = 1.0
B_SCA_CODE = B_SCA_CGS * UNIT_T0 / UNIT_L0  # 1e5 * 1/1.49598e13 ≈ 6.68e-9

# Coarse grid
L_SLAB = 2 * L_HALF
dx = L_SLAB / N_CELL
x0 = -L_HALF

# Geometry dict
geo = {
    'n_cell': np.array([N_CELL, 2, 2], dtype=np.int32),
    'x_min': np.array([x0, 0., 0.], dtype=np.float32),
    'dx': np.array([dx, 1., 1.], dtype=np.float32),
}

# Field arrays (Kratos uses nz,ny,nx)
shape = (geo['n_cell'][2], geo['n_cell'][1], geo['n_cell'][0])
mfp_i = np.full(shape, MFP_I_SCA_0, dtype=np.float32)
b_sca = np.full(shape, B_SCA_CODE, dtype=np.float32)

fields = {
    'mfp_i_sca_0_': mfp_i,
    'b_sca_': b_sca,
    'vel_0_': np.zeros(shape, dtype=np.float32),
    'vel_1_': np.zeros(shape, dtype=np.float32),
    'vel_2_': np.zeros(shape, dtype=np.float32),
    'temp_': np.full(shape, 1e4, dtype=np.float32),
}

# Source: midplane isotropic
ox = np.full(N_PHOTONS, -L_HALF + L_SLAB * 0.5, dtype=np.float64)
oy = np.random.uniform(0., 1., N_PHOTONS)
oz = np.random.uniform(0., 1., N_PHOTONS)
mu = 2 * np.random.uniform(0., 1., N_PHOTONS) - 1
phi = 2 * math.pi * np.random.uniform(0., 1., N_PHOTONS)
sm = np.sqrt(np.maximum(0., 1. - mu * mu))
odx = sm * np.cos(phi)
ody = sm * np.sin(phi)
odz = mu
op = np.full(N_PHOTONS, 1.0, dtype=np.float64)  # unit proper

# photon array: x,y,z, dx,dy,dz, proper
photons = np.column_stack([ox, oy, oz, odx, ody, odz, op])

# --- Setup working dir ---
workdir = '/tmp/ph_mode1_test'
os.makedirs(workdir, exist_ok=True)

# --- Run Kratos ---
np.savetxt(os.path.join(workdir, 'bc_flags.txt'), [0], fmt='%d')
write_field_data(os.path.join(workdir, 'fields_cycle0.bin'), fields, geo)
write_photon_data(os.path.join(workdir, 'photons_cycle0.bin'), photons)

par_content = f'''# Kratos parameter file for a=0 Voigt test

[unit]
length  = {UNIT_L0:.12e}
time    = 1.0
density = 1.0

[mesh]
x_min = {-L_HALF} 0 0
x_max = {L_HALF} 1 1
n_cell_global = {N_CELL} 2 2

[cycle]
n_cycle_lim = 1
t_lim  = 2
dt_output = 2

[particle]
n_step = {N_STEP}
n_scat = {N_STEP}
output = 1
n_radiation = {N_PHOTONS}

[line_rt]
field_file  = fields_cycle0.bin
photon_file = photons_cycle0.bin
ph_mode     = 1
b_sca       = {B_SCA_CODE:.10e}
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = {A_VOIGT}
ray_output  = 0
ray_id      = -1

[boundary]
kinds = fre fre per per per per
'''
with open(os.path.join(workdir, 'a0.par'), 'w') as f:
    f.write(par_content)

# Copy par to scratch and run
scratch = os.path.expanduser('~/scratch/line_rt')
for f in os.listdir(workdir):
    if f.endswith('.bin') or f.endswith('.par') or f == 'bc_flags.txt':
        os.makedirs(scratch, exist_ok=True)
        # Always copy to scratch
        subprocess.run(f'cp {os.path.join(workdir, f)} {scratch}/', shell=True, check=True)

KRATOS_BIN = os.path.expanduser('~/apps/kratos_line_rt/bin/kratos')
result = subprocess.run(
    [KRATOS_BIN, 'a0.par'],
    capture_output=True, text=True, timeout=120,
    cwd=scratch
)
print('=== Kratos stdout ===')
print(result.stdout[-2000:])
if result.stderr:
    print('=== stderr ===')
    print(result.stderr[-2000:])

# Read output: use the last output file (final state)
out_files = sorted([f for f in os.listdir(scratch) if f.startswith('test_')])
escaped = None
if out_files:
    out_path = os.path.join(scratch, out_files[-1])  # last = final
    output = read_output(out_path)
    print(f'\nOutput file: {out_files[-1]}')
    n_cell_r = output.get('n_cell')
    if n_cell_r is not None:
        print(f'  n_cell = {n_cell_r}')
    phot = output.get('photons', {})
    if phot:
        x_flat = phot.get('x', np.array([], dtype=np.float32))
        vel_raw = phot.get('vel', np.array([], dtype=np.float32))
        l_raw = phot.get('l', np.array([], dtype=np.float32))
        n_esc = len(l_raw)
        if n_esc > 0 and x_flat.size >= 3:
            esc_x = x_flat[0::3]  # x component
            esc_y = x_flat[1::3]
            esc_z = x_flat[2::3]
            # vel is in code units → x_freq = vel_code / b_sca_code
            x_freq_kratos = vel_raw / B_SCA_CODE
            escaped = {
                'n_esc': n_esc,
                'x': esc_x,
                'y': esc_y,
                'z': esc_z,
                'vel_code': vel_raw,
                'x_freq': x_freq_kratos,
                'proper': l_raw,
            }
            print(f'  escaped: {n_esc}')
            print(f'  x range: [{esc_x.min():.3f}, {esc_x.max():.3f}]')
            print(f'  x_freq range: [{x_freq_kratos.min():.2e}, {x_freq_kratos.max():.2e}]')
        else:
            print('  No escaped photons found')
    else:
        print('  No escaped photons in output')

# --- Run Python reference ---
print('\n=== Python reference (ph_mode=1) ===')
sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline/docs/reference_mcrt')
import mcrt as ref
py_res = ref.mcrt_slab(
    L_slab=L_SLAB, tau0=TAU0_HALF * 2, tau_abs=0,
    b_sca=B_SCA_CGS, n_photons=N_PHOTONS, seed=42,
    ph_mode=1, a_voigt=A_VOIGT, n_cell=N_CELL,
)
# escaped[n_esc, 3]: col0=vel_CGS, col1=proper, col2=sv
esc_py = py_res['escaped']
term_py = py_res['term_reason']
x_freq_py = esc_py[:, 0] / B_SCA_CGS
print(f'  Escaped: {esc_py.shape[0]} / {N_PHOTONS}')
print(f'  x_freq range: [{x_freq_py.min():.2e}, {x_freq_py.max():.2e}]')
n_term = np.bincount(term_py.astype(int)) if term_py.max() > 0 else {}
print(f'  Termination: { {k: int(v) for k, v in enumerate(n_term) if v > 0} }')

# --- Compare ---
print('\n=== Comparison ===')
if escaped is not None:
    xf_k = escaped['x_freq']
    xf_p = x_freq_py
    print(f'  {"Metric":20s} {"Kratos":>10s} {"Python":>10s} {"Diff%":>10s}')
    print(f'  {"-"*52}')
    for name, k, p in [
        ('n_escaped', escaped['n_esc'], esc_py.shape[0]),
        ('median|x_freq|', float(np.median(np.abs(xf_k))),
         float(np.median(np.abs(xf_p)))),
        ('mean|x_freq|', float(np.mean(np.abs(xf_k))),
         float(np.mean(np.abs(xf_p)))),
        ('std(x_freq)', float(np.std(xf_k)),
         float(np.std(xf_p))),
        ('P(|x_freq|>3)', float(np.mean(np.abs(xf_k) > 3)),
         float(np.mean(np.abs(xf_p) > 3))),
    ]:
        dp = (k - p) / p * 100 if p != 0 else 0
        print(f'  {name:20s} {k:>10.4g} {p:>10.4g} {dp:>+9.2f}%')
else:
    print('  No Kratos escaped photons available')

# Save for later analysis
result_data = {
    'a_voigt': A_VOIGT,
    'tau0': int(TAU0_HALF * 2),
    'params': {
        'L_slab': L_SLAB,
        'n_photons': N_PHOTONS,
        'n_step': N_STEP,
        'n_cell': N_CELL,
    },
}
if escaped is not None:
    result_data['kratos'] = {
        'n_esc': escaped['n_esc'],
        'x_freq': [float(np.median(np.abs(escaped['x_freq']))),
                    float(np.std(escaped['x_freq']))],
        'p_gt3': float(np.mean(np.abs(escaped['x_freq']) > 3)),
    }
result_data['python'] = {
    'n_esc': esc_py.shape[0],
    'x_freq': [float(np.median(np.abs(x_freq_py))),
                float(np.std(x_freq_py))],
    'p_gt3': float(np.mean(np.abs(x_freq_py) > 3)),
}
with open(os.path.join(workdir, 'comparison.json'), 'w') as f:
    json.dump(result_data, f, indent=2)
print(f'\nSaved to {workdir}/comparison.json')
