#pragma once

#include <cstring>
#include <chrono>

#include "../../src/utilities/mapping/loop.h"
#include "../../usr/extension/algo/interp.h"

#include "pool.h"

namespace prob
{

////////////////////////////////////////////////////////////
//  Types
////////////////////////////////////////////////////////////

using interp_t = extension::interp_t< float, 3 >;

////////////////////////////////////////////////////////////
//  GPU kernel: initialize radiation fields by
//  sampling the device-resident interp_t tables
//  at cell centers.
////////////////////////////////////////////////////////////

template< class bdt_T, class ini_T >
__global__ void init_rad_fields_kernel
( const bdt_T bdt, const ini_T ini )
{
    type::idx_t i;
    i[ 0 ] = threadIdx.x;
    i[ 1 ] = blockIdx.x;
    i[ 2 ] = blockIdx.y;

    type::coord_t x;
    bdt.geo.x_cc( x, i );
    bdt.rad.mfp_i_sca_0( i )
        = utils::max( ini.f_mfp_i_sca_0( x ), 0 );
    bdt.rad.mfp_i_abs_0( i )
        = utils::max( ini.f_mfp_i_abs_0( x ), 0 );
    bdt.rad.b_sca( i ) = utils::max( ini.f_b_sca( x ), 0 );
    //  Emissivity field is optional:
    //  missing -> 0 everywhere.
    const auto emiss = ini.f_emiss
        ? utils::max( ini.f_emiss( x ), 0 ) : 0;
    bdt.rad.emiss( i ) = emiss;

    auto * p_v = bdt.rad.vel.at( i );
    for( int a = 0; a < 3; ++ a )
        p_v[ a ] = ini.f_vel[ a ]( x );
    return;
}

////////////////////////////////////////////////////////////
//  Radiation driver
////////////////////////////////////////////////////////////

class radiation_t
    : public particle::radiation::base_t
{
public:
    struct ini_t
    {
        //  Line-dependent ( change per cycle /
        //  per line )
        interp_t f_mfp_i_sca_0;
        interp_t f_mfp_i_abs_0;
        interp_t f_emiss;
        //  Line-independent ( bulk velocity,
        //  thermal b )
        interp_t f_b_sca;
        interp_t f_vel[ 3 ];

        bool ray_output;
        int  ray_id;

        //  Imaging configuration (read from
        //  par, mirrored into rad_t via
        //  block_yield so the device proxy
        //  sees them).
        bool imaging = false;
        int  n_chan  = 0;

        void read( const input & args )
        {
            binary_io::default_t bio;
            bio.open( args.get< std::string >
                ( "line_rt", "field_file" ),
                "r" );
            bio.load(  );

            f_mfp_i_sca_0.read_bin( bio, "mfp_i_sca_0_" );
            f_mfp_i_abs_0.read_bin( bio, "mfp_i_abs_0_" );
            f_emiss.read_bin      ( bio, "emiss_"       );
            f_mfp_i_sca_0.set_nearest(  );
            f_mfp_i_abs_0.set_nearest(  );
            f_emiss.set_nearest(  );

            //  Read from field_fixed_file if specified;
            //  otherwise fall back to field_file (backward
            //  compatibility with single-file workflow).
            const auto fixed_file
                = args.get< std::string >
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

            ray_output = args.get< bool >
                  ( "line_rt", "ray_output", false );
            ray_id = args.get< int >
                  ( "line_rt", "ray_id", -1 );

            imaging = args.get< bool >
                  ( "imaging", "enabled", false );
            n_chan  = args.get< int >
                  ( "imaging", "n_chan", 0 );
            return;
        };
        
        //  Move all interp_t tables to device global
        //  memory.  Must be called after p_dev is
        //  available, in init( ), NOT in read( ).
        void to_device( device::base_t & dev )
        {
            f_mfp_i_sca_0.to_device( dev );
            f_mfp_i_abs_0.to_device( dev );
            if( f_emiss )
                f_emiss.to_device( dev );
            f_b_sca.to_device( dev );
            for( int a = 0; a < 3; ++ a )
                f_vel[ a ].to_device( dev );
        }

        //  Free device-resident tables after
        //  initialization is complete.
        void free_device
        ( device::base_t & dev )
        {
            f_mfp_i_sca_0.free_device( dev );
            f_mfp_i_abs_0.free_device( dev );
            if( f_emiss )
                f_emiss.free_device( dev );
            f_b_sca.free_device( dev );
            for( int a = 0; a < 3; ++ a )
                f_vel[ a ].free_device( dev );
        }
    };

protected:
    ini_t ini;
    bool  profile = false;

protected:
    virtual void init_cond
    ( mesh::block::dual_t & d ) override
    {
        auto & b_h = prx_t::ref( d.h(  ) );
        auto & b_d = prx_t::ref( d.d(  ) );
        b_d.set_output( true );
        b_h.set_output( true );

        //  Zero ALL field memory (including
        //  ghost cells) on the device to
        //  prevent garbage reads from ghost
        //  zones.
        auto & dev( * p_dev );
        const auto f_null = [ & ]( auto & arr )
        {
            dev.f_mset( arr.dat, 0, arr.n_size,
                        d.stream );
        };
        f_null( b_d.rad.mfp_i_sca_0 );
        f_null( b_d.rad.mfp_i_abs_0 );
        f_null( b_d.rad.b_sca );
        f_null( b_d.rad.vel );
        f_null( b_d.rad.flx );
        f_null( b_d.rad.excitation_flux );
        f_null( b_d.rad.emiss );
        //  j_cam is only allocated when imaging is on; zero
        //  it unconditionally (n_size == 0 -> no-op when
        //  off).
        f_null( b_d.rad.j_cam );

        const dim3 n_th( b_h.geo.n_ceff[ 0 ] );
        const dim3 n_bl( b_h.geo.n_ceff[ 1 ] ,
                         b_h.geo.n_ceff[ 2 ] );

        dev.launch( init_rad_fields_kernel, n_bl, n_th, 0,
                    d.stream, b_d, ini );
        dev.sync_stream( d.stream );

        //  Set scalar flags on both host and
        //  device blocksq so they propagate
        //  to the device proxy at step time.
        b_d.rad.ray_output = ini.ray_output;
        b_d.rad.ray_id     = ini.ray_id;
        b_h.rad.ray_output = ini.ray_output;
        b_h.rad.ray_id     = ini.ray_id;
        b_d.rad.imaging    = ini.imaging;
        b_h.rad.imaging    = ini.imaging;
        b_d.rad.n_chan     = ini.n_chan;
        b_h.rad.n_chan     = ini.n_chan;
        //  Skipping copy_h2d as init done
        //  on GPU
    }

public:
    virtual void read( const input & args ) override
    {
        enroll< prx_t, pol_t, gen_t, intg_t >(  );
        ini.read( args );
        profile = args.get< bool >
            ( "profile", "enabled", false );
        //  When imaging is on, the
        //  scattering integrator must NOT
        //  zero j_cam in pre_proc each step:
        if( ini.imaging )
        {
            auto & itg
                = dynamic_cast< intg_t & >
                  ( * p_itg );
            itg.zero_j_cam = false;
        }
        //  Override block_yield to also
        //  propagate the imaging flags
        //  (imaging, n_chan) into rad_t on
        //  each block, so block_data_t::
        //  setup() allocates j_cam with
        //  the right n_int and the device
        //  proxy sees the flags.
        auto base_yield = this->block_yield;
        this->block_yield = [ this, base_yield ]
            ( mesh::block_t & b, mesh::mesh_t & m )
        {
            auto     p = base_yield( b, m );
            auto & b_h = prx_t::ref( p->h(  ) );
            auto & b_d = prx_t::ref( p->d(  ) );
            b_h.rad.imaging = ini.imaging;
            b_h.rad.n_chan  = ini.n_chan;
            b_d.rad.imaging = ini.imaging;
            b_d.rad.n_chan  = ini.n_chan;
            return p;
        };
        particle::radiation::base_t::read( args );
    }

    virtual void init( const  input & args ,
                       mesh::mesh_t & mesh ) override
    {
        mesh.p_dev->prep_rng
        ( args.get< int > ( "line_rt", "num_rng", 16381 ) );
        //  Move field interpolation tables to device global
        //  memory before init_cond
        ini.to_device( * mesh.p_dev );
        particle::radiation::base_t::init( args, mesh );
        return;
    };

    virtual void finalize( mesh::mesh_t & mesh ) override
    {
        //  Free device-resident interp_t
        //  tables once field initialization
        //  is complete.
        ini.free_device( * mesh.p_dev );
        particle::base_t::finalize( mesh );
    }

    virtual void step( mesh::mesh_t & mesh ) override
    {
        mesh.p_cyc->redc_dt_start ( mesh );
        mesh.p_cyc->redc_dt_finish( mesh );
        for( auto & d : ( * this ) )
            d.d(  ).dt = ( * mesh.p_cyc->p_dt_h );
        auto t0 = std::chrono::steady_clock::now(  );
        particle::base_t::step( mesh );
        auto t1 = std::chrono::steady_clock::now(  );
        if( profile )
        {
            std::cout << "[profile] mcrt:   "
                << std::chrono::duration< double >
                   ( t1 - t0 ).count(  )<< " s\n";
        }
        return;
    };
};

}  //  namespace prob
