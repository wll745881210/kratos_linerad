#!/usr/bin/env python3
"""
High-Level Interface — Plane-Parallel Slab with Callable Fields
================================================================

Uses the high-level `LineRt` class with callable functions for scattering density
and temperature. Mirrors plane_parallel_callables.py but via the high-level API.

Run as:  python3 plane_parallel_hl_callables.py
"""

import sys, os
_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, _PROJECT)

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from core.line_rt import LineRt

AU = 1.49598e13

# ── 1. Callable field functions ────────────────────────────────────────
# Each receives n_tot (total number of cells) and returns a 1D ndarray.

def n_total_callable(n_tot):
    return np.full(n_tot, 1.87e12, dtype=np.float64)

def vx_callable(n_tot):
    return np.zeros(n_tot, dtype=np.float64)

def vy_callable(n_tot):
    return np.zeros(n_tot, dtype=np.float64)

def vz_callable(n_tot):
    return np.zeros(n_tot, dtype=np.float64)

def temperature_callable(n_tot):
    x_vals = np.array([(i % 64) * (10.0 / 64) - 5.0 for i in range(n_tot)])
    return 10.0 + 90.0 * (x_vals + 5.0) / 10.0

# ── 2. Configure LineRt ────────────────────────────────────────────────

rt = LineRt(
    n_cell=(64, 2, 2),
    x_min=(-5, 0, 0),
    x_max=(5, 0.2, 0.2),
    unit_l0=AU, unit_t0=1.0,

    species="CO", transition_idx=0,
    n_species=n_total_callable,
    temperature=temperature_callable,
    vel=(vx_callable, vy_callable, vz_callable),

    ph_mode=1,
    n_step=20000, n_scat=200000, n_cycles=3,
    mol_mass=28.0,
    n_emission_max=5,
    visualize=False,
)

rt.set_boundary("fre fre per per per per")

rt.add_source(
    type="slab",
    x=-5.0,
    n_photon=20000,
    flux=0.8 * 3.828e33 / (0.2 * 0.2 * AU * AU),
    wavelength=2.35e-4,
)

print(f"Mesh: {rt._n_cell}")
print(f"Sources: {len(rt._sources)}")

# ── 3. Run ─────────────────────────────────────────────────────────────

print("Running 3 cycles ...")
results = rt.run()

# ── 4. Plot results ────────────────────────────────────────────────────

res_list = results["results"]
mesh = results["mesh"]
nxc = mesh["n_cell"][0]
x_cell = np.linspace(-5, 5, nxc)

fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 4a. Emergent spectrum from last cycle
spectrum = results.get("spectrum", {})
vel_data = np.asarray(spectrum.get("vel", []))
if len(vel_data) > 0:
    v_kms = vel_data * 1e-5
    axes[0, 0].hist(v_kms, bins=60, density=True, alpha=0.6, color="steelblue")
    max_v = max(abs(v_kms.min()), abs(v_kms.max()))
    axes[0, 0].set(xlabel="v [km/s]", ylabel="PDF",
                   xlim=(-max_v * 1.1, max_v * 1.1))
else:
    axes[0, 0].text(0.5, 0.5, "No escaped photons",
                    transform=axes[0, 0].transAxes, ha="center")
axes[0, 0].set_title("Emergent Spectrum (CO J=1→0, callable fields)")

# 4b. Excitation flux profile (1D cut along x, y=z=0)
exc_flat = results.get("exc_flux_flat", None)
flx_flat = results.get("flx", None)
if exc_flat is not None and flx_flat is not None:
    exc_x = exc_flat[:nxc]
    flx_x = flx_flat[:nxc]
    axes[0, 1].plot(x_cell, exc_x / (exc_x.max() or 1), "b-", lw=2, label="excitation_flux")
    axes[0, 1].plot(x_cell, flx_x / (flx_x.max() or 1), "orange", lw=1.5, label="flx")
    axes[0, 1].set(xlabel="x [AU]", ylabel="normalised")
    axes[0, 1].legend(fontsize=7)
    axes[0, 1].set_title("Spatial Flux Distribution")
else:
    axes[0, 1].text(0.5, 0.5, "No flux data",
                    transform=axes[0, 1].transAxes, ha="center")

# 4c. Velocity distribution of escaped photons
if len(vel_data) > 0:
    axes[1, 0].hist(vel_data * 1e-5, bins=60, density=True,
                    alpha=0.6, color="steelblue")
    axes[1, 0].set(xlabel="v [km/s]", ylabel="PDF")
else:
    axes[1, 0].text(0.5, 0.5, "No escaped photons",
                    transform=axes[1, 0].transAxes, ha="center")
axes[1, 0].set_title("Escaped Photon Velocities")

# 4d. Convergence of populations across cycles
pop_hist = []
for res in res_list:
    if "populations" in res:
        pop_hist.append(res["populations"])
if len(pop_hist) >= 2:
    from core.visualize import plot_convergence
    plot_convergence(axes[1, 1], pop_hist, list(range(len(pop_hist))))
else:
    axes[1, 1].text(0.5, 0.5, "No convergence data",
                    transform=axes[1, 1].transAxes, ha="center")

fig.tight_layout()
_HERE = os.path.dirname(os.path.realpath(__file__))
outpath = os.path.join(_HERE, "plane_parallel_hl_callables_results.png")
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")

# ── 5. Summary ──────────────────────────────────────────────────────────
for k, res in enumerate(res_list):
    exc = res.get("exc_flux_flat", res.get("excitation_flux"))
    flx = res.get("flx")
    photons = res.get("photons", {})
    n_esc = len(photons.get("vel", []))
    print(f"Cycle {k+1}: flx_max={flx.max():.2e}" if flx is not None else "",
          f"exc_max={exc.max():.2e}" if exc is not None else "",
          f"n_esc={n_esc}")

print("\nHigh-level callable example complete.")
