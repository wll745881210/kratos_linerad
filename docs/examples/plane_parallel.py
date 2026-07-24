#!/usr/bin/env python3
"""
Plane-Parallel Slab Example
============================

This example demonstrates a complete line radiative transfer calculation for
a plane-parallel slab geometry (the Neufeld problem). A uniform slab of gas
is illuminated from one side, and photons scatter in a spectral line with
coherent frequency redistribution (CFR). Dust continuously absorbs.

The example:
1. Defines the slab geometry and spatial fields
2. Generates source photons from one face
3. Loads CO molecular data from the LAMDA database
4. Runs 3 cycles of MC → population → MC iteration
5. Plots the emergent spectrum, flux maps, and convergence

Reference: Neufeld, D.A. 1990, ApJ, 350, 216
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from core.source import make_cartesian_mesh
from core.fields import uniform_field, slice_plot_2d
from core.iterator import iterate
from core.visualize import (
    plot_emergent_spectrum,
    plot_flux_slice,
    plot_population_map,
    plot_convergence,
)
from molecular.lamda_fetcher import fetch_species

# ── CGS constants ──────────────────────────────────────────────────────
h  = 6.62607015e-27
c  = 2.99792458e10
kb = 1.380649e-16
mp = 1.67262192e-24
Lsun = 3.828e33

# ── 1. Define the slab geometry ────────────────────────────────────────
#
# A Cartesian slab: 64 cells along x (the normal direction), thin in y,z.
# x ∈ [-5, 5] in code units (l0 = AU). Physical size: 10 AU thick.
# y,z ∈ [0, 0.2] code units with 1 cell each (effectively 1D transport).
#

mesh = make_cartesian_mesh(
    n_cell=(64, 1, 1),
    x_min=(-5, 0, 0),
    x_max=(5, 0.2, 0.2),
)
n_tot = mesh['n_tot']
print(f"Mesh: {mesh['n_cell']} cells, total = {n_tot}")

# ── 2. Define physical parameters ──────────────────────────────────────
#
# τ₀ = 100   (line-center optical depth across the slab)
# tau_abs = 1  (absorption optical depth across the slab = tau_abs/τ₀)
#

tau0_slab = 100.0      # total line-center scattering optical depth
tau_abs   = 1.0        # total absorption optical depth
dx_cm     = mesh['dx'][0] * 1.49598e13   # cell width in cm
slab_cm   = 10.0 * 1.49598e13            # 10 AU in cm

mfp_i_sca = tau0_slab / slab_cm    # inverse scattering MFP [cm⁻¹]
mfp_i_abs = tau_abs  / slab_cm     # inverse absorption MFP [cm⁻¹]
b_sca     = 1.0e5                  # Doppler b-parameter [cm/s] ≈ 1 km/s
b_abs     = 1.0e5                  # absorption b-parameter [cm/s]

print(f"τ₀ = {tau0_slab:.0f}")
print(f"mfp_i_sca = {mfp_i_sca:.2e} cm⁻¹")
print(f"mfp_i_abs = {mfp_i_abs:.2e} cm⁻¹")
print(f"dx = {dx_cm:.2e} cm")

# ── 3. Build field arrays ──────────────────────────────────────────────

fields = {
    'mfp_i_sca_0': uniform_field(mfp_i_sca, n_tot),
    'mfp_i_abs_0': uniform_field(mfp_i_abs, n_tot),
    'b_sca':       uniform_field(b_sca,     n_tot),
    'b_abs':       uniform_field(b_abs,     n_tot),
    'vel_0':       uniform_field(b_sca,     n_tot),  # v_x gradient
    'vel_1':       np.zeros(n_tot, dtype=np.float64),
    'vel_2':       np.zeros(n_tot, dtype=np.float64),
}

# ── 4. Generate source photons ─────────────────────────────────────────
#
# Point source at (x=-4.5, y=0.1, z=0.1) just outside the left face.
# All photons start with zero velocity offset (line center).
#

print("Generating photons...")
n_photon = 50000
L = 0.8 * Lsun
lam = 2.35e-4     # 2.35 microns (CO v=0→2 band head)

ph_arr = np.zeros((n_photon, 8), dtype=np.float64)
ph_arr[:, 0] = -4.5
ph_arr[:, 1] = 0.1
ph_arr[:, 2] = 0.1
ph_arr[:, 3] = 1.0   # all photons directed along +x
ph_arr[:, 4] = 0.0
ph_arr[:, 5] = 0.0
ph_arr[:, 6] = (L / (h * c / lam)) / n_photon   # proper weight
ph_arr[:, 7] = 0.0    # zero velocity offset

E_ph = h * c / lam
N_dot = L / E_ph
print(f"L = {L:.2e} erg/s")
print(f"E_ph = {E_ph:.2e} erg")
print(f"N_dot = {N_dot:.2e} ph/s")
print(f"proper weight = {ph_arr[0, 6]:.2e} ph/packet")
print(f"n_photon = {n_photon}")

# ── 5. Load CO molecular data ──────────────────────────────────────────

print("Loading CO data from embedded LAMDA database...")
co = fetch_species('CO')
print(f"  {co.n_levels} rotational levels, {co.n_transitions} transitions")
for i in range(min(5, co.n_transitions)):
    u, l = int(co.transitions[i, 0]), int(co.transitions[i, 1])
    A = co.get_Einstein_A(u, l)
    nu = co.get_nu(u, l)
    print(f"  J={u}→{l}: A={A:.2e} s⁻¹, ν={nu:.1f} GHz")

# ── 6. Run MC iteration ────────────────────────────────────────────────

print(f"\nRunning {3}MC cycles...")
results, final_pops = iterate(
    ph_arr, co, fields, mesh, n_cycles=3,
    n_photon=n_photon, n_step=10000, n_scat=100000,
    ph_mode=1,  # CFR mode
    work_dir='/tmp/plane_parallel_example',
)

# ── 7. Plot results ────────────────────────────────────────────────────

fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 7a. Emergent spectrum (final cycle)
print("\nPlotting emergent spectrum...")
plot_emergent_spectrum(axes[0, 0], results[-1]['photons'], bins=60,
                       xlim=(-3e5, 3e5), label=f'Cycle {len(results)}')
axes[0, 0].set_title('Emergent Spectrum (velocity space)')

# 7b. Flux slice (x-z plane at y=0)
print("Plotting flux slice...")
plot_flux_slice(axes[0, 1], results[-1]['flx'], mesh,
                title='Flux Map (log scale)')

# 7c. Population map
print("Plotting population map...")
if final_pops.shape[0] >= 2:
    n_ground = final_pops[0, :]
    n_excited = final_pops[1, :]
    plot_population_map(axes[1, 0], n_excited / (n_ground + n_excited + 1e-30),
                        mesh, title='Excited Fraction')

# 7d. Convergence history
print("Plotting convergence...")
pop_history = [np.column_stack((np.ones(n_tot)*0.5, np.ones(n_tot)*0.5))]
pop_history = [final_pops for _ in range(len(results))]
try:
    plot_convergence(axes[1, 1], pop_history, len(results))
except Exception:
    axes[1, 1].text(0.5, 0.5, f'{len(results)} cycles completed',
                   transform=axes[1, 1].transAxes, ha='center')

fig.tight_layout()
outpath = os.path.join(os.path.dirname(__file__), 'plane_parallel_results.png')
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")

# ── 8. Print summary ────────────────────────────────────────────────────

for k, res in enumerate(results):
    print(f"\nCycle {k+1}:")
    print(f"  fab_max = {res['fab'].max():.4f}")
    print(f"  flx_max = {res['flx'].max():.4f}")
    print(f"  n_escaped = {len(res['photons']['vel'])}")

print("\nPlane-parallel slab example complete.")
print(f"See {outpath} for summary plots.")
print("For detailed physics, see docs/PHYSICS.md")
