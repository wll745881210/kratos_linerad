"""Tests for the statistical-equilibrium population solver.

Covers collisional thermalisation of the target transition pair: with
colliders and a gas temperature, a cell with zero external flux relaxes
to collisional equilibrium (Boltzmann ratio via detailed balance).
Pure Python - no Kratos run needed.
"""

import os;
import sys;

from math import isclose;

import numpy as np;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from molecular.transition_info import TransitionInfo;  # noqa: E402
from molecular.equilibrium   import solve_populations;  # noqa: E402
from molecular.lamda_format  import SpeciesData;  # noqa: E402


def make_co( ):
    return TransitionInfo( 'CO', 0 ).species_data;


def make_3level_collisional( ):
    """3-level species (0<->1 radiative) + an H2 collision partner."""
    sd = SpeciesData(
        name            = 'TestCO',
        n_levels        = 3,
        levels        = np.array( [ [ 0.0, 1.0 ], [ 5.0, 3.0 ], \
                                     [ 20.0, 5.0 ] ] ),
        n_transitions = 1,
        transitions   = np.array( [ [ 1, 0, 1e-5, 115.271 ] ] ),
        collision_partners = [
            dict( species = 'H2',
                  temps   = np.array( [ 10.0, 100.0, 1000.0 ] ),
                  rates   = np.array( [ [ 1e-12, 1e-11, 1e-10 ], \
                                        [ 1e-13, 1e-12, 1e-11 ] ] ),
                  trans_indices = np.array( [ [ 1, 0 ], [ 2, 1 ] ] ) ),
        ],
    );
    return sd;


def make_2level_collisional( ):
    """2-level species (0<->1) + an H2 collision partner on that pair."""
    sd = SpeciesData(
        name            = 'Test2L',
        n_levels        = 2,
        levels        = np.array( [ [ 0.0, 1.0 ], [ 5.0, 3.0 ] ] ),
        n_transitions = 1,
        transitions   = np.array( [ [ 1, 0, 1e-5, 115.271 ] ] ),
        collision_partners = [
            dict( species = 'H2',
                  temps   = np.array( [ 10.0, 100.0, 1000.0 ] ),
                  rates   = np.array( [ [ 1e-12, 1e-11, 1e-10 ] ] ),
                  trans_indices = np.array( [ [ 1, 0 ] ] ) ),
        ],
    );
    return sd;


def excited_fraction( n ):
    n = np.asarray( n, dtype = float );
    tot = n.sum( );
    if tot <= 0:
        return 0.0;
    return ( tot - n[ 0 ] ) / tot;


############################################################
# Thermalisation at zero external flux

def test_zero_flux_high_T_thermalises( ):
    """Zero external flux, high T + colliders: excited fraction > 0."""
    sd = make_3level_collisional( );
    sol = solve_populations( sd, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 1800.0 ] ), \
                             colliders = { 'H2': { 'density': 1e8 } }, \
                             b_param = 1e5, transition_idx = 0 );
    frac = excited_fraction( sol[ :, 0 ] );
    assert frac > 0.5, "T=1800 K with colliders gave frac_exc=%.4f" % frac;


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
    """T -> inf with colliders: n_upper/(n_lower+n_upper) -> g_u/(g_l+g_u) = 3/4."""
    sd = make_2level_collisional( );
    sol = solve_populations( sd, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 1e6 ] ), \
                             colliders = { 'H2': { 'density': 1e12 } }, \
                             b_param = 1e5, transition_idx = 0 );
    frac = excited_fraction( sol[ :, 0 ] );
    assert isclose( frac, 0.75, rel_tol = 1e-2 ), \
        "T->inf excited fraction %.4f (expected ~0.75)" % frac;


def test_thermalisation_2level_agrees( ):
    """2-level collisional equilibrium matches the analytic Boltzmann ratio."""
    sd = make_2level_collisional( );
    t = sd.transitions[ 0 ];
    upper, lower = int( t[ 0 ] ), int( t[ 1 ] );
    h = 6.62607015e-27;
    kB = 1.380649e-16;
    c_cgs = 2.99792458e10;
    g_u = sd.get_level_weight( upper );
    g_l = sd.get_level_weight( lower );
    T = 1000.0;
    # Analytic collisional equilibrium: n_u/n_l = (g_u/g_l)*exp(-dE/kT)
    # with C_ul >> A_ul (high density).  dE from level energies
    # (TRUE cm^-1: E[erg] = E[cm^-1] * h * c).
    dE = float( sd.levels[ upper, 0 ] - sd.levels[ lower, 0 ] ) \
         * h * c_cgs;
    ratio = ( g_u / g_l ) * np.exp( -dE / ( kB * T ) );
    expect = ratio / ( 1.0 + ratio );
    sol = solve_populations( sd, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ T ] ), \
                             colliders = { 'H2': { 'density': 1e12 } }, \
                             b_param = 1e5, transition_idx = 0 );
    got = sol[ upper, 0 ] / sol[ :, 0 ].sum( );
    assert isclose( got, expect, rel_tol = 1e-2 ), \
        "got %.6f expected %.6f" % ( got, expect );


############################################################
# External flux still drives the pair

def test_external_flux_above_thermal( ):
    """Strong external flux dominates collisional equilibrium."""
    sd = make_3level_collisional( );
    sol = solve_populations( sd, np.array( [ 1e12 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 10.0 ] ), \
                             colliders = { 'H2': { 'density': 1e8 } }, \
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


############################################################
# Collisional excitation (batched rate-matrix path)

def test_collisional_ground_state_no_drive( ):
    """With colliders but zero flux + very cold T: ground state preserved."""
    sd = make_3level_collisional( );
    sol = solve_populations( sd, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 1e-3 ] ), \
                             colliders = { 'H2': { 'density': 1e6 } }, \
                             b_param = 1e5, transition_idx = 0 );
    n = sol[ :, 0 ];
    assert np.all( np.isfinite( n ) );
    assert excited_fraction( n ) < 0.5, "cold collisional gas excited";


def test_collisional_thermalises_at_high_T( ):
    """High T + colliders: pair approaches g_u/(g_l+g_u) = 3/4."""
    sd = make_3level_collisional( );
    sol = solve_populations( sd, np.array( [ 0.0 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 1000.0 ] ), \
                             colliders = { 'H2': { 'density': 1e12 } }, \
                             b_param = 1e5, transition_idx = 0 );
    n = sol[ :, 0 ];
    assert np.all( np.isfinite( n ) );
    frac = ( n[ 1 ] + n[ 2 ] ) / n.sum( );
    assert frac > 0.6, "high-T collisional gas frac_exc=%.4f" % frac;


def test_collisional_flux_drives_pair( ):
    """External flux on top of collisions: upper level saturates."""
    sd = make_3level_collisional( );
    sol = solve_populations( sd, np.array( [ 1e13 ] ), \
                             np.array( [ 1.0 ] ), \
                             T = np.array( [ 100.0 ] ), \
                             colliders = { 'H2': { 'density': 1e8 } }, \
                             b_param = 1e5, transition_idx = 0 );
    n = sol[ :, 0 ];
    assert np.all( np.isfinite( n ) );
    assert n[ 1 ] > n[ 0 ], "flux should excite level 1 above ground";
    assert excited_fraction( n ) > 0.9, \
        "strong flux should saturate, got %.4f" % excited_fraction( n );


def test_collisional_batch_matches_scalar( ):
    """Batched multi-cell solve equals the scalar single-cell solve."""
    sd = make_3level_collisional( );
    T = np.array( [ 50.0, 200.0, 800.0 ] );
    exc = np.array( [ 0.0, 1e10, 1e12 ] );
    n_tot = np.array( [ 1.0, 2.0, 3.0 ] );
    sol = solve_populations( sd, exc, n_tot, T = T, \
                             colliders = { 'H2': { 'density': 1e10 } }, \
                             b_param = 1e5, transition_idx = 0 );
    assert sol.shape == ( 3, 3 );
    for c in range( 3 ):
        sc = solve_populations( sd, np.array( [ exc[ c ] ] ), \
                                np.array( [ n_tot[ c ] ] ), \
                                T = np.array( [ T[ c ] ] ), \
                                colliders = { 'H2': { 'density': 1e10 } }, \
                                b_param = 1e5, transition_idx = 0 );
        assert np.allclose( sol[ :, c ] / sol[ :, c ].sum( ), \
                            sc[ :, 0 ] / sc[ :, 0 ].sum( ), \
                            atol = 1e-8 ), \
            "cell %d batch != scalar: %s vs %s" % \
            ( c, sol[ :, c ], sc[ :, 0 ] );


############################################################
#  LAMDA-species LTE regression (true cm^-1 level energies)
#  Before the cm^-1 unification the detailed-balance dE carried a
#  spurious x100, exp( -dE/kT ) underflowed and LAMDA species with
#  colliders relaxed to the ground state instead of LTE.

def test_lamda_species_collisional_lte( ):
    """LAMDA CO (cached, with collision tables) at high collider density
    relaxes to the full Boltzmann partition over ALL levels."""
    sp = TransitionInfo( 'CO', 0 ).species_data;
    if not sp.collision_partners:
        import pytest;
        pytest.skip( 'LAMDA CO cache (collision tables) not available' );
    coll = { cp[ 'species' ]: { 'density': 1e10 }
             for cp in sp.collision_partners };
    T = 20.0;
    sol = solve_populations( sp, np.array( [ 0.0 ] ),
                             np.array( [ 1.0 ] ), T = np.array( [ T ] ),
                             colliders = coll, b_param = 1e5,
                             transition_idx = 0 );
    n1 = float( sol[ 1, 0 ] ) if sol.ndim == 2 else \
         float( np.asarray( sol )[ 1 ].ravel( )[ 0 ] );
    h = 6.62607015e-27; c = 2.99792458e10; kB = 1.380649e-16;
    Z = sp.partition_function( T );
    n1_lte = ( 3.0 * np.exp( -sp.levels[ 1, 0 ] * h * c / ( kB * T ) )
               / Z );
    assert isclose( n1, n1_lte, rel_tol = 1e-2 ), \
        'LAMDA LTE: n1=%.5f vs Boltzmann %.5f (x100 dE regression?)' \
        % ( n1, n1_lte );


def test_lamda_partition_function_boltzmann( ):
    """Partition function uses TRUE cm^-1: Z(T->inf) -> sum(g)."""
    sp = TransitionInfo( 'CO', 0 ).species_data;
    Z_hot = float( sp.partition_function( 1e8 ).ravel( )[ 0 ] );
    Z_true = float( sp.levels[ :, 1 ].sum( ) );
    assert isclose( Z_hot, Z_true, rel_tol = 1e-3 ), \
        'Z(1e6 K)=%.2f vs sum(g)=%.2f' % ( Z_hot, Z_true );
    #  At 20 K the J=1 Boltzmann factor must be ~exp(-5.5 K / 20 K),
    #  not ~0 (which the x100 convention produced).
    f1 = ( 3.0 * np.exp( -sp.levels[ 1, 0 ] * 6.62607015e-27
                         * 2.99792458e10 / 1.380649e-16 / 20.0 )
           / float( sp.partition_function( 20.0 ).ravel( )[ 0 ] ) );
    assert f1 > 0.2, 'J=1 LTE fraction %.4f (x100 convention?)' % f1;


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
