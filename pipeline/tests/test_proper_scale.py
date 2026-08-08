"""Tests for the user-specified photon proper-weight rescale (proper_scale).

Kratos MCRT is linear in photon weights, so scaling all ``proper`` values
by a constant factor scales all output fields (flx, excitation_flux) by
the same amount.  ``proper_scale`` lets the user shrink the weights when
the physical flux is so large that the FP32 output fields would overflow
(>= 3.4e38).  The read-back flux is divided back by the same factor.
Pure Python - Kratos is monkeypatched.
"""

import os;
import sys;
import tempfile;

from numpy import zeros, ones, full, float64, abs, max as np_max;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from core.pipeline import make_cartesian_mesh;  # noqa: E402
from core.kratos_io import write_photon_data, binary_io;  # noqa: E402
import core.iterator as it_mod;  # noqa: E402


def _read_photon_proper( path ):
    """Return the proper column (col 6) read back from a photon binary."""
    from numpy import frombuffer;
    bio = binary_io( path );
    bio.open( );
    dat = frombuffer( bio[ 'par_par_dat' ], dtype = '<f4' );
    n_col = int( frombuffer( bio[ 'par_n_col' ], dtype = '<i4' )[ 0 ] );
    n_par = int( frombuffer( bio[ 'par_n_par' ], dtype = '<i8' )[ 0 ] );
    return dat.reshape( n_par, n_col )[ :, 6 ];


def _write_tmp( photons, proper_scale = 1.0 ):
    path = os.path.join( tempfile.mkdtemp( prefix = 'proper_scale_' ), \
                         'ph.bin' );
    scale = write_photon_data( path, photons, proper_scale = proper_scale );
    return path, scale;


class _FakeKratos:
    """Mimics Kratos linearity: output flux scales with written propers.

    Kratos MCRT is linear in photon proper weights, so if the photon
    weights are multiplied by S, every output field is multiplied by S.
    This fake reads the written photon file's max proper and returns
    flx = flx_true * (max_proper / max_proper_original) so the read-back
    division by scale_factor must restore flx_true.
    """

    def __init__( self, n_tot, flx_true, max_proper_orig, n_esc = 0 ):
        self.n_tot = n_tot;
        self.flx_true = flx_true;
        self.max_proper_orig = max_proper_orig;
        self.n_esc = n_esc;

    def __call__( self, work_dir, cycle, field_file, photon_file, \
                  prefix, par_template, par_overrides, kratos_bin = None ):
        written = _read_photon_proper( photon_file );
        scale = float( np_max( written ) ) / self.max_proper_orig;
        flx_val = self.flx_true * scale;
        esc_proper = full( self.n_esc, written[ 0 ], dtype = float64 );
        output = { 'exc_flux_flat' : zeros( self.n_tot, \
                                            dtype = float64 ), \
                   'flx'           : full( self.n_tot, flx_val, \
                                           dtype = float64 ), \
                   'photons'       : { 'vel'  : full( self.n_esc, 0.0, \
                                                      dtype = float64 ), \
                                       'x'    : zeros( self.n_esc * 3, \
                                                       dtype = float64 ), \
                                       'l'    : esc_proper, \
                                       'proper' : esc_proper.copy( ) } };
        return output, '[fake]', 0.01;


def _base_fields( mesh ):
    shape = ( int( mesh[ 'n_cell' ][ 2 ] ), \
              int( mesh[ 'n_cell' ][ 1 ] ), \
              int( mesh[ 'n_cell' ][ 0 ] ) );
    b = full( shape, 3.99e3, dtype = float64 );
    return { 'b_sca'       : b, \
             'temp'        : full( shape, 2.7, dtype = float64 ), \
             'vel_0'       : zeros( shape, dtype = float64 ), \
             'vel_1'       : zeros( shape, dtype = float64 ), \
             'vel_2'       : zeros( shape, dtype = float64 ), \
             'mfp_i_sca_0' : full( shape, 1e-9, dtype = float64 ), \
             'mfp_i_abs_0' : zeros( shape, dtype = float64 ) };


def test_write_proper_scale_applied( ):
    """write_photon_data scales proper by proper_scale and returns it."""
    ph = zeros( ( 4, 9 ), dtype = float64 );
    ph[ :, 6 ] = 1e30;                      # huge weight (would overflow)
    path, scale = _write_tmp( ph, proper_scale = 1e-20 );
    assert scale == 1e-20, "returned scale should equal proper_scale";
    proper = _read_photon_proper( path );
    assert np_max( proper ) == 1e10, \
        "proper should be scaled by 1e-20, got %g" % np_max( proper );
    print( "OK: proper scaled 1e30 -> %.1f, scale=%.1e" \
           % ( np_max( proper ), scale ) );


def test_write_proper_scale_default_noop( ):
    """Default proper_scale=1.0 leaves proper unchanged."""
    ph = zeros( ( 4, 9 ), dtype = float64 );
    ph[ :, 6 ] = 42.0;
    path, scale = _write_tmp( ph );
    assert scale == 1.0;
    proper = _read_photon_proper( path );
    assert np_max( proper ) == 42.0, "proper must be unchanged";
    print( "OK: default proper_scale=1.0 is a no-op" );


def test_write_proper_scale_rejects_nonpositive( ):
    """proper_scale <= 0 raises ValueError."""
    ph = zeros( ( 2, 7 ), dtype = float64 );
    ph[ :, 6 ] = 1.0;
    raised = False;
    try:
        _write_tmp( ph, proper_scale = 0.0 );
    except ValueError:
        raised = True;
    assert raised, "proper_scale=0 must raise";
    raised = False;
    try:
        _write_tmp( ph, proper_scale = -1.0 );
    except ValueError:
        raised = True;
    assert raised, "proper_scale<0 must raise";
    print( "OK: proper_scale<=0 raised ValueError" );


def test_iterate_readback_undoes_proper_scale( ):
    """iterate() divides the read-back flux by proper_scale."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    fields = _base_fields( mesh );

    ext = zeros( ( 5, 9 ), dtype = float64 );
    ext[ :, 0 ] = 0.0;   # x
    ext[ :, 3 ] = 1.0;   # dir_x
    ext[ :, 6 ] = 1.0;   # proper
    ext[ :, 7 ] = 0.0;   # vel
    ext[ :, 8 ] = 1e4;   # sv

    flx_true = 3.14e30;   # a flux that would overflow FP32 (>= 3.4e38)
    fake = _FakeKratos( n_tot, flx_true = flx_true, max_proper_orig = 1.0 );
    work_dir = tempfile.mkdtemp( prefix = 'proper_scale_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    # Without proper_scale the read-back flx would equal flx_true (in
    # code units); with a rescale it must come back identical.
    for ps in ( 1.0, 1e-30 ):
        results, pops = it_mod.iterate( \
            ext.copy( ), None, fields, mesh, \
            n_cycles = 1, work_dir = work_dir, \
            transition_idx = 0, unit_l0 = 1.49598e13, \
            unit_t0 = 1.0, kratos_root = '/', proper_scale = ps );
        flx = results[ 0 ].get( 'flx' );
        assert flx is not None, "flx missing from output";
        flx_cgs = flx[ 0 ] * ( 1.49598e13 ** 2 ) * 1.0;
        assert abs( flx_cgs - flx_true ) < 1e-6 * flx_true, \
            "flx not restored: ps=%g got %g want %g" \
            % ( ps, flx_cgs, flx_true );
    print( "OK: read-back flx identical for proper_scale in {1, 1e-30}" );


def test_line_rt_ctor_accepts_proper_scale( ):
    """LineRt stores proper_scale and hands it to iterate()."""
    from core.line_rt import LineRt;  # noqa: E402
    rt = LineRt( proper_scale = 1e-25, kratos_root = '/' );
    assert rt._proper_scale == 1e-25, "proper_scale not stored";
    print( "OK: LineRt stores proper_scale = %.1e" % rt._proper_scale );


def test_escaped_proper_is_weight_not_length( ):
    """iterate() must NOT multiply escaped proper by unit_l0."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    fields = _base_fields( mesh );

    ext = zeros( ( 5, 9 ), dtype = float64 );
    ext[ :, 0 ] = 0.0;
    ext[ :, 3 ] = 1.0;
    ext[ :, 6 ] = 1.0;
    ext[ :, 7 ] = 0.0;
    ext[ :, 8 ] = 1e4;

    fake = _FakeKratos( n_tot, flx_true = 1.0, max_proper_orig = 1.0, \
                        n_esc = 3 );
    work_dir = tempfile.mkdtemp( prefix = 'proper_scale_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    results, pops = it_mod.iterate( \
        ext.copy( ), None, fields, mesh, n_cycles = 1, \
        work_dir = work_dir, transition_idx = 0, \
        unit_l0 = 1.49598e13, unit_t0 = 1.0, kratos_root = '/' );

    phot = results[ 0 ][ 'photons' ];
    assert 'proper' in phot, "escaped photons must carry 'proper'";
    prop = phot[ 'proper' ];
    assert prop[ 0 ] == 1.0, \
        "escaped proper must be the weight (1.0), got %g" % prop[ 0 ];
    assert prop[ 0 ] != 1.49598e13, \
        "escaped proper must NOT be multiplied by unit_l0";
    assert phot.get( 'l' ) is not None, "'l' alias must remain";
    assert phot[ 'l' ][ 0 ] == prop[ 0 ], "'l' alias must equal proper";
    print( "OK: escaped proper kept as weight (not scaled by unit_l0)" );


def test_escaped_proper_undoes_proper_scale( ):
    """iterate() divides escaped proper back by the applied proper_scale."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    fields = _base_fields( mesh );

    ext = zeros( ( 5, 9 ), dtype = float64 );
    ext[ :, 0 ] = 0.0;
    ext[ :, 3 ] = 1.0;
    ext[ :, 6 ] = 1.0;
    ext[ :, 7 ] = 0.0;
    ext[ :, 8 ] = 1e4;

    fake = _FakeKratos( n_tot, flx_true = 1.0, max_proper_orig = 1.0, \
                        n_esc = 3 );
    work_dir = tempfile.mkdtemp( prefix = 'proper_scale_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    # proper_scale=1e-20: written proper = 1e-20, escaped must come back 1.0.
    results, pops = it_mod.iterate( \
        ext.copy( ), None, fields, mesh, n_cycles = 1, \
        work_dir = work_dir, transition_idx = 0, \
        unit_l0 = 1.49598e13, unit_t0 = 1.0, \
        kratos_root = '/', proper_scale = 1e-20 );

    phot = results[ 0 ][ 'photons' ];
    prop = phot[ 'proper' ];
    assert abs( prop[ 0 ] - 1.0 ) < 1e-6, \
        "escaped proper must be restored after proper_scale undo, got %g" \
        % prop[ 0 ];
    print( "OK: escaped proper restored to 1.0 after proper_scale=1e-20" );


if __name__ == '__main__':
    failures = 0;
    for name, fn in sorted( globals( ).items( ) ):
        if name.startswith( 'test_' ) and callable( fn ):
            try:
                fn( );
            except Exception as e:
                failures += 1;
                print( "FAIL %s: %s" % ( name, e ) );
            else:
                print( "PASS %s" % name );
    print( "\n%d/%d passed" % ( sum( 1 for n in globals( ) \
        if n.startswith( 'test_' ) and callable( globals( )[ n ] ) ) \
        - failures, \
        sum( 1 for n in globals( ) if n.startswith( 'test_' ) \
             and callable( globals( )[ n ] ) ) ) );
    sys.exit( 1 if failures else 0 );
