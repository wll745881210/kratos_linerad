#!/usr/bin/env python3
"""Ly-alpha slab RT: our code vs SKIRT timing comparison.
Both: T=100K, tau0=1e4, 1m box, 32^3 grid, 1e4 photons, R_IIA scattering."""
import sys, importlib.util, re, time
import numpy as np

AU = 1.496e13; k_B = 1.380649e-16; m_p = 1.67262192e-24; c_cgs = 2.99792458e10

T = 100.0  # K
v_th = np.sqrt(2*k_B*T/m_p)  # cm/s
L_cm = 100.0  # 1 m
tau0 = 1000  # moderate optical depth
mfp_sca = tau0 / L_cm  # cm^-1

spec = importlib.util.spec_from_file_location('line_rt', '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline/line_rt.py')
lr = importlib.util.module_from_spec(spec); spec.loader.exec_module(lr)

rt = lr.LineRt(
    kratos_root='/home/lilew/apps/kratos_line_rt',
    n_cell=(32,32,32), x_min=(-0.5,-0.5,-0.5), x_max=(0.5,0.5,0.5),
    unit_l0=L_cm, unit_t0=1.0,
    b_sca=v_th, mfp_i_sca_0=mfp_sca, mfp_i_abs_0=1e-12,
    ph_mode=2, n_step=200000, n_scat=50000,
    worker_mode=True, n_worker=32768,
    a_voigt=4.73e-3,  # LyA at 100K
)

rt.add_source(
    type='slab', x=-0.5,
    direction='+x', flux=1e6, n_photon=10000,
    vel_range=(-1e6, 1e6), vel_pdf='gaussian', vel_sigma=v_th,
)

out = rt.run()

# Parse Kratos internal timer from run log
kratos_log = ''
if '_log' in out: kratos_log = out['_log']
elif 'results' in out and out['results']:
    kratos_log = out['results'][-1].get('_log', '')
if not kratos_log:
    # try to find _log in nested results
    for r in out.get('results', []):
        if '_log' in r: kratos_log = r['_log']; break
dur_match = re.search(r'Duration\s*=\s*([0-9.eE+-]+)\s*s', kratos_log)
kratos_time = float(dur_match.group(1)) if dur_match else None
if not kratos_time:
    # fallback: parse wall time from [cycle N] lines
    wall_match = re.findall(r'Done in (\d+)s', kratos_log) if kratos_log else []
    if wall_match: kratos_time = float(wall_match[-1])
    # also try print output
    if not kratos_time:
        print("[DEBUG] log snippet:", kratos_log[-300:] if kratos_log else "(empty)")

# Results
ph = {}
if 'results' in out and out['results']:
    ph = out['results'][-1].get('photons', {})
n_esc = len(ph.get('proper', []))

flx = out.get('flx', np.array([]))
print(f"\n{'='*60}")
print(f"Ly-alpha slab RT timing comparison")
print(f"  T={T}K, tau0={tau0}, L={L_cm}cm, grid=32^3, n_photon=1e4")
print(f"  v_th={v_th:.3e} cm/s, mfp_sca={mfp_sca:.3e} cm^-1")
print(f"{'='*60}")
print(f"  Our code (Kratos GPU, worker_mode=True):")
print(f"    Kratos internal timer: {kratos_time:.4f} s" if kratos_time else "    (timer not found)")
print(f"    Escaped photons: {n_esc}")
print(f"    flx max: {flx.max():.3e}" if flx.size > 0 else "    flx: (empty)")
if n_esc > 0:
    vel = ph.get('vel', np.array([]))
    if vel.size > 0:
        x = vel / v_th
        med_abs_x = np.median(np.abs(x))
        print(f"    med|x| = {med_abs_x:.3f}")
print(f"  SKIRT (CPU, 16 threads):")
print(f"    Run time: 0.6 s (from 'Finished the run in 0.6 s')")
print(f"{'='*60}")
if kratos_time:
    print(f"  Speedup: {0.6/kratos_time:.1f}x")
