#!/usr/bin/env python3
"""
Neufeld (1990) Test — Numerical comparison only, no plotting.
=================================================================

Compares Monte Carlo line RT results (ph_mode=1 PRD, a_voigt > 0)
against analytic predictions from Neufeld 1990, ApJ, 350, 216.

Physics:
  - Static, uniform, plane-parallel slab, 1 AU wide
  - Group 2 (explicit opacity): mfp_i_sca_0 = τ₀ / L
  - a = 0.01, b_sca = 1e5 cm/s, mono source at line centre
  - Voigt profile (64×128 table) affects scattering MFP
  - Frequency redistribution: Gaussian (ph_mode=1 - CFR)

Output: text table only, printed to stdout.
"""

import sys, os, time
_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, _PROJECT)

import numpy as np
from neufeld_analytic import x_peak

c_cgs   = 2.99792458e10
AU      = 1.49598e13
sqrt2   = np.sqrt(2.0)

a      = 0.01
b_sca  = 1.0e5
sigma_th = b_sca / sqrt2
L_slab_cm = 1.0 * AU

print("=" * 72)
print("  Neufeld (1990) Numerical Test")
print("=" * 72)
print(f"  a = {a}, b_Doppler = {b_sca:.1e} cm/s, σ_th = {sigma_th:.1e} cm/s")
print(f"  L_slab = 1 AU = {L_slab_cm:.2e} cm")
print(f"  Scattering model: ph_mode=1 (CFR, Gaussian redistribution)")
print(f"  Voigt profile: 64×128 table, affects scattering MFP")
print(f"  Analytic: x_peak = 1.066 · (2a·τ₀)^(1/3)")
print()

# ---- test parameters ----
tau0_values = [10, 30, 100, 300, 1000, 3000]
n_source = 50000
n_cell_x = 55

results = {}  # tau0 -> (velocities, esc_count)

for tau0 in tau0_values:

    mfp_i_sca_0 = tau0 / L_slab_cm
    n_step = max(200000, int(tau0 * 500))
    n_scat = max(200000, int(tau0 * 100))

    from core.line_rt import LineRt
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
    results[tau0] = vel
    time.sleep(3)

# ---- spectrum metrics ----
def spectrum_metrics(velocities, tau0):
    """Return (x_peak_mc, fwhm_mc, escaped) from escaped photon velocities."""
    n_esc = len(velocities)
    if n_esc == 0:
        return np.nan, np.nan, 0, 0.0, 0.0

    abs_vel = np.abs(velocities)
    x_values = abs_vel / sigma_th       # in Doppler units

    # Peak: mode of |x| histogram (smoothing with Gaussian kernel)
    bins = np.linspace(0, 10, 200)
    cnt, edges = np.histogram(x_values, bins=bins, density=False)
    # Gaussian-kernel smooth (σ = 1 bin)
    sigma_sm = 2.0
    kernel = np.exp(-0.5 * ((np.arange(-10, 11) / sigma_sm)) ** 2)
    kernel /= kernel.sum()
    cnt_sm = np.convolve(cnt.astype(float), kernel, mode='same')
    idx_peak = np.argmax(cnt_sm)
    x_peak_mc = 0.5 * (bins[idx_peak] + bins[idx_peak + 1])

    # FWHM: range containing 50% of photons (percentile-based)
    x_sorted = np.sort(x_values)
    n_half = n_esc // 2
    fwhm_mc = x_sorted[n_half]  # median = half-width at half-maximum for symmetric

    # Fraction at |x| > 1σ
    frac_wing = (abs_vel > sigma_th).sum() / n_esc
    # Fraction at |x| > 3σ
    frac_tail = (abs_vel > 3 * sigma_th).sum() / n_esc

    return x_peak_mc, fwhm_mc, n_esc, frac_wing, frac_tail


print("-" * 72)
print(f" {'τ₀':>5s}  {'a·τ₀':>6s}  {'x_pred':>7s}  {'x_mc':>7s}  "
      f"{'HWHM':>7s}  {'|x|>1σ':>7s}  {'|x|>3σ':>7s}  {'n_esc':>7s}")
print("-" * 72)

for tau0 in tau0_values:
    vel = results[tau0]
    xp, hwhm, n_esc, fw, ft = spectrum_metrics(vel, tau0)
    x_pred = x_peak(a * 2.0 * tau0)
    print(f"  {tau0:4d}  {a*tau0:6.1f}  {x_pred:6.2f}  "
          f"{xp:6.2f}  {hwhm:6.2f}  {fw:6.4f}  {ft:6.4f}  {n_esc:6d}")

print("-" * 72)
print()
print("  x_peak = peak of |velocity| distribution [Doppler units]")
print("  HWHM   = median |velocity| / σ_th")
print("  |x|>kσ = fraction of photons with |velocity| > k·σ_th")
print()
print("  NOTE: ph_mode=1 uses Gaussian (not Voigt) frequency")
print("  redistribution after each scatter. This produces narrower")
print("  spectra than Neufeld's analytic solution, which assumes")
print("  CFR with a Voigt frequency profile (R_IIA).")
print()
print("  The Voigt profile in this test correctly modulates the")
print("  scattering MFP via the table-based itg.voigt_H(a,u).")
print("  Full Neufeld agreement would require Voigt-based")
print("  frequency redistribution in photon.h (R_IIA model).")
print()

# ---- Block 3: dust suppression (quick check) ----
print("=" * 72)
print("  Dust Suppression (τ₀ = 100)")
print("=" * 72)
print(f" {'τ_abs':>7s}  {'escaped frac':>13s}  {'analytic':>9s}")
print("-" * 42)

tau0_fixed = 100
mfp_i_sca_fixed = tau0_fixed / L_slab_cm

for ta in [0.0, 0.5, 1.0, 3.0, 10.0]:
    mfp_abs_inv = ta / L_slab_cm if ta > 0 else 0.0
    from core.line_rt import LineRt
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
    from neufeld_analytic import escape_fraction_dust
    a_esc = escape_fraction_dust(tau0_fixed, ta)
    print(f"  {ta:5.1f}  {frac:12.6f}  {a_esc:9.6f}")
    time.sleep(3)

print("-" * 42)
print()
print("Done.")
