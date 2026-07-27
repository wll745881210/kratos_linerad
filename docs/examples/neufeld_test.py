#!/usr/bin/env python3
"""
Neufeld (1990) Analytic Test — Resonance-Line Radiative Transfer
=================================================================

Compares Monte Carlo line RT results (ph_mode=1 PRD, a_voigt > 0)
against the analytic solution for a static, uniform, plane-parallel
slab (Neufeld 1990, ApJ, 350, 216).

Three test blocks:
  Block 1 — emergent spectrum shape vs analytic J(x) at 3 tau0 values
  Block 2 — peak-position scaling  |x_peak| ∝ (a·T₀)^(1/3)
  Block 3 — dust suppression: escaped fraction vs τ_abs

Uses Group 2 (explicit opacity): mfp_i_sca_0 = τ₀ / L.
a = 0.01, b_sca = 1e5 cm/s, ph_mode=1 (PRD), single cycle.
"""

import sys, os, time
_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, _PROJECT)

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from core.line_rt import LineRt
from neufeld_analytic import x_peak, emergent_central_slab, escape_fraction_dust

c_cgs   = 2.99792458e10
AU      = 1.49598e13
sqrt2   = np.sqrt(2.0)

# ═══════════════════════════════════════════════════════════════════════
# 1. Parameters
# ═══════════════════════════════════════════════════════════════════════

a      = 0.01
b_sca  = 1.0e5
sigma_th = b_sca / sqrt2
L_slab_cm = 1.0 * AU

print("=== Neufeld (1990) Test Parameters ===")
print(f"  a = {a}, b_sca = {b_sca:.1e} cm/s, σ_th = {sigma_th:.1e} cm/s")
print(f"  L_slab = {L_slab_cm:.2e} cm = 1 AU")
print(f"  Mode: PRD (ph_mode=1), a_voigt = {a}")
print(f"  Group 2 (explicit): mfp_i_sca_0 = τ₀ / L")
print(f"  x_peak ≈ 1.066 × (2aτ₀)^(1/3)\n")

# ═══════════════════════════════════════════════════════════════════════
# 2. Block 1 & 2: spectrum shape + peak scaling
# ═══════════════════════════════════════════════════════════════════════

tau0_values = [10, 30, 100, 300, 1000, 3000]
n_source = 50000
n_cell_x = max(32, int(np.sqrt(max(tau0_values))) + 1)
results = {}

print("=" * 60)
print("Running MC simulations (Group 2, ph_mode=1, a_voigt=0.01)")
print("=" * 60)

for tau0 in tau0_values:
    mfp_i_sca_0 = tau0 / L_slab_cm  # inverse MFP (cm⁻¹)
    n_step = max(200000, int(tau0 * 500))
    n_scat = max(200000, int(tau0 * 100))

    print(f"\n--- τ₀ = {tau0} "
          f"(mfp_i_sca_0={mfp_i_sca_0:.2e} cm⁻¹, "
          f"n_step={n_step/1000:.0f}k) ---")

    rt = LineRt(
        n_cell=(n_cell_x, 2, 2),
        x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        b_sca=b_sca, mfp_i_sca_0=mfp_i_sca_0,
        mfp_i_abs_0=0.0,
        vel=(0., 0., 0.),
        ph_mode=1, n_step=n_step, n_scat=n_scat,
        n_cycles=1, a_voigt=a,
        visualize=False,
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(
        type="slab", x=-0.49, n_photon=n_source,
        luminosity=float(n_source),
    )
    res = rt.run()

    vel = np.asarray(res["results"][0]["photons"]["vel"])
    all_vel = vel
    transmitted = vel  # all escaped = transmitted for source near left face

    x_peak_pred = x_peak(a * 2.0 * tau0)
    x_mc = np.nan
    if len(transmitted) > 20:
        mask = transmitted > 0
        if mask.sum() > 5:
            tv = transmitted[mask]
            bins = np.linspace(0, 5 * sigma_th, 100)
            cnt, _ = np.histogram(tv, bins=bins)
            sm = np.convolve(cnt.astype(float), np.ones(5) / 5, mode='same')
            v_mc = 0.5 * (bins[np.argmax(sm)] + bins[np.argmax(sm) + 1])
            x_mc = v_mc / sigma_th

    results[tau0] = {
        "all": all_vel, "transmitted": transmitted,
        "mfp_i_sca_0": mfp_i_sca_0,
        "x_peak_pred": x_peak_pred,
    }
    n_esc = len(all_vel)
    print(f"  escaped: {n_esc}/{n_source} ({100*n_esc/n_source:.1f}%)  "
          f"x_peak_pred={x_peak_pred:.2f}  x_peak_mc={x_mc}")
    time.sleep(5)

# ═══════════════════════════════════════════════════════════════════════
# 3. Block 3: dust suppression
# ═══════════════════════════════════════════════════════════════════════

tau0_fixed = 100
mfp_i_sca_fixed = tau0_fixed / L_slab_cm
tau_abs_values = [0.0, 0.5, 1.0, 3.0, 10.0]
escaped_frac = []
analytic_esc = []

print("\n" + "=" * 60)
print(f"Block 3: Dust suppression (τ₀ = {tau0_fixed})")
print("=" * 60)

for ta in tau_abs_values:
    mfp_abs_inv = ta / L_slab_cm if ta > 0 else 0.0
    rt = LineRt(
        n_cell=(n_cell_x, 2, 2),
        x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        b_sca=b_sca, mfp_i_sca_0=mfp_i_sca_fixed,
        mfp_i_abs_0=mfp_abs_inv,
        vel=(0., 0., 0.),
        ph_mode=1, n_step=200000, n_scat=200000,
        n_cycles=1, a_voigt=a,
        visualize=False,
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(
        type="slab", x=-0.49, n_photon=n_source,
        luminosity=float(n_source),
    )
    res = rt.run()
    vel = np.asarray(res["results"][0]["photons"]["vel"])
    frac = len(vel) / n_source
    escaped_frac.append(frac)
    analytic_esc.append(escape_fraction_dust(tau0_fixed, ta))
    print(f"  τ_abs={ta:.1f}   escaped={frac:.4f}   "
          f"analytic:{escape_fraction_dust(tau0_fixed, ta):.4f}")
    time.sleep(5)

# ═══════════════════════════════════════════════════════════════════════
# 4. Plot
# ═══════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Block 1: spectrum shape
ax = axes[0]
plot_taus = [100, 1000, 3000]
for tau0 in plot_taus:
    if tau0 not in results:
        continue
    vel = results[tau0]["transmitted"]
    if len(vel) == 0:
        continue
    v_km = vel * 1e-5
    bins = np.linspace(-5, 5, 80)
    ax.hist(v_km, bins=bins, density=True, alpha=0.35,
            label=f"MC  τ₀={tau0}")

    x_dop = np.linspace(-8, 8, 400)
    a_tau0 = a * 2.0 * tau0
    j = emergent_central_slab(x_dop, a_tau0)
    j /= j.max() + 1e-40
    v_analytic = x_dop * sigma_th * 1e-5
    ax.plot(v_analytic, j, '-', lw=1.5,
            label=f"Analytic aT₀={a_tau0:.2f}")

ax.set_xlabel("velocity [km/s]")
ax.set_ylabel("normalised density")
ax.set_title("Block 1: Emergent Spectrum Shape (PRD, transmitted)")
ax.legend(fontsize=7, loc='upper right')

# Block 2: peak position
ax = axes[1]
aT_arr = np.array([a * 2.0 * t for t in sorted(results.keys())])
x_pred = x_peak(aT_arr)
ax.loglog(aT_arr, x_pred, 'k--', lw=2, label="$1.066\\,(aT_0)^{1/3}$")

t_list, x_list = [], []
for tau0 in sorted(results.keys()):
    vel = results[tau0]["transmitted"]
    if len(vel) < 20:
        continue
    vp = vel[vel > 0]
    if len(vp) < 10:
        continue
    bins = np.linspace(0, 10 * sigma_th, 120)
    cnt, _ = np.histogram(vp, bins=bins)
    sm = np.convolve(cnt.astype(float), np.ones(5) / 5, mode='same')
    xp = 0.5 * (bins[np.argmax(sm)] + bins[np.argmax(sm) + 1]) / sigma_th
    t_list.append(a * 2.0 * tau0)
    x_list.append(xp)

ax.loglog(t_list, x_list, 'ro-', ms=7, label='MC (PRD)')
ax.set_xlabel("$a\\,T_0$")
ax.set_ylabel("$|x_{\\rm peak}|$ [Doppler units]")
ax.set_title("Block 2: Peak-Position Scaling")
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

# Block 3: dust suppression
ax = axes[2]
ax.semilogy(tau_abs_values, escaped_frac, 'ro-', ms=8, label='MC (transmitted)')
ax.semilogy(tau_abs_values, analytic_esc, 'k--', lw=2,
            label="$\\exp(-\\tau_a\\sqrt{\\tau_0})$")
ax.set_xlabel("$\\tau_{\\rm abs}$")
ax.set_ylabel("escaped fraction")
ax.set_title(f"Block 3: Dust Suppression ($\\tau_0={tau0_fixed}$)")
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

fig.tight_layout()
_HERE = os.path.dirname(os.path.realpath(__file__))
outpath = os.path.join(_HERE, "neufeld_test_results.png")
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")

# ═══════════════════════════════════════════════════════════════════════
# 5. Summary table
# ═══════════════════════════════════════════════════════════════════════

print("\n=== Neufeld Test Summary ===")
print(f"  a = {a}, b_sca = {b_sca:.1e} cm/s, σ_th = {sigma_th:.1e} cm/s")
print(f"  L_slab = {L_slab_cm:.2e} cm = 1 AU")
print(f"  Mode: PRD (ph_mode=1), a_voigt = {a}")
print(f"  Group 2: mfp_i_sca_0 = τ₀ / L")
print()
print(f"{'τ₀':>6s}  {'a·T₀':>8s}  {'x_p(pred)':>9s}  "
      f"{'x_p(mc)':>9s}  {'n_esc':>8s}")

for tau0 in sorted(results.keys()):
    r = results[tau0]
    vel = r["transmitted"]
    aT = a * 2.0 * tau0
    xp = x_peak(aT)
    xm = np.nan
    n_tot = len(vel)
    if len(vel) > 20:
        vp = vel[vel > 0]
        if len(vp) > 5:
            bins = np.linspace(0, 10 * sigma_th, 120)
            cnt, _ = np.histogram(vp, bins=bins)
            sm = np.convolve(cnt.astype(float), np.ones(5) / 5, mode='same')
            xm = 0.5 * (bins[np.argmax(sm)] + bins[np.argmax(sm) + 1]) / sigma_th
    print(f"  {tau0:4d}  {aT:6.1f}  {xp:8.2f}  "
          f"{xm:7.2f}  {n_tot:8d}")

print("\nDone.")
