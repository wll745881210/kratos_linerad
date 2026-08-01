#!/usr/bin/env python3
"""
Test B — Compare ph_mode=1 (table Voigt+R_IIA) vs ph_mode=2 (old Gaussian CFR).
================================================================================

Isolates whether the bug is in the new Voigt table / R_IIA code (ph_mode=1 only)
or fundamental (both modes fail).

Hypothesis: ph_mode=2 uses old Gaussian CFR + analytic Voigt, should match old behavior.
If ph_mode=2 gives correct scaling but ph_mode=1 doesn't → bug in Voigt table/R_IIA.
If neither works → problem is fundamental (gen.h sv init, unit scaling, etc.).

Pipeline commit:  b9dda65
Kratos usr_ext:    d335aef (gen.h: sv=sigma)
"""

import os, sys, time
import numpy as np

_PROJECT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT, "docs", "examples"))
from neufeld_analytic import x_peak

c_cgs    = 2.99792458e10
AU       = 1.49598e13
a        = 0.01
b_sca    = 1.0e5
L_slab   = 1.0 * AU

tau0_values = [10, 100, 1000]
n_src = 20000

def run_one(tau0, ph_mode, label):
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
        ph_mode=ph_mode,
        n_step=n_step, n_scat=n_scat,
        n_cycles=1, a_voigt=a,
        visualize=False,
        path=f'/tmp/testB_m{ph_mode}_t{tau0}/run',
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
    n_esc = len(vel)

    x_pred = x_peak(a * tau0)
    x_esc = np.abs(vel) / (b_sca / np.sqrt(2))
    hwhm = np.median(x_esc) if n_esc > 0 else np.nan
    f_esc = n_esc / n_src

    print(f"  {label:20s}  tau0={tau0:5d}  n_esc={n_esc:6d}  "
          f"f_esc={f_esc:.4f}  hwhm={hwhm:.2f}  x_pred={x_pred:.2f}")

    return {"tau0": tau0, "n_esc": n_esc, "f_esc": f_esc,
            "hwhm": hwhm, "x_pred": x_pred, "vel": vel}

print("=" * 70)
print("  Test B — ph_mode=1 vs ph_mode=2 at tau0 = [10, 100, 1000]")
print("=" * 70)

results = {}
for ph_mode, label in [(1, "ph_mode=1 (table+R_IIA)"), (2, "ph_mode=2 (old Gaussian)")]:
    print(f"\n-- {label} --")
    rlist = []
    for tau0 in tau0_values:
        r = run_one(tau0, ph_mode, label)
        rlist.append(r)
    results[ph_mode] = rlist

print()
print("=" * 70)
print("  Comparison")
print("=" * 70)
print(f"{'tau0':>6s}  {'f_esc(1)':>9s}  {'f_esc(2)':>9s}  "
      f"{'hwhm(1)':>8s}  {'hwhm(2)':>8s}  {'x_pred':>7s}")
for i, tau0 in enumerate(tau0_values):
    r1 = results[1][i]
    r2 = results[2][i]
    print(f"  {tau0:5d}  {r1['f_esc']:9.4f}  {r2['f_esc']:9.4f}  "
          f"{r1['hwhm']:8.2f}  {r2['hwhm']:8.2f}  {r1['x_pred']:7.2f}")

print()
print("Done.")
