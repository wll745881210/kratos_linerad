#!/usr/bin/env python3
"""
Test F — Single-scatter velocity distribution.
================================================

Approach A (primary): τ₀=0.1, classify scattered vs unscattered by velocity.
  Only ~7% scatter; scattered photons get CFR velocity kick of width σ_th.

Approach B (backup): n_scat=1, large τ₀=100, small n_step.
  Uses n_scat limit to restrict scatter count.

Tests: after a scatter, the photon's sv = σ_th = b/√2 and Δv draws from
Gaussian of width σ_th (CFR).

Pipeline commit:  b9dda65
Kratos usr_ext:    d335aef + sv fix (sv = b/sqrt2 after scatter)
"""

import os, sys
import numpy as np

_PROJECT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, _PROJECT)

AU       = 1.49598e13
b_sca    = 1.0e5
sigma_th = b_sca / np.sqrt(2.0)
L_slab   = 1.0 * AU

# ============================================================================
# Approach A: low τ₀, classify by velocity
# ============================================================================
print("=" * 60)
print("  Test F-A — τ₀=0.1, classify by velocity threshold")
print("=" * 60)

tau0 = 0.1
n_source = 200000
mfp = tau0 / L_slab

from core.line_rt import LineRt
rt = LineRt(
    n_cell=(21, 2, 2),
    x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
    unit_l0=AU, unit_t0=1.0,
    b_sca=b_sca, mfp_i_sca_0=mfp,
    mfp_i_abs_0=0.0,
    vel=(0., 0., 0.),
    ph_mode=0,
    n_step=2000, n_scat=2000,
    n_cycles=1, a_voigt=0.0,
    visualize=False,
    path='/tmp/testFA/run',
)
rt.set_boundary("fre fre per per per per")
rt.add_source(type="slab", x=-0.49, n_photon=n_source, luminosity=float(n_source))
res = rt.run()

photons = res["results"][0]["photons"]
vel = np.asarray(photons["vel"], dtype=np.float64)
sigma_arr = np.asarray(photons.get("sigma", []), dtype=np.float64)
vel_c = vel[~np.isnan(vel)]
sigma_c = sigma_arr[~np.isnan(sigma_arr)] if len(sigma_arr) > 0 else np.array([])

threshold = 1.0e3  # cm/s — anything above this had a CFR scatter
scattered_mask = np.abs(vel_c) > threshold
n_scat_obs = scattered_mask.sum()
n_unscat   = len(vel_c) - n_scat_obs

# τ_eff at line centre: τ₀ × I(0, sv=b/√2) = τ₀ × 1/√2
tau_eff_0 = tau0 / np.sqrt(2.0)
p_scat_pred = 1.0 - np.exp(-tau_eff_0)
n_scat_pred = p_scat_pred * n_source

print(f"  Source photons: {n_source}")
print(f"  Escaped: {len(vel_c)}")
print(f"  τ_eff(0) = {tau_eff_0:.4f}")
print(f"  Predicted scattered: {n_scat_pred:.0f} ({100*p_scat_pred:.2f}%)")
print(f"  Observed  scattered: {n_scat_obs} ({100*n_scat_obs/len(vel_c):.2f}%)")
print()

if n_scat_obs > 30:
    vel_scat = vel_c[scattered_mask]
    print(f"  Scattered photon velocity stats:")
    print(f"    mean(|vel|)    = {np.mean(np.abs(vel_scat)):.2e} cm/s")
    print(f"    std(vel)       = {np.std(vel_scat):.2e} cm/s")
    print(f"    σ_th (expected std) = {sigma_th:.2e} cm/s")
    print(f"    std(vel)/σ_th  = {np.std(vel_scat) / sigma_th:.4f}  (expected ~1.0)")
    print()

    if len(sigma_c) == len(vel_c):
        sigma_scat = sigma_c[scattered_mask]
        print(f"    mean(sigma)    = {np.mean(sigma_scat):.2e} cm/s")
        print(f"    σ_th (expected) = {sigma_th:.2e} cm/s")
        print(f"    mean(sigma)/σ_th = {np.mean(sigma_scat)/sigma_th:.4f}  (expected ~1.0)")
    print()

# Print histogram to check bimodality
print(f"  Velocity distribution (binned):")
bins = np.linspace(-3*sigma_th, 3*sigma_th, 25)
hist, edges = np.histogram(vel_c, bins=bins)
for i in range(len(hist)):
    if hist[i] > 0:
        print(f"    [{edges[i]:.1e}, {edges[i+1]:.1e}): {hist[i]}")

print()

# ============================================================================
# Approach B: n_scat=1, large τ₀, small n_step
# ============================================================================
print("=" * 60)
print("  Test F-B — n_scat=1, large τ₀=100, n_step=500")
print("=" * 60)

tau0 = 100.0
mfp = tau0 / L_slab
n_source = 200000

rt2 = LineRt(
    n_cell=(21, 2, 2),
    x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
    unit_l0=AU, unit_t0=1.0,
    b_sca=b_sca, mfp_i_sca_0=mfp,
    mfp_i_abs_0=0.0,
    vel=(0., 0., 0.),
    ph_mode=0,
    n_step=500, n_scat=1,
    n_cycles=1, a_voigt=0.0,
    visualize=False,
    path='/tmp/testFB/run',
)
rt2.set_boundary("fre fre per per per per")
rt2.add_source(type="slab", x=-0.49, n_photon=n_source, luminosity=float(n_source))
res2 = rt2.run()

photons2 = res2["results"][0]["photons"]
vel2 = np.asarray(photons2["vel"], dtype=np.float64)
vel2 = vel2[~np.isnan(vel2)]
sigma2 = np.asarray(photons2.get("sigma", []), dtype=np.float64)
sigma2 = sigma2[~np.isnan(sigma2)] if len(sigma2) > 0 else np.array([])

print(f"  Escaped: {len(vel2)} / {n_source}")
print(f"  mean(|vel|)      = {np.mean(np.abs(vel2)):.2e} cm/s")
print(f"  std(vel)         = {np.std(vel2):.2e} cm/s")
print(f"  σ_th (expected std per scatter) = {sigma_th:.2e} cm/s")

# If n_scat=1 actually limits to 1 scatter, then std(vel) ≈ σ_th
# If it scatters many times, std(vel) >> σ_th
ratio_b = np.std(vel2) / sigma_th
print(f"  std(vel)/σ_th = {ratio_b:.4f}")
if ratio_b < 1.5:
    print(f"  → Likely single-scatter or few scatters (ratio close to 1)")
elif ratio_b < 3.0:
    print(f"  → Several scatters (ratio ~ {ratio_b:.1f})")
else:
    print(f"  → Many scatters (ratio ~ {ratio_b:.1f}, n_scat=1 not a hard limit)")

print()
print("Done.")
