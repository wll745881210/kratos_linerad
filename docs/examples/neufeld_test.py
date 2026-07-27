#!/usr/bin/env python3
"""
Neufeld (1990) Numerical Test — KDE-based peak finding.
=========================================================

Compares MC line RT results against analytic predictions from
Neufeld 1990, ApJ, 350, 216.

Two physics modes:
  ph_mode=1  — table-based Voigt + R_IIA (CFR core, coherent wing)
  ph_mode=2  — old Gaussian CFR + analytic Voigt (test mode)

Peak finding: Gaussian KDE, find the local maximum at x > 0.
The line-centre x=0 mode is always present; we report the
first off-centre peak (sidelobe for double-peak spectra).
"""

import os, sys, time
import numpy as np
from scipy.stats import gaussian_kde
from scipy.signal import argrelextrema

_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))
sys.path.insert(0, _PROJECT)
from neufeld_analytic import x_peak, emergent_central_slab

c_cgs    = 2.99792458e10
AU       = 1.49598e13
sqrt2    = np.sqrt(2.0)
a        = 0.01
b_sca    = 1.0e5
sigma_th = b_sca / sqrt2
L_slab   = 1.0 * AU


# ---- KDE-based peak finder ------------------------------------------------
def kde_peak(velocities, sigma_th, x_max=10.0, n_points=500):
    """Find the first off-centre peak of the |v| distribution.

    Uses Gaussian KDE to get a smooth PDF, then finds local
    maxima at x > 0.  Skips the x=0 delta-function-like peak
    by starting the search at 0.3 Doppler widths.
    Returns (x_peak, frac_escaped, hwhm).
    """
    v = np.asarray(velocities, dtype=np.float64)
    v = v[~np.isnan(v)]
    n_tot = len(v)
    if n_tot < 10:
        return np.nan, 0.0, np.nan

    x = np.abs(v) / sigma_th
    hwhm = np.median(x)

    # KDE with Silverman bandwidth
    bw = 1.06 * np.std(x) * n_tot**(-1.0 / 5.0) if n_tot > 1 else 0.1
    bw = max(bw, 0.02)
    try:
        kde = gaussian_kde(x, bw_method=bw)
    except (np.linalg.LinAlgError, ValueError):
        return np.nan, 0.0, hwhm

    x_grid = np.linspace(0, x_max, n_points)
    pdf = kde(x_grid)

    # Find local maxima (skip indices < 5 to avoid x≈0 spike)
    maxima = argrelextrema(pdf, np.greater, order=15)[0]
    maxima = maxima[maxima >= 10]   # start at ~0.2 Doppler widths

    if len(maxima) == 0:
        return np.nan, 0.0, hwhm

    # Pick the first significant peak (height > 20% of global max)
    global_max = pdf.max()
    for idx in maxima:
        if pdf[idx] > 0.20 * global_max:
            return  float(x_grid[idx]), n_tot, hwhm

    return np.nan, 0.0, hwhm


# ---- Main test ------------------------------------------------------------
def run_test(tau0_list, ph_mode, label, n_source=50000):
    """Run MC test and return (tau0, x_mc, n_esc, hwhm) arrays."""
    print(f"\n{'='*60}")
    print(f"  {label}  (ph_mode={ph_mode})")
    print(f"{'='*60}")
    print(f" {'t_0':>6s}  {'at_0':>7s} {'x_pred':>7s} {'x_mc':>7s} "
          f"{'HWHM':>7s} {'n_esc':>7s}")
    print(f"{'-'*60}")

    results = []
    for tau0 in tau0_list:
        mfp = tau0 / L_slab
        n_src = 20000 if tau0 >= 10000 else n_source
        n_step = max(10000000 if tau0 >= 10000 else 200000, int(tau0 * 500))
        n_scat = max(100000 if tau0 >= 100000 else 200000, int(tau0 * 100))

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
            path=f'/tmp/nf_{ph_mode}_t{tau0}/run',
        )
        rt.set_boundary("fre fre per per per per")
        rt.add_source(
            type="slab", x=-0.49,
            n_photon=n_src,
            luminosity=float(n_src),
        )
        res = rt.run()
        vel = np.asarray(res["results"][0]["photons"]["vel"])
        xp, n_esc, hwhm = kde_peak(vel, sigma_th)
        x_pred = x_peak(a * tau0)
        results.append((tau0, xp, n_esc, hwhm))

        xp_str = f"{xp:.2f}" if not np.isnan(xp) else "   nan"
        h_str = f"{hwhm:.2f}" if not np.isnan(hwhm) else "  nan"
        print(f"  {tau0:5d}  {a*tau0:5.1f}  {x_pred:5.2f}  {xp_str:>7s}  "
              f"{h_str:>7s}  {n_esc:6d}")

        import time as _t
        _t.sleep(3)

    print(f"{'-'*60}")
    return results


# ---- Scaling fit ----------------------------------------------------------
def fit_scaling(results, label):
    """Fit power-law x_mc ∝ (a·τ₀)^β and compare with predicted β=1/3."""
    xs = np.array([r[0] for r in results])
    ys = np.array([r[1] for r in results])
    valid = ~np.isnan(ys) & (ys > 0)
    if valid.sum() < 3:
        print(f"  {label}: insufficient valid points for fit")
        return

    x_valid = xs[valid]
    y_valid = ys[valid]
    at = a * x_valid

    # Fit log(y) = α + β·log(aτ₀)
    coeff = np.polyfit(np.log10(at), np.log10(y_valid), 1)
    beta = coeff[0]
    r2 = np.corrcoef(np.log10(at), np.log10(y_valid))[0, 1] ** 2

    print(f"  {label}:  x_peak ∝ (aτ₀)^{beta:.3f}   "
          f"(Neufeld: 1/3 ≈ 0.333),  R² = {r2:.4f}")


# ---- Run ------------------------------------------------------------------
print("=" * 60)
print("  Neufeld (1990) Test — KDE Peak Finding")
print("=" * 60)
tau0_values = [10, 30, 100, 300, 1000, 3000, 10000, 100000]

# R_IIA mode
res1 = run_test(tau0_values, ph_mode=1, label="ph_mode=1  (table Voigt + R_IIA)")
fit_scaling(res1, "ph_mode=1")

# Old-style test mode
res2 = run_test(tau0_values, ph_mode=2, label="ph_mode=2  (old Gaussian CFR)")
fit_scaling(res2, "ph_mode=2")

print()
print("=" * 60)
print("  Summary: x_peak scaling exponents")
print("=" * 60)
print(f"  Neufeld prediction:  x_peak = 0.88 * (a·τ₀)^(1/3)")
print(f"  Slope: β = 1/3 ≈ 0.333")
print()
print("  ph_mode=1 (table Voigt + R_IIA):  table-based H(a,u) for scattering")
print("    opacity, Voigt sampling (Gaussian ⊛ Lorentzian) in CFR core,")
print("    wing coherent |u|≥2 preserved lab-frame velocity.")
print()
print("  ph_mode=2 (old Gaussian CFR):  cruder max(Gaussian, a/(πx²))")
print("    Voigt approximation, pure Gaussian CFR, no wing coherence.")
print("    Matches July 2024 behaviour more closely.")
print()

print("Done.")
