#!/usr/bin/env python3
"""
Test — Post-scatter sv fix verification (ph_mode=2, CFR).
==========================================================

Fixes: photon.h sets sv = b_sca/sqrt(2) after scattering (was sv=0).
This makes the overlap integral width correct per notes.tm §2.3.2.

Pipeline commit:  b9dda65
Kratos usr_ext:    d335aef + sv fix (sv = b/sqrt2 after scatter)
"""

import os, sys, time
import numpy as np

_PROJECT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT, "docs", "examples"))
from neufeld_analytic import x_peak

AU       = 1.49598e13
a        = 0.01
b_sca    = 1.0e5
L_slab   = 1.0 * AU
sigma_th = b_sca / np.sqrt(2)
n_src    = 20000

# With the fix: I(x=0) = 1/sqrt(2) ≈ 0.707
# Effective optical depth: tau_eff = tau0 * 1/sqrt(2)
# Neufeld comparison: x_peak takes tau_eff directly (since tau0 in code IS our tau0)
T_ALREADY_DIFF = False

tau0_values = [10, 100, 300, 1000]

print("=" * 60)
print("  Post-fix scattering test — ph_mode=2 (sv=b/sqrt2)")
print("=" * 60)
print(f"  {'tau0':>6s}  {'HWHM':>7s}  {'x_pred':>7s}  {'ratio':>7s}")
print(f"  {'-'*38}")

for tau0 in tau0_values:
    mfp = tau0 / L_slab
    n_step = max(200000, int(tau0 * 500))
    n_scat = max(200000, int(tau0 * 100))

    from core.line_rt import LineRt
    rt = LineRt(
        n_cell=(55, 2, 2),
        x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        b_sca=b_sca, mfp_i_sca_0=mfp,
        mfp_i_abs_0=0.0,
        vel=(0., 0., 0.),
        ph_mode=2,
        n_step=n_step, n_scat=n_scat,
        n_cycles=1, a_voigt=a,
        visualize=False,
        path=f'/tmp/testS_t{tau0}/run',
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(
        type="slab", x=-0.49,
        n_photon=n_src,
        luminosity=float(n_src),
    )
    res = rt.run()
    photons = res["results"][0]["photons"]
    vel = np.asarray(photons["vel"], dtype=np.float64)
    vel = vel[~np.isnan(vel)]

    x_esc = np.abs(vel) / sigma_th
    hwhm = np.median(x_esc)
    xp = x_peak(a * tau0)
    ratio = hwhm / xp if xp > 0 else np.nan

    print(f"  {tau0:6d}  {hwhm:7.2f}  {xp:7.2f}  {ratio:7.3f}")

print()
print("Done.")
