"""Tests for the memory-saving controls (keep_intermediate, retain_cycles).

- keep_intermediate=False deletes per-cycle files as they are read back,
  keeping the fixed fields file and the final cycle's output.
- retain_cycles=N trims the returned results list to the last N cycles.
- run() removes the auto-created run directory when keep_intermediate=False
  (only for auto-created dirs, never an explicit path).

Pure Python - Kratos is monkeypatched.
"""

import os;
import sys;
import tempfile;

from numpy import zeros, ones, full, float64;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

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


class _FakeKratos:
    """Records photon/field files passed to run_kratos_cycle."""

    def __init__( self, n_tot, n_cycles ):
        self.photon_files = [ ];
        self.n_tot = n_tot;
        self.n_cycles = n_cycles;
        self.calls = 0;

    def __call__( self, work_dir, cycle, field_file, photon_file, \
                  prefix, par_template, par_overrides, kratos_bin = None ):
        self.photon_files.append( photon_file );
        self.calls += 1;
        # Simulate Kratos output that also creates the per-cycle bin/par/log
        for name in ( '%s.par' % prefix, '%s.txt' % prefix, \
                      '%s_00000.bin' % prefix ):
            open( os.path.join( work_dir, name ), 'w' ).close( );
        exc = zeros( self.n_tot, dtype = float64 );
        flx = zeros( self.n_tot, dtype = float64 );
        output = { 'exc_flux_flat' : exc, 'flx' : flx, \
                   'photons' : { 'vel' : zeros( 0 ), \
                                 'x'   : zeros( 0 ), \
                                 'l'   : zeros( 0 ) } };
        return output, '[fake]', 0.01;


def _ext_photons( n = 5 ):
    ext = zeros( ( n, 9 ), dtype = float64 );
    ext[ :, 0 ] = 0.0;   # x
    ext[ :, 3 ] = 1.0;   # dir_x
    ext[ :, 6 ] = 1.0;   # proper
    ext[ :, 7 ] = 0.0;   # vel
    ext[ :, 8 ] = 1e4;   # sv
    return ext;


def test_keep_intermediate_true_keeps_files( ):
    """keep_intermediate=True leaves all per-cycle files intact."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    species = _make_rt_species( );
    fields = _make_fields( mesh, n_species = 1e4 );

    fake = _FakeKratos( n_tot, n_cycles = 3 );
    work_dir = tempfile.mkdtemp( prefix = 'keep_int_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    it_mod.iterate( _ext_photons( ), species, fields, mesh, \
        n_cycles = 3, n_emission_max = 4, work_dir = work_dir, \
        transition_idx = 0, unit_l0 = 1.49598e13, unit_t0 = 1.0, \
        keep_intermediate = True, kratos_root = '/' );

    assert os.path.exists( os.path.join( work_dir, 'fields_fixed.bin' ) );
    for cycle in range( 3 ):
        for f in ( 'fields_cycle%d.bin' % cycle, \
                   'photons_cycle%d.bin' % cycle, \
                   'cycle%d.par' % cycle, 'cycle%d.txt' % cycle, \
                   'cycle%d_00000.bin' % cycle ):
            assert os.path.exists( os.path.join( work_dir, f ) ), \
                "keep_intermediate=True must keep %s" % f;
    print( "OK: keep_intermediate=True kept all per-cycle files" );


def test_keep_intermediate_false_deletes_intermediate( ):
    """keep_intermediate=False removes intermediate cycles but keeps the last."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    species = _make_rt_species( );
    fields = _make_fields( mesh, n_species = 1e4 );

    fake = _FakeKratos( n_tot, n_cycles = 3 );
    work_dir = tempfile.mkdtemp( prefix = 'keep_int_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    it_mod.iterate( _ext_photons( ), species, fields, mesh, \
        n_cycles = 3, n_emission_max = 4, work_dir = work_dir, \
        transition_idx = 0, unit_l0 = 1.49598e13, unit_t0 = 1.0, \
        keep_intermediate = False, kratos_root = '/' );

    assert os.path.exists( os.path.join( work_dir, 'fields_fixed.bin' ) ), \
        "fixed fields file must be kept";
    for cycle in ( 0, 1 ):
        for f in ( 'fields_cycle%d.bin' % cycle, \
                   'photons_cycle%d.bin' % cycle, \
                   'cycle%d.par' % cycle, 'cycle%d.txt' % cycle, \
                   'cycle%d_00000.bin' % cycle ):
            assert not os.path.exists( os.path.join( work_dir, f ) ), \
                "keep_intermediate=False must delete %s" % f;
    for f in ( 'fields_cycle2.bin', 'photons_cycle2.bin', \
               'cycle2.par', 'cycle2.txt', 'cycle2_00000.bin' ):
        assert os.path.exists( os.path.join( work_dir, f ) ), \
            "final cycle output must be kept: %s" % f;
    print( "OK: keep_intermediate=False removed intermediate cycles" );


def test_retain_cycles_trims_results( ):
    """retain_cycles=N keeps only the last N cycle dicts in results."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    species = _make_rt_species( );
    fields = _make_fields( mesh, n_species = 1e4 );

    fake = _FakeKratos( n_tot, n_cycles = 5 );
    work_dir = tempfile.mkdtemp( prefix = 'keep_int_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    results, pops = it_mod.iterate( _ext_photons( ), species, fields, \
        mesh, n_cycles = 5, n_emission_max = 4, work_dir = work_dir, \
        transition_idx = 0, unit_l0 = 1.49598e13, unit_t0 = 1.0, \
        retain_cycles = 2, kratos_root = '/' );

    assert len( results ) == 2, \
        "retain_cycles=2 must trim results to 2, got %d" % len( results );
    assert results[ -1 ][ 'cycle' ] == 4, "last cycle must be retained";
    assert results[ 0 ][ 'cycle' ] == 3, "oldest kept cycle must be cycle 3";
    print( "OK: retain_cycles=2 kept cycles %d..%d" \
           % ( results[ 0 ][ 'cycle' ], results[ -1 ][ 'cycle' ] ) );


def test_stored_flux_float32( ):
    """Stored flx/exc_flux_flat are float32 (Kratos output precision)."""
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    species = _make_rt_species( );
    fields = _make_fields( mesh, n_species = 1e4 );

    fake = _FakeKratos( n_tot, n_cycles = 1 );
    work_dir = tempfile.mkdtemp( prefix = 'keep_int_' );
    it_mod.run_kratos_cycle = fake;
    it_mod.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    results, pops = it_mod.iterate( _ext_photons( ), species, fields, \
        mesh, n_cycles = 1, n_emission_max = 4, work_dir = work_dir, \
        transition_idx = 0, unit_l0 = 1.49598e13, unit_t0 = 1.0, \
        kratos_root = '/' );

    from numpy import float32;
    assert results[ 0 ][ 'flx' ].dtype == float32, \
        "flx must be stored float32, got %s" % results[ 0 ][ 'flx' ].dtype;
    assert results[ 0 ][ 'exc_flux_flat' ].dtype == float32, \
        "exc_flux_flat must be stored float32, got %s" \
        % results[ 0 ][ 'exc_flux_flat' ].dtype;
    print( "OK: stored flx/exc_flux_flat are float32" );


def test_line_rt_run_removes_auto_dir_when_no_keep( ):
    """run() with keep_intermediate=False removes the auto-created dir."""
    from line_rt import LineRt;

    mesh = make_cartesian_mesh( ( 8, 4, 4 ), ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    fake = _FakeKratos( n_tot, n_cycles = 1 );

    # Point LineRt at an auto-style dir under /dev/shm (or /tmp fallback).
    import line_rt as lr_mod;
    import core.pipeline as pipe_mod;
    import core.line_rt as lr_core;
    import core.iterator as it2;

    pipe_mod.run_kratos_cycle = fake;
    it2.run_kratos_cycle = fake;
    it2.resolve_kratos_bin = lambda root = None: '/fake/kratos';
    # Ensure _resolve_path builds under /dev/shm (mock DEFAULT_RUN_ROOT)
    saved_root = pipe_mod.DEFAULT_RUN_ROOT;
    pipe_mod.DEFAULT_RUN_ROOT = tempfile.mkdtemp( prefix = 'auto_root_' );
    it_mod.DEFAULT_RUN_ROOT = pipe_mod.DEFAULT_RUN_ROOT;

    try:
        rt = LineRt(
            n_cell = ( 8, 4, 4 ), x_min = ( -4, -1, -1 ), \
            x_max = ( 4, 1, 1 ), \
            transition_info = TransitionInfo.user_defined( \
                A_ul = 1.0e-6, freq_GHz = 115.271, \
                species_name = 'CO' ), \
            n_species = 1e4, temperature = 2.7, \
            visualize = False, n_cycles = 1, \
            keep_intermediate = False, kratos_root = '/' );

        # Monkeypatch _resolve_path to a known dir we can verify is removed.
        import time
        probe = os.path.join( pipe_mod.DEFAULT_RUN_ROOT, \
                              'rt_probe_%s' % time.strftime( '%H%M%S' ) );
        os.makedirs( probe );
        open( os.path.join( probe, 'fields_fixed.bin' ), 'w' ).close( );
        rt._path = None;
        saved_path = rt._resolve_path;
        rt._resolve_path = lambda: probe;

        out = rt.run( );
        assert not os.path.exists( probe ), \
            "auto run dir must be removed when keep_intermediate=False";
        assert 'run_dir' in out;
    finally:
        pipe_mod.DEFAULT_RUN_ROOT = saved_root;
        it_mod.DEFAULT_RUN_ROOT = saved_root;
        lr_mod = None; lr_core = None;

    print( "OK: run() removed auto-created run dir" );


def test_line_rt_run_keeps_explicit_path( ):
    """run() with keep_intermediate=False leaves an explicit path intact."""
    from line_rt import LineRt;

    mesh = make_cartesian_mesh( ( 8, 4, 4 ), ( -4, -1, -1 ), ( 4, 1, 1 ) );
    n_tot = int( mesh[ 'n_tot' ] );
    fake = _FakeKratos( n_tot, n_cycles = 1 );

    import core.pipeline as pipe_mod;
    import core.iterator as it2;
    pipe_mod.run_kratos_cycle = fake;
    it2.run_kratos_cycle = fake;
    it2.resolve_kratos_bin = lambda root = None: '/fake/kratos';

    explicit = tempfile.mkdtemp( prefix = 'explicit_path_' );

    rt = LineRt(
        n_cell = ( 8, 4, 4 ), x_min = ( -4, -1, -1 ), \
        x_max = ( 4, 1, 1 ), \
        transition_info = TransitionInfo.user_defined( \
            A_ul = 1.0e-6, freq_GHz = 115.271, \
            species_name = 'CO' ), \
        n_species = 1e4, temperature = 2.7, \
        visualize = False, n_cycles = 1, path = explicit, \
        keep_intermediate = False, kratos_root = '/' );

    rt.run( );
    assert os.path.isdir( explicit ), \
        "explicit path must NOT be removed";
    print( "OK: run() left explicit path intact" );


def test_prune_scratch_age_and_size( ):
    """prune_scratch removes old rt_* dirs (age) and over-cap dirs (size)."""
    from core.pipeline import prune_scratch;
    import time as _time;

    base = tempfile.mkdtemp( prefix = 'prune_' );
    try:
        #  two dirs, one > 3h old, one fresh, each holding a small file
        old = os.path.join( base, 'rt_20260801_000000' );
        os.makedirs( old );
        with open( os.path.join( old, 'a.bin' ), 'wb' ) as fh:
            fh.write( b'\0' * 1000 );
        t = _time.time( ) - 4 * 3600;
        os.utime( old, ( t, t ) );

        fresh = os.path.join( base, 'rt_20260803_000000' );
        os.makedirs( fresh );
        with open( os.path.join( fresh, 'b.bin' ), 'wb' ) as fh:
            fh.write( b'\0' * 1000 );
        t = _time.time( ) - 1 * 3600;
        os.utime( fresh, ( t, t ) );

        #  age pruning: only the >3h dir is removed
        n_age, n_size = prune_scratch( max_run_age = 3 * 3600.0, \
                                       size_cap = None, base = base );
        assert n_age == 1 and n_size == 0, \
            "age prune: expected (1,0), got (%d,%d)" % ( n_age, n_size );
        assert not os.path.exists( old );
        assert os.path.isdir( fresh );

        #  size cap: total now 1000 B; cap of 500 must remove the dir
        n_age, n_size = prune_scratch( max_run_age = None, \
                                       size_cap = 500.0, base = base );
        assert n_age == 0 and n_size == 1, \
            "size prune: expected (0,1), got (%d,%d)" % ( n_age, n_size );
        assert not os.path.exists( fresh );
    finally:
        import shutil;
        shutil.rmtree( base, ignore_errors = True );
    print( "OK: prune_scratch age + size pruning" );


def test_line_rt_run_prunes_and_cleans_on_failure( ):
    """Auto-created dirs are pruned at start; a failed run still cleans up."""
    import core.line_rt as lrt_mod;
    import core.iterator as it3;
    import time as _time;
    from line_rt import LineRt;

    base = tempfile.mkdtemp( prefix = 'auto_root_' );
    saved = lrt_mod.DEFAULT_RUN_ROOT;
    lrt_mod.DEFAULT_RUN_ROOT = base;
    try:
        #  a stale >3h dir under the (fake) scratch root
        stale = os.path.join( base, 'rt_20260801_000000' );
        os.makedirs( stale );
        with open( os.path.join( stale, 'a.bin' ), 'wb' ) as fh:
            fh.write( b'\0' * 100 );
        t = _time.time( ) - 4 * 3600;
        os.utime( stale, ( t, t ) );

        #  force iterate to raise -> run() must still remove its own dir
        def _boom( *a, **k ):
            raise RuntimeError( 'boom' );
        it3.run_kratos_cycle = _boom;
        it3.resolve_kratos_bin = lambda root = None: '/fake/kratos';

        rt = LineRt(
            n_cell = ( 8, 4, 4 ), x_min = ( -4, -1, -1 ), \
            x_max = ( 4, 1, 1 ), \
            transition_info = TransitionInfo.user_defined( \
                A_ul = 1.0e-6, freq_GHz = 115.271, \
                species_name = 'CO' ), \
            n_species = 1e4, temperature = 2.7, \
            visualize = False, n_cycles = 1, kratos_root = '/', \
            max_run_age = 3 * 3600.0, size_cap = None );

        try:
            rt.run( );
        except RuntimeError:
            pass;
        else:
            raise AssertionError( "run() should have propagated the error" );

        #  stale dir pruned at start; no auto rt_* dirs left behind
        assert not os.path.exists( stale ), \
            "stale dir must be pruned before the run";
        leftovers = [ n for n in os.listdir( base ) \
                      if n.startswith( 'rt_' ) ];
        assert leftovers == [ ], \
            "failed run must clean up its auto-created dir, left: %s" \
            % leftovers;
    finally:
        import shutil;
        shutil.rmtree( base, ignore_errors = True );
        lrt_mod.DEFAULT_RUN_ROOT = saved;
    print( "OK: run() prunes stale dirs and cleans up on failure" );


if __name__ == '__main__':
    failures = 0;
    total = 0;
    for name, fn in sorted( globals( ).items( ) ):
        if name.startswith( 'test_' ) and callable( fn ):
            total += 1;
            try:
                fn( );
            except Exception as e:
                failures += 1;
                print( "FAIL %s: %s" % ( name, e ) );
            else:
                print( "PASS %s" % name );
    print( "\n%d/%d passed" % ( total - failures, total ) );
