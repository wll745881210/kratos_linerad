#!/usr/bin/env python3
"""
Binary I/O helpers for Kratos line_rt.

Self-contained: ships its own copy of the binary_io class (originally
from kratos/visual/binary_io.py).  No external sys.path hack needed.
"""

from .binary_io import binary_io
from numpy import asarray, array, int32, float32, float64

############################################################
# Field prefixes
############################################################

_LINE_FIELD_PREFIXES  = [ 'mfp_i_sca_0_', 'mfp_i_abs_0_', 'temp_',
                           'emiss_' ];
_FIXED_FIELD_PREFIXES = [ 'b_sca_', 'vel_0_', 'vel_1_', 'vel_2_' ];


def write_field_data( filename, fields, mesh, unit_l0 = 1.0, \
                      group = 'all' ):
    """
    Write Kratos field binary.

    Split into two groups (Task 2): line-dependent fields
    (mfp_i_sca_0, mfp_i_abs_0) that change per cycle / per line,
    and line-independent fields (b_sca, vel) that stay fixed
    across lines.  This prepares the pipeline for multi-line
    problems where bulk velocity and thermal broadening depend
    only on the gas, not the selected transition.

    Parameters
    ----------
    filename : str
    fields : dict
        Keys: 'mfp_i_sca_0', 'mfp_i_abs_0', 'b_sca',
              'vel_0', 'vel_1', 'vel_2', ['temp_']
        Values: 3D float32 arrays of shape (nz, ny, nx)
    mesh : dict
        'n_cell' : ndarray[int32], 'x_min' : ndarray[float32],
        'dx' : ndarray[float32]
    unit_l0 : float
        Ignored - kept for API compatibility. Kratos uses CGS
        coordinates for geo.x_cc(), so the field binary grid must
        use CGS x0/dx matching the par-file mesh.
    group : {'all', 'line', 'fixed'}
        'line'  - write only line-dependent fields (mfp_i_sca_0,
                  mfp_i_abs_0, temp_)  -> field_file
        'fixed' - write only line-independent fields (b_sca,
                  vel_0..2)             -> field_fixed_file
        'all'   - write both (backward compat, single file)

    Data layout: ijkl=0 is written so interp_t indexes as
    iz*ny*nx + iy*nx + ix (z slowest, x fastest), matching the
    (nz, ny, nx) C-order of the 3D arrays directly.

    Node layout: cell-centered. The interp_t grid is placed at
    cell centres (x0 = x_min + 0.5*dx, n_pts = n_cell), so the
    data array is the field values evaluated at cell centres
    themselves - no padding, no half-cell shift. Kratos samples
    the table at cell centres (geo.x_cc()), which then coincide
    with the nodes and return the exact stored value. The earlier
    vertex scheme (x0 = x_min, n_pts = n_cell+1, edge-padded)
    stored cell-centre values at vertex positions, producing a
    half-cell shift and an asymmetric high-side duplicate that
    broke mirror symmetry for spatially-varying fields.
    """
    bio = binary_io( filename );
    n_cell = asarray( mesh[ 'n_cell' ], dtype = int32   );
    x_min  = asarray( mesh[ 'x_min'  ], dtype = float32 );
    dx     = asarray( mesh[ 'dx'     ], dtype = float32 );

    n_pts    = n_cell.copy( );
    x0_nodes = x_min + 0.5 * dx;
    ijkl_flag = array( 0, dtype = int32 );

    if   group == 'all':
        prefixes = _LINE_FIELD_PREFIXES + _FIXED_FIELD_PREFIXES;
    elif group == 'line':
        prefixes = _LINE_FIELD_PREFIXES;
    elif group == 'fixed':
        prefixes = _FIXED_FIELD_PREFIXES;
    else:
        raise ValueError( "group must be 'all', 'line', or 'fixed', \
got %r" % ( group ) );
    #

    for prefix in prefixes:
        key = prefix.rstrip( '_' ) if prefix.endswith( '_' ) \
                                     else prefix;
        if  key not in fields and prefix not in fields:
            continue;
        arr = asarray( fields.get( key, fields.get( prefix ) ), \
                       dtype = float32 );

        bio.cache( prefix + 'ijkl',  ijkl_flag,           \
                   dtype = 'int32' );
        bio.cache( prefix + 'n_pts', n_pts,               \
                   dtype = 'int32' );
        bio.cache( prefix + 'x0',    x0_nodes,            \
                   dtype = 'float32' );
        bio.cache( prefix + 'dx',    dx,                  \
                   dtype = 'float32' );
        bio.cache( prefix + 'data',  arr.ravel( ).astype( float32 ), \
                   dtype = 'float32' );
    #
    bio.save(  );
    print( 'Wrote fields (%s): %s' % ( group, filename ) );
    return;


def write_photon_data( filename, photons, n_col = None, proper_scale = 1.0 ):
    """
    Write Kratos photon binary.

    Parameters
    ----------
    filename : str
    photons : ndarray (n_ph, n_col)
        Columns: x, y, z, dir_x, dir_y, dir_z, proper, [vel], [sv]
    n_col : int, optional
        Default: photons.shape[1]. Must be 7, 8, or 9.
    proper_scale : float, optional
        Extra rescaling factor applied to the ``proper`` weights
        (column 6) before writing.  Since Kratos MCRT is linear in
        the photon weights, a constant factor scales all outputs
        (flx, excitation_flux) by the same amount.  Use a small
        value (< 1) when the physical flux is so large that the
        FP32 output fields would overflow (>= 3.4e38).  The caller
        must divide the read-back flux by the returned scale.

    Returns
    -------
    float
        Total scale applied to ``proper`` (user ``proper_scale``
        combined with any internal FP32 safety rescale).
    """
    if proper_scale <= 0.0:
        raise ValueError( 'proper_scale must be > 0, got %.3g'
                          % ( proper_scale ) );
    ph = array( photons, dtype = float64 );
    scale = float( proper_scale );
    if  ph.shape[ 1 ] >= 7:
        ph[ :, 6 ] *= scale;
        proper_max = abs( ph[ :, 6 ].max( ) );
        if  proper_max > 1e38:
            s2 = 1.0 / proper_max;
            ph[ :, 6 ] *= s2;
            scale *= s2;
            print( "Warning: proper weight scaled by %.2e to fit \
float32 (after user proper_scale %.2e)" % ( s2, proper_scale ) );
    #
    ph = ph.astype( float32 );
    if  n_col is None:
        n_col = ph.shape[ 1 ];
    if  n_col not in ( 7, 8, 9 ):
        raise ValueError( 'n_col must be 7, 8, or 9, got %d' % n_col );
    #

    bio = binary_io( filename );
    bio.cache( 'par_n_col',   n_col,          dtype = 'int32'   );
    bio.cache( 'par_n_par',   ph.shape[ 0 ],  dtype = 'int64'   );
    bio.cache( 'par_par_dat', ph,             dtype = 'float32' );
    bio.save(  );
    print( 'Wrote photons: %s (%d photons, %d cols)' \
           % ( filename, ph.shape[ 0 ], n_col ) );
    return scale;


def read_output( filename ):
    """
    Read Kratos mesh output binary.

    Returns
    -------
    dict with keys:
      'n_cell', 'x_min', 'dx' - mesh metadata
      'flx' - effective flux array (n_tot + ghosts stripped to
              n_tot, float32)
      'excitation_flux' - flux for excitation array (n_tot, float32)
      'photons' - dict with keys 'x', 'dir', 'proper', 'vel'
                  (escaped photons only; 'l' is a deprecated alias
                  for 'proper')
    """
    bio = binary_io( filename );
    bio.open(  );
    result = dict(   );

    # Read all metadata from first block
    n_cell = None;
    n_gh   = None;
    n_int  = 1;
    for prefix in [ '', 'block_0|' ]:
        for key in bio.hmap:
            if  not key.startswith( prefix ):
                continue;
            base = key[ len( prefix ): ];
            if   base == 'n_ceff':
                n_cell = bio.as_array( key, 'i' );
            elif base == 'xf0':
                result[ 'x_min' ] = bio.as_array( key, 'f' );
            elif base == 'dx0':
                result[ 'dx' ] = bio.as_array( key, 'f' );
        #
    #

    # Read ghost cells and n_int from any field
    for key in bio.hmap:
        if  key.startswith( 'block_' ) and \
            key.endswith( '|rad_flx_n_gh' ):
            n_gh = bio.as_array( key, 'i' );
            break;
    #
    for key in bio.hmap:
        if  key.startswith( 'block_' ) and \
            key.endswith( '|rad_flx_n_int' ):
            n_int = int( bio.as_array( key, 'i' )[ 0 ] );
            break;
    #

    if  n_cell is not None:
        result[ 'n_cell' ] = n_cell;
        nx, ny, nz = int( n_cell[ 0 ] ), int( n_cell[ 1 ] ), \
                     int( n_cell[ 2 ] );

        def _strip_ghosts_3d( full_arr, n_cell, n_gh, n_int ):
            """
            Extract effective cells as 3D (nz, ny, nx[, n_int]).

            Kratos stores fields in C++ row-major order:
            cells[nz][ny][nx], so nx varies fastest in memory.
            """
            nz_w = int( n_cell[ 2 ] ) + 2 * int( n_gh[ 2 ] );
            ny_w = int( n_cell[ 1 ] ) + 2 * int( n_gh[ 1 ] );
            nx_w = int( n_cell[ 0 ] ) + 2 * int( n_gh[ 0 ] );
            gh2, gh1, gh0 = int( n_gh[ 2 ] ), int( n_gh[ 1 ] ), \
                            int( n_gh[ 0 ] );
            if  n_int == 1:
                rsh = full_arr.reshape( nz_w, ny_w, nx_w );
                return rsh[ gh2:gh2 + nz, gh1:gh1 + ny, \
                            gh0:gh0 + nx ].copy( );
            else:
                rsh = full_arr.reshape( nz_w, ny_w, nx_w, n_int );
                return rsh[ gh2:gh2 + nz, gh1:gh1 + ny, \
                            gh0:gh0 + nx, : ].copy( );
            #
        #

        for key in bio.hmap:
            if  key.startswith( 'block_' ) and \
                key.endswith( '|rad_flx_field' ):
                result[ 'flx' ] = _strip_ghosts_3d \
                    ( bio.as_array( key, 'f' ), n_cell, n_gh, n_int );
            elif key.startswith( 'block_' ) and \
                key.endswith( '|rad_excitation_flux_field' ):
                result[ 'excitation_flux' ] = _strip_ghosts_3d \
                    ( bio.as_array( key, 'f' ), n_cell, n_gh, n_int );
            elif key.startswith( 'block_' ) and \
                key.endswith( '|rad_exc_rate_field' ):
                result[ 'exc_rate' ] = _strip_ghosts_3d \
                    ( bio.as_array( key, 'f' ), n_cell, n_gh, n_int );
        #
    #

    # Escaped photons
    phot = dict(   );
    for raw_key in bio.hmap:
        if  '_rank_' in raw_key and raw_key.endswith( '_x_last_scat' ):
            phot[ 'x_last_scat' ] = bio.as_array( raw_key, 'f' );
        elif '_rank_' in raw_key and raw_key.endswith( '_x' ):
            phot[ 'x' ] = bio.as_array( raw_key, 'f' );
        elif '_rank_' in raw_key and raw_key.endswith( '_dir' ):
            phot[ 'dir' ] = bio.as_array( raw_key, 'f' );
        elif '_rank_' in raw_key and raw_key.endswith( '_l' ):
            proper = bio.as_array( raw_key, 'f' );
            phot[ 'proper' ] = proper;
            phot[ 'l' ]      = proper;   # deprecated alias
        elif '_rank_' in raw_key and raw_key.endswith( '_vel' ):
            phot[ 'vel' ] = bio.as_array( raw_key, 'f' );
    #
    if  phot:
        result[ 'photons' ] = phot;
    #

    # Imaging output: per-pixel intensity cube (written by
    # pol_img_t when imaging is enabled).  Keys _i2d_img,
    # _l_img, _dir_img, _x_img.  _l_img is a flat float32
    # array of length n_par * n_chan (pixel-major).
    img = dict( );
    for raw_key in bio.hmap:
        if  raw_key.endswith( '_i2d_img' ):
            img[ 'i2d' ] = bio.as_array( raw_key, 'i' );
        elif raw_key.endswith( '_l_img' ):
            img[ 'l' ] = bio.as_array( raw_key, 'f' );
        elif raw_key.endswith( '_dir_img' ):
            img[ 'dir' ] = bio.as_array( raw_key, 'f' );
        elif raw_key.endswith( '_x_img' ):
            img[ 'x' ] = bio.as_array( raw_key, 'f' );
    #
    if  'i2d' in img and 'l' in img:
        result[ 'image' ] = img;
    #

    bio.close(  );
    return result;


def write_par_file( par_path, template_path, overrides ):
    """
    Write a Kratos .par file from a template with key-value
    overrides.

    Parameters
    ----------
    par_path : str
    template_path : str
    overrides : dict
        Key-value pairs to override in the par file.
    """
    with open( template_path ) as f:
        lines = f.readlines(  );

    # Rewrite with explicit key matching
    with open( par_path, 'w' ) as f_out:
        for line in lines:
            matched = False;
            for key, val in overrides.items( ):
                # Match lines like "key  = value" or "key = value"
                # or "key value"
                stripped = line.strip( );
                if  stripped.startswith( key ) and \
                    not stripped.startswith( key + '_' ):
                    leading = line[ : len( line ) - \
                                   len( line.lstrip( ) ) ];
                    # Preserve format: keyword + space + value
                    parts = stripped.split( None, 1 );
                    if  len( parts ) >= 2:
                        rest = parts[ 1 ];
                        if  '=' in rest:
                            f_out.write( '%s%s  = %s\n' \
                                         % ( leading, key, val ) );
                        else:
                            f_out.write( '%s%s  %s\n' \
                                         % ( leading, key, val ) );
                    else:
                        f_out.write( '%s%s  = %s\n' \
                                     % ( leading, key, val ) );
                    #
                    matched = True;
                    break;
                #
            #
            if  not matched:
                f_out.write( line );
        #
    #

    print( 'Wrote par file: %s' % ( par_path ) );
    return;
