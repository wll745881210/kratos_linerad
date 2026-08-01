#!/usr/bin/env python3
"""Plane-parallel slab example using the high-level ``LineRt`` API.

Same physics and geometry as ``plane_parallel_lowlevel.py`` but using the
``LineRt`` orchestrator instead of the bare ``iterate()`` loop.

Run from ``/tmp/line_rt``:

    python3 docs/examples/plane_parallel_hl.py
"""

import os, sys
_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.line_rt import LineRt
from core.visualize import plot_emergent_spectrum, plot_flux_slice, plot_population_map

# ── CGS constants ───────────────────────────────────────────────────
AU = 1.49598e13

# ── 1. Physical parameters (identical to plane_parallel_lowlevel.py) ──
tau0_slab   = 1e1
b_sca       = 1.0e5
mol_mass    = 28.0
temperature = 2.0

# ── 2. Configure LineRt (Group 1: species-based) ────────────────────
# n_species derived from tau0_slab:  n = tau0 / (L_slab * sigma_co)
# LineRt computes sigma_co internally from species + b_sca, so we
# pass n_species as a callable that returns the same constant.
lamda_path = os.path.join(_PROJECT, "molecular", "embedded", "co.dat")
from molecular.lamda_format import load_species_transition
co, tr = load_species_transition(lamda_path, freq_GHz=115.271202)
tr_idx = co.find_transition_idx(tr)
sigma_co = co.cross_section(0, b_sca)
L_slab_cm = 10.0 * AU   # x_min=-5, x_max=5 -> L=10 AU
n_species = (tau0_slab / L_slab_cm) / sigma_co   # cm^-3
n_cycle   = 1

def n_total_callable(X, Y, Z):
    res = np.full(X.shape, n_species, dtype=np.float64);
    res[X > 0.10 * AU] *= 1e1;
    return res;

def temperature_callable(X, Y, Z):
    return np.full(X.shape, temperature, dtype=np.float64)

def vx_callable(X, Y, Z):
    return np.zeros(X.shape, dtype=np.float64)

rt = LineRt(
    n_cell=(64, 4, 2),
    x_min=(-5, 0, 0),
    x_max=(5, 0.2, 0.2),
    unit_l0=AU, unit_t0=1.0,

    species="CO", transition_idx=tr_idx,
    n_species=n_total_callable,
    temperature=temperature_callable,
    b_sca=b_sca,
    vel=(vx_callable, 0.0, 0.0),

    ph_mode=2,           # R_IIA const-mem (production)
    n_step=20000, n_scat=10000, n_cycles=n_cycle,
    mol_mass=mol_mass,
    visualize=False,
)
rt.set_boundary("fre fre per per per per")

# ── 3. Source (flux-based, matching lowlevel) ───────────────────────
# Lowlevel: F0 = 1e6 photon/cm^2/s, sv = b_sca/sqrt(2), x=-4.999
F0_cgs = 1e6   # photon number flux [photons cm^-2 s^-1]
rt.add_source(
    type="slab", x=-4.999, direction="+x",
    n_photon=20000,
    flux=F0_cgs,            # photon number flux (no wavelength)
    sigma=b_sca / np.sqrt(2),
)

print(f"CO J={tr.upper}->{tr.lower}, n_species={n_species:.2e} cm^-3")
print(f"Mesh: {rt._n_cell}, sources: {len(rt._sources)}")
print( "Running %d MC cycles ..." % n_cycle );
results = rt.run()

# ── 4. Plot (same 4 panels as lowlevel) ─────────────────────────────
res_list = results["results"]
mesh = results["mesh"]

fig, axes = plt.subplots(2, 2, figsize=(12, 10))

if "photons" in res_list[-1]:
    plot_emergent_spectrum(axes[0, 0], res_list[-1]["photons"], bins=60,
                           xlim=(-3e5, 3e5))
axes[0, 0].set_title("Emergent Spectrum")

plot_flux_slice(axes[0, 1], res_list[-1]["flx"], mesh, title="Flux Map", slice_idx = 0)
plot_flux_slice(axes[1, 0], res_list[-1]["flx"], mesh, title="Flux Map", slice_idx = 1)

# final_pops = results["populations"]
# if len(final_pops) >= 2:
#     vals = list(final_pops.values())
#     n_g, n_e = vals[0], vals[1]
#     plot_population_map(axes[1, 0], n_e / (n_g + n_e + 1e-30), mesh, title="Excited Fraction")

mfp_sca = res_list[-1].get("mfp_i_sca_0")
if mfp_sca is not None:
    plot_flux_slice(axes[1, 1], mfp_sca, mesh, title="mfp_i_sca_0",
                    log=False, cbar_label=r"mfp_i_sca_0 [cm$^{-1}$]")

fig.tight_layout()
outpath = os.path.join(os.path.dirname(__file__), "plane_parallel_hl_results.png")
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")

for k, res in enumerate(res_list):
    flx = res.get("flx")
    exc = res.get("exc_flux_flat", res.get("excitation_flux"))
    n_esc = len(res.get("photons", {}).get("vel", []))
    print(f"  Cycle {k}: "
          f"flx_max={np.max(flx):.2e}" if flx is not None else f"  Cycle {k}: flx=N/A",
          f"exc_max={np.max(exc):.2e}" if exc is not None else "exc=N/A",
          f"n_esc={n_esc}")
