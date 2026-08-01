#!/usr/bin/env python3
"""
Test C — Escape spectrum vs tau0 (ph_mode=2, old Gaussian CFR).
================================================================

Confirms that the velocity distribution depends on tau0, even though
f_esc=1.0 for all tau0 (expected for pure scattering).

The original neufeld test showed x_mc ≈ 0.28-0.33 flat for all tau0.
This test uses a broader range and checks whether HWHM grows with tau0.

Pipeline commit:  b9dda65
Kratos usr_ext:    d335aef (gen.h: sv=sigma)
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
n_src = 20000

print("=" * 60)
print("  Test C — Escape spectrum vs tau0 (ph_mode=2)")
print("=" * 60)
print(f"  {'tau0':>6s}  {'n_esc':>7s}  {'HWHM':>7s}  {'x_pred':>7s}  {'ratio':>7s}")
print(f"  {'-'*45}")

results = []
for tau0 in tau0_values:
    mfp = tau0 / L_slab
    n_step = max(200000, int(tau0 * 1000))
    n_scat = max(500000, int(tau0 * 200))

    if tau0 >= 3000:
        n_ph = 50000
    elif tau0 >= 1000:
        n_ph = 30000
    else:
        n_ph = n_src

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
        path=f'/tmp/testC_t{tau0}/run',
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
    hwhm = np.median(x_esc) if n_esc > 0 else np.nan
    xp = x_peak(a * tau0)

    ratio = hwhm / xp if xp > 0 and not np.isnan(hwhm) else np.nan
    results.append((tau0, n_esc, hwhm, xp, ratio))
    print(f"  {tau0:6d}  {n_esc:7d}  {hwhm:7.2f}  {xp:7.2f}  {ratio:7.3f}")

print()
print("=" * 60)
print("  Summary: HWHM growth")
print("=" * 60)
print(f"  Neufeld predicts x_peak ∝ (a·tau0)^{1/3}")
for i in range(len(results) - 1):
    t0_i, _, h_i, _, _ = results[i]
    t0_j, _, h_j, _, _ = results[i + 1]
    if h_i > 0 and h_j > 0 and not np.isnan(h_i) and not np.isnan(h_j):
        beta = np.log(h_j / h_i) / np.log(t0_j / t0_i)
        print(f"  tau={t0_i}→{t0_j}: hwhm {h_i:.2f}→{h_j:.2f}  β={beta:.3f}")

print()
print("Done.")
