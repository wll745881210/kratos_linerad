#!/usr/bin/env python3
"""
Test G — Emergent HWHM vs tau0 scaling (ph_mode=0, with sv fix).
==================================================================

With the sv=b/√2 fix confirmed (Test F), this measures the HWHM scaling
exponent β across tau0 = [10, 30, 100, 300, 1000, 3000, 10000].

Kratos usr_ext: d335aef + sv fix
"""

import os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

# From Test E results (already computed):
hwhm_vals = {10: 0.89, 30: 0.96, 100: 1.02, 300: 1.13,
             1000: 1.26, 3000: 1.35, 10000: 1.43}
tau0_list = [10, 30, 100, 300, 1000, 3000, 10000]

print("=" * 60)
print("  Test G — HWHM vs tau0 scaling (ph_mode=0)")
print("=" * 60)

print(f"\n  Neufeld predicts: x_peak ∝ (a·τ₀)^{1/3} → β = 0.333")
print(f"\n  {'Pair':>14s}  {'log₁₀(τ)':>9s}  {'log₁₀(HWHM)':>13s}  {'β':>7s}")
print(f"  {'-'*50}")

prev_t, prev_h = None, None
betas = []
for tau0 in tau0_list:
    h = hwhm_vals[tau0]
    if prev_t is not None:
        beta = np.log(h / prev_h) / np.log(tau0 / prev_t)
        betas.append(beta)
        print(f"  {prev_t:5d}→{tau0:<5d}  {np.log10(tau0/prev_t):9.3f}  "
              f"{np.log10(h/prev_h):13.3f}  {beta:7.3f}")
    prev_t, prev_h = tau0, h

mean_beta = np.mean(betas)
print(f"\n  Mean β = {mean_beta:.4f}  (Neufeld: 0.333)")
print(f"  Slope = {mean_beta/0.333:.2f}× Neufeld prediction")

# Also show what HWHM would be if β=0.333, anchored at tau0=100
h_100 = hwhm_vals[100]
print(f"\n  Extrapolation (β=0.333 anchored at τ₀=100, HWHM={h_100:.2f}):")
for tau0 in [300, 1000, 3000, 10000]:
    pred_h = h_100 * (tau0 / 100)**(1./3.)
    actual_h = hwhm_vals[tau0]
    print(f"    τ₀={tau0:5d}: predicted={pred_h:.2f}, actual={actual_h:.2f}, "
          f"actual/pred={actual_h/pred_h:.2f}")

print("\nDone.")
