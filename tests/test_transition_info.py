"""Tests for TransitionInfo.user_defined( ... ) - user-defined transitions.

Covers building a TransitionInfo for a transition that is NOT in the
LAMDA database, from physical transition parameters (A_ul, frequency,
g_u/g_l, E_u) plus an optional species name / molecular mass.  Pure
Python - no Kratos run needed.
"""

import os;
import sys;
import warnings;

from math import isclose;

from typing import Any;

import numpy as np;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from molecular.transition_info import TransitionInfo, \
                                      MolecularMassError;  # noqa: E402

H_CGS = 6.62607015e-27;    # erg s
K_B   = 1.380649e-16;      # erg / K


def make_ti( A_ul: float = 1e-6, freq_GHz: float | None = 115.271, \
             value: float | None = None, unit: str | None = None, \
             g_u: float = 1.0, g_l: float = 1.0, \
             E_u_K: float | None = None, mol_mass: float | None = None, \
             species_name: str = 'CO' ):
    """Build a user-defined TransitionInfo with CO-like defaults."""
    kw: dict[ str, Any ] = dict( A_ul = A_ul, g_u = g_u, g_l = g_l, \
                                 species_name = species_name );
    if value is not None:
        kw[ 'value' ] = value;
        kw[ 'unit' ] = unit;
    elif freq_GHz is not None:
        kw[ 'freq_GHz' ] = freq_GHz;
    if E_u_K is not None:
        kw[ 'E_u_K' ] = E_u_K;
    if mol_mass is not None:
        kw[ 'mol_mass' ] = mol_mass;
    return TransitionInfo.user_defined( **kw );


############################################################
# Parameter propagation

def test_basic_propagation( ):
    """A_ul, freq, wavelength and E_u propagate onto the transition."""
    ti = make_ti( );
    tr = ti.transition;
    assert isclose( tr.A_ul, 1e-6, rel_tol = 1e-12 );
    assert isclose( tr.freq_GHz, 115.271, rel_tol = 1e-12 );
    assert isclose( tr.wavelength_um, 299792.458 / 115.271, \
                    rel_tol = 1e-9 );
    assert isclose( tr.E_u_K, H_CGS * 115.271e9 / K_B, rel_tol = 1e-9 );


def test_default_E_u_is_photon_energy( ):
    """Without E_u_K the upper-level energy is h*nu/k_B above ground."""
    ti = make_ti( );
    levels = ti._species_data.levels;
    assert isclose( levels[ 0, 0 ], 0.0 );
    assert isclose( levels[ 1, 0 ], H_CGS * 115.271e9 / K_B, \
                    rel_tol = 1e-9 );


def test_explicit_E_u_K( ):
    """An explicit E_u_K overrides the photon-energy default."""
    ti = make_ti( E_u_K = 500.0 );
    assert isclose( ti._species_data.levels[ 1, 0 ], 500.0, \
                    rel_tol = 1e-12 );


def test_default_weights_are_one( ):
    """g_u = g_l = 1 by default."""
    ti = make_ti( );
    levels = ti._species_data.levels;
    assert isclose( levels[ 0, 1 ], 1.0 );
    assert isclose( levels[ 1, 1 ], 1.0 );


def test_custom_weights( ):
    """g_u and g_l are honoured when given."""
    ti = make_ti( g_u = 3.0, g_l = 1.0 );
    levels = ti._species_data.levels;
    assert isclose( levels[ 1, 1 ], 3.0 );
    assert isclose( levels[ 0, 1 ], 1.0 );


############################################################
# Frequency specification variants

def test_value_unit_wavelength( ):
    """(value, unit) wavelength form matches freq_GHz."""
    ti = make_ti( value = 2600.762, unit = 'um' );
    assert isclose( ti.transition.freq_GHz, 115.271, rel_tol = 1e-4 );


def test_value_unit_energy( ):
    """(value, unit) eV photon-energy form resolves a frequency."""
    ti = make_ti( value = 4.77e-4, unit = 'eV' );
    assert ti.transition.freq_GHz > 0;
    assert isclose( ti.transition.E_u_K, H_CGS * \
                    ti.transition.freq_GHz * 1e9 / K_B, rel_tol = 1e-9 );


def test_freq_GHz_and_value_mutually_exclusive( ):
    with np.testing.assert_raises( ValueError ):
        TransitionInfo.user_defined( A_ul = 1e-6, value = 2600.762, \
                                     unit = 'um', freq_GHz = 115.271, \
                                     species_name = 'CO' );


def test_missing_frequency_raises( ):
    with np.testing.assert_raises( ValueError ):
        make_ti( freq_GHz = None );


def test_value_without_unit_raises( ):
    with np.testing.assert_raises( ValueError ):
        make_ti( value = 2600.762 );


def test_nonpositive_A_ul_raises( ):
    with np.testing.assert_raises( ValueError ):
        make_ti( A_ul = 0.0 );


############################################################
# Molecular mass resolution

def test_mass_from_builtin_table( ):
    """species_name='CO' resolves the molecular mass automatically."""
    ti = make_ti( species_name = 'CO' );
    assert ti.mol_mass == 28.0;
    assert ti._mol_mass_source == 'built-in table';


def test_mass_from_table_with_explicit_override( ):
    """An explicit mol_mass overrides the built-in table."""
    ti = make_ti( species_name = 'CO', mol_mass = 30.0 );
    assert ti.mol_mass == 30.0;
    assert ti._mol_mass_source == 'explicit';


def test_unknown_name_requires_mol_mass( ):
    """An unknown species_name needs an explicit mol_mass."""
    with np.testing.assert_raises( MolecularMassError ):
        make_ti( species_name = 'bogus_molecule' );


def test_unknown_name_with_mol_mass_ok( ):
    """Unknown name + explicit mol_mass builds fine."""
    ti = make_ti( species_name = 'bogus_molecule', mol_mass = 28.0 );
    assert ti.mol_mass == 28.0;
    assert ti.species == 'bogus_molecule' or \
           ti.species_data.name == 'bogus_molecule';


############################################################
# Derived physics

def test_cross_section_and_doppler_b( ):
    """sigma_0 and b_sca are computable from the synthetic species."""
    ti = make_ti( );
    b = ti.doppler_b( 100.0 );
    assert b > 0;
    assert isclose( b, np.sqrt( 2.0 * K_B * 100.0 / ( 28.0 * 1.67262192e-24 ) ), \
                    rel_tol = 1e-6 );
    sig = ti.cross_section( 100.0 );
    assert sig > 0;


############################################################
# Deprecation of the old helper

def test_make_synthetic_2level_deprecated( ):
    """make_synthetic_2level emits a DeprecationWarning."""
    from molecular.synthetic_molecule import make_synthetic_2level;
    with warnings.catch_warnings( record = True ) as caught:
        warnings.simplefilter( 'always' );
        make_synthetic_2level( b = 1e5, nu = 115.271e9, a = 1e-3 );
    assert any( issubclass( w.category, DeprecationWarning ) \
                for w in caught ), 'no DeprecationWarning emitted';


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
