"""Tests for the LineRt.add_source() interface.

Covers the strict flux<->slab / luminosity<->point pairing checks,
the units='photon'/'energy' semantics, and the generated photon
'proper' weights.  Pure Python — no Kratos run required.
"""

import os;
import sys;

from math import isclose;

import numpy as np;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from line_rt import LineRt, TransitionInfo;  # noqa: E402

H_CGS = 6.62607015e-27;
C_CGS = 2.99792458e10;


def make_rt( **kw ):
    """Minimal LineRt with no Kratos run."""
    kw.setdefault( 'b_sca', 1e5 );
    kw.setdefault( 'mfp_i_sca_0', 1e-13 );
    return LineRt( **kw );


def make_rt_species( ):
    """LineRt configured with CO J=1-0 for units='energy' tests."""
    return LineRt(
        transition_info = TransitionInfo( 'CO', 0 ),
        n_species       = 1e4,
        temperature     = 100.0,
    );


############################################################
# Pairing checks (strict)

def test_slab_accepts_flux( ):
    rt = make_rt( );
    rt.add_source( type = 'slab', flux = 1e-3 );
    assert rt._sources[ 0 ][ 'units' ] == 'photon';


def test_slab_rejects_luminosity( ):
    rt = make_rt( );
    try:
        rt.add_source( type = 'slab', luminosity = 1e30 );
        assert False, "expected ValueError";
    except ValueError as e:
        assert 'luminosity' in str( e );
        assert 'slab' in str( e );


def test_slab_requires_flux( ):
    rt = make_rt( );
    try:
        rt.add_source( type = 'slab' );
        assert False, "expected ValueError";
    except ValueError as e:
        assert 'requires flux' in str( e );


def test_point_accepts_luminosity( ):
    rt = make_rt( );
    rt.add_source( type = 'point', luminosity = 1e30 );
    assert rt._sources[ 0 ][ 'units' ] == 'photon';


def test_point_rejects_flux( ):
    rt = make_rt( );
    try:
        rt.add_source( type = 'point', flux = 1e-3 );
        assert False, "expected ValueError";
    except ValueError as e:
        assert 'flux' in str( e );
        assert 'point' in str( e );


def test_point_requires_luminosity( ):
    rt = make_rt( );
    try:
        rt.add_source( type = 'point' );
        assert False, "expected ValueError";
    except ValueError as e:
        assert 'requires luminosity' in str( e );


def test_unknown_type( ):
    rt = make_rt( );
    try:
        rt.add_source( type = 'cyl', flux = 1e-3 );
        assert False, "expected ValueError";
    except ValueError as e:
        assert 'slab' in str( e ) and 'point' in str( e );


############################################################
# Units validation

def test_invalid_units( ):
    rt = make_rt( );
    try:
        rt.add_source( type = 'slab', flux = 1e-3, units = 'erg' );
        assert False, "expected ValueError";
    except ValueError as e:
        assert 'photon' in str( e ) and 'energy' in str( e );


def test_energy_requires_transition( ):
    rt = make_rt( );    # no transition_info
    try:
        rt.add_source( type = 'slab', flux = 1e-3, units = 'energy' );
        assert False, "expected ValueError";
    except ValueError as e:
        assert 'transition' in str( e );


def test_energy_with_transition_ok( ):
    rt = make_rt_species( );
    rt.add_source( type = 'slab', flux = 1e-3, units = 'energy' );
    src = rt._sources[ 0 ];
    assert src[ 'units' ] == 'energy';
    assert src[ 'wavelength' ] is not None;
    assert isclose( src[ 'wavelength' ],
                    C_CGS / ( 115.271e9 ), rel_tol = 1e-6 );


############################################################
# Photon proper-weight conversion

def test_slab_photon_flux_proper( ):
    rt = make_rt( );
    rt.add_source( type = 'slab', n_photon = 100, flux = 2.0 );
    mesh = rt._build_mesh( );
    ph = rt._generate_one_source( rt._sources[ 0 ], mesh, 1e5 );
    # slab full-domain y/z at unit_l0=1.49598e13 cm each.
    area = ( 0.2 - 0.0 ) * ( 0.2 - 0.0 ) * \
           rt._unit_l0 * rt._unit_l0;
    expected = 2.0 * area / 100;
    assert isclose( ph[ :, 6 ].mean( ), expected, rel_tol = 1e-6 );


def test_slab_energy_flux_proper( ):
    rt = make_rt_species( );
    rt.add_source( type = 'slab', n_photon = 100, flux = 2.0, \
                   units = 'energy' );
    mesh = rt._build_mesh( );
    ph = rt._generate_one_source( rt._sources[ 0 ], mesh, 1e5 );
    wl = rt._sources[ 0 ][ 'wavelength' ];
    E_ph = H_CGS * C_CGS / wl;
    area = ( 0.2 - 0.0 ) * ( 0.2 - 0.0 ) * \
           rt._unit_l0 * rt._unit_l0;
    expected = ( 2.0 / E_ph ) * area / 100;
    assert isclose( ph[ :, 6 ].mean( ), expected, rel_tol = 1e-6 );


def test_point_photon_luminosity_proper( ):
    rt = make_rt( );
    rt.add_source( type = 'point', n_photon = 100, luminosity = 5e30 );
    mesh = rt._build_mesh( );
    ph = rt._generate_one_source( rt._sources[ 0 ], mesh, 1e5 );
    assert isclose( ph[ :, 6 ].mean( ), 5e30 / 100, rel_tol = 1e-12 );


def test_point_energy_luminosity_proper( ):
    rt = make_rt_species( );
    rt.add_source( type = 'point', n_photon = 100, luminosity = 5e30, \
                   units = 'energy' );
    mesh = rt._build_mesh( );
    ph = rt._generate_one_source( rt._sources[ 0 ], mesh, 1e5 );
    wl = rt._sources[ 0 ][ 'wavelength' ];
    E_ph = H_CGS * C_CGS / wl;
    assert isclose( ph[ :, 6 ].mean( ), ( 5e30 / E_ph ) / 100, \
                    rel_tol = 1e-12 );


############################################################
# show_sources() smoke test

def test_show_sources( ):
    rt = make_rt_species( );
    rt.add_source( type = 'slab', flux = 1e-3, units = 'energy' );
    rt.add_source( type = 'point', luminosity = 1e30 );
    rt.show_sources( );    # must not raise


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
