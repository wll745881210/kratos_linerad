#!/usr/bin/env python3
"""
Kratos-based population-updating radiative transfer pipeline.

Key insight from mc_ph:
  excitation_flux -> excited population -> updated opacity -> next RT cycle

Flow:
  1. Generate initial field + photon files
  2. Run Kratos(line_rt)
  3. Read output (flx + excitation_flux)
  4. Update populations from excitation_flux
  5. Generate new field + photon files
  6. Repeat until convergence
"""

import subprocess, sys, os, time

from .kratos_io import \
    ( write_field_data, write_photon_data, read_output, \
      write_par_file );

from numpy import asarray, int32, float32, float64, nan_to_num

#  Kratos binary location is NOT hardcoded.  Set it via:
#    - environment variable  KRATOS_ROOT=/path/to/build/tree
#    - LineRt(kratos_root=...) / iterate(kratos_root=...) kwarg
#  The build tree must contain bin/kratos.
_PAR_TEMPLATE = os.path.join( os.path.dirname( __file__ ), \
                              'line_rt_pipeline.par' );


def resolve_kratos_bin( kratos_root = None ):
    """Resolve the Kratos binary path and validate it exists.

    Resolution order:
      1. ``kratos_root`` argument (a directory or full bin path)
      2. ``KRATOS_ROOT`` environment variable

    There is NO default - you must set one of the above.  The build
    tree must contain ``bin/kratos``.

    Parameters
    ----------
    kratos_root : str or None
        Path to the Kratos build tree root (containing ``bin/kratos``)
        or directly to the ``kratos`` binary.  If None, falls back to
        the ``KRATOS_ROOT`` env var.

    Returns
    -------
    str
        Absolute path to the ``kratos`` binary.

    Raises
    ------
    FileNotFoundError
        If the binary cannot be found, or if neither ``kratos_root``
        nor ``KRATOS_ROOT`` is set.
    """
    if kratos_root is None:
        kratos_root = os.environ.get( 'KRATOS_ROOT' );
    if kratos_root is None:
        raise FileNotFoundError(
            "Kratos root not set.  Set it via one of:\n"
            "  Python:    rt = LineRt( kratos_root='/path/to/kratos_line_rt' )\n"
            "  Notebook:  %env KRATOS_ROOT /path/to/kratos_line_rt\n"
            "  Shell:     export KRATOS_ROOT=/path/to/kratos_line_rt\n"
            "The path must contain bin/kratos (the compiled binary)." );
    kratos_root = os.path.expanduser( kratos_root );

    #  Accept either the build-tree root or the binary path itself.
    if os.path.basename( kratos_root ) == 'kratos' \
       and os.path.isfile( kratos_root ):
        return kratos_root;
    kratos_bin = os.path.join( kratos_root, 'bin', 'kratos' );

    if not os.path.isfile( kratos_bin ):
        msg = (
            "Kratos binary not found at: %s\n"
            "Set the build tree root via one of:\n"
            "  Python:    rt = LineRt( kratos_root='/path/to/kratos_line_rt' )\n"
            "  Notebook:  %%env KRATOS_ROOT /path/to/kratos_line_rt\n"
            "  Shell:     export KRATOS_ROOT=/path/to/kratos_line_rt\n"
            "The path must contain bin/kratos (the compiled binary)."
        ) % kratos_bin;
        raise FileNotFoundError( msg );
    return kratos_bin;



class PopulationModel:
    """
    Abstract base: maps population arrays to Kratos fields and back.

    Each derived class defines:
      - initial_populations() -> dict of arrays
      - make_fields(populations, step, cycle) -> dict of field arrays
      - update_populations(exc_flux, flx, populations, cycle)
        -> dict of arrays
      - generate_photons(populations, mesh, cycle) -> ndarray
    """

    def initial_populations( self, n_species ):
        raise NotImplementedError;

    def make_fields( self, populations, step, cycle ):
        raise NotImplementedError;

    def update_populations( self, exc_flux, flx, populations, cycle ):
        raise NotImplementedError;

    def generate_photons( self, populations, mesh, cycle ):
        raise NotImplementedError;


def make_cartesian_mesh( n_cell, x_min, x_max ):
    """
    Create a uniform Cartesian mesh dictionary.
    """
    n_cell = asarray( n_cell, dtype = int32   );
    x_min  = asarray( x_min,  dtype = float32 );
    x_max  = asarray( x_max,  dtype = float32 );
    dx     = ( x_max - x_min ) / n_cell.astype( float32 );
    return { 'n_cell': n_cell, 'x_min': x_min, 'dx': dx, \
             'n_tot': int( n_cell.prod( ) ) };


def run_kratos_cycle( work_dir, cycle, field_file, photon_file, \
                      prefix, par_template, par_overrides, \
                      kratos_bin = None ):
    """
    Run one Kratos cycle.

    Parameters
    ----------
    kratos_bin : str or None
        Path to the Kratos binary.  If None, resolved via
        resolve_kratos_bin() (KRATOS_ROOT env var or default).

    Returns
    -------
    output : dict from read_output()
    log_text : str
    elapsed : float
    """
    par_path = os.path.join( work_dir, '%s.par' % prefix );
    log_path = os.path.join( work_dir, '%s.txt' % prefix );

    overrides = dict( par_overrides );
    overrides.update( { 'field_file':    field_file, \
                        'photon_file':   photon_file, \
                        'prefix_output': prefix } );

    write_par_file( par_path, par_template, overrides );

    if kratos_bin is None:
        kratos_bin = resolve_kratos_bin( );
    t0 = time.time( );
    result = subprocess.run \
        ( [ kratos_bin, par_path ],
          stdout = subprocess.PIPE, stderr = subprocess.STDOUT,
          timeout = 3600, cwd = work_dir );
    elapsed = time.time( ) - t0;
    log_text = result.stdout.decode( 'utf-8', errors = 'replace' );

    if  result.returncode != 0:
        print( '[cycle %d] Kratos FAILED after %.0fs' \
               % ( cycle, elapsed ) );
        print( log_text[ -500: ] );
        return None, log_text, elapsed;
    #

    out_bin = os.path.join( work_dir, '%s_00000.bin' % prefix );
    if  not os.path.exists( out_bin ):
        print( '[cycle %d] No output file: %s' % ( cycle, out_bin ) );
        return None, log_text, elapsed;
    #

    output = read_output( out_bin );
    output[ '_bin_path' ] = out_bin;
    output[ '_log' ]      = log_text;
    output[ '_elapsed' ]  = elapsed;

    print( '[cycle %d] Done in %.0fs, bin=%s' \
           % ( cycle, elapsed, os.path.basename( out_bin ) ) );
    return output, log_text, elapsed;


def run_pipeline( model, mesh, work_dir = None, n_cycles = 3, \
                  n_photon = 10000, n_step = 1000, n_scat = 100, \
                  n_fld = 2, ph_mode = 0, par_overrides = None, \
                  keep_intermediate = True, \
                  unit_l0 = 1.0, unit_t0 = 1.0, kratos_root = None ):
    """
    Run the full population-updating pipeline.

    Parameters
    ----------
    model : PopulationModel
    mesh : dict from make_cartesian_mesh()
    work_dir : str
        Output directory.  If None, a per-run subdir under
        /tmp/line_rt/ is created.
    n_cycles : int
    n_photon : int
    n_step, n_scat : int
    n_fld : int  Number of flux/field components
    ph_mode : int  0=CFR, 1=R_IIA (USampler)
    par_overrides : dict  Additional par file overrides
    unit_l0 : float  code length unit in CGS (cm per code-length)
    unit_t0 : float  code time unit in CGS (s per code-time)
    kratos_root : str or None
        Path to the Kratos build tree root (containing ``bin/kratos``).
        If None, falls back to ``KRATOS_ROOT`` env var, then the
        default ``~/apps/kratos_line_rt``.

    Returns
    -------
    results : list of dicts (one per cycle)
    final_populations : dict
    """
    if  work_dir is None:
        work_dir = os.path.join( '/tmp/line_rt', \
            'run_%s' % time.strftime( '%Y%m%d_%H%M%S' ) );
    #
    os.makedirs( work_dir, exist_ok = True );
    print( '[run_pipeline] Run directory: %s' % ( work_dir ) );
    n_tot = mesh[ 'n_tot' ];

    if  par_overrides is None:
        par_overrides = dict(   );
    #

    base_overrides = {
        'n_cell_global': ' '.join( str( v ) for v in mesh[ 'n_cell' ] ),
        'x_min':         ' '.join( str( v ) for v in mesh[ 'x_min' ] ),
        'x_max':         ' '.join( \
            str( mesh[ 'x_min' ][ i ] + mesh[ 'dx' ][ i ] * \
                 mesh[ 'n_cell' ][ i ] ) for i in range( 3 ) ),
        'n_step':        str( n_step ),
        'n_scat':        str( n_scat ),
        'n_photon':      str( n_photon ),
        'ph_mode':       str( ph_mode ),
        'n_fld':         str( n_fld ),
        'n_cycle_lim':   '0',
        't_output_next': '1e32',
        'dt_output':     '1e32',
        'final_output':  '1',
    };
    base_overrides.update( par_overrides );

    populations = model.initial_populations( n_tot );
    results = [ ];

    # Write line-independent fields (b_sca, vel) ONCE - they
    # depend only on the gas, not the selected line/band.
    fields0 = model.make_fields( populations, step = 'pre', \
                                 cycle = 0 );
    fixed_fields = { k: v for k, v in fields0.items( ) \
                     if k in ( 'b_sca', 'vel_0', 'vel_1', 'vel_2', \
                               'temp' ) };
    fixed_file = os.path.join( work_dir, 'fields_fixed.bin' );
    write_field_data( fixed_file, fixed_fields, mesh, \
                      unit_l0 = unit_l0, group = 'fixed' );
    base_overrides[ 'field_fixed_file' ] = 'fields_fixed.bin';

    for cycle in range( n_cycles ):
        print( '\n=== Cycle %d / %d ===' % ( cycle, n_cycles ) );

        # Generate line-dependent fields (mfp_i_sca_0, mfp_i_abs_0)
        fields = model.make_fields( populations, step = 'pre', \
                                    cycle = cycle );
        line_fields = { k: v for k, v in fields.items( ) \
                        if k in ( 'mfp_i_sca_0', 'mfp_i_abs_0' ) };
        field_file = os.path.join( work_dir, \
                                   'fields_cycle%d.bin' % cycle );
        write_field_data( field_file, line_fields, mesh, \
                          unit_l0 = unit_l0, group = 'line' );

        # Write photon binary and capture proper-weight scale factor
        photons = model.generate_photons( populations, mesh, cycle );
        photon_file = os.path.join( work_dir, \
                                    'photons_cycle%d.bin' % cycle );
        scale = write_photon_data( photon_file, photons );

        # Run Kratos
        prefix = 'cycle%d' % cycle;
        output, log_text, elapsed = run_kratos_cycle \
            ( work_dir, cycle, field_file, photon_file, \
              prefix, _PAR_TEMPLATE, base_overrides, \
              kratos_bin = resolve_kratos_bin( kratos_root ) );

        if  output is None:
            print( 'Pipeline stopped at cycle %d' % cycle );
            break;
        #

        # Extract exc_flux and flx - keep as flat arrays (include
        # ghosts).  The model's make_fields uses the same field size
        # as Kratos output, so we don't need to strip ghost cells.
        if  'excitation_flux' in output:
            area_factor = unit_l0 * unit_l0 * unit_t0;
            inv_scale = 1.0 / scale;
            exc = asarray( output[ 'excitation_flux' ], \
                           dtype = float64 );
            exc = nan_to_num( exc, nan = 0.0, posinf = 0.0, \
                              neginf = 0.0 );
            exc = exc * inv_scale / area_factor;
            output[ 'exc_flux_flat' ] = exc;
            output[ 'excitation_flux' ] = exc;
        elif 'fab' in output:
            output[ 'exc_flux_flat' ] = output[ 'fab' ];
        #
        if  'flx' in output:
            area_factor = unit_l0 * unit_l0 * unit_t0;
            inv_scale = 1.0 / scale;
            flx = asarray( output[ 'flx' ], dtype = float64 );
            flx = nan_to_num( flx, nan = 0.0, posinf = 0.0, \
                              neginf = 0.0 );
            flx = flx * inv_scale / area_factor;
            output[ 'flx_flat' ] = flx;
            output[ 'flx' ] = flx;
        #

        output[ 'cycle' ] = cycle;
        output[ 'populations' ] = { k: v.copy( ) \
                                    for k, v in populations.items( ) };
        results.append( output );

        # Update populations
        new_pops = model.update_populations \
            ( output.get( 'exc_flux_flat', None ), \
              output.get( 'flx_flat', None ), \
              populations, cycle );
        populations = new_pops;
    #

    # Save final populations to output
    if  output is not None and 'fab_3d' in output:
        output[ '_final_populations' ] = populations;
    #

    return results, populations;
