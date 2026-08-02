"""Tests for emission-only mode: running without any external sources.

The pipeline should work without add_source(): if a species (Group 1) is
configured, cycle 0 is seeded with internal emission photons generated
from the initial populations, and subsequent cycles regenerate emission
from the updated populations.  Pure Python - Kratos is monkeypatched.
"""

import os;
import sys;
import tempfile;

from numpy import zeros, ones, full, float64;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from core.consistency import check_consistency, ConsistencyError;  # noqa: E402
from core.pipeline import make_cartesian_mesh;  # noqa: E402
import core.iterator as it_mod;  # noqa: E402
from core.kratos_io import binary_io;  # noqa: E402
from molecular.transition_info import TransitionInfo;  # noqa: E402


def _make_rt_species( ):
    """A real SpeciesData via TransitionInfo.user_defined."""
    return TransitionInfo.user_defined( \
        A_ul = 1.0e-6, freq_GHz = 115.271, \
        species_name = 'CO' ).species_data;


def _make_fields( mesh, n_species ):
    shape = ( int( mesh[ 'n_cell' ][ 2 ] ), \
              int( mesh[ 'n_cell' ][ 1 ] ), \
              int( mesh[ 'n_cell' ][ 0 ] ) );
    b = full( shape, 3.99e3, dtype = float64 );
    temp = full( shape, 2.7, dtype = float64 );
    vel = zeros( shape, dtype = float64 );
    return { 'b_sca'       : b, \
             'temp'        : temp, \
             'vel_0'       : vel, \
             'vel_1'       : vel, \
             'vel_2'       : vel, \
             'mfp_i_sca_0' : full( shape, 1e-9, dtype = float64 ), \
             'mfp_i_abs_0' : zeros( shape, dtype = float64 ) };


def _read_photon_file( path ):
    """Return (n_ph, n_col) from a photon binary via binary_io.

    numpy 2.x rejects the char-code dtypes as_array() builds for int64
    ('<l8'/'<q8'), so read the raw buffers with explicit dtypes here.
    """
    from numpy import frombuffer;
    bio = binary_io( path );
    bio.open( );
    n_col = int( frombuffer( bio[ 'par_n_col' ], dtype = '<i4' )[ 0 ] );
    n_par = int( frombuffer( bio[ 'par_n_par' ], dtype = '<i8' )[ 0 ] );
    dat = frombuffer( bio[ 'par_par_dat' ], dtype = '<f4' );
    return n_par, n_col, dat;


class _FakeKratos:
    """Records photon/field files passed to run_kratos_cycle."""

    def __init__( self, n_tot ):
        self.photon_files = [ ];
        self.n_tot = n_tot;

    def __call__( self, work_dir, cycle, field_file, photon_file, \
                  prefix, par_template, par_overrides, kratos_bin = None ):
        self.photon_files.append( photon_file );
        exc = zeros( self.n_tot, dtype = float64 );
        flx = zeros( self.n_tot, dtype = float64 );
        output = { 'exc_flux_flat' : exc, 'flx' : flx, \
                   'photons' : { 'vel' : zeros( 0 ), \
                                 'x'   : zeros( 0 ), \
                                 'l'   : zeros( 0 ) } };
        return output, '[fake]', 0.01;


def test_check_consistency_species_no_sources_ok( ):
    """Species with no sources passes consistency (emission-only)."""
    info = check_consistency( \
        species = _make_rt_species( ), n_species = 1e4, \
        temperature = 100.0, sources = [ ], mol_mass = 28.0 );
    assert info[ 'group' ] in ( 1, 2 );
    print( "OK: emission-only config passed consistency" );


def test_check_consistency_no_species_no_sources_raises( ):
    """No species and no sources still raises (nothing can emit)."""
    raised = False;
    try:
        check_consistency( species = None, b_sca = 1e5, \
                           mfp_i_sca_0 = 1e-13, sources = [ ], \
                           mol_mass = 28.0 );
    except ConsistencyError:
        raised = True;
    assert raised, "expected ConsistencyError when no species and no sources";
    print( "OK: no-species + no-sources raised ConsistencyError" );


def test_iterate_seeds_cycle0_emission( ):
    """Cycle-0 photon file is populated from internal emission."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    species = _make_rt_species( );
    fields = _make_fields( mesh, n_species = 1e4 );

    fake = _FakeKratos( n_tot );
    work_dir = tempfile.mkdtemp( prefix = 'emission_only_' );

    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    results, pops = it_mod.iterate( \
        zeros( ( 0, 10 ), dtype = float64 ), species, fields, mesh, \
        n_cycles = 1, n_emission_max = 4, work_dir = work_dir, \
        transition_idx = 0, unit_l0 = 1.49598e13, unit_t0 = 1.0, \
        kratos_root = '/' );

    assert len( fake.photon_files ) == 1, "expected one Kratos cycle";
    n_par, n_col, _ = _read_photon_file( fake.photon_files[ 0 ] );
    assert n_par > 0, "cycle-0 photon file must contain emission photons";
    assert n_col == 9, "emission photons must have 9 columns, got %d" % n_col;
    assert len( results ) == 1;
    assert 'emissivity' in results[ 0 ];
    print( "OK: cycle-0 seeded with %d emission photons (%d cols)" \
           % ( n_par, n_col ) );


def test_iterate_no_emission_raises( ):
    """No external sources + zero emissivity raises a clear error."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    species = _make_rt_species( );
    fields = _make_fields( mesh, n_species = 1e4 );
    fields[ 'temp' ] = full( ( 4, 4, 8 ), 0.0, dtype = float64 );

    fake = _FakeKratos( n_tot );
    work_dir = tempfile.mkdtemp( prefix = 'emission_only_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    raised = False;
    try:
        it_mod.iterate( \
            zeros( ( 0, 10 ), dtype = float64 ), species, fields, mesh, \
            n_cycles = 1, n_emission_max = 4, work_dir = work_dir, \
            transition_idx = 0, unit_l0 = 1.49598e13, unit_t0 = 1.0, \
            kratos_root = '/' );
    except ValueError:
        raised = True;
    assert raised, "expected ValueError for zero-emissivity emission-only run";
    print( "OK: zero-emissivity emission-only run raised ValueError" );


def test_iterate_with_external_sources_unchanged( ):
    """External-source runs behave as before (photon file has 9 cols)."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    species = _make_rt_species( );
    fields = _make_fields( mesh, n_species = 1e4 );

    fake = _FakeKratos( n_tot );
    work_dir = tempfile.mkdtemp( prefix = 'emission_only_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    ext = zeros( ( 5, 9 ), dtype = float64 );
    ext[ :, 0 ] = 0.0;   # x
    ext[ :, 3 ] = 1.0;   # dir_x
    ext[ :, 6 ] = 1.0;   # proper
    ext[ :, 7 ] = 0.0;   # vel
    ext[ :, 8 ] = 1e4;   # sv (Gaussian sigma)

    results, pops = it_mod.iterate( \
        ext, species, fields, mesh, \
        n_cycles = 1, n_emission_max = 4, work_dir = work_dir, \
        transition_idx = 0, unit_l0 = 1.49598e13, unit_t0 = 1.0, \
        kratos_root = '/' );

    assert len( fake.photon_files ) == 1;
    n_par, n_col, _ = _read_photon_file( fake.photon_files[ 0 ] );
    assert n_col == 9, "external-source photons keep 9 cols, got %d" % n_col;
    assert n_par >= 5, "external photons must all be present, got %d" % n_par;
    print( "OK: external-source run preserved 9-col photon file (%d)" \
           % n_par );


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
