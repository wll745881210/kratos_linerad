"""Tests for LineRt.plot_input() and LineRt.plot_results().

plot_input() resolves the configured input fields (n_species,
temperature, mfp_i_sca_0, b_sca, mfp_i_abs_0, vel components) at cell
centres without running Kratos, then renders them via default_plot.
plot_results() plots run() output via default_plot.  Pure Python + a
matplotlib Agg figure — no Kratos run required.
"""

import os;
import sys;

import matplotlib;
matplotlib.use( 'Agg' );

import numpy as np;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from line_rt import LineRt, TransitionInfo;  # noqa: E402


def make_rt_group2( **kw ):
    kw.setdefault( 'b_sca', 1e5 );
    kw.setdefault( 'mfp_i_sca_0', 1e-13 );
    kw.setdefault( 'vel', ( 1e5, -2e5, 3e5 ) );
    return LineRt( **kw );


def make_rt_group1( ):
    return LineRt(
        transition_info = TransitionInfo( 'CO', 0 ),
        n_species       = lambda X, Y, Z: 1e4 + 0 * X,
        temperature     = 100.0,
        vel             = ( 1e5, 0.0, 0.0 ),
    );


############################################################
# plot_input: Group 2

def test_plot_input_group2_default_fields( ):
    rt = make_rt_group2( );
    fig, axes = rt.plot_input( );
    assert axes.size >= 5;    # mfp_i_sca_0, b_sca, mfp_i_abs_0, vel_0..2


def test_plot_input_group2_no_vel( ):
    rt = LineRt( b_sca = 1e5, mfp_i_sca_0 = 1e-13 );
    fig, axes = rt.plot_input( );
    assert axes.size >= 3;    # mfp_i_sca_0, b_sca, mfp_i_abs_0


def test_plot_input_group2_explicit_fields( ):
    rt = make_rt_group2( );
    fig, axes = rt.plot_input( fields = [ 'b_sca', 'mfp_i_sca_0' ] );
    assert axes.size >= 2;


def test_plot_input_group2_values( ):
    rt = make_rt_group2( );
    data = rt._plot_input_data( );
    assert np.allclose( data[ 'b_sca' ], 1e5 );
    assert np.allclose( data[ 'mfp_i_sca_0' ], 1e-13 );
    assert np.allclose( data[ 'vel_0' ], 1e5 );


############################################################
# plot_input: Group 1

def test_plot_input_group1_default_fields( ):
    rt = make_rt_group1( );
    fig, axes = rt.plot_input( );
    assert axes.size >= 8;    # n_species, temperature, mfp, b_sca, ... vel


def test_plot_input_group1_values( ):
    rt = make_rt_group1( );
    data = rt._plot_input_data( );
    assert np.allclose( data[ 'n_species' ], 1e4 );
    assert np.allclose( data[ 'temperature' ], 100.0 );
    # b_sca derived from T=100 K and CO mass = sqrt(2 kT / m)
    k = 1.380649e-16;
    m_co = 28.0 * 1.67262192e-24;
    b_exp = np.sqrt( 2.0 * k * 100.0 / m_co );
    assert np.allclose( data[ 'b_sca' ], b_exp );
    assert data[ 'mfp_i_sca_0' ].max( ) > 0;    # opacity > 0 at LTE


def test_plot_input_group1_no_nspecies( ):
    rt = LineRt( transition_info = TransitionInfo( 'CO', 0 ), \
                 temperature = 100.0 );
    fig, axes = rt.plot_input( );    # must not raise; mfp panel "(no data)"


def test_plot_input_output_path( tmpdir = None ):
    import tempfile;
    import os as _os;
    rt = make_rt_group2( );
    d = tmpdir or tempfile.mkdtemp( );
    p = _os.path.join( d, 'input.png' );
    rt.plot_input( output_path = p );
    assert _os.path.exists( p );


############################################################
# plot_results

def test_plot_results_empty_out( ):
    rt = make_rt_group2( );
    out = { 'mesh' : rt._build_mesh( ), 'unit_l0' : 1.0, \
            'unit_t0' : 1.0 };
    fig, axes = rt.plot_results( out );    # must not raise


def test_plot_results_with_fields( ):
    rt = make_rt_group2( );
    mesh = rt._build_mesh( );
    out = { 'mesh' : mesh, 'unit_l0' : 1.0, 'unit_t0' : 1.0, \
            'b_sca' : 1e5 * np.ones( mesh[ 'n_tot' ] ), \
            'mfp_i_sca_0' : 1e-13 * np.ones( mesh[ 'n_tot' ] ) };
    fig, axes = rt.plot_results( out, \
                                 fields = [ 'b_sca', 'mfp_i_sca_0' ] );
    assert axes.size >= 2;


def test_plot_results_cached_out( ):
    rt = make_rt_group2( );
    mesh = rt._build_mesh( );
    rt._results = { 'mesh' : mesh, 'unit_l0' : 1.0, 'unit_t0' : 1.0, \
                    'b_sca' : 1e5 * np.ones( mesh[ 'n_tot' ] ), \
                    'mfp_i_sca_0' : 1e-13 * np.ones( mesh[ 'n_tot' ] ) };
    fig, axes = rt.plot_results( );    # no out -> uses self._results
    assert axes.size >= 2;


def test_plot_results_no_cache( ):
    rt = make_rt_group2( );
    try:
        rt.plot_results( );    # self._results unset -> clear ValueError
        assert False, "expected ValueError";
    except ValueError:
        pass;


if __name__ == '__main__':
    import tempfile;
    import traceback;
    fns = [ v for k, v in sorted( globals( ).items( ) ) \
            if k.startswith( 'test_' ) and callable( v ) ];
    n_fail = 0;
    for fn in fns:
        try:
            fn( tmpdir = tempfile.mkdtemp( ) ) \
                if 'tmpdir' in fn.__code__.co_varnames else fn( );
            print( "PASS %s" % fn.__name__ );
        except Exception:
            n_fail += 1;
            print( "FAIL %s" % fn.__name__ );
            traceback.print_exc( );
    print( "\n%d/%d passed" % ( len( fns ) - n_fail, len( fns ) ) );
    sys.exit( 1 if n_fail else 0 );
