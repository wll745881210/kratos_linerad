#!/usr/bin/env python3
"""
Test E — Ph_mode=0 Neufeld scaling test.
==========================================

Ph_mode=0: CFR + exact table-based Voigt profile.
This is the correct match for Neufeld (1990) assumptions.

Test C used ph_mode=2 (analytic Voigt approximation).
Test E uses ph_mode=0 (exact Voigt).

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

tau0_values = [10, 30, 100, 300, 1000, 3000, 10000]

print("=" * 65)
print("  Test E — Neufeld scaling, ph_mode=0 (CFR + exact Voigt)")
print("=" * 65)
print(f"  {'tau0':>7s}  {'n_esc':>7s}  {'HWHM':>7s}  {'x_pred':>7s}  ")
print(f"  {'β_pair':>7s}  {'ratio':>7s}")
print(f"  {'-'*50}")

results = []
prev_hwhm = None
prev_tau0 = None

for tau0 in tau0_values:
    mfp = tau0 / L_slab

    if tau0 >= 10000:
        n_ph, n_step, n_scat = 50000, 10000000, 2000000
    elif tau0 >= 3000:
        n_ph, n_step, n_scat = 50000, 3000000, 500000
    elif tau0 >= 1000:
        n_ph, n_step, n_scat = 30000, 1000000, 200000
    else:
        n_ph, n_step, n_scat = 20000, 200000, 200000

    from core.line_rt import LineRt
    rt = LineRt(
        n_cell=(55, 2, 2),
        x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        b_sca=b_sca, mfp_i_sca_0=mfp,
        mfp_i_abs_0=0.0,
        vel=(0., 0., 0.),
        ph_mode=0,
        n_step=n_step, n_scat=n_scat,
        n_cycles=1, a_voigt=a,
        visualize=False,
        path=f'/tmp/testE_t{tau0}/run',
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(
        type="slab", x=-0.49,
        n_photon=n_ph,
        luminosity=float(n_ph),
    )
    res = rt.run()
    photons = res["results"][0]["photons"]
    vel = np.asarray(photons["vel"], dtype=np.float64)
    vel = vel[~np.isnan(vel)]
    n_esc = len(vel)

    x_esc = np.abs(vel) / sigma_th
    hwhm = np.median(x_esc)
    xp = x_peak(a * tau0)
    ratio = hwhm / xp if xp > 0 else np.nan

    beta_str = ""
    if prev_hwhm is not None and prev_hwhm > 0 and hwhm > 0:
        beta = np.log(hwhm / prev_hwhm) / np.log(tau0 / prev_tau0)
        beta_str = f"{beta:.3f}"
    else:
        beta_str = "-"

    print(f"  {tau0:7d}  {n_esc:7d}  {hwhm:7.2f}  {xp:7.2f}  "
          f"  {beta_str:>7s}  {ratio:7.3f}")

    results.append((tau0, n_esc, hwhm, xp, beta_str, ratio))
    prev_hwhm, prev_tau0 = hwhm, tau0

print()
print("  Summary (pm0) vs previous (pm2, test_C):")
print(f"  {'tau0':>7s}  {'HWHM(0)':>8s}  {'HWHM(2)':>8s}  {'ratio(0)':>8s}  {'ratio(2)':>8s}")
prev_pm2 = {10: 1.21, 30: 1.42, 100: 1.63, 300: 1.93, 1000: 2.39, 3000: 2.80, 10000: 3.20}
for tau0, n_esc, hwhm, xp, _, ratio in results:
    h2 = prev_pm2.get(tau0, np.nan)
    r2 = h2 / xp if xp > 0 and not np.isnan(h2) else np.nan
    print(f"  {tau0:7d}  {hwhm:8.2f}  {h2:8.2f}  {ratio:8.3f}  {r2:8.3f}")

print()
print("Done.")
