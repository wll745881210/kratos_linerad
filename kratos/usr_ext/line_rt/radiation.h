#include <cstring>
#pragma once

#include "../../src/utilities/mapping/loop.h"
#include "../../usr/extension/algo/interp.h"
#include "pool.h"

namespace prob
{
////////////////////////////////////////////////////////////
// Types

using interp_t = extension::interp_t< float, 3 >;

////////////////////////////////////////////////////////////
// GPU kernel: initialize radiation fields by sampling the
// device-resident interp_t tables at cell centers.

template< class bdt_T, class ini_T >
__global__ void init_rad_fields_kernel
( const bdt_T bdt, const ini_T ini )
{
    type::idx_t i;
    i[ 0 ] = threadIdx.x;
    i[ 1 ] =  blockIdx.x;
    i[ 2 ] =  blockIdx.y;

    type::coord_t x;
    bdt.geo.x_cc( x, i );
    bdt.rad.mfp_i_sca_0( i ) = utils::max
                       ( ini.f_mfp_i_sca_0( x ), 0 );
    bdt.rad.mfp_i_abs_0( i ) = utils::max
                       ( ini.f_mfp_i_abs_0( x ), 0 );
    bdt.rad.b_sca( i ) = utils::max( ini.f_b_sca( x ), 0 );
    // Emissivity field is optional: missing -> 0 everywhere.
    const auto emiss = ini.f_emiss
        ? utils::max( ini.f_emiss( x ), 0 ) : 0;
    bdt.rad.emiss( i ) = emiss;

    auto * p_v = bdt.rad.vel.at( i );
    for( int a = 0; a < 3; ++ a )
        p_v[ a ] = ini.f_vel[ a ]( x );

    // When imaging is on, seed s_cam with the line emissivity
    // source function.  For a two-level atom the source
    // function is frequency-independent:
    //   S(v) = j(v) / alpha(v)
    //        = [emiss * phi_norm(v)] / [mfp_s * phi_unnorm(v)]
    //        = emiss / (mfp_s * sqrt(pi) * b)     (Gaussian)
    // where emiss = n_u*A_ul/(4*pi)  [photons cm^-3 s^-1 sr^-1]
    // (per steradian, 4pi already included), phi_norm is the
    // normalised profile (integral = 1), and phi_unnorm (peak=1)
    // cancels with the 1/(sqrt(pi)*b) normalisation.  This is
    // NOT a blackbody term — the line emissivity comes entirely
    // from the Python-calculated emiss field, not from B_nu.
    // The MC scattering pass then ADDS the scattering source on
    // top via atomicAdd in proc_phys.
    if( bdt.rad.imaging && bdt.rad.n_chan > 0 )
    {
        const auto mfp_s = bdt.rad.mfp_i_sca_0( i );
        const auto b_val = bdt.rad.b_sca( i );
        const auto s_emiss = ( mfp_s > 0 && b_val > 0 )
            ? emiss / ( mfp_s * 1.77245385f * b_val ) : 0;
        auto * s = bdt.rad.s_cam.at( i );
        for( int k = 0; k < bdt.rad.n_chan; ++ k )
            s[ k ] = s_emiss;
    }
    return;
}

////////////////////////////////////////////////////////////
// Radiation driver

class radiation_t : public particle::radiation::base_t
{
public:                         // Type
    struct ini_t
    {
        // Line-dependent ( change per cycle / per line )
        interp_t f_mfp_i_sca_0;
        interp_t f_mfp_i_abs_0;
        interp_t        f_emiss;      // line-centre emissivity
        // Line-independent ( bulk velocity, thermal b ) 
        interp_t       f_b_sca;
        interp_t    f_vel[ 3 ];
        
        bool ray_output;
        int      ray_id;

        // Imaging configuration (read from par, mirrored into
        // rad_t via block_yield so the device proxy sees them).
        bool imaging = false;
        int   n_chan =       0;

        void read( const input & args )
        {
            binary_io::default_t bio;
            bio.open( args.get<std::string>
                ( "line_rt", "field_file" ), "r" );
            bio.load(  );

            f_mfp_i_sca_0.read_bin( bio, "mfp_i_sca_0_" );
            f_mfp_i_abs_0.read_bin( bio, "mfp_i_abs_0_" );
            // Line-centre emissivity j0 = n_u*A_ul/(4*pi*sqrt(pi)*b)
            // (photon-number, code units).  Optional: missing key
            // leaves the table empty -> samples as 0 everywhere,
            // so non-imaging / legacy field files still work.
            f_emiss.read_bin( bio, "emiss_" );
            // Clamp out-of-grid samples to the nearest edge
            // value, so the interpolant effectively covers
            // the whole mesh domain between the boundary
            // coordinates (a zero fill would silently
            // produce zero opacity when the field grid is
            // narrower than the mesh).
            f_mfp_i_sca_0.set_nearest(  );
            f_mfp_i_abs_0.set_nearest(  );
            f_emiss.      set_nearest(  );

            // ---- Line-independent fields ----
            // Read from field_fixed_file if specified;
            // otherwise fall back to field_file (backward
            // compatibility with single-file workflow).
            const auto fixed_file = args.get<std::string>
                ( "line_rt", "field_fixed_file", "" );
            if( ! fixed_file.empty(  ) )
            {
                bio.close(  );
                bio.open ( fixed_file, "r" );
                bio.load (  );
            }
            f_b_sca.read_bin( bio, "b_sca_" );
            f_b_sca.set_nearest(  );

            for( int a = 0; a < 3; ++ a )
            {
                f_vel[ a ].read_bin
                ( bio, "vel_" + std::to_string( a ) + "_" );
                f_vel[ a ].set_nearest(  );
            }
            bio.close(  );

            ray_output = args.get<bool>
                ( "line_rt", "ray_output", false );
            ray_id = args.get<int>
                ( "line_rt", "ray_id",        -1 );

            imaging = args.get<bool>
                ( "imaging", "enabled", false );
            n_chan  = args.get<int>
                ( "imaging", "n_chan",        0 );
            return;
        };        

        // Move all interp_t tables to device global memory.
        // Must be called after p_dev is available, in init(
        // ), NOT in read( ).
        void to_device( device::base_t & dev )
        {
            f_mfp_i_sca_0.to_device( dev );
            f_mfp_i_abs_0.to_device( dev );
            if( f_emiss ) f_emiss.to_device( dev );
            f_b_sca.      to_device( dev );
            for( int a = 0; a < 3; ++ a )
                f_vel[ a ].to_device( dev );
            return;
        };

        // Free device-resident tables after initialization
        // is complete.
        void free_device( device::base_t & dev )
        {
            f_mfp_i_sca_0.free_device( dev );
            f_mfp_i_abs_0.free_device( dev );
            if( f_emiss ) f_emiss.free_device( dev );
            f_b_sca.       free_device( dev );
            for( int a = 0; a < 3; ++ a )
                f_vel[ a ].free_device( dev );
            return;
        }
    };
protected:                      // Data
    ini_t ini;

protected:
    virtual void init_cond
    ( mesh::block::dual_t & d ) override
    {
        auto & b_h = prx_t::ref( d.h(  ) );
        auto & b_d = prx_t::ref( d.d(  ) );
        b_d.set_output( true );
        b_h.set_output( true );        

        // Zero ALL field memory (including ghost cells) on
        // the device to prevent garbage reads from ghost
        // zones.
        auto & dev( * p_dev );
        const auto f_null = [ & ] ( auto & arr )
        {
            dev.f_mset( arr.dat, 0, arr.n_size, d.stream );
        };
        f_null( b_d.rad.mfp_i_sca_0     );
        f_null( b_d.rad.mfp_i_abs_0     );
        f_null( b_d.rad.b_sca           );
        f_null( b_d.rad.  vel           );
        f_null( b_d.rad.  flx           );
        f_null( b_d.rad.excitation_flux );
        f_null( b_d.rad.  emiss         );
        // s_cam is only allocated when imaging is on; zero
        // it unconditionally (n_size == 0 -> no-op when off).
        f_null( b_d.rad.  s_cam        );

        const dim3 n_th( b_h.geo.n_ceff[ 0 ] );
        const dim3 n_bl( b_h.geo.n_ceff[ 1 ] ,
                         b_h.geo.n_ceff[ 2 ] );

        dev.launch( init_rad_fields_kernel, n_bl, n_th, 0,
                    d.stream, b_d, ini );
        dev.sync_stream( d.stream );

        // Set scalar flags on both host and device blocks so
        // they propagate to the device proxy at step time.
        b_d.rad.ray_output = ini.ray_output;
        b_d.rad.ray_id     = ini.    ray_id;
        b_h.rad.ray_output = ini.ray_output;
        b_h.rad.ray_id     = ini.    ray_id;
        b_d.rad.imaging    = ini.imaging;
        b_d.rad.  n_chan   = ini.  n_chan;
        b_h.rad.imaging    = ini.imaging;
        b_h.rad.  n_chan   = ini.  n_chan;
        return;  // Skipping copy_h2d as init done on GPU
    };          

public:
    virtual void read( const input & args ) override
    {
        enroll< prx_t, pol_t, gen_t, intg_t >(  );
        ini.read( args );
        // When imaging is on, the scattering integrator must
        // NOT zero s_cam in pre_proc each step: s_cam is
        // seeded with the line emissivity source function in
        // init_cond and accumulates the scattering source
        // across the whole MC pass.  Wiping it per step would
        // lose the emission seed and only keep the last
        // step's scattering contribution.
        if( ini.imaging )
        {
            auto & itg = dynamic_cast< intg_t & >( * p_itg );
            itg.zero_s_cam = false;
        }
        // Override block_yield to also propagate the imaging
        // flags (imaging, n_chan) into rad_t on each block,
        // so block_data_t::setup() allocates s_cam with the
        // right n_int and the device proxy sees the flags.
        auto base_yield = this->block_yield;
        this->block_yield =
            [ this, base_yield ]
            ( mesh::block_t & b, mesh::mesh_t & m )
            -> std::shared_ptr< mesh::block::dual_t >
        {
            auto p = base_yield( b, m );
            auto & b_h = prx_t::ref( p->h(  ) );
            auto & b_d = prx_t::ref( p->d(  ) );
            b_h.rad.imaging = ini.imaging;
            b_h.rad.  n_chan = ini.  n_chan;
            b_d.rad.imaging = ini.imaging;
            b_d.rad.  n_chan = ini.  n_chan;
            return p;
        };
        return particle::radiation::base_t::read( args );
    };

    virtual void init
    ( const input & args, mesh::mesh_t & mesh ) override
    {
        mesh.p_dev->prep_rng
        ( args.get<int>( "line_rt", "num_rng", 16381 ) );
        // Move field interpolation tables to device global
        // memory before init_cond launches the sampling
        // kernel.
        ini.to_device( * mesh.p_dev );
        return particle::radiation::base_t::init
               ( args,  mesh );
    };

    virtual void finalize( mesh::mesh_t & mesh ) override
    {   // Free device-resident interp_t tables once field
        // initialization is complete.
        ini.free_device( * mesh.p_dev );
        return particle::base_t::finalize( mesh );
    };
    virtual void step( mesh::mesh_t & mesh ) override
    {
        mesh.p_cyc->redc_dt_start ( mesh );
        mesh.p_cyc->redc_dt_finish( mesh );
        for( auto & d : ( * this ) )
            d.d(  ).dt = ( * mesh.p_cyc->p_dt_h );
        return particle::base_t::step( mesh );
    }
};

}
