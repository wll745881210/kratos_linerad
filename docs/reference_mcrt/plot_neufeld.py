#!/usr/bin/env python3
"""
Neufeld (1990) analytic solution vs reference MCRT.

Compares ph_mode=1 (R_IIA, USampler) against the
analytic emergent spectrum from Neufeld 1990, ApJ 350, 216.

J(x) = (√6/√π) · x² / cosh(√(π³/54) · |x|³ / (a τ₀))

Usage:
  python docs/reference_mcrt/plot_neufeld.py [output_prefix]
"""

import os, sys, time
import numpy as np

_project = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))
sys.path.insert(0, _project)

from docs.reference_mcrt.mcrt import run_mcrt

A_VOIGT = 0.01
B_SCA = 1.0e5

_NEUFELD_K = np.sqrt(np.pi ** 3 / 54.0)
_NEUFELD_A = np.sqrt(6.0 / np.pi)


def neufeld_J(x, a_tau):
    xa = np.abs(x)
    denom = _NEUFELD_K * xa * xa * xa / (a_tau + 1e-35)
    if denom.max() > 600:
        denom = np.clip(denom, -600, 600)
    return _NEUFELD_A * xa * xa / np.cosh(denom)


def run_one(tau, n_ph, a, b_sca, ph_mode, seed):
    dx = 1.0e13
    mesh = {
        'n_cell': np.array([1, 2, 2], dtype=np.int32),
        'x_min': np.array([-dx / 2.0, 0.0, 0.0], dtype=np.float64),
        'dx': np.array([dx, dx * 0.1, dx * 0.1], dtype=np.float64),
    }
    mfp_s = 2 * tau / dx

    rng = np.random.default_rng(seed)
    ph = np.zeros((n_ph, 9), dtype=np.float64)
    ph[:, 0] = 0.0
    ph[:, 1] = rng.uniform(0, dx * 0.1, n_ph)
    ph[:, 2] = rng.uniform(0, dx * 0.1, n_ph)
    n_half = n_ph // 2
    ph[:n_half, 3] = 1.0
    ph[n_half:, 3] = -1.0
    ph[:, 6] = 1.0 / n_ph

    result = run_mcrt(
        mesh=mesh, photons=ph, b_sca=b_sca,
        mfp_i_sca_0=mfp_s, mfp_i_abs_0=0.0,
        vel=None, ph_mode=ph_mode, a_voigt=a,
        seed=seed, parallel=True,
    )

    esc = result['escaped']
    esc_mask = result['term_reason'] == 1
    n_scat_all = result['n_scat']
    n_scat = n_scat_all[esc_mask]

    if len(esc) == 0:
        return None

    x = esc[:, 0] / b_sca
    weights = esc[:, 1]
    n_escaped = len(esc)
    med_n_scat = np.median(n_scat) if len(n_scat) > 0 else 0
    mean_n_scat = float(np.mean(n_scat)) if len(n_scat) > 0 else 0.0
    harrington_N = 1.612 * tau
    med_x = np.median(np.abs(x))
    x_peak_emp = _find_peak(x, weights)

    return {'x': x, 'weights': weights, 'n_escaped': n_escaped,
            'med_n_scat': med_n_scat, 'mean_n_scat': mean_n_scat,
            'harrington_N': harrington_N,
            'med_x': med_x, 'x_peak': x_peak_emp,
            'tau': tau, 'n_ph': n_ph, 'ph_mode': ph_mode, 'a': a,
            'f_esc': n_escaped / n_ph}


def _find_peak(x, w):
    if len(x) < 50:
        return np.nan
    xa = np.abs(x)
    hi = xa.max()
    bins = np.linspace(0, hi, 120)
    bc = (bins[:-1] + bins[1:]) / 2.0
    hist, _ = np.histogram(xa, bins=bins, weights=w)
    J = hist / np.diff(bins)
    top = np.argmax(J)
    lo, hi2 = max(0, top - 2), min(len(bc), top + 3)
    if hi2 - lo >= 3:
        coeffs = np.polyfit(bc[lo:hi2], J[lo:hi2], 2)
        return -coeffs[1] / (2.0 * coeffs[0])
    return bc[top]


def plot_results(results, output_prefix='neufeld'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    font = {'family': 'sans-serif', 'size': 10}
    fig, axes = plt.subplots(2, 1, figsize=(10, 12))

    # ── Panel 1: emergent spectrum J(x) vs x ──
    ax = axes[0]
    x_plot = np.linspace(0.01, 40, 400)
    colors = plt.cm.viridis(np.linspace(0.0, 0.95, len(results)))

    for (res, ci) in zip(results, colors):
        tau = res['tau']
        at = A_VOIGT * tau
        x = res['x']
        w = res['weights']

        xa = np.abs(x)
        hi = min(xa.max(), 50.0)
        bins = np.linspace(0, hi, 60)
        bc = (bins[:-1] + bins[1:]) / 2.0
        hist, _ = np.histogram(xa, bins=bins, weights=w)
        J_emp = hist / np.diff(bins)
        norm = np.trapz(J_emp, bc) if len(bc) > 1 else 1.0
        if norm > 0:
            J_emp /= norm

        J_an = neufeld_J(x_plot, at)
        norm_an = np.trapz(J_an, x_plot)
        if norm_an > 0:
            J_an /= norm_an

        ax.step(bc, J_emp, where='mid', color=ci, lw=1.2,
                label=f'τ={tau:.0e} (MC)')
        ax.plot(x_plot, J_an, '--', color=ci, lw=1.0, alpha=0.7)

    ax.set_xscale('linear')
    ax.set_yscale('linear')
    ax.set_xlabel(r'$|x|$ (frequency, Doppler units)')
    ax.set_ylabel(r'$J(|x|)$ (normalized)')
    ax.set_title(r'Neufeld (1990) emergent spectrum, a=0.01, R$_\mathrm{II}$A (ph_mode=1)')
    ax.legend(fontsize=7, loc='upper right')
    ax.set_xlim(0, 40)
    ax.grid(True, alpha=0.3)

    # ── Panel 2: x_peak vs a τ₀ ──
    ax = axes[1]
    ataus = np.array([A_VOIGT * r['tau'] for r in results])
    x_peaks = np.array([r['x_peak'] for r in results])

    at_plot = np.logspace(np.log10(max(ataus.min(), 1.0)), np.log10(ataus.max()) + 0.3, 200)
    x_pred = 1.07 * at_plot ** (1.0 / 3.0)
    ax.loglog(at_plot, x_pred, 'k-', lw=1.5, alpha=0.6,
              label=r'$x_\mathrm{peak} = 1.07\,(a\tau_0)^{1/3}$')
    ax.fill_between(at_plot, x_pred * 0.85, x_pred * 1.15, color='k', alpha=0.08)

    ax.loglog(ataus, x_peaks, 'o-', color='C0', ms=8, label='x_peak (MC)')

    # Mark aτ₀=100 validity threshold
    ax.axvline(100, color='grey', ls=':', lw=1.0, alpha=0.5)
    ax.text(100, ax.get_ylim()[1] * 0.9, r'$a\tau_0=100$', fontsize=7,
            color='grey', ha='left', va='top')

    ax.set_xlabel(r'$a \tau_0$')
    ax.set_ylabel(r'$x_\mathrm{peak}$ (Doppler units)')
    ax.set_title('Frequency peak scaling (valid for aτ₀ ≳ 100)')
    ax.legend(fontsize=8, loc='lower right')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(1, 100)

    plt.tight_layout()
    out_path = f'{output_prefix}_comparison.png'
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"\n  Saved figure: {out_path}")
    return out_path


def main():
    output_prefix = sys.argv[1] if len(sys.argv) > 1 else 'neufeld'

    configs = [
        (1e3,   5000),
        (3e3,   5000),
        (1e4,   5000),
        (3e4,   5000),
        (1e5,   10000),
        (3e5,   10000),
        (1e6,   20000),
    ]

    results = []
    print(f"Neufeld (1990) slab, R_IIA (ph_mode=1, USampler), a={A_VOIGT}")
    print(f"{'τ':>10s}  {'n_ph':>6s}  {'n_esc':>6s}  "
          f"{'<N_sc>':>8s}  {'Harr':>8s}  "
          f"{'x_peak':>8s}  {'x_pred':>8s}  {'time':>7s}")

    for tau, n_ph in configs:
        t0 = time.time()
        res = run_one(tau, n_ph, A_VOIGT, B_SCA, 1, seed=42 + int(tau))
        dt = time.time() - t0

        if res is None:
            print(f"  {tau:10.0f}  NO ESCAPERS")
            continue

        at = A_VOIGT * tau
        x_pred = 1.07 * at ** (1.0 / 3.0)
        print(f"  {tau:10.0f}  {n_ph:6d}  {res['n_escaped']:6d}  "
              f"{res['mean_n_scat']:8.0f}  {res['harrington_N']:8.0f}  "
              f"{res['x_peak']:8.3f}  {x_pred:8.3f}  "
              f"{dt:6.1f}s")
        results.append(res)

    if not results:
        print("No results!")
        return

    # ── aτ₀ scaling invariance cross-check ──
    # Same (aτ₀)^(1/3)=10 but different (a, τ₀): a=0.01/τ=1e3 vs a=0.05/τ=200
    print("\n  --- aτ₀ scaling invariance check ---")
    at_target = 10.0
    scaling_configs = [
        (A_VOIGT, int(at_target / A_VOIGT), 42),           # a=0.01, τ=1000
        (0.05, int(at_target / 0.05), 1042),                # a=0.05, τ=200
    ]
    scaling_results = []
    for a_s, tau_s, seed_s in scaling_configs:
        t0 = time.time()
        res = run_one(tau_s, 5000, a_s, B_SCA, 1, seed=seed_s)
        dt = time.time() - t0
        if res:
            at_s = a_s * tau_s
            x_pred_s = 1.07 * at_s ** (1.0 / 3.0)
            scaling_results.append(res)
            print(f"  a={a_s:.3f} τ={tau_s}: n_esc={res['n_escaped']} "
                  f"<N_sc>={res['mean_n_scat']:.0f} (Harr={res['harrington_N']:.0f}) "
                  f"x_peak={res['x_peak']:.3f} x_pred={x_pred_s:.3f} "
                  f"ratio={res['x_peak']/x_pred_s:.3f}  {dt:.1f}s")
        else:
            print(f"  a={a_s:.3f} τ={tau_s}: NO ESCAPERS")

    print(f"\n  --- R_IIA (ph_mode=1) summary (Neufeld valid for aτ₀ ≳ 100) ---")
    print(f"  {'τ':>10s}  {'a τ₀':>10s}  {'x_peak/x_pred':>13s}  "
          f"{'N_sc/Harr':>10s}")
    for res in results:
        at = A_VOIGT * res['tau']
        x_pred = 1.07 * at ** (1.0 / 3.0)
        valid = "*" if at >= 100 else " "
        nsc_rat = res['mean_n_scat'] / res['harrington_N'] if res['harrington_N'] > 0 else 0
        print(f"  {res['tau']:10.0f}  {at:10.0f}  "
              f"{res['x_peak']/x_pred:13.3f}  "
              f"{nsc_rat:10.3f}  {valid}")

    ataus = np.array([A_VOIGT * r['tau'] for r in results])
    x_peaks = np.array([r['x_peak'] for r in results])
    slope, icept = np.polyfit(np.log10(ataus), np.log10(x_peaks), 1)
    print(f"  log(x_peak) = {slope:.3f}·log(aτ₀) + {icept:.3f}")
    print(f"  x_peak coefficient = {10**icept:.2f}  (expected 1.07, slope 0.333)")

    plot_results(results + scaling_results, output_prefix)


if __name__ == '__main__':
    main()
