#pragma once

#include "intg.h"
#include "gen.h"

namespace prob
{
////////////////////////////////////////////////////////////
//  Imaging-photon generator: one ray per pixel.
////////////////////////////////////////////////////////////

struct gen_img_t : particle::generate::base_t< gen_t >
{
    using super_t = particle::generate::base_t< gen_t >;

    int  n_par[ 2 ];

    __host__ virtual void init
    ( const input & args, particle::base_t & mod ) override;

    template< class pol_T, class map_T > __host__
    void generate( pol_T & pool, const map_T & bmap,
                   particle::base_t & mod )
    {
        pool.n_par = n_par[ 0 ] * n_par[ 1 ];
        pool.set_mem( mod, pool.n_par );
        return mod.p_dev->sync_all_streams(  );
    };
};

}  // namespace prob
