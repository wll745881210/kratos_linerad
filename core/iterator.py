import os
from numpy import ones, zeros, asarray, broadcast_to, nan_to_num, \
                  mean, hstack, vstack, float32, float64, int32;

from .pipeline import run_kratos_cycle, \
                    DEFAULT_RUN_ROOT, \
                    make_cartesian_mesh as _pipeline_make_cartesian_mesh
from .kratos_io import write_field_data, write_photon_data, \
                       read_output, write_par_file
from .pipeline import resolve_kratos_bin


_PAR_TEMPLATE = os.path.join( os.path.dirname( __file__ ), \
                              'line_rt_pipeline.par' );


def _remove_intermediate( work_dir, cycle, field_file, photon_file ):
    """Delete one cycle's binary/par/log files from the run dir.

    Called after the cycle's data has been read back into RAM, so the
    on-disk copies are no longer needed.  Frees /dev/shm (tmpfs = RAM)
    space while the simulation is still running.
    """
    for f in ( field_file, photon_file, \
               os.path.join( work_dir, 'cycle%d.par' % cycle ), \
               os.path.join( work_dir, 'cycle%d.txt' % cycle ), \
               os.path.join( work_dir, 'cycle%d_00000.bin' % cycle ) ):
        try:
            if f and os.path.exists( f ):
                os.remove( f );
        except OSError as e:
            print( "[iterate] could not remove %s: %s" % ( f, e ) );


def iterate( source_photons, species, fields_init, mesh, \
             n_cycles = 5, n_photon = None, n_step = 10000, \
             n_scat = 10000, ph_mode = 1, par_overrides = None, \
             mol_mass = 28.0, work_dir = None, callback = None, \
             n_species = None, transition_idx = 0, n_emission_max = 10, \
             colliders = None, proper_scale = 1.0, \
             keep_intermediate = True, retain_cycles = None, \
             unit_l0 = 1.49598e13, unit_t0 = 1.0, kratos_root = None, \
             imaging = None ):
    """
    imaging : dict or None
        When provided, enables imaging on the FINAL cycle.  Keys:
        'dir_cam'   : (theta, phi) camera direction [rad], or a 3-vector
                      (direction INTO the domain).
        'n_chan'    : number of velocity channels.
        'v_chan'    : (v_min, v_max) channel velocity range [cm/s, CGS].
        'img_xmin'  : (x0, y0) image-plane lower corner [code units] (opt).
        'img_xmax'  : (x1, y1) image-plane upper corner [code units] (opt).
        'img_resol' : (nx, ny) image resolution in pixels (opt).
        Returns the image cube in results[-1]['image'].
    """
    if work_dir is None:
        work_dir = os.path.join( DEFAULT_RUN_ROOT, 'iterate_output' );
    os.makedirs( work_dir, exist_ok = True );
    print( "[iterate] Run directory: %s" % work_dir );

    if par_overrides is None:
        par_overrides = { };

    x_max_str = ' '.join( \
        str( float( mesh[ 'x_min' ][ i ] ) + \
             float( mesh[ 'dx' ][ i ] ) * int( mesh[ 'n_cell' ][ i ] ) ) \
        for i in range( 3 ) );
    base_overrides = { 'length'        : str( float( unit_l0 ) ), \
                       'time'          : str( float( unit_t0 ) ), \
                       'n_cell_global' : ' '.join( \
                                          str( int( v ) ) \
                                          for v in mesh[ 'n_cell' ] ), \
                       'x_min'         : ' '.join( \
                                          str( v ) \
                                          for v in mesh[ 'x_min' ] ), \
                       'x_max'         : x_max_str, \
                       'n_step'        : str( int( n_step ) ), \
                       'n_scat'        : str( int( n_scat ) ), \
                       'ph_mode'       : str( int( ph_mode ) ), \
                       'n_fld'         : '1', \
                       'n_cycle_lim'   : '0', \
                       't_output_next' : '1e32', \
                       'dt_output'     : '1e32', \
                       'final_output'  : '1', \
                       'output'        : '1', \
                       'mol_mass'      : str( float( mol_mass ) ), };
    if n_photon is not None:
        base_overrides[ 'n_photon' ] = str( int( n_photon ) );
    base_overrides.update( par_overrides );

    # ---- Imaging configuration ----
    # Imaging par keys are injected ONLY on the final cycle (see
    # below), so base_overrides stays clean for non-imaging cycles.
    imaging_pars = None;
    if imaging is not None:
        from numpy import sqrt as _sqrt, arctan2 as _atan2;
        dc = imaging.get( 'dir_cam', ( 0.7853981633974483, 0.0 ) );
        if len( dc ) == 3:
            # Cartesian -> spherical (theta, phi)
            dx, dy, dz = float( dc[ 0 ] ), float( dc[ 1 ] ), \
                         float( dc[ 2 ] );
            theta = _atan2( _sqrt( dx * dx + dy * dy ), dz );
            phi   = _atan2( dy, dx );
        else:
            theta, phi = float( dc[ 0 ] ), float( dc[ 1 ] );
        v_lo, v_hi = imaging.get( 'v_chan', ( -1e5, 1e5 ) );
        # Convert channel velocities from CGS (cm/s) to code units
        # (code-v = v_cgs * unit_t0 / unit_l0) so they match b_sca,
        # vel, and the photon vel convention used inside Kratos.
        _v2c = float( unit_t0 ) / float( unit_l0 );
        imaging_pars = {
            'enabled'         : '1',
            'n_chan'          : str( int( imaging.get( 'n_chan', 32 ) ) ),
            'dir_cam_theta'   : str( float( theta ) ),
            'dir_cam_phi'     : str( float( phi ) ),
            'v_chan_min'      : str( float( v_lo ) * _v2c ),
            'v_chan_max'      : str( float( v_hi ) * _v2c ),
        };
        if 'img_xmin' in imaging:
            imaging_pars[ 'img_xmin' ] = ' '.join(
                str( float( v ) ) for v in imaging[ 'img_xmin' ] );
        if 'img_xmax' in imaging:
            imaging_pars[ 'img_xmax' ] = ' '.join(
                str( float( v ) ) for v in imaging[ 'img_xmax' ] );
        if 'img_resol' in imaging:
            imaging_pars[ 'img_resol' ] = ' '.join(
                str( int( v ) ) for v in imaging[ 'img_resol' ] );

    n_tot = mesh[ 'n_tot' ];
    results = [ ];

    nx, ny, nz = int( mesh[ 'n_cell' ][ 0 ] ), \
                 int( mesh[ 'n_cell' ][ 1 ] ), int( mesh[ 'n_cell' ][ 2 ] );
    shape3d = ( nz, ny, nx );

    fields = dict( fields_init );
    base_fields_cgs = { k: asarray( v, dtype = float64 ).copy( ) \
                        for k, v in fields.items( ) };

    # Initial populations are ALWAYS thermalised to LTE at the gas
    # temperature (with colliders when available) — even when external
    # sources are present — so that cycle-0 opacity and emissivity are
    # physically consistent.  Without a temperature, they fall back to
    # all-in-ground-state.
    if species is not None and hasattr( species, 'initial_populations' ):
        if n_species is None:
            n_species_arr = ones( shape3d, dtype = float64 );
        else:
            n_species_arr = broadcast_to( \
                asarray( n_species, dtype = float64 ), shape3d ).copy( );
        populations = species.initial_populations( n_species_arr, \
                          T = base_fields_cgs.get( 'temp', None ), \
                          colliders = colliders );
    else:
        populations = { 'n0'      : ones( shape3d, dtype = float32 ), \
                        'n_total' : ones( shape3d, dtype = float32 ) };

    # External source photons are FIXED across cycles.  Internal emission
    # photons are recomputed each cycle from the updated populations and
    # combined here, so the photon count does not accumulate.
    ext_source = asarray( source_photons, dtype = float64 ).copy( );
    emission_ph = None;

    # Emission-only mode: if there are no external photons, seed cycle 0
    # with internal emission generated from the (LTE) populations so
    # Kratos still has photons to propagate.  The per-cycle block below
    # regenerates emission from the updated populations for cycles 1+.
    if ext_source.shape[ 0 ] == 0 and species is not None and \
       hasattr( species, 'generate_emission_photons' ):
        temp_field_0 = base_fields_cgs.get( 'temp', \
                         zeros( mesh[ 'n_tot' ], dtype = float64 ) );
        emission_ph = species.generate_emission_photons( \
            populations, transition_idx, temp_field_0, mesh, \
            n_per_cell_max = n_emission_max );
        if len( emission_ph ) == 0:
            emission_ph = None;
        else:
            print( "[iterate] No external sources: seeding cycle 0 from "
                   "internal emission (%d photons)" % \
                   len( emission_ph ) );

    if species is not None and hasattr( species, 'make_fields' ):
        fields = species.make_fields( populations, 'pre', -1, \
                                      base_fields = base_fields_cgs, \
                                      transition_idx = transition_idx, \
                                      unit_l0 = unit_l0, unit_t0 = unit_t0 );
        # make_fields may not return mfp_i_abs_0 (absorption is
        # user-provided, not species-derived).  Preserve it from
        # base_fields_cgs, converted to code units.
        if 'mfp_i_abs_0' not in fields and 'mfp_i_abs_0' in base_fields_cgs:
            v_factor = unit_l0;
            fields[ 'mfp_i_abs_0' ] = asarray( \
                base_fields_cgs[ 'mfp_i_abs_0' ], dtype = float64 ) * v_factor;

    # Write line-independent fields (b_sca, vel) ONCE - these
    # depend only on the gas (bulk motion, thermal temperature,
    # molecular weight), not on the selected line/band.
    fixed_fields = { k: v for k, v in fields.items( ) \
                     if k in ( 'b_sca', 'vel_0', 'vel_1', 'vel_2', 'temp' ) };
    fixed_file = os.path.join( work_dir, 'fields_fixed.bin' );
    write_field_data( fixed_file, fixed_fields, mesh, unit_l0 = unit_l0, \
                      group = 'fixed' );
    base_overrides[ 'field_fixed_file' ] = 'fields_fixed.bin';

    for cycle in range( n_cycles ):
        # Line-dependent fields (mfp_i_sca_0, mfp_i_abs_0,
        # emiss) are written per cycle (populations evolve).
        line_fields = { k: v for k, v in fields.items( ) \
                        if k in ( 'mfp_i_sca_0', 'mfp_i_abs_0',
                                  'emiss' ) };
        field_file = os.path.join( work_dir, 'fields_cycle%d.bin' % cycle );
        write_field_data( field_file, line_fields, mesh, \
                          unit_l0 = unit_l0, group = 'line' );

        photon_file = os.path.join( work_dir, 'photons_cycle%d.bin' % cycle );
        n_ext = ext_source.shape[ 0 ];
        if n_ext == 0:
            # Emission-only mode: use internal emission photons directly
            # (no external sources).  vstack([ (0,10), (n,9) ]) would
            # fail on column count, so branch here.
            if emission_ph is not None:
                ph_arr = emission_ph;
            else:
                raise ValueError( "No photons to propagate: no external "
                                  "sources and no internal emission. "
                                  "Add a source or ensure non-zero "
                                  "emissivity." );
        elif emission_ph is None:
            ph_arr = ext_source;
        else:
            ph_arr = vstack( [ ext_source, emission_ph ] );
        ph_arr = asarray( ph_arr, dtype = float64 ).copy( );
        if ph_arr.shape[ 1 ] >= 8:
            v_factor = unit_t0 / unit_l0;
            ph_arr[ :, 7 ] *= v_factor;
            if ph_arr.shape[ 1 ] >= 9:
                ph_arr[ :, 8 ] *= v_factor;
        scale_factor = write_photon_data( photon_file, ph_arr, \
                                          proper_scale = proper_scale );
        if proper_scale != 1.0:
            print( "[iterate] proper_scale = %.3e, max proper after \
scale = %.3e" % ( proper_scale, \
                  abs( ph_arr[ :, 6 ].max( ) ) \
                  if ph_arr.shape[ 1 ] >= 7 else 0.0 ) );
        del ph_arr;

        prefix = 'cycle%d' % cycle;
        # Inject imaging par keys ONLY on the final cycle so
        # non-imaging cycles run with imaging disabled (the
        # rad_img_t module defaults enabled=false).
        cycle_overrides = base_overrides;
        if imaging_pars is not None and cycle == n_cycles - 1:
            cycle_overrides = dict( base_overrides );
            cycle_overrides.update( imaging_pars );
        output, log_text, elapsed = run_kratos_cycle( \
            work_dir, cycle, field_file, photon_file, \
            prefix, _PAR_TEMPLATE, cycle_overrides, \
            kratos_bin = resolve_kratos_bin( kratos_root ) );

        if output is None:
            break;

        output[ 'cycle' ] = cycle;

        if 'mfp_i_sca_0' in fields:
            output[ 'mfp_i_sca_0' ] = asarray( \
                fields[ 'mfp_i_sca_0' ], dtype = float64 );

        if 'photons' in output:
            v_factor = unit_t0 / unit_l0;
            inv_scale = 1.0 / scale_factor;
            phot = output[ 'photons' ];
            for key in ( 'vel', 'x', 'proper' ):
                if key in phot:
                    arr = asarray( phot[ key ], dtype = float64 );
                    if key == 'x':
                        arr *= unit_l0;
                    elif key == 'vel':
                        arr /= v_factor;
                    else:
                        arr *= inv_scale;
                    phot[ key ] = arr;
            if 'l' in phot:
                phot[ 'l' ] = phot.get( 'proper', phot[ 'l' ] );

        # ---- Imaging readback ----
        # The image cube: _l_img is a flat array of
        # n_par * n_chan floats (pixel-major).  Reshape into
        # (n_pix, n_chan) and index by (iy, ix).  Off-image
        # pixels (i_rank == -2) are filtered out by pol_img_t
        # at write time, so only valid pixels remain.
        if 'image' in output:
            img = output[ 'image' ];
            if 'l' in img and 'i2d' in img:
                l_flat = asarray( img[ 'l' ], dtype = float64 );
                i2d    = asarray( img[ 'i2d' ], dtype = int32 );
                # i2d is flat: 2 ints per pixel (ix, iy).
                n_pix  = i2d.shape[ 0 ] // 2;
                n_chan = l_flat.size // max( n_pix, 1 );
                if n_chan > 0 and \
                   l_flat.size == n_pix * n_chan:
                    cube = l_flat.reshape( n_pix, n_chan );
                    img[ 'cube' ] = cube;  # (n_pix, n_chan) code units
                    img[ 'n_chan' ] = n_chan;
                    img[ 'i2d' ] = i2d.reshape( n_pix, 2 );
                    # Convert code-unit intensity to CGS
                    # [erg cm^-2 s^-1 sr^-1].  The thermal seed
                    # (emiss/mfp_s, emiss in code units) gives
                    # code-unit intensity; divide by unit_l0^2 *
                    # unit_t0 to recover CGS intensity.
                    i_conv = 1.0 / ( unit_l0 ** 2 * unit_t0 );
                    img[ 'cube_cgs' ] = ( cube * i_conv ) \
                                         .astype( float32 );

        results.append( output );

        if retain_cycles is not None and len( results ) > retain_cycles:
            # Bound RAM: drop oldest cycles' full dicts (kept as a bare
            # record of the cycle number so the trim is visible).
            del results[ : len( results ) - retain_cycles ];

        always_process_flux = True;
        if always_process_flux:
            exc_flux = output.get( 'excitation_flux', \
                         output.get( 'exc_flux_flat', \
                           output.get( 'fab_flat', \
                             output.get( 'fab', None ) ) ) );
            flx = output.get( 'flx_flat', output.get( 'flx', None ) );
            area_factor = unit_l0 * unit_l0 * unit_t0;
            inv_scale = 1.0 / scale_factor;
            if exc_flux is not None:
                exc_flux = asarray( exc_flux, dtype = float64 );
                exc_flux = nan_to_num( exc_flux, nan = 0.0, posinf = 0.0, \
                                       neginf = 0.0 );
                exc_flux = exc_flux * inv_scale / area_factor;
                output[ 'exc_flux_flat' ] = exc_flux.astype( float32 );
            if flx is not None:
                flx = nan_to_num( asarray( flx, dtype = float64 ), \
                                  nan = 0.0, posinf = 0.0, \
                                  neginf = 0.0 ) * inv_scale / area_factor;
                output[ 'flx' ] = flx.astype( float32 );

        if species is not None and hasattr( species, 'update_populations' ):
            T_field = base_fields_cgs.get( 'temp', None );
            b_sca_field = base_fields_cgs.get( 'b_sca', None );
            if b_sca_field is not None and hasattr( b_sca_field, '__len__' ):
                b_sca_scalar = float( mean( b_sca_field ) );
            else:
                b_sca_scalar = b_sca_field;
            populations = species.update_populations( \
                exc_flux, flx, populations, cycle, \
                transition_idx = transition_idx, \
                T = T_field, b_sca = b_sca_scalar, \
                colliders = colliders );
            output[ 'populations' ] = { k: asarray( v, \
                                                   dtype = float64 ).copy( ) \
                                        for k, v in populations.items( ) };

        if species is not None and hasattr( species, 'make_fields' ):
            fields = species.make_fields( populations, 'post', cycle, \
                                          base_fields = base_fields_cgs, \
                                          transition_idx = transition_idx, \
                                          unit_l0 = unit_l0, \
                                          unit_t0 = unit_t0 );
            if 'mfp_i_abs_0' not in fields and \
               'mfp_i_abs_0' in base_fields_cgs:
                fields[ 'mfp_i_abs_0' ] = asarray( \
                    base_fields_cgs[ 'mfp_i_abs_0' ], \
                    dtype = float64 ) * unit_l0;

        if species is not None and hasattr( species, 'compute_emissivity' ):
            temp_field = fields.get( 'temp', zeros( mesh[ 'n_tot' ], \
                                                    dtype = float64 ) );
            output[ 'emissivity' ] = species.compute_emissivity( \
                populations, transition_idx, temp_field );

        if species is not None and \
           hasattr( species, 'generate_emission_photons' ) and \
           cycle < n_cycles - 1:
            emission_ph = species.generate_emission_photons( \
                populations, transition_idx, temp_field, mesh, \
                n_per_cell_max = n_emission_max );
            if len( emission_ph ) > 0:
                if ext_source.shape[ 1 ] < emission_ph.shape[ 1 ]:
                    pad = zeros( ( ext_source.shape[ 0 ], \
                                   emission_ph.shape[ 1 ] - \
                                   ext_source.shape[ 1 ] ) );
                    ext_source = hstack( [ ext_source, pad ] );
                elif emission_ph.shape[ 1 ] < ext_source.shape[ 1 ]:
                    pad = zeros( ( emission_ph.shape[ 0 ], \
                                   ext_source.shape[ 1 ] - \
                                   emission_ph.shape[ 1 ] ) );
                    emission_ph = hstack( [ emission_ph, pad ] );
            else:
                emission_ph = None;
        else:
            for key in fields:
                if key.startswith( 'mfp' ):
                    exc_flux_norm = zeros( n_tot, dtype = float32 );
                    exc_flux_ptr = output.get( 'excitation_flux', \
                                     output.get( 'exc_flux_flat', \
                                       output.get( 'fab_flat', \
                                         output.get( 'fab', None ) ) ) );
                    if exc_flux_ptr is not None:
                        exc_flux_norm = exc_flux_ptr.astype( float32 ) / \
                                        ( exc_flux_ptr.max( ) + 1e-35 );
                    fields[ key ] = exc_flux_norm;

        if callback is not None:
            callback( cycle, \
                output.get( 'excitation_flux', \
                  output.get( 'exc_flux_flat', \
                    output.get( 'fab_flat', output.get( 'fab', None ) ) ) ), \
                populations );

        if not keep_intermediate and cycle < n_cycles - 1:
            # Free /dev/shm (tmpfs = RAM) as we go.  Keep the fixed
            # fields file and the final cycle's outputs for inspection.
            _remove_intermediate( work_dir, cycle, field_file, \
                                  photon_file );

    return results, populations;
