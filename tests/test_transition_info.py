############################################################
# Smoke test for molecular/transition_info.py
#
#  Run:  python3 tests/test_transition_info.py

import os;
import sys;

_PROJECT = os.path.dirname( os.path.dirname( os.path.realpath( __file__ ) ) );
if _PROJECT not in sys.path:
    sys.path.insert( 0, _PROJECT );

from molecular.transition_info import TransitionInfo, \
    MolecularMassError, show_available_species, \
    show_available_transitions;

_N_PASS = [ 0 ];
_N_FAIL = [ 0 ];

def _check( name, cond, detail = '' ):
    if cond:
        _N_PASS[ 0 ] += 1;
        print( '  PASS  %s' % name );
    else:
        _N_FAIL[ 0 ] += 1;
        print( '  FAIL  %s  %s' % ( name, detail ) );

def _raises( name, exc_type, fn ):
    try:
        fn( );
        _check( name, False, 'no exception raised' );
    except exc_type:
        _check( name, True );
    except Exception as e:
        _check( name, False, 'wrong exception: %s' % type( e ).__name__ );

############################################################
# Catalog queries

def test_catalog( ):
    print( 'test_catalog' );
    names = show_available_species( );
    _check( 'embedded CO listed', 'co' in names );
    _check( 'embedded OH listed', 'oh' in names );
    show_available_transitions( 'CO' );

############################################################
# Transition resolution by index and by physical quantity

def test_transition_by_index( ):
    print( 'test_transition_by_index' );
    ti = TransitionInfo( 'CO', 0 );
    _check( 'name', ti.species_data.name == 'CO' );
    _check( 'idx', ti.transition_idx == 0 );
    _check( 'upper/lower', ( ti.transition.upper, ti.transition.lower ) == ( 1, 0 ) );
    _check( 'A_ul', abs( ti.transition.A_ul - 7.2e-8 ) < 1e-10 );
    _check( 'freq', abs( ti.transition.freq_GHz - 115.271 ) < 1e-3 );
    _check( 'mol_mass auto', ti.mol_mass == 28.0 );
    _check( 'mol_mass source', ti._mol_mass_source == 'built-in table' );
    ti.show_transition( );
    ti.show( );

def test_transition_by_freq( ):
    print( 'test_transition_by_freq' );
    ti = TransitionInfo( 'CO', freq_GHz = 230.538 );
    _check( 'freq alias idx', ti.transition_idx == 1 );
    _check( 'freq alias upper/lower', \
            ( ti.transition.upper, ti.transition.lower ) == ( 2, 1 ) );

def test_transition_by_value_unit( ):
    print( 'test_transition_by_value_unit' );
    specs = [ ( 115.271, 'GHz' ), ( 0.115271, 'THz' ), \
              ( 0.2600, 'cm' ), ( 2.600, 'mm' ), ( 2600.0, 'um' ), \
              ( 2.6008e6, 'nm' ), ( 2.6008e7, 'angstrom' ), \
              ( 4.766e-4, 'eV' ), ( 7.638e-16, 'erg' ) ];
    for value, unit in specs:
        ti = TransitionInfo( 'CO', value = value, unit = unit );
        _check( 'spec %g %s' % ( value, unit ), ti.transition_idx == 0 );

############################################################
# Error paths

def test_errors( ):
    print( 'test_errors' );
    _raises( 'unknown species', FileNotFoundError, \
             lambda: TransitionInfo( 'XYZ' ) );
    _raises( 'unknown mass', MolecularMassError, \
             lambda: TransitionInfo( 'oi' ) );
    _raises( 'unknown unit', ValueError, \
             lambda: TransitionInfo( 'CO', value = 1.0, unit = 'furlong' ) );
    _raises( 'unit required', ValueError, \
             lambda: TransitionInfo( 'CO', value = 115.271 ) );
    _raises( 'value and freq_GHz', ValueError, \
             lambda: TransitionInfo( 'CO', value = 115.271, unit = 'GHz', \
                                     freq_GHz = 115.271 ) );
    _raises( 'out-of-range idx', ValueError, \
             lambda: TransitionInfo( 'CO', transition_idx = 99 ) );

def test_explicit_mass( ):
    print( 'test_explicit_mass' );
    ti = TransitionInfo( 'oi', mol_mass = 16.0 );
    _check( 'explicit mass', ti.mol_mass == 16.0 );
    _check( 'explicit source', ti._mol_mass_source == 'explicit' );

############################################################
# Main

def main( ):
    test_catalog( );
    test_transition_by_index( );
    test_transition_by_freq( );
    test_transition_by_value_unit( );
    test_errors( );
    test_explicit_mass( );
    print( '' );
    print( 'PASS: %d, FAIL: %d' % ( _N_PASS[ 0 ], _N_FAIL[ 0 ] ) );
    return 0 if _N_FAIL[ 0 ] == 0 else 1;

if __name__ == '__main__':
    sys.exit( main( ) );
