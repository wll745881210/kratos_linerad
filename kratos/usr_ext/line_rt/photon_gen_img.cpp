#include "../../src/device/general.h"
#include "../../src/types.h"

#include "rad_img.h"
#include "photon_gen_img.h"

namespace prob
{
////////////////////////////////////////////////////////////
//  Imaging-photon generator
////////////////////////////////////////////////////////////

__host__ void gen_img_t::init
( const input & args,
  particle::base_t & mod )
{
    super_t::init( args, mod );

    auto p_itg
        = dynamic_cast< rad_img_t & >( mod ).p_itg;
    auto & itg
        = dynamic_cast< intg_t & >( * p_itg );

    for( int a = 0; a < 2; ++ a )
        n_par[ a ] = itg.img_n[ a ];
}

}  // namespace prob
