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
2. Generates source photons from one face (11-column format)
3. Loads CO molecular data, selects the J=1→0 transition
4. Runs 3 cycles of MC → population → MC iteration
5. Plots the emergent spectrum, flux maps, and convergence

Reference: Neufeld, D.A. 1990, ApJ, 350, 216
"""

import sys, os
_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, _PROJECT)
sys.path.insert(0, '/home/lilew/Seafile/seafile_sync/code/line_rt_pipeline')

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
from molecular.lamda_format import load_species_transition

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
    n_cell=(64, 2, 2),
    x_min=(-5, 0, 0),
    x_max=(5, 0.2, 0.2),
)
n_tot = mesh['n_tot']
print(f"Mesh: {mesh['n_cell']} cells, total = {n_tot}")

# ── 2. Define physical parameters ──────────────────────────────────────
#
# τ₀ = 100   (line-center optical depth across the slab)
# tau_abs = 1  (absorption optical depth across the slab)
#

tau0_slab = 100.0      # total line-center scattering optical depth
tau_abs   = 1.0        # total absorption optical depth
dx_cm     = mesh['dx'][0] * 1.49598e13   # cell width in cm
slab_cm   = 10.0 * 1.49598e13            # 10 AU in cm

b_sca     = 1.0e5                  # Doppler b-parameter [cm/s] ≈ 1 km/s
mol_mass  = 28.0                   # g/mol (CO)
temperature = 100.0                # K

print(f"τ₀ = {tau0_slab:.0f}")
print(f"dx = {dx_cm:.2e} cm")

# ── 3. Build field arrays ──────────────────────────────────────────────

fields = {
    'b_sca':       uniform_field(b_sca,     n_tot),
    'temp':        uniform_field(temperature, n_tot),
    'vel_0':       uniform_field(b_sca,     n_tot),  # v_x gradient
    'vel_1':       np.zeros(n_tot, dtype=np.float64),
    'vel_2':       np.zeros(n_tot, dtype=np.float64),
}

# ── 4. Generate source photons ─────────────────────────────────────────
#
# External slab source at x=-5 (left face), uniformly distributed across
# the y-z face. All photons initially directed along +x.
# 10-column format: x,y,z, dir_x,dir_y,dir_z, proper, vel, sigma, amplitude
#

print("Generating photons...")
n_photon = 50000
L = 0.8 * Lsun
lam = 2.35e-4     # 2.35 microns (CO v=0→2 band head)

sigma     = b_sca / np.sqrt(2)   # intrinsic Doppler width
amplitude = 1.0                   # line strength (unit for scaling)

ph_arr = np.zeros((n_photon, 10), dtype=np.float64)
ph_arr[:, 0] = -4.5                    # just inside left face
ph_arr[:, 1] = np.random.uniform(0, 0.2, n_photon)   # uniform across y-face
ph_arr[:, 2] = np.random.uniform(0, 0.2, n_photon)   # uniform across z-face
ph_arr[:, 3] = 1.0                     # all photons directed along +x
ph_arr[:, 4] = 0.0
ph_arr[:, 5] = 0.0
ph_arr[:, 6] = (L / (h * c / lam)) / n_photon   # proper weight
ph_arr[:, 7] = 0.0                     # vel: zero velocity offset (line center)
ph_arr[:, 8] = sigma                   # sigma: intrinsic Doppler width
ph_arr[:, 9] = amplitude               # amplitude: line strength

E_ph = h * c / lam
N_dot = L / E_ph
print(f"L = {L:.2e} erg/s")
print(f"E_ph = {E_ph:.2e} erg")
print(f"N_dot = {N_dot:.2e} ph/s")
print(f"proper weight = {ph_arr[0, 6]:.2e} ph/packet")
print(f"sigma = {sigma:.1f} cm/s, amplitude = {amplitude}")
print(f"n_photon = {n_photon}")

# ── 5. Load CO molecular data with explicit transition selection ───────

lamda_path = os.path.join(_PROJECT, 'molecular', 'embedded', 'co.dat')

print(f"Loading CO data from: {lamda_path}")
co, tr = load_species_transition(lamda_path, freq_GHz=115.271202)
tr_idx = co.find_transition_idx(tr)
print(f"  {co.n_levels} rotational levels, {co.n_transitions} transitions")
print(f"  Selected transition: J={tr.upper}→{tr.lower}")
print(f"    A_ul = {tr.A_ul:.2e} s⁻¹")
print(f"    ν_0  = {tr.freq_GHz:.1f} GHz")
print(f"    λ    = {tr.wavelength_um:.1f} µm")
print(f"    E_u/K = {tr.E_u_K:.1f} K")
print(f"  Transition index: {tr_idx}")

# Compute n_gas from tau0 and cross-section
sigma_co = co.cross_section(0, b_sca)
n_gas = (tau0_slab / slab_cm) / sigma_co  # cm⁻³
print(f"  n_gas (from τ₀={tau0_slab:.0f}): {n_gas:.2e} cm⁻³")

# ── 6. Run MC iteration ────────────────────────────────────────────────

print(f"Running 3 MC cycles...")
results, final_pops = iterate(
    ph_arr, co, fields, mesh, n_cycles=3,
    n_photon=n_photon, n_step=10000, n_scat=100000,
    ph_mode=1,  # CFR mode
    work_dir='/tmp/plane_parallel_example',
    n_gas=n_gas,
    transition_idx=tr_idx,
    mol_mass=mol_mass,
    unit_l0=1.49598e13,
    unit_t0=1.0,
)

# ── 7. Plot results ────────────────────────────────────────────────────

fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 7a. Emergent spectrum (final cycle)
print("\nPlotting emergent spectrum...")
if 'photons' in results[-1]:
    plot_emergent_spectrum(axes[0, 0], results[-1]['photons'], bins=60,
                           xlim=(-3e5, 3e5), label=f'Cycle {len(results)}')
    axes[0, 0].set_title('Emergent Spectrum (velocity space)')
else:
    axes[0, 0].text(0.5, 0.5, 'No escaped photons\n(1D slab)',
                    transform=axes[0, 0].transAxes, ha='center', va='center')

# 7b. Flux slice (x-z plane at y=0)
print("Plotting flux slice...")
plot_flux_slice(axes[0, 1], results[-1]['flx'], mesh,
                title='Flux Map (log scale)')

# 7c. Population map
print("Plotting population map...")
if len(final_pops) >= 2:
    pop_vals = list(final_pops.values())
    n_ground = pop_vals[0]
    n_excited = pop_vals[1]
    plot_population_map(axes[1, 0], n_excited / (n_ground + n_excited + 1e-30),
                        mesh, title='Excited Fraction',
                        cbar_label='ne/(ng+ne) [dimensionless]')

# 7d. Convergence history
print("Plotting convergence...")
pop_history = []
for res in results:
    if 'populations' in res:
        pop_history.append(res['populations'])
if len(pop_history) >= 2:
    plot_convergence(axes[1, 1], pop_history, list(range(len(pop_history))))
else:
    axes[1, 1].text(0.5, 0.5, f'{len(results)} cycles completed\n(no convergence data)',
                   transform=axes[1, 1].transAxes, ha='center')

fig.tight_layout()
outpath = os.path.join(os.path.dirname(__file__), 'plane_parallel_results.png')
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")

# ── 8. Print summary ────────────────────────────────────────────────────

for k, res in enumerate(results):
    print(f"\nCycle {k+1}:")
    exc_flux = res.get('exc_flux_flat', res.get('excitation_flux'))
    flx = res.get('flx')
    if exc_flux is not None:
        print(f"  excitation_flux_max = {exc_flux.max():.4f}")
    if flx is not None:
        print(f"  flx_max = {flx.max():.4f}")
    if 'photons' in res:
        n_esc = len(res['photons']['vel']) if res['photons'].get('vel') is not None else 0
        print(f"  n_escaped = {n_esc}")
    else:
        print("  n_escaped = 0")

print("\nPlane-parallel slab example complete.")
print(f"See {outpath} for summary plots.")
print("For detailed physics, see LINE_RT_DOCS.html")
