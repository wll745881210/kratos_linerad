from .kratos_io import write_field_data, read_output, write_photon_data

from numpy import asarray, full, exp, abs, sin, cos, array, zeros, \
                  diff, linspace, meshgrid, float32, float64, int32;

from .source import AU


############################################################
# Field construction

def uniform_field( value, n_tot ):
    return full( n_tot, value, dtype = float32 );


def spherical_power_law( r_cc, theta_cc, n0, r0, p ):
    r_cc = asarray( r_cc, dtype = float64 );
    return ( n0 * ( r_cc / r0 ) ** p ).astype( float32 );


def cylindrical_disk( R_cc, z_cc, n0, R0, H0 ):
    R_cc = asarray( R_cc, dtype = float64 );
    z_cc = asarray( z_cc, dtype = float64 );
    return ( n0 * exp( -R_cc / R0 ) * \
             exp( -abs( z_cc ) / H0 ) ).astype( float32 );


def make_spherical_mesh( r_face, theta_face, phi_face ):
    r_face = asarray( r_face, dtype = float64 );
    theta_face = asarray( theta_face, dtype = float64 );
    phi_face = asarray( phi_face, dtype = float64 );

    nr = len( r_face ) - 1;
    nt = len( theta_face ) - 1;
    np_phi = len( phi_face ) - 1;

    n_cell = array( [ nr, nt, np_phi ], dtype = int32 );
    n_tot = int( n_cell.prod( ) );

    r_face_au = ( r_face * AU ).astype( float32 );
    x_min = array( \
        [ r_face_au[ 0 ], theta_face[ 0 ], phi_face[ 0 ] ], dtype = float32 );
    dx = array( \
        [ ( r_face_au[ -1 ] - r_face_au[ 0 ] ) / nr, \
          ( theta_face[ -1 ] - theta_face[ 0 ] ) / nt, \
          ( phi_face[ -1 ] - phi_face[ 0 ] ) / np_phi, ], \
        dtype = float32 );

    dr = diff( r_face_au );
    dtheta = diff( theta_face );
    dphi = diff( phi_face );
    r_c = 0.5 * ( r_face_au[ : -1 ] + r_face_au[ 1 : ] );
    theta_c = 0.5 * ( theta_face[ : -1 ] + theta_face[ 1 : ] );

    dv = zeros( ( nr, nt, np_phi ), dtype = float32 );
    for i in range( nr ):
        sin_th = sin( theta_c );
        dv[ i, :, : ] = ( r_c[ i ] ** 2 ) * sin_th[ :, None ] * dr[ i ] * \
                        dtheta[ :, None ] * dphi[ None, : ];

    return { 'n_cell'      : n_cell, \
             'x_min'       : x_min, \
             'dx'          : dx, \
             'n_tot'       : n_tot, \
             'coords'      : 'spherical', \
             'r_face'      : r_face_au, \
             'theta_face'  : theta_face, \
             'phi_face'    : phi_face, \
             'dv'          : dv.ravel( ).astype( float32 ), };


############################################################
# Kratos I/O wrappers

def write_kratos_fields( filename, fields, mesh, unit_l0 = 1.0 ):
    write_field_data( filename, fields, mesh, unit_l0 = unit_l0 );


def read_kratos_output( filename ):
    return read_output( filename );


############################################################
# Visualization

def _edges_from_mesh( mesh, dim ):
    x0 = mesh[ 'x_min' ][ dim ];
    nc = int( mesh[ 'n_cell' ][ dim ] );
    dx_val = mesh[ 'dx' ][ dim ];
    return linspace( x0, x0 + nc * dx_val, nc + 1 );


def slice_plot_2d( ax, data, mesh, plane = 'xy', \
                   slice_idx = None, log = True, \
                   cmap = 'turbo', **kwargs ):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    n_cell = mesh[ 'n_cell' ];
    coords = mesh.get( 'coords', 'cartesian' );
    nx, ny, nz = int( n_cell[ 0 ] ), int( n_cell[ 1 ] ), int( n_cell[ 2 ] );

    data = asarray( data );
    if data.ndim == 1:
        if data.size > nx * ny * nz:
            data_3d = data.reshape( nz, ny, nx, -1 )[ :, :, :, 0 ];
        else:
            data_3d = data.reshape( nz, ny, nx );
    else:
        data_3d = data;
    if 'norm' in kwargs:
        norm = kwargs.pop( 'norm' );
    else:
        norm = LogNorm( ) if log else None;

    if coords == 'cartesian':
        xe = _edges_from_mesh( mesh, 0 );
        ye = _edges_from_mesh( mesh, 1 );
        ze = _edges_from_mesh( mesh, 2 );

        if plane == 'xy':
            si = slice_idx if slice_idx is not None else nz // 2;
            X, Y = meshgrid( xe, ye, indexing = 'ij' );
            pc = ax.pcolormesh \
                ( X, Y, data_3d[ si, :, : ].T, \
                  cmap = cmap, norm = norm, **kwargs );
        elif plane == 'xz':
            si = slice_idx if slice_idx is not None else ny // 2;
            X, Z = meshgrid( xe, ze, indexing = 'ij' );
            pc = ax.pcolormesh \
                ( X, Z, data_3d[ :, si, : ].T, \
                  cmap = cmap, norm = norm, **kwargs );
        elif plane == 'yz':
            si = slice_idx if slice_idx is not None else nx // 2;
            Y, Z = meshgrid( ye, ze, indexing = 'ij' );
            pc = ax.pcolormesh \
                ( Y, Z, data_3d[ :, :, si ].T, \
                  cmap = cmap, norm = norm, **kwargs );
        else:
            raise ValueError( "Unknown plane '%s' for Cartesian mesh" \
                              % plane );

    elif coords == 'spherical':
        r_face = mesh[ 'r_face' ];
        theta_face = mesh[ 'theta_face' ];
        phi_face = mesh[ 'phi_face' ];

        if plane == 'rtheta':
            si = slice_idx if slice_idx is not None else \
                 ( len( phi_face ) - 1 ) // 2;
            slc = data_3d[ :, :, si ];
            R, Theta = meshgrid( r_face, theta_face, indexing = 'ij' );
            X = R * sin( Theta );
            Y = R * cos( Theta );
            pc = ax.pcolormesh \
                ( X, Y, slc.T, cmap = cmap, norm = norm, **kwargs );
        else:
            raise ValueError( "Unknown plane '%s' for spherical mesh" \
                              % plane );
    else:
        raise ValueError( "Unknown coordinate system '%s'" % coords );

    return pc;


############################################################
# Unit validation

def validate_units( fields ):
    c_val = 2.99792458e10;    # CGS speed of light [ cm / s ]
    ok = True;
    for key in fields:
        val = asarray( fields[ key ] );
        if key.startswith( 'mfp' ):
            if ( ( val != 0 ) & ( ( val < 1e-30 ) | ( val > 1e10 ) ) ).any( ):
                ok = False;
        elif key.startswith( 'vel' ):
            if ( abs( val ) >= c_val ).any( ):
                ok = False;
    return ok;
