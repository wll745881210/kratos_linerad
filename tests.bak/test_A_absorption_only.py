#!/usr/bin/env python3
"""
Test A — Absorption-only transport (zero scattering).
=====================================================

Validates: binary I/O, unit conversion, photon transport without scattering physics.
Sets mfp_i_sca_0 = 0, mfp_i_abs_0 such that tau_abs = [1, 2, 3].

Physics: absorption reduces proper (weight), NOT photon count.
  Kratos photon.h:148 → proper *= exp(-tau_abs)

Since the iterator scales escaped `l` (proper) by unit_l0 (bug), we compare
ratios rather than absolute values:
  sum(proper[tau_i]) / sum(proper[tau_j]) ≈ exp(-tau_i + tau_j)

Pipeline commit:  b9dda65
Kratos usr_ext:    d335aef (gen.h: sv=sigma)
"""

import os, sys, time
import numpy as np

_PROJECT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, _PROJECT)

AU       = 1.49598e13
b_sca    = 1.0e5
L_slab   = 1.0 * AU
n_source = 50000

tau_abs_values = [1.0, 2.0, 3.0]

results = []
for tau_abs in tau_abs_values:
    mfp_i_abs = tau_abs / L_slab

    from core.line_rt import LineRt
    rt = LineRt(
        n_cell=(21, 2, 2),
        x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        b_sca=b_sca,
        mfp_i_sca_0=0.0,
        mfp_i_abs_0=mfp_i_abs,
        vel=(0., 0., 0.),
        ph_mode=1,
        n_step=2000, n_scat=2000,
        n_cycles=1, a_voigt=0.0,
        visualize=False,
        path=f'/tmp/testA_t{tau_abs:.0f}/run',
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(
        type="slab", x=-0.49,
        n_photon=n_source,
        luminosity=float(n_source),
    )
    res = rt.run()
    photons = res["results"][0]["photons"]

    n_esc = len(photons["vel"])
    proper_arr = np.asarray(photons["l"], dtype=np.float64)
    sum_proper = proper_arr.sum()
    results.append((tau_abs, n_esc, sum_proper))

    print(f"  tau_abs={tau_abs:.0f}  n_esc={n_esc:6d}  sum(proper)={sum_proper:.5e}")

print()
print("=" * 60)
print("  Summary — ratio tests (unit_l0 bug makes absolute values wrong)")
print("=" * 60)
for i in range(len(results) - 1):
    tau_i, _, p_i = results[i]
    tau_j, _, p_j = results[i + 1]
    ratio = p_j / p_i
    expected_ratio = np.exp(-(tau_j - tau_i))
    print(f"  proper(tau={tau_j:.0f}) / proper(tau={tau_i:.0f}) = {ratio:.4f}"
          f"  (expected exp(-{tau_j-tau_i:.0f}) = {expected_ratio:.4f})")

# Also check inferred tau
print()
print("  Inferred tau_abs from proper decay:")
for tau_abs, _, p in results:
    inferred = -np.log(p / results[0][2])
    print(f"    tau_abs={tau_abs:.0f}  inferred={inferred:.3f}")

print()
print("Done.")
