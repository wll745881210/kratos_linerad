#!/usr/bin/env python3
"""
Plane-Parallel Slab with Callable Fields
=========================================

This example demonstrates a complete line radiative transfer calculation for
a plane-parallel slab geometry using **callable functions** for scattering
particle density, absorption opacity, and temperature.

Unlike plane_parallel.py (which uses pre-computed flat arrays), this example
shows how to define arbitrary spatial functions that Kratos evaluates at each
cell centre during field initialisation.

The CO J=1→0 transition is explicitly selected by specifying `upper=1, lower=0`
rather than by its rest frequency, making the transition identity clear.

Reference: Neufeld, D.A. 1990, ApJ, 350, 216
"""

import sys, os
_HERE = os.path.dirname(os.path.realpath(__file__))
_PROJECT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _PROJECT)

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
AU = 1.49598e13
Lsun = 3.828e33

# ── 1. Slab geometry ───────────────────────────────────────────────────

mesh = make_cartesian_mesh(
    n_cell=(64, 2, 2),
    x_min=(-5, 0, 0),
    x_max=(5, 0.2, 0.2),
)
n_tot = mesh['n_tot']
slab_cm = 10.0 * AU
b_param = 1.0e5                                       # Doppler b = 1 km/s

x_cell = np.linspace(-5, 5, mesh['n_cell'][0])        # AU (code units)
x_cm   = x_cell * AU                                   # cm

print(f"Mesh: {mesh['n_cell']} cells, total = {n_tot}")
print(f"Slab thickness: 10 AU = {slab_cm:.2e} cm")
print(f"Doppler b = {b_param:.1e} cm/s")

# ── 2. Callable field functions ────────────────────────────────────────
#
# These functions receive arrays (X, Y, Z) of cell-centre coordinates in
# AU (Kratos code units) and must return arrays of the same shape.
#
# The user can replace the bodies below with any desired spatial dependence,
# e.g. power-law profiles, Gaussian disks, or temperature gradients.

def n_total_callable(X, Y, Z):
    """Scattering particle number density [cm⁻³] as a function of position.

    For this example we return a constant 1e4 cm⁻³ everywhere.
    Replace with e.g. power-law: n0 * (x / x0)**-1.5
    """
    return np.full_like(X, 1e4, dtype=np.float64)


def mfp_i_sca_callable(X, Y, Z):
    """Line-centre scattering inverse mean free path [cm⁻¹].

    For a uniform slab with τ₀ = 100 across 10 AU:
    mfp_i_sca = τ₀ / L = 100 / (10 AU) ≈ 6.7e-13 cm⁻¹

    A spatially varying example:
        tau_profile = 100 * np.exp(-0.5 * (X / 2.)**2)
        return tau_profile / slab_cm
    """
    tau0 = 100.0
    return np.full_like(X, tau0 / slab_cm, dtype=np.float64)


def mfp_i_abs_callable(X, Y, Z):
    """Inverse mean free path for dust absorption [cm⁻¹].

    Here: τ_abs = 1 across the slab (1% of scattering opacity).
    A spatially varying example:
        return tau0_abs / slab_cm * np.exp(-X**2 / 2.)
    """
    tau_abs = 1.0
    return np.full_like(X, tau_abs / slab_cm, dtype=np.float64)


def temperature_callable(X, Y, Z):
    """Gas temperature [K] as a function of position.

    Here: linear gradient from 10 K (left, x=-5) to 100 K (right, x=+5).
    A constant-temperature example:
        return np.full_like(X, 50.0)
    """
    return 10.0 + (100.0 - 10.0) * (X + 5.0) / 10.0


print("\nCallable fields defined:")
print(f"  n_total:     constant 1e4 cm⁻³")
print(f"  mfp_i_sca:   constant τ₀=100 → {100 / slab_cm:.3e} cm⁻¹")
print(f"  mfp_i_abs:   constant τ_abs=1 → {1 / slab_cm:.3e} cm⁻¹")
print(f"  temperature: linear 10 K (left) → 100 K (right)")

# ── 3. Build field arrays by evaluating callables ──────────────────────

X, Y, Z = np.meshgrid(
    np.linspace(-5, 5, mesh['n_cell'][0]),
    np.linspace(0, 0.2, mesh['n_cell'][1]),
    np.linspace(0, 0.2, mesh['n_cell'][2]),
    indexing='ij',
)

fields = {
    'mfp_i_sca_0': mfp_i_sca_callable(X, Y, Z).ravel().astype(np.float64),
    'mfp_i_abs_0': mfp_i_abs_callable(X, Y, Z).ravel().astype(np.float64),
    'b_sca':       uniform_field(b_param, n_tot),
    'temp':        temperature_callable(X, Y, Z).ravel().astype(np.float64),
    'vel_0':       np.zeros(n_tot, dtype=np.float64),   # static medium
    'vel_1':       np.zeros(n_tot, dtype=np.float64),
    'vel_2':       np.zeros(n_tot, dtype=np.float64),
}

print(f"\nBuilt {len(fields)} field arrays, each {n_tot} cells")

# ── 4. Generate source photons ─────────────────────────────────────────

n_photon = 20000
L = 0.8 * Lsun
lam = 2.35e-4                                         # cm
E_ph = h * c / lam
proper_weight = (L / E_ph) / n_photon
sigma   = b_param / np.sqrt(2)
amplitude = 1.0

print(f"\nSource: L={L:.2e} erg/s, λ={lam:.2e} cm, E_ph={E_ph:.2e} erg")
print(f"  N_dot = {L/E_ph:.2e} ph/s")
print(f"  proper_weight = {proper_weight:.2e} ph/packet")
print(f"  sigma = {sigma:.1f} cm/s")

# 10-column photons: x,y,z, dir_x,dir_y,dir_z, proper, vel, sigma, amplitude
ph_arr = np.zeros((n_photon, 10), dtype=np.float64)
ph_arr[:, 0] = -4.5          # x = left face + small offset
ph_arr[:, 1] = 0.1           # y
ph_arr[:, 2] = 0.1           # z
ph_arr[:, 3] = 1.0           # all photons → +x
ph_arr[:, 4] = 0.0
ph_arr[:, 5] = 0.0
ph_arr[:, 6] = proper_weight
ph_arr[:, 7] = 0.0           # vel = 0 (line centre)
ph_arr[:, 8] = sigma         # intrinsic Doppler width
ph_arr[:, 9] = amplitude     # line strength

# ── 5. Load CO and select transition explicitly ────────────────────────
#
# Using upper=1, lower=0 to identify CO J=1→0 without needing to know
# the rest frequency (though freq_GHz also works).
#
# Other useful ways to specify the transition:
#   freq_GHz=115.271202   — by rest frequency
#   wavelength_um=2600.76 — by wavelength
#   E_u_K=3.87            — by upper-level energy (for CO, J=1 has ~3.9 K)

lamda_path = os.path.join(_PROJECT, 'molecular', 'embedded', 'co.dat')
co, tr = load_species_transition(lamda_path, upper=1, lower=0)
tr_idx = co.find_transition_idx(tr)

print(f"\nCO species loaded from {os.path.basename(lamda_path)}")
print(f"  Levels: {co.n_levels}, Transitions: {co.n_transitions}")
print(f"  Selected:  CO J={tr.upper}→{tr.lower}  ← explicitly by level numbers")
print(f"    A_ul  = {tr.A_ul:.2e} s⁻¹")
print(f"    ν₀    = {tr.freq_GHz:.2f} GHz")
print(f"    λ     = {tr.wavelength_um:.1f} µm")
print(f"    E_u/K = {tr.E_u_K:.2f} K")
print(f"  Transition index: {tr_idx}")

# ── 6. Run MC iteration ────────────────────────────────────────────────

print(f"\nRunning 3 MC cycles with {n_photon} photons each ...")
results, final_pops = iterate(
    ph_arr, co, fields, mesh,
    n_cycles=3,
    n_photon=n_photon,
    n_step=20000,
    n_scat=200000,
    ph_mode=1,                           # CFR mode
    transition_idx=tr_idx,
    mol_mass=28.0,                        # CO molecular mass [g/mol]
    work_dir='/tmp/plane_parallel_callables',
)

# ── 7. Print summary ────────────────────────────────────────────────────

print(f"\nCompleted {len(results)} cycle(s):")
for k, res in enumerate(results):
    exc_flux = res.get('excitation_flux')
    flx = res.get('flx')
    if exc_flux is not None:
        print(f"  Cycle {k}: excitation_flux_max = {exc_flux.max():.4e}", end='')
    if flx is not None:
        print(f",  flx_max = {flx.max():.4e}", end='')
    if 'photons' in res and res['photons'].get('vel') is not None:
        n_esc = len(res['photons']['vel'])
        print(f",  n_escaped = {n_esc}")
    else:
        print()

# ── 8. Plot results ────────────────────────────────────────────────────

fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 8a. Emergent spectrum
if 'photons' in results[-1]:
    plot_emergent_spectrum(axes[0, 0], results[-1]['photons'], bins=60,
                           xlim=(-3e5, 3e5), label=f'Cycle {len(results)}')
    axes[0, 0].set_title('Emergent Spectrum (CO J=1→0, callable fields)')
else:
    axes[0, 0].text(0.5, 0.5, 'No escaped photons',
                    transform=axes[0, 0].transAxes, ha='center', va='center')

# 8b. Excitation flux slice along x
flx_arr = results[-1].get('excitation_flux', results[-1].get('flx'))
if flx_arr is not None:
    x_cell = np.linspace(-5, 5, mesh['n_cell'][0])
    flx_x = flx_arr[:mesh['n_cell'][0]]
    axes[0, 1].plot(x_cell, flx_x / flx_x.max(), 'b-', lw=2,
                    label='excitation_flux')
    T_x = fields['temp'][:mesh['n_cell'][0]]
    ax2 = axes[0, 1].twinx()
    ax2.plot(x_cell, T_x, 'r--', lw=1.5, label='T(x)')
    ax2.set_ylabel('T [K]', color='r')
    axes[0, 1].set(xlabel='x [AU]', ylabel='normalised')
    axes[0, 1].legend(loc='upper left', fontsize=7)
    ax2.legend(loc='upper right', fontsize=7)
    axes[0, 1].set_title('Excitation Flux & Temperature Profile')
else:
    axes[0, 1].text(0.5, 0.5, 'No flux data',
                    transform=axes[0, 1].transAxes, ha='center', va='center')

# 8c. Population map
if len(final_pops) >= 2:
    pop_vals = list(final_pops.values())
    n_ground = pop_vals[0]
    n_excited = pop_vals[1]
    frac = n_excited / (n_ground + n_excited + 1e-30)
    plot_population_map(axes[1, 0], frac, mesh,
                        title='Excited Fraction (CO J=1→0)')

# 8d. Convergence
pop_history = []
for res in results:
    if 'populations' in res:
        pop_history.append(res['populations'])
if len(pop_history) >= 2:
    plot_convergence(axes[1, 1], pop_history, list(range(len(pop_history))))
else:
    axes[1, 1].text(0.5, 0.5, f'{len(results)} cycles completed',
                   transform=axes[1, 1].transAxes, ha='center')

fig.tight_layout()
outpath = os.path.join(_HERE, 'plane_parallel_callables_results.png')
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")
print("\nPlane-parallel slab with callable fields — complete.")
print(f"See {outpath} for summary plots.")
