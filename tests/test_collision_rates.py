"""Tests for collisional de-excitation rates and destruction opacity.

Tests:
1. user_defined collision_rates: number rate -> SpeciesData collision_partners
2. user_defined collision_rates: callable rate -> sampled temperature grid
3. destruction_opacity: epsilon = C*n/(A+C*n), mfp_i_abs_line = n_l*sigma*epsilon
4. Full LAMDA CO: collision partners present (pH2 + oH2)
"""

import os, sys
from numpy import isclose, zeros, ones, array, mean

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from molecular.transition_info import TransitionInfo


def test_user_defined_number_rate( ):
    """A constant collision rate builds a 1-transition collision partner."""
    ti = TransitionInfo.user_defined(
        A_ul = 1e-6, freq_GHz = 115.271,
        g_u = 3.0, g_l = 1.0, species_name = 'CO',
        collision_rates = { 'H2': { 'rate': 1e-12 } },
    );
    sd = ti.species;
    assert len( sd.collision_partners ) == 1;
    cp = sd.collision_partners[ 0 ];
    assert cp[ 'species' ] == 'H2';
    assert cp[ 'n_trans' ] == 1;
    #  rates should be shape (n_trans=1, n_temps) - rate-only columns
    assert cp[ 'rates' ].shape[ 1 ] == cp[ 'n_temps' ];
    assert isclose( cp[ 'rates' ][ 0, 0 ], 1e-12 );
    #  trans_indices: [[upper, lower]] = [[1, 0]]
    assert cp[ 'trans_indices' ][ 0, 0 ] == 1;
    assert cp[ 'trans_indices' ][ 0, 1 ] == 0;


def test_user_defined_callable_rate( ):
    """A callable rate is sampled on the temperature grid."""
    def rate_fn( T ):
        return 1e-12 * ( T / 100.0 ) ** 0.5;

    ti = TransitionInfo.user_defined(
        A_ul = 1e-6, freq_GHz = 115.271,
        g_u = 3.0, g_l = 1.0, species_name = 'CO',
        collision_rates = { 'H2': { 'rate': rate_fn } },
    );
    sd = ti.species;
    cp = sd.collision_partners[ 0 ];
    #  Check that the rate at T=100K matches the callable
    from numpy import interp;
    r100 = interp( 100.0, cp[ 'temps' ], cp[ 'rates' ][ 0, : ] );
    assert isclose( r100, 1e-12, rtol = 1e-6 );
    #  And at T=400K
    r400 = interp( 400.0, cp[ 'temps' ], cp[ 'rates' ][ 0, : ] );
    assert isclose( r400, 2e-12, rtol = 1e-6 );


def test_destruction_opacity_epsilon( ):
    """Destruction opacity = n_l * sigma0 * epsilon, epsilon = Cn/(A+Cn)."""
    A_ul = 1e-6;
    ti = TransitionInfo.user_defined(
        A_ul = A_ul, freq_GHz = 115.271,
        g_u = 3.0, g_l = 1.0, species_name = 'CO',
        collision_rates = { 'H2': { 'rate': 3e-12 } },
    );
    sd = ti.species;
    #  Populations: n_total = 1e4, all in ground state (n0=1e4, n1=0)
    pops = { 'n0': array( [ 1e4 ] ), 'n1': array( [ 0.0 ] ),
             'n_total': array( [ 1e4 ] ) };
    colliders = { 'H2': { 'density': array( [ 1e6 ] ) } };
    T = array( [ 100.0 ] );
    sigma0 = sd.cross_section( 0, b_param = 1e5 );

    destr = sd.destruction_opacity(
        pops, transition_idx = 0, b_sca = 1e5,
        T = T, colliders = colliders );
    #  epsilon = C*n / (A + C*n) = 3e-12*1e6 / (1e-6 + 3e-12*1e6)
    #          = 3e-6 / (1e-6 + 3e-6) = 3e-6/4e-6 = 0.75
    eps_expected = 3e-12 * 1e6 / ( A_ul + 3e-12 * 1e6 );
    expected = 1e4 * sigma0 * eps_expected;
    assert isclose( float( destr[ 0 ] ), float( expected ), rtol = 1e-6 ), \
        "destruction_opacity = %e, expected %e" % ( float( destr[ 0 ] ),
                                                     float( expected ) );
    assert isclose( eps_expected, 0.75, rtol = 1e-6 );


def test_destruction_opacity_zero_without_colliders( ):
    """Without colliders, destruction opacity is zero."""
    ti = TransitionInfo.user_defined(
        A_ul = 1e-6, freq_GHz = 115.271,
        g_u = 3.0, g_l = 1.0, species_name = 'CO',
    );
    sd = ti.species;
    pops = { 'n0': array( [ 1e4 ] ), 'n1': array( [ 0.0 ] ),
             'n_total': array( [ 1e4 ] ) };
    destr = sd.destruction_opacity( pops, transition_idx = 0,
                                    b_sca = 1e5, T = None,
                                    colliders = None );
    assert destr[ 0 ] == 0.0;


def test_full_lamda_co_has_collision_partners( ):
    """Full LAMDA CO has 2 collision partners (pH2 + oH2)."""
    from molecular.lamda_fetcher import fetch_species;
    sd = fetch_species( 'co', force_download = True );
    assert len( sd.collision_partners ) >= 2, \
        "Expected >= 2 collision partners, got %d" % \
        len( sd.collision_partners );
    #  Check rates shape: should be (n_trans, n_temps) - rate-only
    cp = sd.collision_partners[ 0 ];
    n_temps = cp[ 'n_temps' ];
    assert cp[ 'rates' ].shape[ 1 ] == n_temps, \
        "rates shape %s, expected (n_trans, %d)" % \
        ( str( cp[ 'rates' ].shape ), n_temps );
