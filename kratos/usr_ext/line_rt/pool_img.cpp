#include "../../src/device/general.h"
#include "../../src/types.h"

#include "rad_img.h"
#include "pool_img.h"
#include "intg.h"

namespace prob
{
////////////////////////////////////////////////////////////
//  Pool of imaging photons (line-RT)
////////////////////////////////////////////////////////////

__host__ void pol_img_t::init
( const input & args,
  particle::base_t & mod )
{
    particle::driver::base_t::init( args, mod );

    auto   & rimg = dynamic_cast< rad_img_t & >( mod );
    output = rimg.enabled;

    //  Read n_chan directly from par (the integrator may
    //  not have been initialised yet at this point in the
    //  module init sequence).
    n_chan_img = args.get< int >( "imaging", "n_chan", 0 );
    return;
}

__host__ void pol_img_t::write
( const mesh::f_cp_t & f_cp, const mesh::f_write_t & f_w )
{
    if( ! output )
        return;

    const int nch = n_chan_img;
    if( nch <= 0 )
        return;

    std::vector< float_t > dir_h( n_par *   3 );
    std::vector< float_t >   x_h( n_par *   3 );
    std::vector< int     > i2d_h( n_par *   2 );
    std::vector< float_t >   l_h( n_par * nch );
    auto * par_h = new par_t[ n_par ];

    f_cp( par_h, par, n_par * sizeof( par_t ) );

    size_t j( 0 );
    for( size_t i = 0; i < n_par; ++ i )
    {
        //  Off-image / failed rays carry
        //  i_rank == -2; skip them.
        if( par_h[ i ].dest.i_rank == -2 )
            continue;

        for( int a = 0; a < 3; ++ a )
        {
            dir_h[ 3 * j + a ] = par_h[ i ].dir   [ a ];
            x_h  [ 3 * j + a ] = par_h[ i ].x     [ a ];
        }
        for( int a = 0; a < 2; ++ a )
            i2d_h[ 2 * j + a ] = par_h[ i ].i2d   [ a ];
        for( int k = 0; k < nch; ++ k )
            l_h[ j * nch + k ] = par_h[ i ].I_chan[ k ];
        ++ j;
    }
    const auto s_f( sizeof( float ) );
    const auto s_i( sizeof( int   ) );
    f_w( dir_h.data(  ),  j *   3, s_f, "_dir_img" );
    f_w( x_h.data(  ),    j *   3, s_f,   "_x_img" );
    f_w( i2d_h.data(  ),  j *   2, s_i, "_i2d_img" );
    f_w( l_h.data(  ),    j * nch, s_f,   "_l_img" );
    delete [  ] par_h;
    return;
}

}  // namespace prob
