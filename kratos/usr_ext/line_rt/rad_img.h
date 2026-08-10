#pragma once

#include <chrono>

#include "photon.h"
#include "photon_img.h"
#include "block_data.h"
#include "intg.h"
#include "gen.h"
#include "pool.h"
#include "radiation.h"
#include "pool_img.h"
#include "photon_gen_img.h"

namespace prob
{
////////////////////////////////////////////////////////////
//  Line-RT imaging driver (parasite of radiation_t).
//
//  Enrolled alongside radiation_t in usr.cpp via
//    q->parasite( p );
//  Shares the block_data (p_map) with radiation_t
//  so the imaging rays see the MC-accumulated j_cam
//  and the field arrays.  Runs its own
//  (non-scattering) photon pool (pol_img_t) over
//  the image-plane pixels after the scattering MC
//  step.
//
//  The imaging integrator (intg_t) reuses the same
//  par keys as the scattering one (it rebuilds the
//  Voigt / USampler tables, which is a small
//  one-off cost) but its pre_proc is a no-op
//  w.r.t. j_cam so it does not wipe the MC
//  accumulation.

class rad_img_t : public particle::radiation::base_t
{
public:  //  Data
    bool enabled = false;
    bool profile = false;

protected:  //  Functions
    virtual void init_cond
    ( mesh::block::dual_t & d ) override
    {   //  Fields already initialised by radiation_t.
        return;
    };

public:                         // Functions
    virtual void read( const input & args ) override
    {
        enabled = args.get< bool >
            ( "imaging", "enabled", false );
        enroll< prx_t, pol_img_t, gen_img_t, intg_t >(  );
        //  Share the block map (and thus j_cam /
        //  fields) with the scattering module.
        p_map = dynamic_cast< radiation_t & >
            ( * q_mod.lock(  ) ).p_map;
        auto & itg = dynamic_cast< intg_t & >( * p_itg );
        itg.zero_j_cam   = false;
        itg.zero_fields  = false;
        itg.build_tables = false;
        profile = args.get< bool >
            ( "profile", "enabled", false );
        return particle::radiation::base_t::read( args );
    };

    virtual void init
    ( const input & args, mesh::mesh_t & mesh ) override
    {
        particle::radiation::base_t::init( args, mesh );
        dynamic_cast< intg_t & >
                    ( * p_itg ).worker_mode = false;
        //  Share the Voigt table from the scattering
        //  integrator so voigt_H uses the smooth tabulated
        //  form instead of the max( gauss, lorentz )
        //  fallback (which has a derivative discontinuity
        //  at the crossover).  The scattering module is
        //  enrolled first (i_step 0), so its tables are
        //  built before this init() runs.
        auto & rad     = dynamic_cast< radiation_t & >
                       ( * q_mod.lock(  ) );
        auto & rad_itg = dynamic_cast< intg_t & >
                       ( * rad.p_itg );
        auto & img_itg = dynamic_cast< intg_t & >
                       ( * p_itg );
        if( rad_itg.ph_mode <= 1 )
            img_itg.voigt_interp  = rad_itg.voigt_interp;
        else if( rad_itg.ph_mode == 2 )
            img_itg.d_log_voigt_c = rad_itg.d_log_voigt_c;
        return;
    };

    virtual void step( mesh::mesh_t & mesh ) override
    {
        if( enabled )
        {
            auto t0 = std::chrono::steady_clock::now(  );
            particle::radiation::base_t::step( mesh );
            auto t1 = std::chrono::steady_clock::now(  );
            if( profile )
                std::cout << "[profile] imaging: "
                          << std::chrono::duration< double >
                           ( t1 - t0 ).count(  ) << " s\n";
        }
        return;
    };

    //  Skip the imaging-pool save entirely when imaging is
    //  disabled: the pool was never generated ( par ==
    //  nullptr, n_par == 0 ) and the default f_par_save
    //  would dereference it.  When enabled, defer to the
    //  base save (which calls pol_img_t::write, itself
    //  guarded by `output`).
    virtual void save( mesh::mesh_t & mesh,
                       binary_io::base_t & bio ) override
    {
        if( enabled )
            particle::radiation::base_t::save( mesh, bio );
        return;
    };
};

}  //  namespace prob
