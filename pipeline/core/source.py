from numpy import random, sqrt, zeros, asarray, array, where, dot, \
                  cross, linalg, pi, cos, sin, abs, float32, float64, \
                  int32;


h    = 6.62607e-27;     # Planck constant [ erg s ]
c    = 2.99792458e10;   # speed of light [ cm / s ]
kb   = 1.38065e-16;     # Boltzmann constant [ erg / K ]
mp   = 1.67262e-24;     # proton mass [ g ]
Lsun = 3.828e33;        # solar luminosity [ erg / s ]
AU   = 1.49598e13;      # astronomical unit [ cm ]


############################################################
# Point sources

def point_source( L, lam, pos, n_ph, vel_width = None, seed = None ):
    rng = random.default_rng( seed );
    E_ph = h * c / lam;
    proper = ( L / E_ph ) / n_ph;

    cos_theta = rng.uniform( -1, 1, n_ph );
    sin_theta = sqrt( 1.0 - cos_theta * cos_theta );
    phi = rng.uniform( 0, 2.0 * pi, n_ph );

    photons = zeros( ( n_ph, 8 ), dtype = float64 );
    photons[ :, 0 ] = pos[ 0 ];
    photons[ :, 1 ] = pos[ 1 ];
    photons[ :, 2 ] = pos[ 2 ];
    photons[ :, 3 ] = sin_theta * cos( phi );
    photons[ :, 4 ] = sin_theta * sin( phi );
    photons[ :, 5 ] = cos_theta;
    photons[ :, 6 ] = proper;

    if vel_width is not None:
        photons[ :, 7 ] = rng.uniform( -0.5 * vel_width, \
                                       0.5 * vel_width, \
                                       n_ph ).astype( float32 );

    return photons;


############################################################
# Parallel beams

def parallel_beam( flux, lam, direction, area, n_ph, \
                   vel_width = None, seed = None ):
    rng = random.default_rng( seed );
    E_ph = h * c / lam;
    L = flux * area;
    proper = ( L / E_ph ) / n_ph;

    d = asarray( direction, dtype = float64 );
    d_norm = linalg.norm( d );
    if d_norm == 0:
        raise ValueError( "direction must be non-zero" );
    d = d / d_norm;

    if abs( d[ 0 ] ) < 0.9:
        v1 = array( [ 1.0, 0.0, 0.0 ], dtype = float64 );
    else:
        v1 = array( [ 0.0, 1.0, 0.0 ], dtype = float64 );
    v1 = v1 - dot( v1, d ) * d;
    v1 = v1 / linalg.norm( v1 );
    v2 = cross( d, v1 );

    half = 0.5 * sqrt( area );
    uv = rng.uniform( -half, half, ( n_ph, 2 ) );

    photons = zeros( ( n_ph, 8 ), dtype = float64 );
    photons[ :, 0 ] = uv[ :, 0 ] * v1[ 0 ] + uv[ :, 1 ] * v2[ 0 ];
    photons[ :, 1 ] = uv[ :, 0 ] * v1[ 1 ] + uv[ :, 1 ] * v2[ 1 ];
    photons[ :, 2 ] = uv[ :, 0 ] * v1[ 2 ] + uv[ :, 1 ] * v2[ 2 ];
    photons[ :, 3 ] = d[ 0 ];
    photons[ :, 4 ] = d[ 1 ];
    photons[ :, 5 ] = d[ 2 ];
    photons[ :, 6 ] = proper;

    if vel_width is not None:
        photons[ :, 7 ] = rng.uniform( -0.5 * vel_width, \
                                       0.5 * vel_width, n_ph );

    return photons;


############################################################
# Custom distributions

def custom_distribution( pos_gen, dir_gen, proper_gen, n_ph, \
                         vel_width = None, seed = None ):
    rng = random.default_rng( seed );

    pos_arr = asarray( pos_gen( n_ph ), dtype = float64 );
    dir_arr = asarray( dir_gen( n_ph ), dtype = float64 );
    proper_arr = asarray( proper_gen( n_ph ), dtype = float64 );

    norms = linalg.norm( dir_arr, axis = 1, keepdims = True );
    dir_arr = dir_arr / where( norms > 0, norms, 1.0 );

    photons = zeros( ( n_ph, 8 ), dtype = float64 );
    photons[ :, : 3 ] = pos_arr;
    photons[ :, 3 : 6 ] = dir_arr;
    photons[ :, 6 ] = proper_arr;

    if vel_width is not None:
        photons[ :, 7 ] = rng.uniform( -0.5 * vel_width, \
                                       0.5 * vel_width, n_ph );

    return photons;


############################################################
# Mesh helpers

def make_cartesian_mesh( n_cell, x_min, x_max ):
    n_cell = asarray( n_cell, dtype = int32 );
    x_min = asarray( x_min, dtype = float32 );
    x_max = asarray( x_max, dtype = float32 );
    dx = ( x_max - x_min ) / n_cell.astype( float32 );
    return { 'n_cell' : n_cell, \
             'x_min'  : x_min, \
             'dx'     : dx, \
             'n_tot'  : int( n_cell.prod( ) ), };
