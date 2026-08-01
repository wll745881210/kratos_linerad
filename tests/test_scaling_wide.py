#!/usr/bin/env python3
"""
Wide a*tau0 spectrum validation: Kratos vs Python vs Neufeld analytic.

Sweeps a=0.5 over a range of tau0 (Neufeld mean-depth convention) and
compares the emergent escape-frequency spectrum against:
  (a) Python reference MCRT (mcrt_slab, ph_mode=1, isotropic midplane)
  (b) Neufeld (1990) eq. (2.24) analytic (mean-depth convention)

The spectrum panels follow the style of neufeld_test_validation.png:
signed x, xlim +/- 3.5*(a*tau0)^(1/3), analytic curve overlaid.

tau convention (mean-depth, half-slab)
--------------------------------------
Both MCs use the raw-Hjerting opacity

    kappa(x) = mfp_i_sca_0 * H(a, x)        (Kratos photon.h, mcrt.py:204-207)

with  integral H(a, x) dx = sqrt(pi).  The half-slab mean depth is therefore

    tau_m = mfp_i_sca_0 * sqrt(pi) * L_slab / 2 .

To run at a target Neufeld mean depth tau0_fid we set

    mfp_i_sca_0 = 2 * tau0_fid / (sqrt(pi) * L_slab) .

NOTE: the earlier `tau0_LC = tau0_fid / sqrt(pi)` conversion with
`mfp = tau0_LC / L_slab` was missing the factor 2 (half-slab vs full-slab)
and ran the MCs at tau0_fid / 2, producing a constant 2**(-1/3) = 0.794
offset vs the analytic.

The Verhamme (2006) line-centre transcription (peak 1.066 (a tau0_LC)**(1/3))
is NOT used here: it assumes H(a, 0) = 1, which fails for a >= 0.1
(H(0.5, 0) = 0.616).  We use the Neufeld ORIGINAL eq. (2.24) directly,
peak 0.881 (a tau0)**(1/3), which is convention-independent.

Usage
-----
  python tests/test_scaling_wide.py
  python tests/test_scaling_wide.py --tau0-fid-list 200 2000 32000 --n 5000
  python tests/test_scaling_wide.py --no-kratos   # Python + analytic only
"""
import argparse, os, subprocess, sys;
from pathlib import Path;
from numpy import array, zeros, full, linspace, logspace, log10, \
                 asarray, abs, sqrt, cos, sin, cosh, pi, argsort, \
                 histogram, argmax, median, nan, trapezoid, \
                 float32, float64, int32, random;

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
#  Analytic formulas (Neufeld 1990 eq. 2.24, mean-depth convention)

def neufeld_peak( a_tau0 ):
    """Neufeld (1990) peak: |x_p| = 0.881 * (a*tau0)**(1/3),
    tau0 = mean depth."""
    return 0.881 * a_tau0 ** ( 1.0 / 3.0 );


def neufeld_J( x, a_tau0 ):
    """
    Neufeld (1990) emergent spectrum, eq. (2.24), mean-depth convention.

        J(x) = (sqrt(6)/24) * x^2 / (a*tau0)
               / cosh[ (pi^4/54)**(1/2) * |x^3| / (a*tau0) ]

    Peak at |x| = 0.881 * (a*tau0)**(1/3).  Normalization is convention-
    independent (depends only on the frequency-integrated optical depth
    tau0 = mfp_i_sca_0 * sqrt(pi) * L_half, not on H(a, 0)).
    """
    xa = abs( asarray( x, dtype = float64 ) );
    K = sqrt( pi ** 4 / 54.0 );
    A = sqrt( 6.0 ) / 24.0;
    return A * xa * xa / ( a_tau0 + 1e-35 ) / \
        cosh( K * xa * xa * xa / ( a_tau0 + 1e-35 ) );

############################################################
#  Kratos input generation

def estimate_n_scatt( tau0, a_voigt ):
    if a_voigt > 1e-6:
        return max( 100, int( 2.857 * tau0 ) );
    else:
        return max( 100, int( tau0 * tau0 ) );


PAR_TEMPLATE = """# Kratos wide-scaling test - auto-generated

[unit]
length  = {unit_l0:.6e}
time    = {unit_t0}
density = 1.0

[mesh]
x_min = {x_min:.6f} 0 0
x_max = {x_max:.6f} 1 1
n_cell_global = {nx} 2 2

[cycle]
prefix_output = test
n_cycle_lim   = 0
t_lim         = {t_lim}
t_output_next = 1e32
dt_output     = 1e32
final_output  = 1

[particle]
n_step = {n_step}
n_scat = {n_step}
output = 1
n_radiation = {n_radiation}

[line_rt]
field_file  = {field_file}
photon_file = {photon_file}
ph_mode     = {ph_mode}
b_sca       = {b_sca_code:.10e}
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = {a_voigt}

[boundary]
kinds = fre fre per per per per
"""


def generate_kratos_inputs( tau0_fid, a_voigt, n_radiation, \
                            out_dir, tag, n_cell = 128, \
                            L_slab = 1.49598e14, b_sca = 1.0e5, \
                            t_lim = 1800.0, seed = 42, \
                            ph_mode = 1 ):
    """Generate Kratos field/photon/par files for a target mean depth
    tau0_fid.

    mfp_i_sca_0 is set so that the half-slab mean depth
        tau_m = mfp_i_sca_0 * sqrt(pi) * L_slab / 2
    equals tau0_fid.  See module docstring for the convention.
    """
    L_slab_code = L_slab / UNIT_L0;
    nx = n_cell;
    dx_code = L_slab_code / nx;
    half_code = L_slab_code / 2;

    mfp_i_sca_0_code = ( 2.0 * tau0_fid ) / \
                       ( sqrt( pi ) * L_slab ) * UNIT_L0;
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
        'dx'     : array( [ dx_code, 0.5, 0.5 ], dtype = float32 ),
    };

    field_file = os.path.join( out_dir, 'fields_%s.bin' % tag );
    write_field_data( field_file, fields, mesh );

    n_sc_est = estimate_n_scatt( tau0_fid, a_voigt );
    n_step = max( n_radiation * n_sc_est * 3, 5000000 );

    par_path = os.path.join( out_dir, 'neufeld_%s.par' % tag );
    par_content = PAR_TEMPLATE.format(
        unit_l0 = UNIT_L0, unit_t0 = UNIT_T0,
        x_min = -half_code, x_max = half_code, nx = nx,
        t_lim = t_lim, n_step = n_step, n_radiation = n_radiation,
        field_file = os.path.basename( field_file ),
        photon_file = 'photons_%s.bin' % tag,
        b_sca_code = b_sca_code, a_voigt = a_voigt, \
        ph_mode = ph_mode,
    );
    with open( par_path, 'w' ) as fp:
        fp.write( par_content );

    photon_file = os.path.join( out_dir, 'photons_%s.bin' % tag );
    rng = random.default_rng( seed );
    ph = zeros( ( n_radiation, 9 ), dtype = float64 );
    ph[ :, 0 ] = 0.0;
    ph[ :, 1 ] = rng.uniform( 0.0, 1.0, n_radiation );
    ph[ :, 2 ] = rng.uniform( 0.0, 1.0, n_radiation );
    mu = rng.uniform( -1.0, 1.0, n_radiation );
    phi = rng.uniform( 0.0, 2.0 * pi, n_radiation );
    smu = sqrt( 1.0 - mu * mu );
    ph[ :, 3 ] = smu * cos( phi );
    ph[ :, 4 ] = smu * sin( phi );
    ph[ :, 5 ] = mu;
    ph[ :, 6 ] = 1.0 / n_radiation;
    ph[ :, 7 ] = 0.0;
    ph[ :, 8 ] = 0.0;
    write_photon_data( photon_file, ph, n_col = 9 );

    return par_path, n_step;


def run_kratos_one( tau0_fid, a_voigt, n_radiation, out_dir, tag, \
                    ph_mode = 1 ):
    print( '  Kratos: tau0_fid=%.1f, a=%s, n=%d, ph_mode=%d' \
           % ( tau0_fid, a_voigt, n_radiation, ph_mode ) );
    par_path, n_step = generate_kratos_inputs(
        tau0_fid, a_voigt, n_radiation, out_dir, tag, \
        ph_mode = ph_mode );

    result = subprocess.run(
        [ KRATOS_BIN, os.path.basename( par_path ) ],
        cwd = out_dir, capture_output = True, text = True, \
        timeout = 1800,
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
    print( '    n_esc=%d, x_peak=%.3f, med|x|=%.3f, n_step=%d' \
           % ( len( x_freq ), x_peak, median( abs_x ), n_step ) );
    return {
        'x_freq' : x_freq, 'x_peak' : x_peak,
        'med_x'  : median( abs_x ), 'n_esc' : len( x_freq ),
    };


def run_python_one( tau0_fid, a_voigt, n_radiation ):
    """Run Python reference MCRT at target mean depth tau0_fid.

    mcrt_slab's `tau0` arg is mfp*L_slab; with kappa = mfp*H(a,x) and
    integral H = sqrt(pi), the half-slab mean depth is
    tau_m = mfp * sqrt(pi) * L_slab/2 = tau0_mcrt * sqrt(pi) / 2.
    Setting tau0_mcrt = 2*tau0_fid/sqrt(pi) gives tau_m = tau0_fid.
    """
    tau0_mcrt = 2.0 * tau0_fid / sqrt( pi );
    print( '  Python: tau0_fid=%.1f, tau0_mcrt=%.1f, a=%s, n=%d' \
           % ( tau0_fid, tau0_mcrt, a_voigt, n_radiation ) );
    result = mcrt_slab(
        n_cell = 128, L_slab = 1.49598e14,
        tau0 = tau0_mcrt, tau_abs = 0.0, b_sca = 1.0e5,
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
        'med_x'  : median( abs_x ), 'n_esc' : len( x_freq ),
    };

############################################################
#  Main

def main( ):
    p = argparse.ArgumentParser( \
        description = 'Wide a*tau0 spectrum validation' );
    p.add_argument( '--tau0-fid-list', type = float, nargs = '+', \
                    default = [ 200, 500, 2000, 8000, 32000 ], \
                    help = 'Neufeld mean-depth tau0 values (half-slab, ' \
                           'frequency-integrated optical depth)' );
    p.add_argument( '--a', dest = 'a_voigt', type = float, \
                    default = 0.149, \
                    help = 'Voigt a parameter (default 0.149, T~10K ' \
                           'Lya, used by Verhamme 2006 and other Lya ' \
                           'papers)' );
    p.add_argument( '--n', dest = 'n_radiation', type = int, \
                    default = 10000 );
    p.add_argument( '--ph-mode-list', type = int, nargs = '+', \
                    default = [ 1, 2 ], \
                    help = 'Kratos ph_mode values to test (1=R_IIA v1 ' \
                           'global, 2=R_IIA coarse const-mem). Pass ' \
                           '"1 2" to compare.' );
    p.add_argument( '--no-kratos', action = 'store_true' );
    p.add_argument( '--no-python', action = 'store_true' );
    args = p.parse_args( );

    os.makedirs( WORKDIR, exist_ok = True );
    ph_modes = args.ph_mode_list;

    results = [ ];
    for tau0_fid in args.tau0_fid_list:
        a_tau0 = args.a_voigt * tau0_fid;
        at13 = a_tau0 ** ( 1.0 / 3.0 );
        pred = neufeld_peak( a_tau0 );
        print( '\n=== tau0=%.0f (mean-depth), a=%s, a*tau0=%.0f, ' \
               '(a*tau0)^(1/3)=%.2f, Neufeld peak=%.3f ===' \
               % ( tau0_fid, args.a_voigt, a_tau0, at13, pred ) );

        entry = {
            'tau0' : tau0_fid,
            'a' : args.a_voigt, 'a_tau0' : a_tau0, 'at13' : at13,
            'neufeld_peak' : pred,
        };

        if not args.no_kratos:
            for pm in ph_modes:
                for f in Path( WORKDIR ).glob( 'test_0*.bin' ):
                    f.unlink( );
                tag = 'fid%.0f_a%s_pm%d' % ( tau0_fid, \
                                             args.a_voigt, pm );
                kres = run_kratos_one( tau0_fid, args.a_voigt, \
                                       args.n_radiation, WORKDIR, \
                                       tag, ph_mode = pm );
                if kres:
                    entry[ 'kratos_peak_pm%d' % pm ] = \
                        kres[ 'x_peak' ];
                    entry[ 'kratos_med_pm%d' % pm ] = \
                        kres[ 'med_x' ];
                    entry[ 'kratos_x_pm%d' % pm ] = \
                        kres[ 'x_freq' ];

        if not args.no_python:
            pres = run_python_one( tau0_fid, args.a_voigt, \
                                   args.n_radiation );
            if pres:
                entry[ 'python_peak' ] = pres[ 'x_peak' ];
                entry[ 'python_med' ] = pres[ 'med_x' ];
                entry[ 'python_x' ] = pres[ 'x_freq' ];

        results.append( entry );

    ############################################################
    #  Colour / marker scheme per ph_mode

    pm_styles = {
        1 : ( 'r', 's', '-', 'ph_mode=1 (R_IIA v1, global, du=0.01)' ),
        2 : ( 'b', '^', '--', \
              'ph_mode=2 (R_IIA coarse, const-mem, du=0.048)' ),
    };

    def kratos_pm_keys( r ):
        return sorted( k for k in r \
                       if k.startswith( 'kratos_peak_pm' ) );

    ############################################################
    #  Plot 1: |x_peak| vs a*tau0

    import matplotlib;
    matplotlib.use( 'Agg' );
    import matplotlib.pyplot as plt;

    fig, ax = plt.subplots( 1, 1, figsize = ( 8, 6 ) );
    at_arr = array( [ r[ 'a_tau0' ] for r in results ] );
    sort_idx = argsort( at_arr );
    at_fine = logspace( log10( max( at_arr.min( ), 1 ) ), \
                        log10( at_arr.max( ) * 1.5 ), 100 );
    ax.plot( at_fine, neufeld_peak( at_fine ), 'k--', \
             linewidth = 2, label = 'Neufeld: $0.881(a\\tau_0)^{1/3}$' );
    first = results[ 0 ];
    for pm in ph_modes:
        key = 'kratos_peak_pm%d' % pm;
        if key in first:
            c, m, ls, lbl = pm_styles.get( pm, \
                                           ( 'g', 'o', '-', \
                                             'pm%d' % pm ) );
            kp = array( [ r.get( key, nan ) for r in results ] ) \
                 [ sort_idx ];
            ax.plot( at_arr[ sort_idx ], kp, color = c, marker = m, \
                     linestyle = ls, markersize = 8, \
                     linewidth = 1.5, \
                     label = 'Kratos (%s)' % lbl );
    if 'python_peak' in first:
        pp = array( [ r.get( 'python_peak', nan ) \
                      for r in results ] )[ sort_idx ];
        ax.plot( at_arr[ sort_idx ], pp, 'g^--', markersize = 8, \
                 linewidth = 1.5, label = 'Python reference' );
    ax.set_xlabel( '$a \\tau_0$ (mean-depth)', fontsize = 14 );
    ax.set_ylabel( '$|x|_{\\rm peak}$', fontsize = 14 );
    ax.set_xscale( 'log' );
    ax.set_yscale( 'log' );
    ax.legend( fontsize = 11 );
    ax.set_title( 'Escape frequency peak scaling vs $a\\tau_0$', \
                  fontsize = 14 );
    ax.grid( True, which = 'both', alpha = 0.3 );
    plot1 = os.path.join( WORKDIR, 'scaling_wide_xpeak.png' );
    fig.savefig( plot1, dpi = 150, bbox_inches = 'tight' );
    print( '\nSaved: %s' % plot1 );
    plt.close( fig );

    ############################################################
    #  Plot 2: Ratio to Neufeld

    fig, ax = plt.subplots( 1, 1, figsize = ( 8, 6 ) );
    for pm in ph_modes:
        key = 'kratos_peak_pm%d' % pm;
        if key in first:
            c, m, ls, lbl = pm_styles.get( pm, \
                                           ( 'g', 'o', '-', \
                                             'pm%d' % pm ) );
            kr = array( [ r.get( key, nan ) / r[ 'neufeld_peak' ] \
                          for r in results ] )[ sort_idx ];
            ax.plot( at_arr[ sort_idx ], kr, color = c, marker = m, \
                     linestyle = ls, markersize = 8, \
                     label = 'Kratos (%s) / Neufeld' % lbl );
    if 'python_peak' in first:
        pr = array( [ r.get( 'python_peak', nan ) / \
                      r[ 'neufeld_peak' ] for r in results ] ) \
             [ sort_idx ];
        ax.plot( at_arr[ sort_idx ], pr, 'g^--', markersize = 8, \
                 label = 'Python / Neufeld' );
    ax.axhline( 1.0, color = 'k', linestyle = ':', linewidth = 1 );
    ax.set_xlabel( '$a \\tau_0$ (mean-depth)', fontsize = 14 );
    ax.set_ylabel( '$x_{\\rm peak} / x_{\\rm Neufeld}$', \
                   fontsize = 14 );
    ax.set_xscale( 'log' );
    ax.legend( fontsize = 11 );
    ax.set_title( 'Peak ratio to Neufeld prediction', fontsize = 14 );
    ax.grid( True, which = 'both', alpha = 0.3 );
    plot2 = os.path.join( WORKDIR, 'scaling_wide_ratio.png' );
    fig.savefig( plot2, dpi = 150, bbox_inches = 'tight' );
    print( 'Saved: %s' % plot2 );
    plt.close( fig );

    ############################################################
    #  Plot 3: Spectrum grid with analytic overlay
    #    Style: neufeld_test_validation.png Panel A.
    #    Signed x, xlim +/- 3.5 * (a*tau0)^(1/3).

    n_pts = len( results );
    n_cols = min( 3, n_pts );
    n_rows = ( n_pts + n_cols - 1 ) // n_cols;
    fig, axes = plt.subplots( n_rows, n_cols, \
                              figsize = ( 5.5 * n_cols, \
                                          4.5 * n_rows ), \
                              squeeze = False );
    for idx, r in enumerate( results ):
        ax = axes[ idx // n_cols ][ idx % n_cols ];
        a_tau0 = r[ 'a_tau0' ];
        xp = neufeld_peak( a_tau0 );
        xlim = 3.5 * ( a_tau0 ** ( 1.0 / 3.0 ) );
        bins = linspace( -xlim, xlim, 81 );
        bc = 0.5 * ( bins[ : -1 ] + bins[ 1: ] );

        has_legend = False;
        for pm in ph_modes:
            xkey = 'kratos_x_pm%d' % pm;
            if xkey in r:
                c, m, ls, lbl = pm_styles.get( pm, \
                                               ( 'g', 'o', '-', \
                                                 'pm%d' % pm ) );
                h, _ = histogram( r[ xkey ], bins = bins, \
                                  density = True );
                ax.plot( bc, h, color = c, linestyle = ls, \
                         linewidth = 1.5, \
                         label = 'Kratos ph_mode=%d' % pm );
                has_legend = True;
        if 'python_x' in r:
            h, _ = histogram( r[ 'python_x' ], bins = bins, \
                              density = True );
            ax.plot( bc, h, 'g--', linewidth = 1.5, \
                     label = 'Python' );
            has_legend = True;

        J = neufeld_J( bc, a_tau0 );
        norm = float( trapezoid( J, bc ) );
        if norm > 0:
            J /= norm;
        ax.plot( bc, J, 'k:', linewidth = 2, \
                 label = 'Neufeld analytic' );
        has_legend = True;

        for s in ( 1, -1 ):
            ax.axvline( s * xp, color = 'gray', linestyle = ':', \
                        linewidth = 0.8 );
        ax.set_xlim( -xlim, xlim );
        ax.set_xlabel( '$x$', fontsize = 11 );
        ax.set_ylabel( '$P(x)$', fontsize = 11 );
        at13 = r[ 'at13' ];
        ax.set_title(
            '$\\tau_0=%.0f$, $(a\\tau_0)^{1/3}=%.1f$' \
            % ( r[ 'tau0' ], at13 ), fontsize = 11 );
        if has_legend:
            ax.legend( fontsize = 8 );
        ax.grid( True, alpha = 0.3 );

    # Hide unused subplots
    for idx in range( n_pts, n_rows * n_cols ):
        axes[ idx // n_cols ][ idx % n_cols ].set_visible( False );

    fig.suptitle(
        'Emergent spectra: Kratos ph_mode comparison vs Neufeld ' \
        'analytic ($a=%s$, isotropic midplane)' % args.a_voigt, \
        fontsize = 13, y = 1.01 );
    plot3 = os.path.join( WORKDIR, 'scaling_wide_spectra.png' );
    fig.savefig( plot3, dpi = 150, bbox_inches = 'tight' );
    print( 'Saved: %s' % plot3 );
    plt.close( fig );

    ############################################################
    #  Summary table

    pm_cols = '';
    for pm in ph_modes:
        pm_cols += ' %8s %7s' % ( 'K(pm%d)' % pm, 'med' );
    header = '%7s %8s %10s %8s' \
             % ( 'tau0', 'a*tau0', '(at)^(1/3)', 'Neufeld' ) \
             + pm_cols \
             + ( ' %8s' % 'Python' if not args.no_python else '' ) \
             + ( ' %6s' % 'P/N' if not args.no_python else '' );
    print( '\n%s' % ( '=' * len( header ) ) );
    print( header );
    print( '%s' % ( '-' * len( header ) ) );
    for r in results:
        np_ = r[ 'neufeld_peak' ];
        line = '%7.0f %8.0f %10.1f %8.3f' \
               % ( r[ 'tau0' ], r[ 'a_tau0' ], r[ 'at13' ], np_ );
        for pm in ph_modes:
            kp = r.get( 'kratos_peak_pm%d' % pm, nan );
            km = r.get( 'kratos_med_pm%d' % pm, nan );
            line += ' %8.3f %7.3f' % ( kp, km );
        if not args.no_python:
            pp = r.get( 'python_peak', nan );
            line += ' %8.3f %6.3f' % ( pp, pp / np_ );
        print( line );
    print( '%s' % ( '=' * len( header ) ) );

    return results;


if __name__ == '__main__':
    main( );
