#!/usr/bin/env python3
"""
R_IIA redistribution kernel table validation
--------------------------------------------
Replicates the GPU kernel-table construction of
usr_ext/line_rt/intg.h (build_riia_kernel, intg.h:572ff) and its
lookup (riia_kernel, intg.h:759ff) in pure Python, and compares
the tabulated kernel against a direct high-resolution quadrature
evaluation of the analytic Gaussian-mixture form

    R(x_out; x_pp, g) = sum_k pdf[k | x_pp]
                        * G(x_out - x_pp - u_k (g - 1); sin_g/sqrt(2))

where pdf[k|x] is the discrete USampler conditional distribution
    p(u||x)  propto  exp(-u^2) / (a^2 + (x - u)^2)
(product of the thermal Maxwellian and the atomic Lorentz profile,
sampled on the code's u-grid), and G(.; s) is a normalized Gaussian
of width s.  The table approximations quantified here are:

  1. the 251-point u-quadrature of the USampler;
  2. the snapping of the conditioning row to the 40-point xg grid
     (18 linear points below 8, then logarithmic to 300) with no
     interpolation in the conditioning variable;
  3. the trilinear interpolation of the 400 x 200 x 40 table over
     (x_out, |x_pp|, g), with |x| <= 120.

Outputs a two-panel figure (kernel curves + fractional error versus
x_pp) and exits non-zero if the interior fractional error exceeds
the tolerance.

Default output: abs path passed via --fig (PDF).
"""

import argparse, os, sys;
import numpy as np;

SQRT_PI = 1.7724538509055159;

# Code constants (intg.h)
N_U      = 251;
U_MAX    = 30.0;
DU       = 2.0 * U_MAX / ( N_U - 1 );
N_XG     = 40;
N_LIN    = 18;
X_LIN_MAX = 8.0;
X_MAX    = 300.0;
N_RIIA_XO = 400;
N_RIIA_XP = 200;
N_RIIA_G  = 40;
RIIA_XO_MAX = 120.0;
RIIA_XP_MAX = 120.0;

def build_usampler( a_voigt ):
    """Replicates build_usampler: returns (xg, cdf) with
    cdf[j, k] = normalized CDF of p(u|xg[j]) on the u-grid."""
    xg = np.empty( N_XG );
    for j in range( N_LIN ):
        xg[ j ] = j / float( N_LIN - 1 ) * X_LIN_MAX;
    for j in range( N_XG - N_LIN ):
        xg[ N_LIN + j ] = X_LIN_MAX * ( X_MAX / X_LIN_MAX ) \
            ** ( ( j + 1.0 ) / ( N_XG - N_LIN ) );
    a_eff = max( a_voigt, 1e-6 );
    u = -U_MAX + DU * np.arange( N_U );
    cdf = np.empty( ( N_XG, N_U ) );
    for j in range( N_XG ):
        p = np.exp( -u * u ) / ( a_eff * a_eff + ( xg[ j ] - u ) ** 2 );
        cdf[ j ] = np.cumsum( p );
        cdf[ j ] /= cdf[ j, -1 ];
    return xg, cdf, u;

def build_riia_table( xg, cdf, u ):
    """Replicates build_riia_kernel: table[io, jp, ig]."""
    dxo = 2.0 * RIIA_XO_MAX / ( N_RIIA_XO - 1 );
    dxp = RIIA_XP_MAX / ( N_RIIA_XP - 1 );
    dg  = 2.0 / ( N_RIIA_G - 1 );
    tab = np.empty( ( N_RIIA_XO, N_RIIA_XP, N_RIIA_G ) );
    for jp in range( N_RIIA_XP ):
        xpp = jp * dxp;
        # binary search: largest j with xg[j] <= xpp, clamped
        jxg = int( np.searchsorted( xg, xpp, side = 'right' ) ) - 1;
        jxg = min( max( jxg, 0 ), N_XG - 2 );
        row = cdf[ jxg ];
        pdf = np.empty( N_U );
        pdf[ 0 ] = row[ 0 ];
        pdf[ 1: ] = row[ 1: ] - row[ :-1 ];
        for ig in range( N_RIIA_G ):
            g = -1.0 + ig * dg;
            sin_g = max( np.sqrt( max( 1.0 - g * g, 0.0 ) ), 1e-3 );
            gm1 = g - 1.0;
            inv_sg = 1.0 / sin_g;
            xo = -RIIA_XO_MAX + dxo * np.arange( N_RIIA_XO );
            y = xo[ :, None ] - xpp - u[ None, : ] * gm1;
            tab[ :, jp, ig ] = ( pdf[ None, : ]
                * np.exp( -( y * inv_sg ) ** 2 ) ).sum( axis = 1 ) \
                * inv_sg / SQRT_PI;
    return tab, dxo, dxp, dg;

def riia_kernel( tab, dxo, dxp, dg, x_out, x_pp, g ):
    """Replicates riia_kernel: trilinear lookup with the symmetry
    R(xo; -xp, g) = R(-xo; xp, g).  Array-safe in x_out."""
    sgn = 1.0 if x_pp >= 0.0 else -1.0;
    ax_pp = abs( x_pp );
    txo = np.asarray( x_out, dtype = float ) * sgn;

    ixp = int( ax_pp / dxp );
    ixp = min( max( ixp, 0 ), N_RIIA_XP - 2 );
    fxp = ( ax_pp - ixp * dxp ) / dxp;
    fxp = min( max( fxp, 0.0 ), 1.0 );

    ixo = ( txo + RIIA_XO_MAX ) / dxo;
    ixo_i = np.clip( ixo.astype( int ), 0, N_RIIA_XO - 2 );
    fxo = np.clip( ( txo + RIIA_XO_MAX - ixo_i * dxo ) / dxo,
                   0.0, 1.0 );

    ig = int( ( g + 1.0 ) / dg );
    ig = min( max( ig, 0 ), N_RIIA_G - 2 );
    fg = ( g + 1.0 - ig * dg ) / dg;
    fg = min( max( fg, 0.0 ), 1.0 );

    def T( io, jp, ig_ ):
        return tab[ io, jp, ig_ ];
    c00 = T( ixo_i, ixp, ig ) * ( 1 - fxo ) \
        + T( ixo_i + 1, ixp, ig ) * fxo;
    c01 = T( ixo_i, ixp, ig + 1 ) * ( 1 - fxo ) \
        + T( ixo_i + 1, ixp, ig + 1 ) * fxo;
    c10 = T( ixo_i, ixp + 1, ig ) * ( 1 - fxo ) \
        + T( ixo_i + 1, ixp + 1, ig ) * fxo;
    c11 = T( ixo_i, ixp + 1, ig + 1 ) * ( 1 - fxo ) \
        + T( ixo_i + 1, ixp + 1, ig + 1 ) * fxo;
    return ( c00 * ( 1 - fg ) + c01 * fg ) * ( 1 - fxp ) \
         + ( c10 * ( 1 - fg ) + c11 * fg ) * fxp;

def riia_reference( x_out, x_pp, g, a_voigt, n_fine = 8001 ):
    """Direct quadrature of the analytic Gaussian mixture with the
    exact conditional p(u|x_pp) (no xg-row snapping)."""
    a_eff = max( a_voigt, 1e-6 );
    u = np.linspace( -U_MAX, U_MAX, n_fine );
    p = np.exp( -u * u ) / ( a_eff * a_eff + ( x_pp - u ) ** 2 );
    p /= p.sum();
    sin_g = max( np.sqrt( max( 1.0 - g * g, 0.0 ) ), 1e-12 );
    y = np.asarray( x_out, dtype = float )[ :, None ] \
        - x_pp - u[ None, : ] * ( g - 1.0 );
    return ( p[ None, : ] * np.exp( -( y / sin_g ) ** 2 ) ).sum( axis = 1 ) \
        / ( sin_g * SQRT_PI );

def main( ):
    p = argparse.ArgumentParser( description = __doc__ );
    p.add_argument( '--a-voigt', type = float, default = 0.149 );
    p.add_argument( '--tol', type = float, default = 0.10,
        help = 'max allowed total-variation error at g = 0' );
    p.add_argument( '--fig', type = str, default = None );
    args = p.parse_args();

    xg, cdf, u = build_usampler( args.a_voigt );
    tab, dxo, dxp, dg = build_riia_table( xg, cdf, u );
    print( 'table built: %dx%dx%d, dxo=%.4f, dxp=%.4f, dg=%.4f'
        % ( N_RIIA_XO, N_RIIA_XP, N_RIIA_G, dxo, dxp, dg ) );

    # ---- error metrics vs x_pp: total variation + mass ----
    xo_eval = np.linspace( -119.5, 119.5, 2401 );
    g_metrics = [ 0.0, 0.9 ];
    xp_scan = np.concatenate( [ np.linspace( 0.2, 8, 12 ),
                                np.linspace( 10, 115, 28 ) ] );
    tv = { g: np.empty( xp_scan.size ) for g in g_metrics };
    mass_err_max = 0.0;
    for i, xpp in enumerate( xp_scan ):
        for g in g_metrics:
            r_ref = riia_reference( xo_eval, xpp, g, args.a_voigt );
            r_tab = riia_kernel( tab, dxo, dxp, dg, xo_eval, xpp, g );
            tv[ g ][ i ] = 0.5 * np.trapezoid(
                np.abs( r_tab - r_ref ), xo_eval );
            mass_err_max = max( mass_err_max, abs(
                np.trapezoid( r_tab, xo_eval ) - 1.0 ) );
        if i % 10 == 9:
            print( '  scan %d/%d done' % ( i + 1, xp_scan.size ) );
    tv0_max = float( tv[ 0.0 ].max() );
    tv9_max = float( tv[ 0.9 ].max() );
    print( 'max TV error: g=0 %.4f, g=0.9 %.4f'
        % ( tv0_max, tv9_max ) );
    print( 'max mass-conservation error: %.4g' % mass_err_max );

    # ---- figure ----
    if args.fig:
        import matplotlib;
        matplotlib.use( 'Agg' );
        import matplotlib.pyplot as plt;
        import sys as _sys;
        _sys.path.insert( 0, '/home/lilew/Seafile/seafile_sync/'
                             'current_work/kratos_linerad/'
                             'Figures/code' );
        from line_rt_style import use_house_style;
        from matplotlib.lines import Line2D;
        use_house_style();
        fig, ( ax1, ax2 ) = plt.subplots( 1, 2,
            figsize = ( 11, 4.6 ) );
        xo_plot = np.linspace( -119.0, 119.0, 2401 );
        cases = [ ( 1.0, 0.0, 'tab:blue' ),
                  ( 5.0, 0.9, 'tab:red' ),
                  ( 20.0, -0.5, 'tab:green' ),
                  ( 60.0, 0.0, 'tab:orange' ) ];
        for xpp, g, col in cases:
            r_ref = riia_reference( xo_plot, xpp, g, args.a_voigt );
            r_tab = riia_kernel( tab, dxo, dxp, dg, xo_plot, xpp, g );
            ax1.plot( xo_plot, r_ref, '-', color = col, lw = 1.8,
                label = '$x_{pp}=%g,\\ g=%g$' % ( xpp, g ) );
            ax1.plot( xo_plot[ :: 60 ], r_tab[ :: 60 ], 'o',
                color = col, ms = 4, mfc = 'none' );
        ax1.set_yscale( 'log' );
        ax1.set_ylim( 1e-6, 3.0 );
        ax1.set_xlim( -119, 119 );
        ax1.set_xlabel( '$x_{\\rm out}$' );
        ax1.set_ylabel( '$R(x_{\\rm out};\\, x_{pp},\\, g)$' );
        handles, labels = ax1.get_legend_handles_labels();
        handles += [ Line2D( [], [], color = 'k', lw = 1.8,
                             label = 'quadrature' ),
                     Line2D( [], [], color = 'k', ls = 'none',
                             marker = 'o', ms = 4, mfc = 'none',
                             label = 'kernel table' ) ];
        ax1.legend( handles = handles, fontsize = 10,
                    loc = 'upper right' );
        ax2.plot( xp_scan, tv[ 0.0 ], 'o-', color = 'tab:blue',
            ms = 4, lw = 1.5, label = '$g = 0$' );
        ax2.plot( xp_scan, tv[ 0.9 ], 's-', color = 'tab:red',
            ms = 4, lw = 1.5, label = '$g = 0.9$' );
        ax2.set_xscale( 'log' );
        ax2.set_ylim( 0.0, 0.30 );
        ax2.set_xlabel( '$x_{pp}$' );
        ax2.set_ylabel( 'total-variation error' );
        ax2.legend( fontsize = 11, loc = 'upper left' );
        fig.tight_layout();
        fig.savefig( args.fig );
        print( 'Saved ' + args.fig );

    ok = ( tv0_max <= args.tol ) and ( mass_err_max <= 0.02 );
    print( 'PASS' if ok else 'FAIL',
        '(TV(g=0) %.4f vs tol %.4f; mass err %.4g vs 0.02)'
        % ( tv0_max, args.tol, mass_err_max ) );
    sys.exit( 0 if ok else 1 );

if __name__ == '__main__':
    main();
