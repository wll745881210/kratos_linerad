#!/usr/bin/env python3
"""
Neufeld (1990) Analytic Test — Resonance-Line Radiative Transfer
=================================================================

Compares Monte Carlo line RT results against the analytic solution for
a static, uniform, plane-parallel slab (Neufeld 1990, ApJ, 350, 216).

Uses a **synthetic 2-level system** with true CFR (sv=0, random frequency
draw at each scattering) and Voigt damping wing a = 0.01.

Tests:
  Block 1 — emergent spectrum shape vs analytic J(tau0, x) at 3 tau0 values
  Block 2 — peak-position scaling: x_peak ~ (a*tau0)^(1/3)
  Block 3 — dust suppression: escaped fraction vs tau_abs
"""

import sys, os
_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, _PROJECT)

import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

from core.line_rt import LineRt
from molecular.lamda_format import SpeciesData
from scipy.signal import find_peaks
from scipy.optimize import curve_fit

AU = 1.49598e13
h_cgs = 6.62607015e-27
c_cgs = 2.99792458e10
k_B   = 1.380649e-16
sqrt_pi = 1.77245385091

# ═══════════════════════════════════════════════════════════════════════
# 1. Synthetic 2-level species (a = 0.01, b_sca = 1e5 cm/s)
# ═══════════════════════════════════════════════════════════════════════

a = 0.01
b_sca = 1.0e5
sigma_th = b_sca / np.sqrt(2.0)
n_species_target = 1.0e3
L_slab_au = 1.0
L_slab_cm = L_slab_au * AU

sigma0_needed = 100.0 / (n_species_target * L_slab_cm)
g_u, g_l = 3.0, 1.0
nu_hz = np.sqrt((g_u / g_l) * a * c_cgs * c_cgs
                 / (2.0 * np.sqrt(2.0) * sqrt_pi * sigma0_needed))
nu_GHz = nu_hz / 1.0e9
A_ul = a * 4.0 * np.pi * nu_hz * sigma_th / c_cgs
E_u_K = h_cgs * nu_hz / k_B

print("=== Synthetic 2-Level Species ===")
print(f"  a = {a:.4f}, b_sca = {b_sca:.1e}, sigma_th = {sigma_th:.1e}")
print(f"  nu_0 = {nu_hz:.3e} Hz ({nu_GHz:.2f} GHz), A_ul = {A_ul:.3e} s^-1")
print(f"  E_u/K = {E_u_K:.1f} K, g_u={g_u:.0f}, g_l={g_l:.0f}")
print(f"  sigma0 = {sigma0_needed:.2e} cm^2 (verified below)")

synthetic = SpeciesData(
    name="Neufeld2Level",
    n_levels=2, n_transitions=1,
    levels=np.array([[0.0, g_l], [E_u_K, g_u]], dtype=np.float64),
    transitions=np.array([[1, 0, A_ul, nu_GHz]], dtype=np.float64),
)
sigma0 = synthetic.cross_section(0, b_sca)
print(f"  Verified sigma0 = {sigma0:.2e} cm^2")

# ═══════════════════════════════════════════════════════════════════════
# 2. Neufeld analytic formula
# ═══════════════════════════════════════════════════════════════════════

def neufeld_transmitted(x, a_tau0):
    """Transmitted J(tau0, x) — Neufeld 1990 eq. 2.24."""
    abs_x = np.abs(x)
    arg = np.sqrt(np.pi**3 / 54.0) * abs_x**3 / np.maximum(a_tau0, 1e-30)
    arg = np.minimum(arg, 100.0)
    denominator = a_tau0 * np.cosh(arg)
    denominator = np.maximum(denominator, 1e-300)
    j = (np.sqrt(6.0) / 24.0) * x**2 / denominator
    return j


def find_peak_x(vel, sigma_th, n_bins=120):
    """Find |x_peak| from velocity histogram using Gaussian fit near peak."""
    # Focus on positive side
    v_pos = vel[vel > 0]
    if len(v_pos) < 20:
        return 0.0, 0.0
    v_min, v_max = 0.0, min(v_pos.max(), 5 * sigma_th)
    bins = np.linspace(v_min, v_max, n_bins + 1)
    counts, edges = np.histogram(v_pos, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    # Find peak via simple smoothing + argmax
    smooth = np.convolve(counts.astype(float), np.ones(5)/5, mode='same')
    i_peak = np.argmax(smooth)
    v_peak = centers[i_peak]
    return v_peak / sigma_th, v_peak


# ═══════════════════════════════════════════════════════════════════════
# 3. Test data collection
# ═══════════════════════════════════════════════════════════════════════

tau0_values = [100, 1000, 10000]
results_data = {}
baseline_escaped = {}

print("\n" + "=" * 60)
print("Running MC simulations (CFR, ph_mode=0, a_voigt=0.01)")
print("=" * 60)

for tau0 in tau0_values:
    n_s = tau0 / (sigma0 * L_slab_cm)
    n_step_use = max(200000, tau0 * 50)
    n_scat_use = max(200000, tau0 * 50)

    print(f"\n--- tau0 = {tau0} (n_species={n_s:.2e}, n_step={n_step_use}) ---")

    rt = LineRt(
        n_cell=(64, 2, 2),
        x_min=(-L_slab_au / 2, 0, 0),
        x_max=(L_slab_au / 2, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        species=synthetic, transition_idx=0,
        n_species=n_s, temperature=10.0,
        b_sca=b_sca,
        ph_mode=0, n_step=n_step_use, n_scat=n_scat_use, n_cycles=1,
        n_emission_max=0,
        mol_mass=1.0, a_voigt=a,
        visualize=False,
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(
        type="slab",
        x=-L_slab_au / 2 + 0.02,
        n_photon=8000,
        flux=1e10 / (0.2 * 0.2 * AU * AU),
        wavelength=c_cgs / nu_hz,
    )
    res = rt.run()

    vel_data = np.asarray(res["spectrum"]["vel"])
    results_data[tau0] = {"vel": vel_data, "n_species": n_s}
    baseline_escaped[tau0] = len(vel_data)

    n_esc = len(vel_data)
    v_rms = float(np.std(vel_data)) if n_esc > 5 else 0.0
    a_tau0 = a * tau0
    x_peak_pred = 1.066 * a_tau0**(1.0 / 3.0)
    v_peak_pred = x_peak_pred * sigma_th
    x_peak_mc, v_peak_mc = find_peak_x(vel_data, sigma_th)

    print(f"  Escaped: {n_esc}, v_rms = {v_rms:.1e} cm/s")
    print(f"  Analytic: x_peak = {x_peak_pred:.3f}, v_peak = {v_peak_pred:.1e} cm/s")
    print(f"  MC:       x_peak = {x_peak_mc:.3f}, v_peak = {v_peak_mc:.1e} cm/s")

# ═══════════════════════════════════════════════════════════════════════
# 4. Block 2 — peak-position scaling (expanded tau0 range)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("Block 2: Peak-position scaling")
print("=" * 60)

tau0_more = [30, 100, 300, 1000, 3000, 10000]
x_peaks_mc = []
x_peaks_analytic = []
a_tau0_list = []

for tau0 in tau0_more:
    a_tau0 = a * tau0
    a_tau0_list.append(a_tau0)
    x_p = 1.066 * a_tau0**(1.0 / 3.0)
    x_peaks_analytic.append(x_p)

    if tau0 in results_data:
        vel_data = results_data[tau0]["vel"]
    else:
        n_s = tau0 / (sigma0 * L_slab_cm)
        n_step_use = max(200000, tau0 * 50)
        n_scat_use = max(200000, tau0 * 50)
        rt = LineRt(
            n_cell=(64, 2, 2),
            x_min=(-L_slab_au / 2, 0, 0),
            x_max=(L_slab_au / 2, 0.2, 0.2),
            unit_l0=AU, unit_t0=1.0,
            species=synthetic, transition_idx=0,
            n_species=n_s, temperature=10.0,
            b_sca=b_sca,
            ph_mode=0, n_step=n_step_use, n_scat=n_scat_use, n_cycles=1,
            n_emission_max=0, mol_mass=1.0, a_voigt=a, visualize=False,
        )
        rt.set_boundary("fre fre per per per per")
        rt.add_source(
            type="slab", x=-L_slab_au / 2 + 0.02, n_photon=8000,
            flux=1e10 / (0.2 * 0.2 * AU * AU), wavelength=c_cgs / nu_hz,
        )
        res = rt.run()
        vel_data = np.asarray(res["spectrum"]["vel"])
        results_data[tau0] = {"vel": vel_data, "n_species": n_s}

    x_mc, v_mc = find_peak_x(vel_data, sigma_th)
    x_peaks_mc.append(x_mc)
    print(f"  tau0={tau0:5d}  a*tau0={a_tau0:.3f}  "
          f"x_peak_pred={x_p:.3f}  x_peak_mc={x_mc:.3f}")

# ═══════════════════════════════════════════════════════════════════════
# 5. Block 3 — dust suppression
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("Block 3: Dust suppression (tau0=100)")
print("=" * 60)

tau_abs_values = [0.0, 1.0, 3.0, 10.0]
tau0_dust = 100
n_s_dust = tau0_dust / (sigma0 * L_slab_cm)
escaped_fraction = []
analytic_suppression = []

for ta in tau_abs_values:
    mfp_abs = L_slab_cm / max(ta, 1e-10)
    rt = LineRt(
        n_cell=(64, 2, 2),
        x_min=(-L_slab_au / 2, 0, 0),
        x_max=(L_slab_au / 2, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        species=synthetic, transition_idx=0,
        n_species=n_s_dust, temperature=10.0,
        b_sca=b_sca, mfp_i_abs_0=mfp_abs,
        ph_mode=0, n_step=200000, n_scat=200000, n_cycles=1,
        n_emission_max=0, mol_mass=1.0, a_voigt=a, visualize=False,
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(
        type="slab", x=-L_slab_au / 2 + 0.02, n_photon=8000,
        flux=1e10 / (0.2 * 0.2 * AU * AU), wavelength=c_cgs / nu_hz,
    )
    res = rt.run()
    vel_data = np.asarray(res["spectrum"]["vel"])
    frac = len(vel_data) / 8000.0
    escaped_fraction.append(frac)
    analytic_s = np.exp(-ta * np.sqrt(tau0_dust))
    analytic_suppression.append(analytic_s)
    print(f"  tau_abs={ta:.1f}  esc_frac={frac:.4f}  "
          f"exp(-tau_a*sqrt(tau0))={analytic_s:.4f}")

# ═══════════════════════════════════════════════════════════════════════
# 6. Plot
# ═══════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Block 1: spectrum shape
ax = axes[0]
for tau0 in tau0_values:
    vel = results_data[tau0]["vel"]
    if len(vel) == 0:
        continue
    vels_km = vel * 1e-5
    bins_fine = np.linspace(-5, 5, 100)
    ax.hist(vels_km, bins=bins_fine, density=True, alpha=0.35,
            label=f"MC $\\tau_0$={tau0}")
    # Analytic envelope
    a_tau0 = a * tau0
    x_dop = np.linspace(-8, 8, 400)
    j_analytic = neufeld_transmitted(x_dop, a_tau0)
    j_analytic /= np.max(j_analytic) if np.max(j_analytic) > 0 else 1.0
    v_analytic = x_dop * sigma_th * 1e-5
    ax.plot(v_analytic, j_analytic, '-', lw=1.5,
            label=f"Analytic $a\\tau_0$={a_tau0:.2f}")
ax.set_xlabel("velocity [km/s]")
ax.set_ylabel("normalised density")
ax.set_title("Block 1: Emergent Spectrum Shape (CFR)")
ax.legend(fontsize=7, loc='upper right')

# Block 2: peak position
ax = axes[1]
a_tau0_arr = np.array(a_tau0_list)
ax.loglog(a_tau0_arr, x_peaks_analytic, 'k--', lw=2,
          label="$x_p = 1.066\\,(a\\tau_0)^{1/3}$")
ax.loglog(a_tau0_arr, x_peaks_mc, 'ro-', ms=7, label='MC (CFR)')
ax.set_xlabel("$a\\,\\tau_0$")
ax.set_ylabel("$|x_{\\rm peak}|$ [Doppler units]")
ax.set_title("Block 2: Peak-Position Scaling")
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

# Block 3: dust
ax = axes[2]
ax.semilogy(tau_abs_values, escaped_fraction, 'ro-', ms=8, label='MC')
ax.semilogy(tau_abs_values, analytic_suppression, 'k--', lw=2,
            label='$\\exp(-\\tau_a\\sqrt{\\tau_0})$')
ax.set_xlabel("$\\tau_{\\rm abs}$"); ax.set_ylabel("escaped fraction")
ax.set_title("Block 3: Dust Suppression ($\\tau_0=100$)")
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)

fig.tight_layout()
_HERE = os.path.dirname(os.path.realpath(__file__))
outpath = os.path.join(_HERE, "neufeld_test_results.png")
fig.savefig(outpath, dpi=150)
print(f"\nResults saved to {outpath}")

# ═══════════════════════════════════════════════════════════════════════
# 7. Summary
# ═══════════════════════════════════════════════════════════════════════

print("\n=== Neufeld Test Summary ===")
print(f"Synthetic species: {synthetic.name}")
print(f"  a = {a:.4f}, b_sca = {b_sca:.1e} cm/s, sigma_th = {sigma_th:.1e}")
print(f"  sigma0 = {sigma0:.2e} cm^2, L_slab = {L_slab_cm:.2e} cm")
print(f"  Mode: CFR (ph_mode=0, sv=0, Gaussian randomization)")
print()
print(f"{'tau0':>6s}  {'a*tau0':>7s}  {'x_peak_pred':>10s}  "
      f"{'x_peak_mc':>10s}  {'v_peak_mc(cm/s)':>15s}  {'n_esc'}")

for tau0, data in results_data.items():
    vel = data["vel"]
    a_tau0 = a * tau0
    x_pred = 1.066 * a_tau0**(1.0 / 3.0)
    x_mc, v_mc = find_peak_x(vel, sigma_th)
    print(f"{tau0:6d}  {a_tau0:7.3f}  {x_pred:10.3f}  "
          f"{x_mc:10.3f}  {v_mc:15.1e}  {len(vel)}")

print("\nNeufeld test complete.")
