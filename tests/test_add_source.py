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
# vel_range / vel_pdf velocity randomization

def _gen_vel( rt, **src_kw ):
    """Generate photons for one source and return column 7."""
    src_kw.setdefault( 'n_photon', 20000 );
    src_kw.setdefault( 'type', 'slab' );
    if src_kw.get( 'type' ) == 'point':
        src_kw.setdefault( 'position', ( 0, 0, 0 ) );
        src_kw.setdefault( 'luminosity', 1e6 );
    else:
        src_kw.setdefault( 'x', -5 );
        src_kw.setdefault( 'direction', '+x' );
        src_kw.setdefault( 'flux', 1e6 );
    rt.add_source( **src_kw );
    mesh = rt._build_mesh( );
    return rt._generate_one_source( rt._sources[ -1 ], mesh, None );


def test_vel_range_off_by_default( ):
    rt = make_rt( );
    ph = _gen_vel( rt, vel_offset = 2e4 );
    assert np.all( ph[ :, 7 ] == 2e4 ), "default must not randomize";


def test_vel_range_uniform_slab( ):
    rt = make_rt( );
    v_lo, v_hi = -1e5, 1e5;
    ph = _gen_vel( rt, vel_offset = 1e4, \
                   vel_range = ( v_lo, v_hi ) );
    v = ph[ :, 7 ];
    assert v.min( ) >= 1e4 + v_lo - 1.0 and \
           v.max( ) <= 1e4 + v_hi + 1.0, "outside band";
    assert isclose( v.mean( ), 1e4, rel_tol = 0.05 ), \
        "uniform mean should be the midpoint of the band";
    assert np.unique( v ).size > 1000, "no randomization";
    assert ph.shape[ 1 ] == 8, "n_col must stay 8";


def test_vel_range_gaussian_slab( ):
    rt = make_rt( );
    v_lo, v_hi = -3e5, 3e5;
    sigma = 1e5;
    ph = _gen_vel( rt, vel_offset = 0.0, \
                   vel_range = ( v_lo, v_hi ), \
                   vel_pdf = 'gaussian', vel_sigma = sigma );
    v = ph[ :, 7 ];
    assert v.min( ) >= v_lo - 1.0 and v.max( ) <= v_hi + 1.0, \
        "truncated Gaussian must stay in [v_lo, v_hi]";
    assert isclose( v.std( ), sigma, rel_tol = 0.05 ), \
        "std should be vel_sigma";
    assert isclose( v.mean( ), 0.0, abs_tol = 3e3 ), \
        "Gaussian centred on interval midpoint";


def test_vel_range_callable_unnormalized( ):
    rt = make_rt( );
    v_lo, v_hi = -2e5, 2e5;
    def pdf( x ):
        # unnormalized Gaussian, mu=5e4, sigma=4e4
        return 2.5 * np.exp( -( x - 5e4 ) ** 2 / ( 2 * 4e4 ** 2 ) );
    ph = _gen_vel( rt, type = 'point', \
                   vel_range = ( v_lo, v_hi ), vel_pdf = pdf );
    v = ph[ :, 7 ];
    assert v.min( ) >= v_lo - 1.0 and v.max( ) <= v_hi + 1.0;
    assert isclose( v.mean( ), 5e4, rel_tol = 0.1 ), \
        "callable PDF mean should track its peak";
    assert isclose( v.std( ), 4e4, rel_tol = 0.1 ), \
        "callable PDF std should track its width";


def test_vel_range_point( ):
    rt = make_rt( );
    v_lo, v_hi = -5e4, 5e4;
    ph = _gen_vel( rt, type = 'point', \
                   vel_range = ( v_lo, v_hi ) );
    v = ph[ :, 7 ];
    assert v.min( ) >= v_lo - 1.0 and v.max( ) <= v_hi + 1.0;
    assert ph.shape[ 1 ] == 8;


def test_vel_range_validation( ):
    rt = make_rt( );
    # reversed range
    try:
        rt.add_source( type = 'slab', flux = 1e6, \
                       vel_range = ( 1e5, -1e5 ) );
        assert False, "must reject v_lo > v_hi";
    except ValueError:
        pass;
    # bad pdf name
    try:
        rt.add_source( type = 'slab', flux = 1e6, \
                       vel_range = ( -1e5, 1e5 ), vel_pdf = 'trapezoid' );
        assert False, "must reject unknown vel_pdf";
    except ValueError:
        pass;
    # gaussian without vel_sigma
    try:
        rt.add_source( type = 'slab', flux = 1e6, \
                       vel_range = ( -1e5, 1e5 ), \
                       vel_pdf = 'gaussian' );
        assert False, "must require vel_sigma for gaussian";
    except ValueError:
        pass;
    # zero-valued callable over the range
    rt2 = make_rt( );
    rt2.add_source( type = 'slab', flux = 1e6, \
                    vel_range = ( -1e5, 1e5 ), \
                    vel_pdf = lambda x: 0.0 );
    try:
        rt2._generate_one_source( rt2._sources[ -1 ], \
                                  rt2._build_mesh( ), None );
        assert False, "zero PDF over the range must raise";
    except ValueError:
        pass;


def test_show_sources_vel_range( ):
    rt = make_rt( );
    rt.add_source( type = 'slab', flux = 1e6, \
                   vel_offset = 1e4, vel_range = ( -1e5, 1e5 ) );
    rt.add_source( type = 'point', luminosity = 1e30, \
                   vel_range = ( -2e5, 2e5 ), \
                   vel_pdf = 'gaussian', vel_sigma = 5e4 );
    rt.show_sources( );    # must not raise


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
