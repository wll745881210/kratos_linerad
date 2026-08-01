#!/usr/bin/env python3
"""
Test D — gen.h sv=0 patch: rerun Test B with ph_mode=2.
=========================================================

Patches gen.h line 107: par.sv = 0.f (was: par.sv = par.sigma).
Kratos rebuilt. Rerunning ph_mode=2 (old Gaussian CFR) at representative tau0.

Pipeline commit:  b9dda65
Kratos usr_ext:    d335aef + patch (sv = 0.f)
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

tau0_values_before = [10, 100, 1000]  # from Test B (ph_mode=2)
hwhm_before = {10: 1.26, 100: 1.60, 1000: 2.39}
n_src = 20000

print("=" * 70)
print("  Test D — gen.h sv=0 patch (ph_mode=2 only)")
print("=" * 70)
print(f"  Kratos usr_ext patch: par.sv = 0.f (was: par.sv = par.sigma)")
print()

tau0_values = [10, 100, 1000]
print(f"  {'tau0':>6s}  {'HWHM(before)':>13s}  {'HWHM(after)':>12s}  "
      f"{'x_pred':>7s}  {'β_after':>8s}")
print(f"  {'-'*60}")

hwhm_after = {}
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
        path=f'/tmp/testD_t{tau0}/run',
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
    hwhm_after[tau0] = hwhm
    xp = x_peak(a * tau0)

    h_before = hwhm_before.get(tau0, float('nan'))
    print(f"  {tau0:6d}  {h_before:13.2f}  {hwhm:12.2f}  {xp:7.2f}")

print()
print("=" * 70)
print("  Summary: HWHM changes")
print("=" * 70)
for tau0 in tau0_values:
    b = hwhm_before[tau0]
    a = hwhm_after[tau0]
    if b and a:
        delta = (a - b) / b * 100
        print(f"  tau0={tau0:5d}: {b:.2f} -> {a:.2f}  ({delta:+.1f}%)")
print()
print("Done.")
