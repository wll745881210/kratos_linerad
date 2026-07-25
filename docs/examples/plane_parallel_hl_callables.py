#!/usr/bin/env python3
"""
High-Level Interface — Plane-Parallel Slab with Callable Fields
================================================================

This example uses the **linert.LineRT** convenience class with callable
functions for scattering density, absorption, and temperature.  It mirrors
plane_parallel_callables.py but uses the high-level API instead of the
low-level iterate() interface.

The CO J=1→0 transition is selected explicitly by level numbers:
    load_species_transition(path, upper=1, lower=0)

Run as:  python3 plane_parallel_hl_callables.py
"""

import sys, os
_HERE = os.path.dirname(os.path.realpath(__file__))
_PROJECT = os.path.normpath(os.path.join(_HERE, os.pardir, os.pardir))
_LINERT = os.path.expanduser('~/scratch/line_rt')
if _LINERT not in sys.path:
    sys.path.insert(0, _LINERT)

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from linert import LineRT, SlabSource, Result
from molecular.lamda_format import load_species_transition

# ── CGS constants ──────────────────────────────────────────────────────
AU = 1.49598e13
Lsun = 3.828e33

# ── 1. Callable field functions ────────────────────────────────────────
#
# Unlike plane_parallel.py (flat arrays), these functions are evaluated at
# every cell centre by LineRT.  Replace the bodies with any spatial profile.

def n_total_callable(X, Y, Z):
    """Scattering particle density [cm⁻³] — τ₀=100 across 10 AU, CO J=1→0.

    From the flat equivalent: τ₀ = n_gas * σ_co * slab_cm
      n_gas = τ₀ / (σ_co * slab_cm) ≈ 1.87e12 cm⁻³
    where σ_co = c² g_u A_ul / (2 ν³ g_l b √π) ≈ 3.6e-25 cm².
    """
    return np.full_like(X, 1.87e12, dtype=np.float64)

def velocity_callable(X, Y, Z):
    """Bulk velocity field [cm/s] — zero everywhere (static slab)."""
    return (np.zeros_like(X), np.zeros_like(X), np.zeros_like(X))

def temperature_callable(X, Y, Z):
    """Gas temperature [K] — linear gradient 10→100 K."""
    return 10.0 + 90.0 * (X + 5.0) / 10.0

# ── 2. Load CO and select transition ───────────────────────────────────
#
# Explicit:  upper=1, lower=0  →  CO J=1→0  (115.27 GHz)
# Also works with:  freq_GHz=115.271202

lamda_path = os.path.join(_PROJECT, 'molecular', 'embedded', 'co.dat')

print(f"Loading CO from: {lamda_path}")
print(f"Project root: {_PROJECT}")
co, tr = load_species_transition(lamda_path, upper=1, lower=0)

print(f"Species: CO  ({co.n_levels} levels, {co.n_transitions} transitions)")
print(f"Transition:  J={tr.upper} → J={tr.lower}")
print(f"  A_ul  = {tr.A_ul:.2e} s⁻¹")
print(f"  ν₀    = {tr.freq_GHz:.2f} GHz")
print(f"  λ     = {tr.wavelength_um:.1f} µm")
print(f"  E_u/K = {tr.E_u_K:.2f} K")
print(f"  index = {co.find_transition_idx(tr)}")

# ── 3. Configure LineRT ────────────────────────────────────────────────

rt = LineRT(
    source=SlabSource(x0=-5., n_photon=20000, b_sca=1e5),

    x_min=(-5, 0, 0),
    x_max=(5, 0.2, 0.2),
    n_cell=(64, 2, 2),

    # Mode 2: species-based opacity
    species=co,
    n_total=n_total_callable,      # callable — evaluated per-cell
    transition=tr,                  # CO J=1→0
    temperature=temperature_callable,  # callable
    velocity=velocity_callable,

    n_photon=20000,
    n_step=20000,
    n_scat=200000,
    ph_mode=1,                      # CFR
    n_cycles=3,
    mol_mass=28.0,                   # CO molecular mass
    n_emission_max=5,
    work_dir='/tmp/linert_callables',
)

print(f"\nMesh: {rt.n_cell} cells, total = {rt.n_tot}")
print(f"Mol mass: {rt.mol_mass} g/mol")

# ── 4. Run ─────────────────────────────────────────────────────────────

print(f"\nRunning 3 cycles ...")
result = rt.run(
    callback=lambda cycle, cr: print(
        f"  Cycle {cycle}:  "
        f"exc_flux_max={cr.excitation_flux.max():.4e},  "
        f"flx_max={cr.flx.max():.4e},  "
        f"exc_max={cr.exc_rate.max():.4e},  "
        f"n_esc={len(cr.photons)},  "
        f"t={cr.elapsed:.1f}s"))

# ── 5. Plot results ────────────────────────────────────────────────────

cr = result.cycles[-1]
esc = cr.photons

fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 5a. Emergent spectrum
spec = esc.synthesize_spectrum(v_min=-2e6, v_max=2e6, n_bins=400)
v_kms = spec['v_mid'] * 1e-5
flux = spec['spectrum']
axes[0, 0].plot(v_kms, flux / flux.max(), 'b-', lw=1.5)
axes[0, 0].set(xlabel='v [km/s]', ylabel='normalised')
axes[0, 0].set_title('Emergent Spectrum (CO J=1→0, callable fields)')

# 5b. Excitation flux profile
nxc = result.n_cell[0]
x_cell = np.linspace(-5, 5, nxc)
exc_x = cr.excitation_flux[:nxc]
flx_x = cr.flx[:nxc]
axes[0, 1].plot(x_cell, exc_x / exc_x.max(), 'b-', lw=2,
                label='excitation_flux')
axes[0, 1].plot(x_cell, flx_x / flx_x.max(), 'orange', lw=1.5,
                label='flx')
axes[0, 1].set(xlabel='x [AU]', ylabel='normalised')
axes[0, 1].legend(fontsize=7)
axes[0, 1].set_title('Spatial Flux Distribution')

# 5c. Escaped photon velocity distribution
axes[1, 0].hist(esc.velocity * 1e-5, bins=60, density=True,
                alpha=0.6, color='steelblue')
axes[1, 0].set(xlabel='v [km/s]', ylabel='PDF')
axes[1, 0].set_title('Escaped Photon Velocities')

# 5d. Population evolution
if cr.populations is not None:
    n_ground = cr.populations.get('n0', np.zeros(nxc))[:nxc]
    n_exc = cr.populations.get('n1', np.zeros(nxc))[:nxc]
    frac = n_exc / (n_ground + n_exc + 1e-30)
    axes[1, 1].plot(x_cell, frac, 'r-', lw=2)
    axes[1, 1].set(xlabel='x [AU]', ylabel='n_exc / (n_exc + n_0)')
    axes[1, 1].set_title('Excited Fraction (CO J=1→0)')
    axes[1, 1].set_yscale('log')
else:
    axes[1, 1].text(0.5, 0.5, 'No population data',
                    transform=axes[1, 1].transAxes, ha='center')

fig.tight_layout()
outpath = os.path.join(_HERE, 'plane_parallel_hl_callables_results.png')
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")

print("\nHigh-level callable example complete.")
print(f"{result}")
