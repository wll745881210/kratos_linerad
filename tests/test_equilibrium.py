"""Tests for the statistical-equilibrium population solver.

Covers the Planck-background thermalisation of the target transition
pair: with a gas temperature given, a cell with zero external flux
must still relax toward the 2-level LTE excited fraction instead of
being pinned to the ground state.  Pure Python - no Kratos run needed.
"""

import os;
import sys;

from math import isclose;

import numpy as np;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from molecular.transition_info import TransitionInfo;  # noqa: E402
from molecular.equilibrium   import solve_populations;  # noqa: E402


def make_co( ):
    return TransitionInfo( 'CO', 0 ).species_data;


def excited_fraction( n ):
    n = np.asarray( n, dtype = float );
    tot = n.sum( );
    if tot <= 0:
        return 0.0;
    return ( tot - n[ 0 ] ) / tot;


############################################################
# Thermalisation at zero external flux

def test_zero_flux_high_T_thermalises( ):
    """Zero external flux, T >> E_u/k_B: excited fraction must NOT be 0."""
    co = make_co( );
    sol = solve_populations( co, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 1800.0 ] ), \
                             b_param = 1e5, transition_idx = 0 );
    frac = excited_fraction( sol[ :, 0 ] );
    assert frac > 0.5, "T=1800 K with zero flux gave frac_exc=%.4f" % frac;


def test_zero_flux_no_T_ground_state( ):
    """No external flux AND no temperature: all population in n0."""
    co = make_co( );
    sol = solve_populations( co, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = None, b_param = 1e5, transition_idx = 0 );
    n = sol[ :, 0 ];
    assert isclose( n[ 0 ], 1.0, rel_tol = 1e-12 );
    assert excited_fraction( n ) == 0.0;


def test_high_T_approaches_LTE_limit( ):
    """T -> inf: n_upper/(n_lower+n_upper) -> g_u/(g_l+g_u) = 3/4 for CO."""
    co = make_co( );
    sol = solve_populations( co, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 1e6 ] ), \
                             b_param = 1e5, transition_idx = 0 );
    frac = excited_fraction( sol[ :, 0 ] );
    assert isclose( frac, 0.75, rel_tol = 1e-3 ), \
        "T->inf excited fraction %.4f (expected ~0.75)" % frac;


def test_thermalisation_2level_agrees( ):
    """Multi-level zero-flux path matches the 2-level closed form."""
    co = make_co( );
    t = co.transitions[ 0 ];
    upper, lower = int( t[ 0 ] ), int( t[ 1 ] );
    A_ul = float( t[ 2 ] );
    nu = float( t[ 3 ] ) * 1e9;
    h = 6.62607015e-27;
    kB = 1.380649e-16;
    g_u = co.get_level_weight( upper );
    g_l = co.get_level_weight( lower );
    T = 100.0;
    x_planck = 1.0 / ( np.exp( h * nu / ( kB * T ) ) - 1.0 );
    R_abs = ( g_u / g_l ) * x_planck * A_ul;
    R_stim = x_planck * A_ul;
    expect = R_abs / ( A_ul + R_stim + R_abs );
    sol = solve_populations( co, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ T ] ), \
                             b_param = 1e5, transition_idx = 0 );
    got = sol[ upper, 0 ] / sol[ :, 0 ].sum( );
    assert isclose( got, expect, rel_tol = 1e-6 ), \
        "got %.6f expected %.6f" % ( got, expect );


############################################################
# External flux still drives the pair

def test_external_flux_above_thermal( ):
    """Strong external flux dominates the Planck background."""
    co = make_co( );
    sol = solve_populations( co, np.array( [ 1e12 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 10.0 ] ), \
                             b_param = 1e5, transition_idx = 0 );
    frac = excited_fraction( sol[ :, 0 ] );
    assert frac > 0.999, "strong flux should saturate n_upper, got %.4f" % frac;


def test_zero_flux_cold_ground_state( ):
    """T -> 0 with zero flux: nothing excited (no numerical NaN)."""
    co = make_co( );
    sol = solve_populations( co, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 1e-3 ] ), \
                             b_param = 1e5, transition_idx = 0 );
    n = sol[ :, 0 ];
    assert np.all( np.isfinite( n ) );
    assert excited_fraction( n ) < 0.5;


if __name__ == '__main__':
    import traceback;
    fns = [ v for k, v in sorted( globals( ).items( ) ) \
            if k.startswith( 'test_' ) and callable( v ) ];
    n_fail = 0;
    for fn in fns:
        try:
            fn( );
            print( "PASS %s" % fn.__name__ );
        except Exception:
            n_fail += 1;
            print( "FAIL %s" % fn.__name__ );
            traceback.print_exc( );
    print( "\n%d/%d passed" % ( len( fns ) - n_fail, len( fns ) ) );
    sys.exit( 1 if n_fail else 0 );
