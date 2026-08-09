#pragma once

namespace prob
{

////////////////////////////////////////////////////////////
//  Particle pool that has particle I/O
////////////////////////////////////////////////////////////

struct pol_t : particle::pool_t< line_rt_photon_t<  > >
{
    //  Server-worker work counter (device).  Reset to 0
    //  in pre_proc; each worker atomically fetches the
    //  next photon index via load_next(  ) until n_par
    //  is reached.
    int_t * work_counter = nullptr;

    using base_t = particle::pool_t< line_rt_photon_t<  > >;

    __host__ virtual void init
    ( const input & args,
      particle::base_t & mod ) override
    {
        output = args.get< bool >
            ( "particle", "output", false );
        return particle::driver::base_t::init
            ( args, mod );
    }

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

    //  Server-worker: fetch next photon index from the
    //  shared atomic counter.  Returns index (>= n_par
    //  when the pool is depleted).  atomicAdd returns
    //  the OLD value, so the first fetch yields `offset`.
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

    __host__ void write
    ( const mesh::f_cp_t   & f_cp,
      const mesh::f_write_t & f_w )
    {
        if( !output )
            return;

        std::vector< float_t > dir_h( n_par * 3 );
        std::vector< float_t > x_h  ( n_par * 3 );
        std::vector< float_t > l_h  ( n_par     );
        std::vector< float_t > vel_h( n_par     );
        std::vector< float_t > xls_h( n_par * 3 );
        auto * par_h = new par_t[ n_par ];
        f_cp( par_h, par, n_par * sizeof( par_t ) );

        size_t j( 0 );
        for( size_t i = 0; i < n_par; ++ i )
        {
            if( par_h[ i ].dest.i_rank >= 0 )
                continue;
            for( int a = 0; a < 3; ++ a )
            {
                dir_h[ 3 * j + a ] = par_h[ i ].dir[ a ];
                x_h  [ 3 * j + a ]
                    = par_h[ i ].x[ a ];
                xls_h[ 3 * j + a ]
                    = par_h[ i ].x_last_scat[ a ];
            }
            l_h  [ j ] = par_h[ i ].proper;
            vel_h[ j ] = par_h[ i ].vel;
            ++ j;
        }
        const auto s_f( sizeof( float_t ) );
        f_w( dir_h.data(  ), j * 3, s_f, "_dir" );
        f_w( vel_h.data(  ), j,     s_f, "_vel" );
        f_w( x_h  .data(  ), j * 3, s_f, "_x"   );
        f_w( l_h  .data(  ), j,     s_f, "_l"   );
        f_w( xls_h.data(  ), j * 3, s_f,
             "_x_last_scat" );
        delete[  ] par_h;
    }
};

}  //  namespace prob
