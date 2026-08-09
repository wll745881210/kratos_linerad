#pragma once

//  Imaging photon pool: writes the per-pixel, per-channel image
//  cube.  Each "particle" is one camera ray (one pixel); its
//  I_chan[0..n_chan-1] array holds the emergent intensity per
//  velocity channel.  Output keys (all per escaped ray):
//    _i2d_img  : int32 [2]   pixel index (ix, iy)
//    _dir_img  : float32 [3] ray direction
//    _x_img    : float32 [3] ray end position
//    _l_img    : float32 [n_chan]  per-channel intensity

#include "photon_img.h"

namespace prob
{

struct pol_img_t : particle::pool_t< line_img_t<  > >
{
    int n_chan_img = 0;

    //  Server-worker work counter (device), reset in
    //  pre_proc; see pol_t::load_next.  Present so that the
    //  shared intg_t worker-mode branch compiles for this
    //  pool type as well.
    int_t * work_counter = nullptr;

    using base_t = particle::pool_t< line_img_t<  > >;

    __host__ virtual bool set_mem
    ( particle::base_t & mod,
      const int_t & n_par,
      const type::float2_t & safe = 1.1,
      const bool & keep_data = true ) override
    {
        if( work_counter == nullptr )
        {
            work_counter
                = mod.p_dev->malloc_device< int_t >( 1 );
            mod.p_dev->f_mset
                ( work_counter, 0,
                  sizeof( int_t ), mod.stream );
        }
        return base_t::set_mem( mod, n_par, safe, keep_data );
    }

    __host__ virtual void finalize
    ( particle::base_t & mod ) override
    {
        if( work_counter != nullptr )
        {
            mod.p_dev->free_device( work_counter );
            work_counter = nullptr;
        }
        return base_t::finalize( mod );
    }

    __host__ virtual void pre_proc
    ( particle::base_t & mod ) override
    {
        if( work_counter != nullptr )
            mod.p_dev->f_mset
                ( work_counter, 0,
                  sizeof( int_t ), mod.stream );
        return base_t::pre_proc( mod );
    }

    __device__ __forceinline__
    int_t load_next( par_t & par, bool & flag ) const
    {
        const auto i
            = utils::atomic_inc( work_counter ) + offset;
        flag = ( i < n_par );
        if( flag )
            par.load( ( * this )[ i ] );
        return i;
    }

    __host__ virtual void init
    ( const input & args,
      particle::base_t & mod ) override;

    __host__ void write
    ( const mesh::f_cp_t    & f_cp,
      const mesh::f_write_t & f_w );
};

}  //  namespace prob
