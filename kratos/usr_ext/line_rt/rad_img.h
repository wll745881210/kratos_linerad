#pragma once

// Line-RT imaging driver (parasite of radiation_t).
//
// Enrolled alongside radiation_t in usr.cpp via
//   q->parasite(p);
// Shares the block_data (p_map) with radiation_t so the
// imaging rays see the MC-accumulated s_cam and the
// field arrays.  Runs its own (non-scattering) photon pool
// (pol_img_t) over the image-plane pixels after the
// scattering MC step.
//
// The imaging integrator (intg_t) reuses the same par keys
// as the scattering one (it rebuilds the Voigt / USampler
// tables, which is a small one-off cost) but its pre_proc
// is a no-op w.r.t. s_cam so it does not wipe the MC
// accumulation.

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

class rad_img_t : public particle::radiation::base_t
{
public:                         // Data
    bool enabled = false;
protected:                      // Functions
    virtual void init_cond
    ( mesh::block::dual_t & d ) override
    {
        return;  // Fields already initialised by radiation_t.
    };
public:
    virtual void read( const input & args ) override
    {
        enabled = args.get< bool >
                 ( "imaging", "enabled", false );
        enroll< prx_t, pol_img_t, gen_img_t, intg_t >(  );
        // Share the block map (and thus s_cam / fields) with
        // the scattering module.
        p_map = dynamic_cast< radiation_t & >
            ( * q_mod.lock(  ) ).p_map;
        // The imaging integrator must NOT zero s_cam in
        // pre_proc (it consumes the MC-accumulated source),
        // and must NOT rebuild the USampler / Voigt tables
        // (the scattering integrator already built them on a
        // separate instance; a second build overflows the
        // device const pool).  voigt_H falls back to the
        // analytic form.
        auto & itg = dynamic_cast< intg_t & >( * p_itg );
        itg.zero_s_cam = false;
        itg.build_tables = false;
        itg.zero_fields = false;
        return particle::radiation::base_t::read ( args );
    };

    virtual void init
    ( const input & args, mesh::mesh_t & mesh ) override
    {
        // Always run base init so sub-modules (pool, gen, itg)
        // are constructed and finalized symmetrically; the
        // actual imaging work is gated in step()/save().
        particle::radiation::base_t::init( args, mesh );
        // Imaging ray tracing always uses classic one-thread-per-
        // photon scheduling: each photon is one fixed ray-march
        // with no scattering and no lifetime imbalance, so the
        // worker work-queue gives no benefit (and the imaging
        // photons are not designed for it).  Must be set AFTER
        // base_t::init() above, because intg_t::init() reads
        // worker_mode from par and would otherwise overwrite it.
        dynamic_cast< intg_t & >( * p_itg ).worker_mode = false;
        return;
    };

    virtual void step( mesh::mesh_t & mesh ) override
    {
        if( enabled )
            particle::radiation::base_t::step( mesh );
        return;
    };

    // Skip the imaging-pool save entirely when imaging is
    // disabled: the pool was never generated (par == nullptr,
    // n_par == 0) and the default f_par_save would dereference
    // it.  When enabled, defer to the base save (which calls
    // pol_img_t::write, itself guarded by `output`).
    virtual void save
    ( mesh::mesh_t & mesh, binary_io::base_t & bio ) override
    {
        if( enabled )
            particle::radiation::base_t::save( mesh, bio );
        return;
    };
};

}  // namespace prob
