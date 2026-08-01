#!/usr/bin/env python3
"""
Scaling test: |x_peak| vs a*tau0 for Kratos vs Python reference vs Neufeld.

Runs Kratos at multiple optical depths and Voigt a values, then compares
the escape-frequency peak position against:
  (a) Python reference MCRT (mcrt_slab, ph_mode=1)
  (b) Neufeld (1990) analytic: x_peak = 1.07 * (a*tau0)^(1/3)

Outputs PNG plots in ~/scratch/line_rt/ .

Usage:
  python tests/test_scaling.py
  python tests/test_scaling.py --tau0-list 1000 2000 5000 10000 --a-list 0.01
  python tests/test_scaling.py --n 2000  # fewer photons for speed
"""
import argparse, os, subprocess, sys;
from pathlib import Path;
from numpy import array, zeros, full, linspace, logspace, log10, \
                 abs, sqrt, pi, argsort, histogram, argmax, median, \
                 nan, float32, float64, int32, random;

REPO = Path( __file__ ).resolve( ).parents[ 1 ];
sys.path.insert( 0, str( REPO ) );

from pipeline.kratos_io import write_field_data, \
    write_photon_data, read_output;
from docs.reference_mcrt.mcrt import mcrt_slab;

UNIT_L0 = 1.49597870691e13;
UNIT_T0 = 1.0;
KRATOS_BIN = os.path.expanduser( \
    '~/apps/kratos_line_rt/bin/kratos' );
WORKDIR = os.path.expanduser( '~/scratch/line_rt' );

############################################################
#  Analytic formula

def neufeld_peak( a_tau0 ):
    return 1.07 * a_tau0 ** ( 1.0 / 3.0 );


def estimate_n_scatt( tau0, a_voigt ):
    if a_voigt > 1e-6:
        return max( 100, int( 2.857 * tau0 ) );
    else:
        return max( 100, int( tau0 * tau0 ) );


def generate_kratos_inputs( tau0, a_voigt, n_radiation, out_dir, \
                            n_cell = 128, L_slab = 1.49598e14, \
                            b_sca = 1.0e5, seed = 42 ):
    L_slab_code = L_slab / UNIT_L0;
    nx = n_cell;
    dx_code = L_slab_code / nx;
    half_code = L_slab_code / 2;

    mfp_i_sca_0_code = tau0 / L_slab * UNIT_L0;
    b_sca_code = b_sca * UNIT_T0 / UNIT_L0;

    n_tot = nx * 2 * 2;
    shape3d = ( 2, 2, nx );  # (nz, ny, nx)
    fields = {
        'mfp_i_sca_0_' : full( shape3d, float32( mfp_i_sca_0_code ) ),
        'mfp_i_abs_0_' : zeros( shape3d, dtype = float32 ),
        'b_sca_'       : full( shape3d, float32( b_sca_code ) ),
        'vel_0_'       : zeros( shape3d, dtype = float32 ),
        'vel_1_'       : zeros( shape3d, dtype = float32 ),
        'vel_2_'       : zeros( shape3d, dtype = float32 ),
    };
    mesh = {
        'n_cell' : array( [ nx, 2, 2 ], dtype = int32 ),
        'x_min'  : array( [ -half_code, 0.0, 0.0 ], dtype = float32 ),
        'dx'     : array( [ dx_code, dx_code * 0.1, dx_code * 0.1 ], \
                          dtype = float32 ),
    };

    tag = 'tau%.0f_a%s' % ( tau0, a_voigt );
    field_file = os.path.join( out_dir, 'fields_%s.bin' % tag );
    write_field_data( field_file, fields, mesh );

    n_sc_est = estimate_n_scatt( tau0, a_voigt );
    n_step = max( n_radiation * n_sc_est * 3, 5000000 );

    par_content = """# Kratos scaling test - %s

[unit]
length  = %.6e
time    = %s
density = 1.0

[mesh]
x_min = %.6f 0 0
x_max = %.6f 1 1
n_cell_global = %d 2 2

[cycle]
prefix_output = test
n_cycle_lim   = 0
t_lim         = 1200.0
t_output_next = 1e32
dt_output     = 1e32
final_output  = 1

[particle]
n_step = %d
n_scat = %d
output = 1
n_radiation = %d

[line_rt]
field_file  = %s
photon_file = photons_%s.bin
ph_mode     = 1
b_sca       = %.10e
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = %s

[boundary]
kinds = fre fre per per per per
""" % ( tag, UNIT_L0, UNIT_T0, -half_code, half_code, nx,
        n_step, n_step, n_radiation, \
        os.path.basename( field_file ), tag, b_sca_code, a_voigt );
    par_path = os.path.join( out_dir, 'neufeld_%s.par' % tag );
    with open( par_path, 'w' ) as fp:
        fp.write( par_content );

    photon_file = os.path.join( out_dir, 'photons_%s.bin' % tag );
    rng = random.default_rng( seed );
    ph = zeros( ( n_radiation, 9 ), dtype = float64 );
    ph[ :, 0 ] = 0.0;
    ph[ :, 1 ] = rng.uniform( 0, dx_code * 0.1, n_radiation );
    ph[ :, 2 ] = rng.uniform( 0, dx_code * 0.1, n_radiation );
    n_half = n_radiation // 2;
    ph[ : n_half, 3 ] = 1.0;
    ph[ n_half:, 3 ] = -1.0;
    ph[ :, 6 ] = 1.0 / n_radiation;
    ph[ :, 7 ] = 0.0;
    ph[ :, 8 ] = 0.0;
    write_photon_data( photon_file, ph, n_col = 9 );

    return par_path, tag;


def run_kratos_one( tau0, a_voigt, n_radiation, out_dir ):
    print( '  Kratos: tau0=%s, a=%s, n=%d' \
           % ( tau0, a_voigt, n_radiation ) );
    par_path, tag = generate_kratos_inputs( \
        tau0, a_voigt, n_radiation, out_dir );

    result = subprocess.run(
        [ KRATOS_BIN, os.path.basename( par_path ) ],
        cwd = out_dir, capture_output = True, text = True, \
        timeout = 900,
    );
    if result.returncode != 0:
        print( '    FAILED: %s' % result.stderr[ -300 : ] );
        return None;

    out_files = sorted( Path( out_dir ).glob( 'test_*.bin' ) );
    if not out_files:
        return None;
    out = read_output( str( out_files[ -1 ] ) );
    if 'photons' not in out or \
            out[ 'photons' ].get( 'vel', array( [ ] ) ).size == 0:
        return None;

    b_sca_code = 1.0e5 * UNIT_T0 / UNIT_L0;
    vel = out[ 'photons' ][ 'vel' ].astype( float64 );
    x_freq = vel / b_sca_code;

    abs_x = abs( x_freq );
    bins = linspace( 0, max( 15, abs_x.max( ) * 1.1 ), 100 );
    h, bc = histogram( abs_x, bins = bins, density = True );
    x_peak = bc[ argmax( h ) ];
    print( '    n_esc=%d, x_peak=%.3f, med|x|=%.3f' \
           % ( len( x_freq ), x_peak, median( abs_x ) ) );
    return {
        'x_freq' : x_freq, 'x_peak' : x_peak,
        'med_x'  : median( abs_x ),
        'n_esc'  : len( x_freq ),
    };


def run_python_one( tau0, a_voigt, n_radiation ):
    print( '  Python: tau0=%s, a=%s, n=%d' \
           % ( tau0, a_voigt, n_radiation ) );
    result = mcrt_slab(
        n_cell = 128, L_slab = 1.49598e14,
        tau0 = tau0, tau_abs = 0.0, b_sca = 1.0e5,
        n_photons = n_radiation, ph_mode = 1,
        a_voigt = a_voigt, seed = 42, parallel = True, \
        source = 'midplane',
    );
    esc = result[ 'escaped' ];
    x_freq = esc[ :, 0 ].astype( float64 ) / 1.0e5;
    abs_x = abs( x_freq );
    bins = linspace( 0, max( 15, abs_x.max( ) * 1.1 ), 100 );
    h, bc = histogram( abs_x, bins = bins, density = True );
    x_peak = bc[ argmax( h ) ];
    print( '    n_esc=%d, x_peak=%.3f, med|x|=%.3f' \
           % ( len( x_freq ), x_peak, median( abs_x ) ) );
    return {
        'x_freq' : x_freq, 'x_peak' : x_peak,
        'med_x'  : median( abs_x ),
        'n_esc'  : len( x_freq ),
    };

############################################################
#  Main

def main( ):
    p = argparse.ArgumentParser( \
        description = 'Scaling test: |x_peak| vs a*tau0' );
    p.add_argument( '--tau0-list', type = float, nargs = '+', \
                    default = [ 1000, 2000, 5000, 10000, 20000 ] );
    p.add_argument( '--a-list', type = float, nargs = '+', \
                    default = [ 0.01 ] );
    p.add_argument( '--n', dest = 'n_radiation', type = int, \
                    default = 5000 );
    p.add_argument( '--no-kratos', action = 'store_true' );
    p.add_argument( '--no-python', action = 'store_true' );
    args = p.parse_args( );

    os.makedirs( WORKDIR, exist_ok = True );

    results = [ ];
    for a_voigt in args.a_list:
        for tau0 in args.tau0_list:
            a_tau0 = a_voigt * tau0;
            pred = neufeld_peak( a_tau0 );
            print( '\n=== a*tau0=%.0f (tau0=%s, a=%s), Neufeld peak=%.3f ===' \
                   % ( a_tau0, tau0, a_voigt, pred ) );

            entry = { 'tau0' : tau0, 'a' : a_voigt, \
                      'a_tau0' : a_tau0, 'neufeld_peak' : pred };

            if not args.no_kratos:
                # Clean old test_*.bin
                for f in Path( WORKDIR ).glob( 'test_0*.bin' ):
                    f.unlink( );
                kres = run_kratos_one( tau0, a_voigt, \
                                       args.n_radiation, WORKDIR );
                if kres:
                    entry[ 'kratos_peak' ] = kres[ 'x_peak' ];
                    entry[ 'kratos_med' ] = kres[ 'med_x' ];
                    entry[ 'kratos_x' ] = kres[ 'x_freq' ];

            if not args.no_python:
                pres = run_python_one( tau0, a_voigt, \
                                       args.n_radiation );
                if pres:
                    entry[ 'python_peak' ] = pres[ 'x_peak' ];
                    entry[ 'python_med' ] = pres[ 'med_x' ];
                    entry[ 'python_x' ] = pres[ 'x_freq' ];

            results.append( entry );

    ############################################################
    #  Plot 1: |x_peak| vs a*tau0

    import matplotlib;
    matplotlib.use( 'Agg' );
    import matplotlib.pyplot as plt;

    fig, ax = plt.subplots( 1, 1, figsize = ( 8, 6 ) );
    a_tau0_arr = array( [ r[ 'a_tau0' ] for r in results ] );
    sort_idx = argsort( a_tau0_arr );

    # Neufeld analytic
    at_fine = logspace( log10( max( a_tau0_arr.min( ), 1 ) ), \
                        log10( a_tau0_arr.max( ) * 1.5 ), 100 );
    ax.plot( at_fine, neufeld_peak( at_fine ), 'k--', \
             linewidth = 2, \
             label = 'Neufeld: $1.07(a\\tau_0)^{1/3}$' );

    if 'kratos_peak' in results[ 0 ]:
        kp = array( [ r.get( 'kratos_peak', nan ) \
                      for r in results ] )[ sort_idx ];
        ax.plot( a_tau0_arr[ sort_idx ], kp, 'rs-', markersize = 8, \
                 linewidth = 1.5, label = 'Kratos (ph_mode=1)' );
    if 'python_peak' in results[ 0 ]:
        pp = array( [ r.get( 'python_peak', nan ) \
                      for r in results ] )[ sort_idx ];
        ax.plot( a_tau0_arr[ sort_idx ], pp, 'b^--', \
                 markersize = 8, linewidth = 1.5, \
                 label = 'Python reference' );

    ax.set_xlabel( '$a \\tau_0$', fontsize = 14 );
    ax.set_ylabel( '$|x|_{\\rm peak}$', fontsize = 14 );
    ax.set_xscale( 'log' );
    ax.set_yscale( 'log' );
    ax.legend( fontsize = 12 );
    ax.set_title( 'Escape frequency peak scaling vs $a\\tau_0$', \
                  fontsize = 14 );
    ax.grid( True, which = 'both', alpha = 0.3 );
    plot1_path = os.path.join( WORKDIR, \
                               'scaling_xpeak_vs_atau0.png' );
    fig.savefig( plot1_path, dpi = 150, bbox_inches = 'tight' );
    print( '\nSaved: %s' % plot1_path );
    plt.close( fig );

    ############################################################
    #  Plot 2: Ratio to Neufeld

    fig, ax = plt.subplots( 1, 1, figsize = ( 8, 6 ) );
    if 'kratos_peak' in results[ 0 ]:
        kr = array( [ r.get( 'kratos_peak', nan ) / \
                      r[ 'neufeld_peak' ] for r in results ] ) \
             [ sort_idx ];
        ax.plot( a_tau0_arr[ sort_idx ], kr, 'rs-', markersize = 8, \
                 label = 'Kratos / Neufeld' );
    if 'python_peak' in results[ 0 ]:
        pr = array( [ r.get( 'python_peak', nan ) / \
                      r[ 'neufeld_peak' ] for r in results ] ) \
             [ sort_idx ];
        ax.plot( a_tau0_arr[ sort_idx ], pr, 'b^--', markersize = 8, \
                 label = 'Python / Neufeld' );
    ax.axhline( 1.0, color = 'k', linestyle = ':', linewidth = 1 );
    ax.set_xlabel( '$a \\tau_0$', fontsize = 14 );
    ax.set_ylabel( '$x_{\\rm peak} / x_{\\rm Neufeld}$', \
                   fontsize = 14 );
    ax.set_xscale( 'log' );
    ax.legend( fontsize = 12 );
    ax.set_title( 'Peak ratio to Neufeld prediction', fontsize = 14 );
    ax.grid( True, which = 'both', alpha = 0.3 );
    plot2_path = os.path.join( WORKDIR, \
                               'scaling_ratio_vs_atau0.png' );
    fig.savefig( plot2_path, dpi = 150, bbox_inches = 'tight' );
    print( 'Saved: %s' % plot2_path );
    plt.close( fig );

    ############################################################
    #  Plot 3: Spectrum examples

    n_examples = min( 3, len( results ) );
    fig, axes = plt.subplots( 1, n_examples, \
                              figsize = ( 6 * n_examples, 5 ), \
                              squeeze = False );
    for idx in range( n_examples ):
        r = results[ idx ];
        ax = axes[ 0, idx ];
        a_tau0 = r[ 'a_tau0' ];
        bins = linspace( 0, 15, 80 );
        bc = 0.5 * ( bins[ : -1 ] + bins[ 1: ] );
        if 'kratos_x' in r:
            h, _ = histogram( abs( r[ 'kratos_x' ] ), bins = bins, \
                              density = True );
            ax.plot( bc, h, 'r-', linewidth = 1.5, \
                     label = 'Kratos' );
        if 'python_x' in r:
            h, _ = histogram( abs( r[ 'python_x' ] ), bins = bins, \
                              density = True );
            ax.plot( bc, h, 'b--', linewidth = 1.5, \
                     label = 'Python' );
        ax.axvline( r[ 'neufeld_peak' ], color = 'k', \
                    linestyle = ':', linewidth = 1, \
                    label = 'Neufeld peak' );
        ax.set_xlabel( '|x|', fontsize = 12 );
        ax.set_ylabel( 'P(|x|)', fontsize = 12 );
        ax.set_title( '$a\\tau_0=%.0f$' % a_tau0, fontsize = 13 );
        ax.legend( fontsize = 10 );
        ax.grid( True, alpha = 0.3 );
    fig.suptitle( 'Escape frequency spectra', fontsize = 14, \
                  y = 1.02 );
    plot3_path = os.path.join( WORKDIR, 'scaling_spectra.png' );
    fig.savefig( plot3_path, dpi = 150, bbox_inches = 'tight' );
    print( 'Saved: %s' % plot3_path );
    plt.close( fig );

    ############################################################
    #  Summary table

    header = '%8s %6s %8s %8s %8s %8s %6s %6s' \
             % ( 'tau0', 'a', 'a*tau0', 'Neufeld', 'Kratos', \
                 'Python', 'K/N', 'P/N' );
    print( '\n%s' % ( '=' * 80 ) );
    print( header );
    print( '%s' % ( '-' * 80 ) );
    for r in results:
        kp = r.get( 'kratos_peak', nan );
        pp = r.get( 'python_peak', nan );
        np_ = r[ 'neufeld_peak' ];
        print( '%8.0f %6.3f %8.0f %8.3f %8.3f %8.3f %6.3f %6.3f' \
               % ( r[ 'tau0' ], r[ 'a' ], r[ 'a_tau0' ], np_, kp, \
                   pp, kp / np_, pp / np_ ) );
    print( '%s' % ( '=' * 80 ) );

    return results;


if __name__ == '__main__':
    main( );
