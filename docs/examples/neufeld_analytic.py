#!/usr/bin/env python3
"""
Neufeld (1990) Analytic Formulas
=================================

Formulas from D. A. Neufeld, 1990, ApJ, 350, 216,
"The Transfer of Resonance-Line Radiation in Static Astrophysical Media".

Normalized frequency:  x = (ν − ν₀) / Δν_D,  Δν_D = ν₀ × σ_th / c
Voigt damping:        a = A_ul / (4π Δν_D)
Cross section:        σ₀ = (g_u/g_l) × A_ul × c³ / (8 π³/² ν₀³ b)
Line-centre opacity:  k₀ = n_lower × σ₀ / √(π) / Δν_D   [cm⁻¹]

All formulas assume:
  - Static, uniform, plane-parallel slab
  - T₀ = 2 t₀ ≫ 10³/a  (extremely large scattering optical depth)
  - Low density (R_IIA — complete frequency redistribution)
  - Monochromatic source at line centre (x_f = 0)
"""

import numpy as np

sqrt_pi  = 1.7724538509055159
sqrt_6   = 2.449489742783178
pi_pow_3 = 31.006276680299816   # π³
fac_cosh = np.sqrt(pi_pow_3 / 54.0)   # √(π³/54)


def a_voigt_from_A_ul(A_ul, nu_0, sigma_th):
    """Compute Voigt damping parameter a."""
    delta_nu_D = nu_0 * sigma_th / 2.99792458e10
    return A_ul / (4.0 * np.pi * delta_nu_D)


def cross_section_0(g_u, g_l, A_ul, nu_0, b):
    """Line-centre cross section σ₀.

    PHYSICS.md §5.1:
      σ₀ = (g_u/g_l) × A_ul × c³ / (8 π^(3/2) ν₀³ b)
    """
    c = 2.99792458e10
    return (g_u / g_l) * A_ul * c**3 / (8.0 * sqrt_pi**3 * nu_0**3 * b)


def mfp_inv_line_centre(sigma_0, n_lower):
    """Inverse MFP at line centre (before overlap integral)."""
    return sigma_0 * n_lower


def tau_line_centre(sigma_0, n_lower, L):
    """Line-centre optical depth.

    Includes the 1/√2 factor from the CFR overlap integral
    I(x=0) = 1/√2.
    """
    return sigma_0 * n_lower * L / np.sqrt(2.0)


def sigma_0_from_tau(tau_0, n_lower, L):
    """Compute σ₀ needed to achieve target τ₀ at line centre."""
    return tau_0 * np.sqrt(2.0) / (n_lower * L)


def to_doppler(x, nu_0, sigma_th):
    """Dimensionless frequency x → physical velocity [cm/s]."""
    return x * sigma_th


def from_velocity(v, sigma_th):
    """Physical velocity [cm/s] → dimensionless x."""
    return v / sigma_th


def emergent_central_slab(x, a_tau0):
    """Transmitted J(x) for a thin central source at line centre.

    Neufeld 1990, eq. 2.24 evaluated at the boundary with x_f=0, t_s=0.
    This is the limit of eq. 2.32 when T_r → ∞ (source at line centre,
    slab opaque at x=0).

    J(x) ∝ x² / [aT₀ × cosh(√(π³/54) × x³/(aT₀))]
    """
    abs_x = np.abs(np.asarray(x, dtype=np.float64))
    arg = fac_cosh * abs_x**3 / np.maximum(a_tau0, 1e-40)
    capped = np.minimum(arg, 100.0)
    return sqrt_6 / 24.0 * x**2 / (a_tau0 * np.cosh(capped) + 1e-300)


def transmitted_external(x, a_tau0, tau_f_line=None):
    """Transmitted spectrum for external illumination at line centre.

    Neufeld 1990, eq. 2.32.
    For a slab illuminated on the left face (x = −t₀), this gives the
    spectrum escaping from the right face (x = +t₀).

    When τ_f (monochromatic optical depth at injection frequency) ≫ 1,
    cos(2π/3T_r) ≈ 1 and sin(2π/3T_r) ≈ 0.  The formula reduces to the
    central-source form.
    """
    x = np.asarray(x, dtype=np.float64)
    abs_x3 = np.abs(x)**3
    arg = fac_cosh * abs_x3 / np.maximum(a_tau0, 1e-40)
    capped = np.minimum(arg, 100.0)
    return sqrt_6 / 24.0 * x**2 / (a_tau0 * np.cosh(capped) + 1e-300)


def x_peak(a_tau0):
    """Predicted peak position |x_peak| in Doppler units.

    From Adams (1972):  |x_peak| ≈ 1.066 × (a τ₀)^(1/3)
    """
    return 1.066 * (max(a_tau0, 1e-10))**(1.0 / 3.0)


def escape_fraction_dust(tau_0, tau_abs):
    """Approximate escaped fraction with continuum absorption.

    Neufeld 1990, §IV:  f_esc ≈ exp(−τ_abs × √τ₀)  for τ₀ ≫ 1.
    """
    tau_0 = np.asarray(tau_0, dtype=np.float64)
    tau_abs = np.asarray(tau_abs, dtype=np.float64)
    return np.exp(-tau_abs * np.sqrt(np.maximum(tau_0, 1.0)))
