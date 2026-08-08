#!/usr/bin/env python3
"""
Neufeld (1990) analytic solution vs reference MCRT.

Compares ph_mode=1 (R_IIA, USampler) against the
analytic emergent spectrum from Neufeld 1990, ApJ 350, 216.

J(x) = (√6/√π) · x² / cosh(√(π³/54) · |x|³ / (a τ₀))

Usage:
  python docs/reference_mcrt/plot_neufeld.py [output_prefix]
"""

import importlib.util, os, sys, time;

from numpy import array, zeros, linspace, logspace, log10, \
                 abs, clip, cosh, sqrt, pi, histogram, diff, \
                 argmax, polyfit, trapz, median, mean, nan, \
                 int32, float64, random;

#  Load the pipeline without installation (works with symlinks too).
#  If installed (``pip install -e .``), delete the 3 lines below and
#  add the repo root to sys.path or use:  from line_rt import ...
_PIPELINE = os.path.join( os.path.dirname( os.path.dirname( \
    os.path.dirname( os.path.realpath( __file__ ) ) ) ), 'line_rt.py' );
_spec = importlib.util.spec_from_file_location( 'line_rt', _PIPELINE );
line_rt = importlib.util.module_from_spec( _spec );
_spec.loader.exec_module( line_rt );

#  The reference MCRT lives in this directory (sibling module).
sys.path.insert( 0, os.path.dirname( os.path.realpath( __file__ ) ) );
from mcrt import run_mcrt;

A_VOIGT = 0.01;
B_SCA   = 1.0e5;

_NEUFELD_K = sqrt( pi ** 3 / 54.0 );
_NEUFELD_A = sqrt( 6.0 / pi );

############################################################
#  Analytic Neufeld spectrum

def neufeld_J( x, a_tau ):
    xa = abs( x );
    denom = _NEUFELD_K * xa * xa * xa / ( a_tau + 1e-35 );
    if denom.max( ) > 600:
        denom = clip( denom, -600, 600 );
    return _NEUFELD_A * xa * xa / cosh( denom );

############################################################
#  Single-tau MCRT run

def run_one( tau, n_ph, a, b_sca, ph_mode, seed ):
    dx = 1.0e13;
    mesh = {
        'n_cell' : array( [ 1, 2, 2 ], dtype = int32 ),
        'x_min'  : array( [ -dx / 2.0, 0.0, 0.0 ], dtype = float64 ),
        'dx'     : array( [ dx, dx * 0.1, dx * 0.1 ], dtype = float64 ),
    };
    mfp_s = 2 * tau / dx;

    rng = random.default_rng( seed );
    ph = zeros( ( n_ph, 9 ), dtype = float64 );
    ph[ :, 0 ] = 0.0;
    ph[ :, 1 ] = rng.uniform( 0, dx * 0.1, n_ph );
    ph[ :, 2 ] = rng.uniform( 0, dx * 0.1, n_ph );
    n_half = n_ph // 2;
    ph[ : n_half, 3 ] = 1.0;
    ph[ n_half :, 3 ] = -1.0;
    ph[ :, 6 ] = 1.0 / n_ph;

    result = run_mcrt(
        mesh = mesh, photons = ph, b_sca = b_sca,
        mfp_i_sca_0 = mfp_s, mfp_i_abs_0 = 0.0,
        vel = None, ph_mode = ph_mode, a_voigt = a,
        seed = seed, parallel = True,
    );

    esc = result[ 'escaped' ];
    esc_mask = result[ 'term_reason' ] == 1;
    n_scat_all = result[ 'n_scat' ];
    n_scat = n_scat_all[ esc_mask ];

    if len( esc ) == 0:
        return None;

    x = esc[ :, 0 ] / b_sca;
    weights = esc[ :, 1 ];
    n_escaped = len( esc );
    med_n_scat = median( n_scat ) if len( n_scat ) > 0 else 0;
    mean_n_scat = float( mean( n_scat ) ) if len( n_scat ) > 0 else 0.0;
    harrington_N = 1.612 * tau;
    med_x = median( abs( x ) );
    x_peak_emp = _find_peak( x, weights );

    return { 'x' : x, 'weights' : weights, 'n_escaped' : n_escaped,
             'med_n_scat' : med_n_scat, 'mean_n_scat' : mean_n_scat,
             'harrington_N' : harrington_N,
             'med_x' : med_x, 'x_peak' : x_peak_emp,
             'tau' : tau, 'n_ph' : n_ph, 'ph_mode' : ph_mode, \
             'a' : a, 'f_esc' : n_escaped / n_ph };

############################################################
#  Empirical peak finder

def _find_peak( x, w ):
    if len( x ) < 50:
        return nan;
    xa = abs( x );
    hi = xa.max( );
    bins = linspace( 0, hi, 120 );
    bc = ( bins[ : -1 ] + bins[ 1 : ] ) / 2.0;
    hist, _ = histogram( xa, bins = bins, weights = w );
    J = hist / diff( bins );
    top = argmax( J );
    lo, hi2 = max( 0, top - 2 ), min( len( bc ), top + 3 );
    if hi2 - lo >= 3:
        coeffs = polyfit( bc[ lo : hi2 ], J[ lo : hi2 ], 2 );
        return -coeffs[ 1 ] / ( 2.0 * coeffs[ 0 ] );
    return bc[ top ];

############################################################
#  Plotting

def plot_results( results, output_prefix = 'neufeld' ):
    import matplotlib;
    matplotlib.use( 'Agg' );
    import matplotlib.pyplot as plt;

    font = { 'family' : 'sans-serif', 'size' : 10 };
    fig, axes = plt.subplots( 2, 1, figsize = ( 10, 12 ) );

    ############################################################
    #  Panel 1: emergent spectrum J(x) vs x

    ax = axes[ 0 ];
    x_plot = linspace( 0.01, 40, 400 );
    colors = plt.cm.viridis( linspace( 0.0, 0.95, len( results ) ) );

    for ( res, ci ) in zip( results, colors ):
        tau = res[ 'tau' ];
        at  = A_VOIGT * tau;
        x   = res[ 'x' ];
        w   = res[ 'weights' ];

        xa  = abs( x );
        hi  = min( xa.max( ), 50.0 );
        bins = linspace( 0, hi, 60 );
        bc = ( bins[ : -1 ] + bins[ 1 : ] ) / 2.0;
        hist, _ = histogram( xa, bins = bins, weights = w );
        J_emp = hist / diff( bins );
        norm = float( trapz( J_emp, bc ) ) if len( bc ) > 1 else 1.0;
        if norm > 0:
            J_emp /= norm;

        J_an = neufeld_J( x_plot, at );
        norm_an = float( trapz( J_an, x_plot ) );
        if norm_an > 0:
            J_an /= norm_an;

        ax.step( bc, J_emp, where = 'mid', color = ci, lw = 1.2, \
                 label = 'τ=%.0e (MC)' % tau );
        ax.plot( x_plot, J_an, '--', color = ci, lw = 1.0, alpha = 0.7 );

    ax.set_xscale( 'linear' );
    ax.set_yscale( 'linear' );
    ax.set_xlabel( r'$|x|$ (frequency, Doppler units)' );
    ax.set_ylabel( r'$J(|x|)$ (normalized)' );
    ax.set_title( r'Neufeld (1990) emergent spectrum, a=0.01, ' \
                  r'R$_\mathrm{II}$A (ph_mode=1)' );
    ax.legend( fontsize = 7, loc = 'upper right' );
    ax.set_xlim( 0, 40 );
    ax.grid( True, alpha = 0.3 );

    ############################################################
    #  Panel 2: x_peak vs a τ₀

    ax = axes[ 1 ];
    ataus   = array( [ A_VOIGT * r[ 'tau' ] for r in results ] );
    x_peaks = array( [ r[ 'x_peak' ] for r in results ] );

    at_plot = logspace( log10( max( ataus.min( ), 1.0 ) ), \
                        log10( ataus.max( ) ) + 0.3, 200 );
    x_pred = 1.07 * at_plot ** ( 1.0 / 3.0 );
    ax.loglog( at_plot, x_pred, 'k-', lw = 1.5, alpha = 0.6, \
               label = r'$x_\mathrm{peak} = 1.07\,(a\tau_0)^{1/3}$' );
    ax.fill_between( at_plot, x_pred * 0.85, x_pred * 1.15, color = 'k', \
                     alpha = 0.08 );

    ax.loglog( ataus, x_peaks, 'o-', color = 'C0', ms = 8, \
               label = 'x_peak (MC)' );

    # Mark aτ₀=100 validity threshold
    ax.axvline( 100, color = 'grey', ls = ':', lw = 1.0, alpha = 0.5 );
    ax.text( 100, ax.get_ylim( )[ 1 ] * 0.9, r'$a\tau_0=100$', \
             fontsize = 7, color = 'grey', ha = 'left', va = 'top' );

    ax.set_xlabel( r'$a \tau_0$' );
    ax.set_ylabel( r'$x_\mathrm{peak}$ (Doppler units)' );
    ax.set_title( 'Frequency peak scaling (valid for aτ₀ ≳ 100)' );
    ax.legend( fontsize = 8, loc = 'lower right' );
    ax.grid( True, alpha = 0.3 );
    ax.set_ylim( 1, 100 );

    plt.tight_layout( );
    out_path = '%s_comparison.png' % output_prefix;
    fig.savefig( out_path, dpi = 150, bbox_inches = 'tight' );
    plt.close( fig );
    print( '\n  Saved figure: %s' % out_path );
    return out_path;

############################################################
#  Main

def main( ):
    output_prefix = sys.argv[ 1 ] if len( sys.argv ) > 1 else 'neufeld';

    configs = [
        ( 1e3,  5000 ),
        ( 3e3,  5000 ),
        ( 1e4,  5000 ),
        ( 3e4,  5000 ),
        ( 1e5,  10000 ),
        ( 3e5,  10000 ),
        ( 1e6,  20000 ),
    ];

    results = [];
    print( 'Neufeld (1990) slab, R_IIA (ph_mode=1, USampler), a=%.2f' \
           % A_VOIGT );
    print( '%10s  %6s  %6s  %8s  %8s  %8s  %8s  %7s' \
           % ( 'τ', 'n_ph', 'n_esc', '<N_sc>', 'Harr', 'x_peak', \
               'x_pred', 'time' ) );

    for tau, n_ph in configs:
        t0 = time.time( );
        res = run_one( tau, n_ph, A_VOIGT, B_SCA, 1, seed = 42 + int( tau ) );
        dt = time.time( ) - t0;

        if res is None:
            print( '  %10.0f  NO ESCAPERS' % tau );
            continue;

        at = A_VOIGT * tau;
        x_pred = 1.07 * at ** ( 1.0 / 3.0 );
        print( '  %10.0f  %6d  %6d  %8.0f  %8.0f  %8.3f  %8.3f  %6.1fs' \
               % ( tau, n_ph, res[ 'n_escaped' ], res[ 'mean_n_scat' ], \
                   res[ 'harrington_N' ], res[ 'x_peak' ], x_pred, dt ) );
        results.append( res );

    if not results:
        print( 'No results!' );
        return;

    # ── aτ₀ scaling invariance cross-check ──
    # Same (a*tau0)^(1/3)=10 but different (a, tau0):
    # a=0.01/tau=1e3 vs a=0.05/tau=200
    print( '\n  --- aτ₀ scaling invariance check ---' );
    at_target = 10.0;
    scaling_configs = [
        ( A_VOIGT, int( at_target / A_VOIGT ), 42 ),    # a=0.01, τ=1000
        ( 0.05, int( at_target / 0.05 ), 1042 ),        # a=0.05, τ=200
    ];
    scaling_results = [];
    for a_s, tau_s, seed_s in scaling_configs:
        t0 = time.time( );
        res = run_one( tau_s, 5000, a_s, B_SCA, 1, seed = seed_s );
        dt = time.time( ) - t0;
        if res:
            at_s = a_s * tau_s;
            x_pred_s = 1.07 * at_s ** ( 1.0 / 3.0 );
            scaling_results.append( res );
            print( '  a=%.3f τ=%d: n_esc=%d <N_sc>=%.0f (Harr=%.0f) ' \
                   'x_peak=%.3f x_pred=%.3f ratio=%.3f  %.1fs' \
                   % ( a_s, tau_s, res[ 'n_escaped' ], \
                       res[ 'mean_n_scat' ], res[ 'harrington_N' ], \
                       res[ 'x_peak' ], x_pred_s, \
                       res[ 'x_peak' ] / x_pred_s, dt ) );
        else:
            print( '  a=%.3f τ=%d: NO ESCAPERS' % ( a_s, tau_s ) );

    print( '\n  --- R_IIA (ph_mode=1) summary ' \
           '(Neufeld valid for aτ₀ ≳ 100) ---' );
    print( '  %10s  %10s  %13s  %10s' \
           % ( 'τ', 'a τ₀', 'x_peak/x_pred', 'N_sc/Harr' ) );
    for res in results:
        at = A_VOIGT * res[ 'tau' ];
        x_pred = 1.07 * at ** ( 1.0 / 3.0 );
        valid = '*' if at >= 100 else ' ';
        nsc_rat = res[ 'mean_n_scat' ] / res[ 'harrington_N' ] \
                  if res[ 'harrington_N' ] > 0 else 0;
        print( '  %10.0f  %10.0f  %13.3f  %10.3f  %s' \
               % ( res[ 'tau' ], at, res[ 'x_peak' ] / x_pred, \
                   nsc_rat, valid ) );

    ataus   = array( [ A_VOIGT * r[ 'tau' ] for r in results ] );
    x_peaks = array( [ r[ 'x_peak' ] for r in results ] );
    slope, icept = polyfit( log10( ataus ), log10( x_peaks ), 1 );
    print( '  log(x_peak) = %.3f·log(aτ₀) + %.3f' % ( slope, icept ) );
    print( '  x_peak coefficient = %.2f  (expected 1.07, slope 0.333)' \
           % 10 ** icept );

    plot_results( results + scaling_results, output_prefix );


if __name__ == '__main__':
    main( );
