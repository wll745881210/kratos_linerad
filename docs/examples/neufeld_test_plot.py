#!/usr/bin/env python3
"""
Neufeld (1990) Test — Generate result figures.
================================================

Produces neufeld_test_results.png with 4 panels:
  1. Emergent spectrum at selected τ₀ (ph_mode=1)
  2. Emergent spectrum at selected τ₀ (ph_mode=2)
  3. Peak-position scaling (MC vs Neufeld prediction)
  4. Comparison summary table

Requires scipy for KDE peak finding.
"""

import os, sys, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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


# ---- Peak finder ------------------------------------------------------------
def kde_peak(velocities, x_max=10.0, n_points=500):
    v = np.asarray(velocities, dtype=np.float64)
    v = v[~np.isnan(v)]
    n_tot = len(v)
    if n_tot < 10:
        return np.nan

    x = np.abs(v) / sigma_th
    bw = 1.06 * np.std(x) * n_tot**(-0.2) if n_tot > 1 else 0.1
    bw = max(bw, 0.02)
    try:
        kde = gaussian_kde(x, bw_method=bw)
    except Exception:
        return np.nan
    x_grid = np.linspace(0, x_max, n_points)
    pdf = kde(x_grid)
    maxima = argrelextrema(pdf, np.greater, order=15)[0]
    maxima = maxima[maxima >= 10]
    if len(maxima) == 0:
        return np.nan
    for idx in maxima:
        if pdf[idx] > 0.20 * pdf.max():
            return float(x_grid[idx])
    return np.nan


# ---- Run single tau0 and collect data ----------------------------------------
def run_one(tau0, ph_mode, n_source=50000):
    mfp = tau0 / L_slab
    n_src = 20000 if tau0 >= 10000 else n_source
    n_step = max(10000000 if tau0 >= 10000 else 200000, int(tau0 * 500))
    n_scat = max(100000 if tau0 >= 100000 else 200000, int(tau0 * 100))
    from core.line_rt import LineRt
    rt = LineRt(
        n_cell=(55, 2, 2), x_min=(-0.5, 0, 0), x_max=(0.5, 0.2, 0.2),
        unit_l0=AU, unit_t0=1.0,
        b_sca=b_sca, mfp_i_sca_0=mfp, mfp_i_abs_0=0.0,
        vel=(0., 0., 0.),
        ph_mode=ph_mode, n_step=n_step, n_scat=n_scat,
        n_cycles=1, a_voigt=a, visualize=False,
        path=f'/tmp/nf_plot_p{ph_mode}_t{tau0}/run',
    )
    rt.set_boundary("fre fre per per per per")
    rt.add_source(type="slab", x=-0.49, n_photon=n_src,
                  luminosity=float(n_src))
    res = rt.run()
    vel = np.asarray(res["results"][0]["photons"]["vel"])
    vel = vel[~np.isnan(vel)]
    return vel


# ---- Main sweep --------------------------------------------------------------
print("=" * 50)
print("  Neufeld (1990) MC vs Analytic")
print("=" * 50)

tau0_list = [10, 30, 100, 300, 1000, 3000, 10000, 100000]
vel_data = {}  # (ph_mode, tau0) -> velocities
peaks = {}     # (ph_mode, tau0) -> x_peak_mc

for ph_mode, label in [(1, "ph_mode=1 (table Voigt + R_IIA)"),
                         (2, "ph_mode=2 (old Gaussian CFR)")]:
    print(f"\n--- {label} ---")
    for tau0 in tau0_list:
        vel = run_one(tau0, ph_mode)
        vel_data[(ph_mode, tau0)] = vel
        xp = kde_peak(vel)
        peaks[(ph_mode, tau0)] = xp
        x_pred = x_peak(a * tau0)
        print(f"  τ₀={tau0:6d}:  x_mc={xp:.2f}  x_pred={x_pred:.2f}  "
              f"esc={len(vel)}")
        time.sleep(3)


# ---- Plotting ---------------------------------------------------------------
print("\nPlotting...")
fig = plt.figure(figsize=(14, 12))

# --- Panel 1: Spectra for ph_mode=1 at selected τ₀ ---
ax1 = fig.add_subplot(2, 2, 1)
colors = plt.cm.viridis(np.linspace(0.1, 0.95, 4))
plot_taus = [10, 100, 1000, 3000]
for tau0, c in zip(plot_taus, colors):
    vel = vel_data[(1, tau0)]
    x_vals = np.abs(vel) / sigma_th
    bins = np.linspace(0, 12, 120)
    cnt, edges = np.histogram(x_vals, bins=bins, density=True)
    xc = 0.5 * (edges[:-1] + edges[1:])
    ax1.plot(xc, cnt, color=c, lw=1.3, alpha=0.9, label=f'τ₀={tau0}')
    xp = peaks[(1, tau0)]
    if not np.isnan(xp):
        ax1.axvline(xp, color=c, ls='--', lw=0.8, alpha=0.5)
ax1.set_xlabel(r'$|x| = |\Delta v| / \sigma_{\rm th}$')
ax1.set_ylabel('PDF (normalised)')
ax1.set_title('ph_mode=1 (table Voigt + R_IIA)')
ax1.legend(fontsize=8, loc='upper right')
ax1.set_xlim(-0.5, 12)

# --- Panel 2: Spectra for ph_mode=2 at selected τ₀ ---
ax2 = fig.add_subplot(2, 2, 2)
for tau0, c in zip(plot_taus, colors):
    vel = vel_data[(2, tau0)]
    x_vals = np.abs(vel) / sigma_th
    bins = np.linspace(0, 12, 120)
    cnt, edges = np.histogram(x_vals, bins=bins, density=True)
    xc = 0.5 * (edges[:-1] + edges[1:])
    ax2.plot(xc, cnt, color=c, lw=1.3, alpha=0.9, label=f'τ₀={tau0}')
    xp = peaks[(2, tau0)]
    if not np.isnan(xp):
        ax2.axvline(xp, color=c, ls='--', lw=0.8, alpha=0.5)
ax2.set_xlabel(r'$|x| = |\Delta v| / \sigma_{\rm th}$')
ax2.set_ylabel('PDF (normalised)')
ax2.set_title('ph_mode=2 (old Gaussian CFR)')
ax2.legend(fontsize=8, loc='upper right')
ax2.set_xlim(-0.5, 12)

# --- Panel 3: Peak-position scaling ---
ax3 = fig.add_subplot(2, 2, 3)
at_smooth = np.logspace(-1.2, 3.2, 80)
x_pred_smooth = x_peak(a * at_smooth / a)
ax3.plot(at_smooth, x_pred_smooth, 'k-', lw=1.2, alpha=0.5,
         label='Neufeld: 0.88·(aτ₀)^(1/3)')

for ph_mode, marker, lbl in [(1, 'o', 'ph_mode=1 (R_IIA)'),
                               (2, 's', 'ph_mode=2 (old)')]:
    at_arr = np.array([a * t for t in tau0_list])
    xp_arr = np.array([peaks[(ph_mode, t)] for t in tau0_list])
    valid = ~np.isnan(xp_arr)
    ax3.plot(at_arr[valid], xp_arr[valid], marker + '-', ms=6,
             lw=1.2, label=lbl)

ax3.set_xlabel(r'$a\,\tau_0$')
ax3.set_ylabel(r'$x_{\rm peak}$')
ax3.set_title('Peak-Position Scaling')
ax3.legend(fontsize=8)
ax3.set_xscale('log')
ax3.set_yscale('log')
ax3.grid(True, alpha=0.3)

# --- Panel 4: Data table ---
ax4 = fig.add_subplot(2, 2, 4)
ax4.axis('off')
table_data = [['τ₀', 'aτ₀', 'x_pred',
               'x_mc (R_IIA)', 'x_mc (old)', 'HWHM (R_IIA)', 'HWHM (old)']]
for tau0 in tau0_list:
    x_pred = x_peak(a * tau0)
    xp1 = peaks[(1, tau0)]
    xp2 = peaks[(2, tau0)]
    h1 = np.median(np.abs(vel_data[(1, tau0)])) / sigma_th
    h2 = np.median(np.abs(vel_data[(2, tau0)])) / sigma_th
    table_data.append([
        f'{tau0}', f'{a*tau0:.1f}', f'{x_pred:.2f}',
        f'{xp1:.2f}' if not np.isnan(xp1) else '—',
        f'{xp2:.2f}' if not np.isnan(xp2) else '—',
        f'{h1:.2f}', f'{h2:.2f}',
    ])
table = ax4.table(cellText=table_data, loc='center',
                  cellLoc='center', colWidths=[0.1]*7)
table.auto_set_font_size(False)
table.set_fontsize(7.5)
table.scale(1.0, 1.3)
for i in range(len(table_data[0])):
    table[0, i].set_facecolor('#404040')
    table[0, i].set_text_props(color='white', fontweight='bold')
ax4.set_title('Summary', fontweight='bold', pad=10)

plt.tight_layout(pad=2.0)
out_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        'neufeld_test_results.png')
fig.savefig(out_path, dpi=150, bbox_inches='tight')
print(f"\nSaved: {out_path}")

# Also save data as text
txt_path = out_path.replace('.png', '.txt')
with open(txt_path, 'w') as f:
    f.write("Neufeld (1990) Test Results\n")
    f.write("============================\n")
    f.write(f"a = {a}, b_sca = {b_sca:.1e} cm/s, "
            f"sigma_th = {sigma_th:.1e} cm/s, L = 1 AU\n\n")
    f.write(" ".join(table_data[0]) + "\n")
    for row in table_data[1:]:
        f.write(" ".join(str(v) for v in row) + "\n")
    f.write(f"\nSaved as {out_path}\n")
print(f"Saved: {txt_path}")
print("Done.")
