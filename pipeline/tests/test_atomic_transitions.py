"""Tests for the embedded atomic species (HI, HeI, HeII) .dat files
and their TransitionInfo integration (mass table, selection, physics).

Physics references (T = 1e4 K):
  Ly alpha:  A(2p->1s)  = 6.265e8 s^-1
             sigma_0    = 5.9e-14 (T/1e4)^-1/2 cm^2  (textbook)
             b_thermal  = 12.87 km/s (m = 1 amu rounding)
  Ly beta:   A(3p->1s)  = 1.672e8 s^-1
  Ly gamma:  A(4p->1s)  = 6.81e7  s^-1
  H alpha:   A(3d->2p)  = 6.465e7 s^-1
  He II Lya: A          = 1.0e10  s^-1 (Z^4 scaling)
"""

import pytest;

from molecular.transition_info import \
    TransitionInfo, MolecularMassError, show_available_species;
from molecular.lamda_format import load_lamda;


# ---------------------------------------------------------------- #
#  Catalog availability
# ---------------------------------------------------------------- #

def test_atomic_species_available( ):
    names = show_available_species( );
    for want in ( 'hi', 'hei', 'heii' ):
        assert want in names;


def test_atomic_dat_parse( ):
    for name in ( 'hi', 'heii', 'hei' ):
        sp = load_lamda( open( 'molecular/embedded/%s.dat' % name
                               ).read( ) );
        assert sp.n_levels >= 2;
        assert sp.n_transitions >= 1;
        assert len( sp.collision_partners ) == 0;
        assert sp.mol_mass is None;   # set by TransitionInfo


# ---------------------------------------------------------------- #
#  Lyman alpha physics (the headline use case)
# ---------------------------------------------------------------- #

TOL = 0.02;   # catalog vs literature: 2%


def test_hi_lya_selection_by_wavelength( ):
    ti = TransitionInfo( 'HI', value = 1215.67, unit = 'angstrom' );
    assert ti.transition[ 2 ] == pytest.approx( 6.265e8, rel = TOL );
    assert ti.transition[ 3 ] == pytest.approx( 2466065.0,
                                                rel = 1e-4 );


def test_hi_lya_selection_by_freq( ):
    ti = TransitionInfo( 'HI', freq_GHz = 2466065.14 );
    ti_w = TransitionInfo( 'HI', value = 1215.67,
                           unit = 'angstrom' );
    assert ti.transition_idx == ti_w.transition_idx;


def test_hi_lya_case_insensitive( ):
    ti = TransitionInfo( 'hi', value = 1215.67, unit = 'angstrom' );
    assert ti.mol_mass == pytest.approx( 1.008 );


def test_hi_lya_cross_section( ):
    """Textbook Ly alpha: sigma_0 = 5.9e-14 (T/1e4)^-1/2 cm^2."""
    ti = TransitionInfo( 'HI', value = 1215.67, unit = 'angstrom' );
    assert ti.cross_section( 1e4 ) == \
        pytest.approx( 5.9e-14, rel = 0.03 );
    assert ti.cross_section( 1e2 ) / ti.cross_section( 1e4 ) == \
        pytest.approx( 10.0, rel = 1e-3 );   # T^-1/2


def test_hi_lya_doppler_b( ):
    """b = sqrt( 2 k T / m ) ~ 12.8 km/s at 1e4 K for 1.008 amu."""
    ti = TransitionInfo( 'HI', value = 1215.67, unit = 'angstrom' );
    assert ti.doppler_b( 1e4 ) / 1e5 == pytest.approx( 12.87,
                                                       rel = 0.02 );
    assert ti.doppler_b( 1e2 ) / ti.doppler_b( 1e4 ) == \
        pytest.approx( 0.1, rel = 1e-3 );    # T^1/2


def test_hi_lya_stat_weights( ):
    """g_u/g_l = 3 (2p g=6 over 1s g=2) -> the classic Ly alpha."""
    ti = TransitionInfo( 'HI', value = 1215.67, unit = 'angstrom' );
    sp = ti.species_data; t = ti.transition;
    assert sp.levels[ t[ 0 ] ][ 1 ] == 6;    # 2p
    assert sp.levels[ t[ 1 ] ][ 1 ] == 2;    # 1s
    assert sp.levels[ t[ 0 ] ][ 0 ] == \
        pytest.approx( 82259.1, rel = 1e-3 );  # 3/4 Ry [cm^-1]


# ---------------------------------------------------------------- #
#  HI catalog rows
# ---------------------------------------------------------------- #

def test_hi_lines_all( ):
    ref = { ( 'Lyb', 1025.723 ): 1.672e8,
            ( 'Lyg', 972.537 ): 6.810e7,
            ( 'Ha', 6564.625 ): 6.465e7,
            ( 'Hb', 4862.685 ): 2.065e7,
            ( 'Hg', 4341.683 ): 9.460e6 };
    for ( name, lam ), a_ref in ref.items( ):
        ti = TransitionInfo( 'HI', value = lam, unit = 'angstrom' );
        assert ti.transition[ 2 ] == pytest.approx( a_ref,
                                                    rel = TOL ), \
            '%s: A=%.3e vs %.3e' % ( name, ti.transition[ 2 ],
                                     a_ref );


# ---------------------------------------------------------------- #
#  He II / He I
# ---------------------------------------------------------------- #

def test_heii_lya( ):
    """He II Ly alpha: A ~ 1e10 s^-1, 303.8 A (Z = 2 hydrogenic)."""
    ti = TransitionInfo( 'HeII', value = 303.8, unit = 'angstrom' );
    assert ti.transition[ 2 ] == pytest.approx( 1.0e10, rel = 0.02 );
    assert ti.mol_mass == pytest.approx( 4.0026 );
    #  hydrogenic scalings at fixed T: A x Z^4, nu x Z^2, b x 1/sqrt(m)
    ti_h = TransitionInfo( 'HI', value = 1215.67, unit = 'angstrom' );
    assert ti.transition[ 2 ] / ti_h.transition[ 2 ] == \
        pytest.approx( 16.0, rel = 0.02 );
    assert ti.doppler_b( 1e4 ) / ti_h.doppler_b( 1e4 ) == \
        pytest.approx( 0.5, rel = 0.01 );    # 4.0026 vs 1.008 amu


def test_hei_584( ):
    ti = TransitionInfo( 'HeI', value = 584.33, unit = 'angstrom' );
    assert ti.transition[ 2 ] == pytest.approx( 1.798e9,
                                                rel = 0.01 );
    assert ti.mol_mass == pytest.approx( 4.0026 );


# ---------------------------------------------------------------- #
#  Guard rails
# ---------------------------------------------------------------- #

def test_unknown_species_raises( ):
    with pytest.raises( FileNotFoundError ):
        TransitionInfo( 'XX', value = 1215.67, unit = 'angstrom' );


def test_user_defined_unknown_mass_raises( ):
    """No more silent 28.0 amu default for unknown species."""
    with pytest.raises( MolecularMassError ):
        TransitionInfo.user_defined( A_ul = 1e8, freq_GHz = 1e6,
                                     species_name = 'zzz' );


def test_user_defined_hi_alias_mass( ):
    ti = TransitionInfo.user_defined( A_ul = 6.265e8,
                                      freq_GHz = 2466065.14,
                                      species_name = 'HI' );
    assert ti.mol_mass == pytest.approx( 1.008 );
