#!/usr/bin/env python3
"""
Optically thick scattering imaging test vs Neufeld (1990).

Validates the st_cam scattering source function accumulation and imaging
ray-tracing in the optically thick regime (a*tau0 >> 1), where the emergent
spectrum follows Neufeld (1990) eq. (2.24).

Setup: uniform slab with internal emission, pure scattering (eps=0),
face-on imaging along the slab axis.  In the thick limit the angular
distribution is isotropic, so the face-on intensity I(x, mu=1) should
match the angle-averaged emergent spectrum J(x).

Tests:
  1. Imaging spectrum vs Neufeld (shape, normalized)
  2. Source function flatness (st_cam algorithm)
  3. Imaging vs escaped spectrum (consistency)
  4. Neufeld scaling (x_peak ~ (a*tau0)^(1/3))
  5. Absolute normalization (thermal seed check)
  6. Golden table (--measure mode)

Usage:
  python3 tests/test_imaging_neufeld.py
  python3 tests/test_imaging_neufeld.py --measure
  python3 tests/test_imaging_neufeld.py --plots
  python3 tests/test_imaging_neufeld.py --tau0-list 200 2000
"""

import argparse, os, sys;
from pathlib import Path;

import numpy as np;
from scipy.special import voigt_profile;

_PIPELINE = os.path.join(
    os.path.dirname( os.path.dirname( os.path.realpath( __file__ ) ) ),
    'line_rt.py' );
import importlib.util;
_spec = importlib.util.spec_from_file_location( 'line_rt', _PIPELINE );
assert _spec is not None and _spec.loader is not None;
line_rt = importlib.util.module_from_spec( _spec );
_spec.loader.exec_module( line_rt );

# -- Constants --------------------------------------------------------

C_CGS   = 2.99792458e10;
H_CGS   = 6.62607015e-27;
KB_CGS  = 1.380649e-16;
AU_CGS  = 1.49597870691e13;
PI      = np.pi;
SQRT_PI = np.sqrt( PI );

# -- Transition parameters (synthetic, tuned for a=0.149) -------------

A_UL     = 7.2e-8;
FREQ_GHZ = 115.27;
G_U      = 3.0;
G_L      = 1.0;
E_U_K    = 5.53;
MOL_MASS = 28.0;
A_VOIGT  = 0.149;
TEMP_K   = 1684.0;
B_SCA    = float( np.sqrt( 2.0 * KB_CGS * TEMP_K
                           / ( MOL_MASS * 1.67262192e-24 ) ) );
L_SLAB   = AU_CGS;
N_CELL   = ( 128, 2, 2 );

# -- Derived quantities ----------------------------------------------

def compute_sigma0():
    """Line-center cross section sigma_0 [cm^2]."""
    nu = FREQ_GHZ * 1e9;
    return ( G_U / G_L ) * A_UL * C_CGS**3 / \
           ( 8.0 * PI**1.5 * nu**3 * B_SCA );

def compute_n_l_frac():
    """LTE lower-level fraction n_l / n_species."""
    ratio = ( G_U / G_L ) * np.exp( -E_U_K / TEMP_K );
    return 1.0 / ( 1.0 + ratio );

def compute_n_species( tau0 ):
    """Total species density [cm^-3] for target mean-depth tau0."""
    sigma0 = compute_sigma0();
    n_l_frac = compute_n_l_frac();
    mfp_cgs = 2.0 * tau0 / ( SQRT_PI * L_SLAB );
    return mfp_cgs / ( sigma0 * n_l_frac );

def compute_mfp_cgs( tau0 ):
    """Line-center inverse MFP [cm^-1] for target mean-depth tau0."""
    return 2.0 * tau0 / ( SQRT_PI * L_SLAB );

# -- Neufeld (1990) analytic formula ---------------------------------

def neufeld_peak( a_tau0 ):
    """Neufeld (1990) peak: |x_p| = 0.881 * (a*tau0)^(1/3)."""
    return 0.881 * a_tau0 ** ( 1.0 / 3.0 );

def neufeld_J( x, a_tau0 ):
    """Neufeld (1990) emergent spectrum, eq. (2.24).

    J(x) = (sqrt(6/pi)) * x^2 / cosh(sqrt(pi^3/54) * |x|^3 / (a*tau0))
    """
    xa = np.abs( np.asarray( x, dtype = np.float64 ) );
    K = np.sqrt( PI**3 / 54.0 );
    A = np.sqrt( 6.0 / PI );
    denom = K * xa**3 / ( a_tau0 + 1e-35 );
    denom = np.clip( denom, 0, 600 );
    return A * xa**2 / np.cosh( denom );

# -- Hjerting function H(a,x) ----------------------------------------

def H_voigt( a, x ):
    """Hjerting function H(a,x) with H(0,0)=1, integral = sqrt(pi).

    Uses scipy.special.voigt_profile.  The Gaussian width sigma=1/sqrt(2)
    gives exp(-x^2) as the Doppler core; gamma=a is the Lorentz HWHM.
    """
    x = np.asarray( x, dtype = np.float64 );
    vp = voigt_profile( x, 1.0 / np.sqrt( 2.0 ), a );
    return vp * SQRT_PI;

# -- Run one tau0 point -----------------------------------------------

def run_one( tau0, n_emission_max = 200, keep_dir = False ):
    """Run LineRt for one tau0 point, return (out, params)."""
    n_species = compute_n_species( tau0 );
    a_tau0 = A_VOIGT * tau0;
    x_peak_pred = neufeld_peak( a_tau0 );
    v_chan_max = max( 3.0 * x_peak_pred, 10.0 ) * B_SCA;

    n_sc_est = max( 100, int( 2.857 * tau0 ) );
    n_photons = N_CELL[0] * N_CELL[1] * N_CELL[2] * n_emission_max;
    n_step = max( 5000000, n_photons * n_sc_est * 3 );

    ti = line_rt.TransitionInfo.user_defined(
        A_ul = A_UL, freq_GHz = FREQ_GHZ,
        g_u = G_U, g_l = G_L, E_u_K = E_U_K,
        mol_mass = MOL_MASS );

    rt = line_rt.LineRt(
        n_cell = N_CELL,
        x_min = ( -0.5, 0.0, 0.0 ),
        x_max = ( 0.5, 1.0, 1.0 ),
        unit_l0 = AU_CGS,
        unit_t0 = 1.0,
        transition_info = ti,
        n_species = n_species,
        temperature = TEMP_K,
        a_voigt = A_VOIGT,
        mfp_i_abs_0 = 0.0,
        ph_mode = 2,
        n_step = n_step,
        n_scat = n_step,
        n_cycles = 1,
        n_emission_max = n_emission_max,
        proper_scale = 1e-20,
        visualize = False,
        kratos_root = os.path.expanduser( '~/apps/kratos_line_rt' ),
        imaging = {
            'dir_cam': ( PI / 2.0, 0.0 ),
            'n_chan': 64,
            'v_chan': ( -v_chan_max, v_chan_max ),
        },
    );

    out = rt.run();

    params = {
        'tau0': tau0,
        'a_tau0': a_tau0,
        'x_peak_pred': x_peak_pred,
        'n_species': n_species,
        'sigma0': compute_sigma0(),
        'mfp_cgs': compute_mfp_cgs( tau0 ),
        'n_l_frac': compute_n_l_frac(),
        'v_chan_max': v_chan_max,
        'b_sca': B_SCA,
    };
    return out, params;

# -- Extract imaging spectrum ----------------------------------------

def extract_imaging_spectrum( out, params ):
    """Extract per-pixel-averaged imaging spectrum.

    Returns (v_chan_cgs, I_cgs) arrays.
    """
    img = out.get( 'image' );
    if img is None or 'cube_cgs' not in img:
        return None, None;
    cube = np.asarray( img[ 'cube_cgs' ], dtype = np.float64 );
    n_pix, n_chan = cube.shape;
    v_lo, v_hi = img.get( 'v_chan', ( -params[ 'v_chan_max' ],
                                      params[ 'v_chan_max' ] ) );
    v_chan = np.linspace( v_lo, v_hi, n_chan );
    I_avg = np.mean( cube, axis = 0 );
    return v_chan, I_avg;

# -- Extract escaped-photon spectrum ----------------------------------

def extract_escaped_spectrum( out, params ):
    """Extract escaped-photon spectrum (angle-averaged).

    Returns (x_dopp, J_norm) arrays where x_dopp = vel / b_sca.
    """
    spec = out.get( 'spectrum', {} );
    vel = np.asarray( spec.get( 'vel', [] ), dtype = np.float64 );
    w   = np.asarray( spec.get( 'n', [] ), dtype = np.float64 );
    if vel.size == 0:
        return None, None;
    x = vel / B_SCA;
    return x, w;

# -- Test 1: imaging spectrum vs Neufeld (shape) ----------------------

def check_spectrum_shape( v_chan, I_avg, params, verbose = True ):
    """Compare imaging spectrum shape to Neufeld J(x)."""
    x = v_chan / B_SCA;
    a_tau0 = params[ 'a_tau0' ];
    x_peak_pred = params[ 'x_peak_pred' ];

    valid = np.isfinite( I_avg ) & ( I_avg > 0 );
    if valid.sum() < 5:
        if verbose:
            print( "    SKIP: too few valid channels" );
        return { 'pass': False, 'reason': 'insufficient valid channels' };

    x_v = x[ valid ];
    I_v = I_avg[ valid ];

    peak_idx = np.argmax( I_v );
    x_peak_meas = abs( x_v[ peak_idx ] );

    I_norm = I_v / I_v[ peak_idx ];
    J_norm = neufeld_J( x_v, a_tau0 );
    J_norm = J_norm / ( J_norm.max() + 1e-35 );

    rms = np.sqrt( np.mean( ( I_norm - J_norm )**2 ) );

    peak_ratio = x_peak_meas / x_peak_pred if x_peak_pred > 0 else 0;
    peak_ok = abs( peak_ratio - 1.0 ) <= 0.15;
    shape_ok = rms <= 0.20;

    result = {
        'x_peak_meas': x_peak_meas,
        'x_peak_pred': x_peak_pred,
        'peak_ratio': peak_ratio,
        'rms': rms,
        'pass': peak_ok and shape_ok,
    };
    if verbose:
        print( f"    [Test 1] x_peak: meas={x_peak_meas:.3f}, "
               f"pred={x_peak_pred:.3f}, ratio={peak_ratio:.3f} "
               f"({'PASS' if peak_ok else 'FAIL'})" );
        print( f"            shape RMS={rms:.4f} "
               f"({'PASS' if shape_ok else 'FAIL'})" );
    return result;

# -- Test 2: source function flatness --------------------------------

def check_source_function_flatness( v_chan, I_avg, params, verbose = True ):
    """Extract S(x) = I(x)/(1-exp(-tau(x))) and check flatness."""
    x = v_chan / B_SCA;
    mfp = params[ 'mfp_cgs' ];
    L_half = L_SLAB / 2.0;
    a = A_VOIGT;

    H = H_voigt( a, x );
    tau_x = mfp * H * L_half;

    thick = tau_x > 3.0;
    if thick.sum() < 3:
        if verbose:
            print( "    SKIP: too few thick channels" );
        return { 'pass': False, 'reason': 'insufficient thick channels' };

    I_thick = I_avg[ thick ];
    tau_thick = tau_x[ thick ];

    escape_factor = 1.0 - np.exp( -tau_thick );
    escape_factor = np.maximum( escape_factor, 1e-10 );
    S = I_thick / escape_factor;

    S_pos = S[ S > 0 ];
    if S_pos.size < 3:
        if verbose:
            print( "    SKIP: too few positive S values" );
        return { 'pass': False, 'reason': 'insufficient positive S' };

    flatness = float( S_pos.max() / S_pos.min() );
    flat_ok = flatness <= 1.15;

    result = {
        'flatness': flatness,
        'n_thick': int( thick.sum() ),
        'pass': flat_ok,
    };
    if verbose:
        print( f"    [Test 2] S flatness: max/min={flatness:.3f} "
               f"({thick.sum()} thick channels) "
               f"({'PASS' if flat_ok else 'FAIL'})" );
    return result;

# -- Test 3: imaging vs escaped spectrum ------------------------------

def check_imaging_vs_escaped( v_chan, I_avg, x_esc, w_esc, params,
                              verbose = True ):
    """Compare imaging spectrum to escaped-photon spectrum."""
    if x_esc is None or x_esc.size == 0:
        if verbose:
            print( "    SKIP: no escaped photons" );
        return { 'pass': False, 'reason': 'no escaped photons' };

    x_img = v_chan / B_SCA;
    I_valid = np.isfinite( I_avg ) & ( I_avg > 0 );
    if I_valid.sum() < 5:
        if verbose:
            print( "    SKIP: too few valid imaging channels" );
        return { 'pass': False, 'reason': 'insufficient imaging channels' };

    x_abs = np.abs( x_esc );
    hi = min( x_abs.max(), abs( x_img ).max() );
    bins = np.linspace( 0, hi, 60 );
    bc = 0.5 * ( bins[ :-1 ] + bins[ 1: ] );
    h_esc, _ = np.histogram( x_abs, bins = bins, weights = w_esc,
                              density = True );
    h_esc_norm = h_esc / ( h_esc.max() + 1e-35 );

    I_abs = np.abs( x_img );
    h_img, _ = np.histogram( I_abs, bins = bins,
                              weights = I_avg[ ::-1 ] if x_img[0] < 0
                                         else I_avg,
                              density = True );
    h_img_norm = h_img / ( h_img.max() + 1e-35 );

    overlap = np.trapezoid( np.minimum( h_esc_norm, h_img_norm ), bc ) / \
              ( np.trapezoid( h_esc_norm, bc ) + 1e-35 );
    ok = overlap > 0.85;

    result = { 'overlap': overlap, 'pass': ok };
    if verbose:
        print( f"    [Test 3] overlap={overlap:.3f} "
               f"({'PASS' if ok else 'FAIL'})" );
    return result;

# -- Test 5: absolute normalization ----------------------------------

def check_normalization( v_chan, I_avg, params, verbose = True ):
    """Check I(0) ~ S_line (source function, thermal seed).

    For a uniform slab with internal emission, the line-center
    intensity should approach the source function S = j/alpha in the
    thick limit.  The thermal seed is S_th = emiss/mfp_sca_0 = S_line.

    If the thermal seed is double-counted (added to st_cam AND captured
    by the scattering accumulation), I(0) ~ 2*S_th.
    """
    sigma0 = params[ 'sigma0' ];
    n_l_frac = params[ 'n_l_frac' ];
    n_species = params[ 'n_species' ];

    n_u = n_species * ( 1.0 - n_l_frac );
    n_l = n_species * n_l_frac;
    j_cgs = n_u * A_UL / ( 4.0 * PI );
    alpha_cgs = sigma0 * n_l;
    S_line_cgs = j_cgs / alpha_cgs;

    x = v_chan / B_SCA;
    center = np.argmin( np.abs( x ) );
    I_center = I_avg[ center ];

    ratio = I_center / S_line_cgs if S_line_cgs > 0 else 0;

    result = {
        'S_line_cgs': S_line_cgs,
        'I_center_cgs': I_center,
        'ratio': ratio,
    };
    note = '';
    if ratio > 1.8:
        note = ' (possible double-count: ~2x)';
    elif ratio > 0.8:
        note = ' (consistent with single S_th)';
    else:
        note = ' (below S_th — MC noise or thin)';
    if verbose:
        print( f"    [Test 5] I(0)/S_line={ratio:.3f}{note}" );
        print( f"            S_line={S_line_cgs:.3e}, "
               f"I(0)={I_center:.3e}" );
    return result;

# -- Main ------------------------------------------------------------

# Golden targets: Neufeld x_peak = 0.881*(a*tau0)^(1/3).
# med|x| targets from test_scaling_wide.py (escaped spectrum, ph_mode=2).
# These are PHYSICS TARGETS, not measured regressions.
# The test FAILS until the st_cam accumulation bug is fixed
# (prof_cam(dv_cam) should be prof(dv_pp) for CRD source function).
GOLDEN = {
    200:   { 'x_peak': 2.73, 'med_x': 1.80 },
    500:   { 'x_peak': 3.71, 'med_x': 2.30 },
    2000:  { 'x_peak': 5.89, 'med_x': 4.40 },
    8000:  { 'x_peak': 9.33, 'med_x': 6.90 },
    32000: { 'x_peak': 14.82, 'med_x': 11.50 },
};

GOLDEN_TOL = 0.15;

def main():
    p = argparse.ArgumentParser(
        description = 'Optically thick scattering imaging test vs Neufeld' );
    p.add_argument( '--tau0-list', type = float, nargs = '+',
                    default = [ 200, 500, 2000, 8000, 32000 ],
                    help = 'Neufeld mean-depth tau0 values' );
    p.add_argument( '--measure', action = 'store_true',
                    help = 'Print golden values and exit' );
    p.add_argument( '--plots', action = 'store_true',
                    help = 'Save PNG plots' );
    p.add_argument( '--n-emission-max', type = int, default = 200,
                    help = 'Emission photons per cell' );
    args = p.parse_args();

    print( f"Transition: A_ul={A_UL:.2e}, freq={FREQ_GHZ} GHz, "
           f"a={A_VOIGT}, b={B_SCA:.1e} cm/s" );
    print( f"sigma_0 = {compute_sigma0():.4e} cm^2" );
    print( f"n_l_frac = {compute_n_l_frac():.4f}" );
    print( f"Temperature = {TEMP_K} K, L_slab = {L_SLAB:.4e} cm" );
    print();

    all_results = {};

    for tau0 in args.tau0_list:
        a_tau0 = A_VOIGT * tau0;
        x_peak_pred = neufeld_peak( a_tau0 );
        n_species = compute_n_species( tau0 );
        print( f"=== tau0={tau0:.0f}, a*tau0={a_tau0:.0f}, "
               f"x_peak_pred={x_peak_pred:.3f}, "
               f"n_species={n_species:.3e} ===" );

        out, params = run_one( tau0,
                                n_emission_max = args.n_emission_max );

        v_chan, I_avg = extract_imaging_spectrum( out, params );
        if v_chan is None:
            print( "    FAILED: no imaging cube" );
            all_results[ tau0 ] = { 'pass': False };
            continue;

        assert v_chan is not None and I_avg is not None;
        x_esc, w_esc = extract_escaped_spectrum( out, params );

        r1 = check_spectrum_shape( v_chan, I_avg, params );
        r2 = check_source_function_flatness( v_chan, I_avg, params );
        r3 = check_imaging_vs_escaped( v_chan, I_avg, x_esc, w_esc,
                                      params );
        r5 = check_normalization( v_chan, I_avg, params );

        med_x_img = float( np.median( np.abs(
            v_chan[ I_avg > 0 ] / B_SCA ) ) ) if \
            ( I_avg > 0 ).any() else 0;

        all_results[ tau0 ] = {
            'x_peak': r1.get( 'x_peak_meas', 0 ),
            'med_x': med_x_img,
            'ratio_norm': r5.get( 'ratio', 0 ),
            'tests': {
                'shape': r1, 'flatness': r2,
                'consistency': r3, 'normalization': r5,
            },
        };
        print();

    # -- Scaling check --
    print( f"{'tau0':>7} {'a*tau0':>7} {'x_peak':>8} {'pred':>8} "
           f"{'ratio':>6} {'med|x|':>8} {'I/S':>6}  status" );
    print( '-' * 70 );
    n_fail = 0;
    for tau0 in args.tau0_list:
        a_tau0 = A_VOIGT * tau0;
        pred = neufeld_peak( a_tau0 );
        r = all_results.get( tau0, {} );
        xp = r.get( 'x_peak', 0 );
        mx = r.get( 'med_x', 0 );
        rn = r.get( 'ratio_norm', 0 );
        pr = xp / pred if pred > 0 else 0;
        ok = abs( pr - 1.0 ) <= 0.15;
        n_fail += 0 if ok else 1;
        print( f"{tau0:7.0f} {a_tau0:7.0f} {xp:8.3f} {pred:8.3f} "
               f"{pr:6.3f} {mx:8.3f} {rn:6.2f}  "
               f"{'PASS' if ok else 'FAIL'}" );
    print( '-' * 70 );

    # -- Golden regression --
    if not args.measure:
        print( "\nGolden regression:" );
        for tau0 in args.tau0_list:
            r = all_results.get( tau0, {} );
            g = GOLDEN.get( tau0 );
            if g is None or 'x_peak' not in r:
                continue;
            xp = r[ 'x_peak' ];
            mx = r[ 'med_x' ];
            ok_x = abs( xp / g[ 'x_peak' ] - 1.0 ) <= GOLDEN_TOL;
            ok_m = abs( mx / g[ 'med_x' ] - 1.0 ) <= GOLDEN_TOL;
            print( f"  tau0={tau0:.0f}: x_peak {xp:.3f} vs "
                   f"{g['x_peak']:.3f} ({'OK' if ok_x else 'DRIFT'}), "
                   f"med|x| {mx:.3f} vs {g['med_x']:.3f} "
                   f"({'OK' if ok_m else 'DRIFT'})" );

    if args.measure:
        print( "\nGOLDEN = {" );
        for tau0 in args.tau0_list:
            r = all_results.get( tau0, {} );
            xp = r.get( 'x_peak', float( 'nan' ) );
            mx = r.get( 'med_x', float( 'nan' ) );
            print( f"    {tau0:.0f}: {{ 'x_peak': {xp:.4f}, "
                   f"'med_x': {mx:.4f} }}," );
        print( "}" );

    if args.plots:
        make_plots( all_results, args );

    return 0 if n_fail == 0 else 1;

# -- Plotting --------------------------------------------------------

def make_plots( results, args ):
    import matplotlib;
    matplotlib.use( 'Agg' );
    import matplotlib.pyplot as plt;

    out_dir = os.path.expanduser( '~/scratch/line_rt' );
    os.makedirs( out_dir, exist_ok = True );

    # Scaling plot
    tau0s = [ t for t in args.tau0_list if t in results ];
    ats = [ A_VOIGT * t for t in tau0s ];
    xps = [ results[ t ][ 'x_peak' ] for t in tau0s ];
    at_fine = np.logspace(
        np.log10( max( min( ats ), 1 ) ),
        np.log10( max( ats ) * 1.5 ), 200 );
    fig, ax = plt.subplots( figsize = ( 8, 6 ) );
    ax.loglog( at_fine, neufeld_peak( at_fine ), 'k--', lw = 2,
               label = r'$0.881(a\tau_0)^{1/3}$' );
    ax.loglog( ats, xps, 'bo-', ms = 8, lw = 1.5,
               label = 'Imaging $x_{peak}$' );
    ax.set_xlabel( r'$a\tau_0$', fontsize = 14 );
    ax.set_ylabel( r'$|x|_{peak}$', fontsize = 14 );
    ax.set_title( 'Imaging spectrum peak scaling vs Neufeld', fontsize = 14 );
    ax.legend( fontsize = 12 );
    ax.grid( True, which = 'both', alpha = 0.3 );
    p1 = os.path.join( out_dir, 'imaging_neufeld_scaling.png' );
    fig.savefig( p1, dpi = 150, bbox_inches = 'tight' );
    print( f"Saved: {p1}" );
    plt.close( fig );

    # Spectrum grid
    n = len( tau0s );
    nc = min( 3, n );
    nr = ( n + nc - 1 ) // nc;
    fig, axes = plt.subplots( nr, nc,
                              figsize = ( 5.5 * nc, 4.5 * nr ),
                              squeeze = False );
    for idx, tau0 in enumerate( tau0s ):
        ax = axes[ idx // nc ][ idx % nc ];
        a_tau0 = A_VOIGT * tau0;
        out, params = run_one( tau0,
                                n_emission_max = args.n_emission_max );
        v_chan, I_avg = extract_imaging_spectrum( out, params );
        if v_chan is None:
            continue;
        assert v_chan is not None and I_avg is not None;
        x = v_chan / B_SCA;
        xlim = 3.5 * neufeld_peak( a_tau0 );
        mask = np.abs( x ) <= xlim;
        x_p = x[ mask ];
        I_p = I_avg[ mask ];
        if I_p.max() > 0:
            I_p = I_p / I_p.max();
        ax.plot( x_p, I_p, 'b-', lw = 1.5, label = 'Imaging' );
        J = neufeld_J( x_p, a_tau0 );
        if J.max() > 0:
            J = J / J.max();
        ax.plot( x_p, J, 'k--', lw = 2, label = 'Neufeld' );
        ax.set_xlabel( r'$x$ (Doppler)', fontsize = 11 );
        ax.set_ylabel( r'$I(x)$ (normalized)', fontsize = 11 );
        ax.set_title( r'$\tau_0=%d$, $a\tau_0=%d$' % ( tau0, a_tau0 ),
                       fontsize = 11 );
        ax.legend( fontsize = 9 );
        ax.grid( True, alpha = 0.3 );
    for idx in range( n, nr * nc ):
        axes[ idx // nc ][ idx % nc ].set_visible( False );
    p2 = os.path.join( out_dir, 'imaging_neufeld_spectra.png' );
    fig.savefig( p2, dpi = 150, bbox_inches = 'tight' );
    print( f"Saved: {p2}" );
    plt.close( fig );

if __name__ == '__main__':
    sys.exit( main() );
