#pragma once

#include "../../src/modules/particle/radiation/radiation.h"
#include "../../src/modules/particle/radiation/photon.h"

namespace prob
{

////////////////////////////////////////////////////////////
//  Types and constants
////////////////////////////////////////////////////////////

using type::  idx_t;
using type::float_t;
using type::coord_t;

constexpr type::float_t sqrt_2( 1.4142135623731 );

////////////////////////////////////////////////////////////
//  Utility function for Voigt sampling
//  -- not used now
////////////////////////////////////////////////////////////

__device__ __forceinline__
float_t voigt_H( const float_t & a, const float_t & u )
{
    const float_t u2 = u * u;
    if( a < 1e-6f )
        return expf( -u2 );
    const float_t wing = a / ( u2 + a * a + 1e-38f )
                       * float_t( 0.5641895835477563 );
    const float_t core = expf( -u2 );
    const float_t u0 = sqrtf
        ( logf( core > 1e-38f ? wing / core + 1 : 1e36f ) );
    const float_t w = 0.5f + 0.5f
        * tanhf( ( sqrtf( u2 ) - u0 ) * 2 );
    return core * ( 1 - w ) + wing * w;
}

////////////////////////////////////////////////////////////
//  The line_rt_photon_t class
////////////////////////////////////////////////////////////

template< class derived_T = crtp::dummy_t >
struct line_rt_photon_t
    : particle::radiation::photon::cart_t
    < crtp::helper< line_rt_photon_t, derived_T > >
{
    ////////// Types //////////
    using super_t = particle::radiation::photon::cart_t
          < crtp::helper< line_rt_photon_t, derived_T > >;
    using geo_loc_t = particle::geo_loc_t;
    __crtp_def_self__( line_rt_photon_t, derived_T );

    ////////// Data //////////
    using super_t::     x;
    using super_t::     i;
    using super_t::   dir;
    using super_t::  ib_l;
    using super_t::  step;
    using super_t::  dest;
    using super_t::proper;

    int            n_scat;
    float_t            sv;
    float_t           vel;
    float_t      proper_0;
    float_t    tau_remain;
    coord_t   x_last_scat;

    ////////// Functions //////////
    __host__ __device__ __forceinline__
    void load( line_rt_photon_t & src )
    {
        ( * this ) = src;
    }
    __host__ __device__ __forceinline__
    void save( line_rt_photon_t & tgt )
    {
        tgt = ( * this );
    }
    __host__ __device__ __forceinline__
    void move( line_rt_photon_t & tgt )
    {   //  No variable-length extra data, move is trivial
        tgt = ( * this );
    }

    template< class x_T, class prx_T,
              class itg_T >
    __device__ __forceinline__ void proc_phys
    ( const int & a_proc, const x_T & dl,
      const geo_loc_t & g_l,const prx_T & prx,
      const itg_T & itg )
    {
        //  All operations moved to proc_geo, no-op here
    }

    //  Stand-alone scattering function template
    template< class f_T, class itg_T >
    __device__ __forceinline__ void scat
    ( const f_T &    dl_a, const     f_T & b_sca,
      const f_T & vel_obs, const coord_t &  v_cc,
      const itg_T & itg )
    {
        const auto vel_lab_old = vel + vel_obs;
        const float_t dir_old[ 3 ]
            = { dir[ 0 ], dir[ 1 ], dir[ 2 ] };

        //  Record the last-scattering position BEFORE
        //  moving (the scattering happens at the current
        //  position).
        for( int a = 0; a < 3; ++ a )
            x_last_scat[ a ] = x[ a ];

        for( int a = 0; a < 3; ++ a )
            x[ a ] += dl_a * dir[ a ];

        const auto mu
            = 2 * device::rand_dev(  ) - 1;
        const auto smu
            = sqrtf( 1 - mu * mu );
        const auto phi
            = 6.28318531f * device::rand_dev(  );
        dir[ 0 ] = smu * cosf( phi );
        dir[ 1 ] = smu * sinf( phi );
        dir[ 2 ] = mu;

        const auto u1 = device::rand_dev(  );
        const auto u2 = device::rand_dev(  );
        const auto r  = sqrtf( -2 * logf( u1 + 1e-35f ) );
        //  Redistribution is done in the gas rest frame, so
        //  the new vel is first set to the gas-frame
        //  outgoing frequency offset dv_new, then converted
        //  to the stored convention vel = dv_new -
        //  vel_obs_new (where vel_obs_new = dir_new
        //  . v_bulk) so that later dv = vel + vel_obs
        //  recovers dv_new.
        if( itg.ph_mode == 0 )
            vel = r * cosf( 6.283185307f * u2 )
                * b_sca / sqrt_2;
        else
        {
            const float_t x_freq
                = vel_lab_old / b_sca;

            float_t g( 0 );
            for( int a = 0; a < 3; ++ a )
                g += dir_old[ a ] * dir[ a ];
            const auto sin_g
                = sqrtf( fmaxf( 0, 1 - g * g ) );

            const auto u_par
                = itg.riia.sample_upar( x_freq );
            const auto u_perp = r
                * cosf( 6.283185307f * u2 ) / sqrt_2;
            const auto x_new = x_freq
                + u_par * ( g - 1 ) + sin_g * u_perp;
            vel = x_new * b_sca;
        }
        //  Convert gas-frame offset to stored convention:
        //  vel = dv_new - dir_new . v_bulk
        for( int a = 0; a < 3; ++ a )
            vel -= dir[ a ] * v_cc[ a ];
        sv = b_sca / sqrt_2;
        tau_remain = -logf( 1e-4f + 0.9999f
                            * device::rand_dev(  ) );
        -- n_scat;
        return;
    };

    template< class x_T, class prx_T, class itg_T >
    __device__ __forceinline__ void proc_geo
    ( const int & a_proc, const x_T & dl,  geo_loc_t & g_l,
      const prx_T &  prx, const itg_T & itg )
    {
        coord_t         v_cc;
        float_t vel_obs( 0 );
        const auto * p_vc = prx.rad.vel.at( i );
        for( int a = 0; a < 3; ++ a )
        {
            v_cc[ a ] = p_vc[ a ] ;
            vel_obs  += v_cc[ a ] * dir[ a ];
        }
        const auto dv2 = ( vel + vel_obs )
                       * ( vel + vel_obs );

        auto mfp_i_s0 = prx.rad.mfp_i_sca_0.at( i )[ 0 ];
        auto mfp_i_a0 = prx.rad.mfp_i_abs_0.at( i )[ 0 ];
        auto b_sca    = prx.rad.      b_sca.at( i )[ 0 ];
        b_sca = __max1( b_sca, 1e-19f );

        auto u2 = ( dv2 > 0 ? dv2 : 0 ) / ( b_sca * b_sca );
        if( __isinf( u2 ) || __isnan( u2 ) )
            u2 = 1e32f;
        const auto u( sqrtf( u2 ) );

        //  The voigt H function value
        float_t H( 0 );
        if( itg.a_voigt > 1e-6f )
        {
            if( itg.ph_mode == 3 )
                H = voigt_H( itg.a_voigt, u );
            else
                H = itg.voigt_H( itg.a_voigt, u );
        }
        else if( u2 < 1e2f )
            H = expf( - u2 );
        const auto mfp_i_s = mfp_i_s0 * H;
        auto dl_a = dl[ a_proc ];
        const auto dtau_s = dl_a * mfp_i_s;

        bool is_scattered( true );
        //  n_scat takes action here!!!
        if( n_scat > 0 && dtau_s > tau_remain )
        {
            //  Rescale dl_a; also used in
            //  absorption.
            dl_a *= tau_remain / ( dtau_s + 1e-35f );
            scat( dl_a, b_sca, vel_obs,  v_cc, itg );
        }
        else
        {
            is_scattered = false;
            tau_remain -= dtau_s;
        }

        //  Absorption
        const auto dtau_a = __max1( dl_a * mfp_i_a0, 0 );
        const auto e_mtau = expf( -dtau_a );
        const auto dsi = dl[ a_proc ] / prx.geo.volume( i );
        const auto flx = proper * dsi
            * ( dtau_a > 1e-3f
                ? ( 1 - e_mtau ) / dtau_a  : 1 );

        atomicAdd( prx.rad.flx.at( i ), flx );
        atomicAdd( prx.rad.excitation_flux.at( i ),
                   flx * H );
        proper *= e_mtau;

        //  Imaging: accumulate j_cam per channel.  Note:
        //  This is NOT a blackbody term! The line
        //  emissivity comes from the input emiss field.
        if( itg.imaging && itg.n_chan > 0 )
        {
            //  dir_cam . v_bulk (gas bulk projected onto
            //  the camera LOS; dir_cam points INTO the
            //  domain).
            float_t vobs_cam( 0 );
            for( int a = 0; a < 3; ++ a )
                vobs_cam += itg.dir_cam[ a ] * v_cc[ a ];

            //  g = photon direction . camera direction
            float_t g_dot( 0 );
            for( int a = 0; a < 3; ++ a )
                g_dot += dir[ a ] * itg.dir_cam[ a ];

            //  Photon gas-frame frequency in b units
            const auto x_pp = ( vel + vel_obs ) / b_sca;

            //  Extinction-in-cell correction factor
            const auto d_tau_e = dl[ a_proc ]
                     * ( mfp_i_s + mfp_i_a0 );
            float_t corr( 1 );
            if( d_tau_e > 1e-4f )
                corr = ( 1 - expf( - d_tau_e ) ) / d_tau_e;
            //  base == F_pp / ( 4 * pi ) * correction
            auto base = flx * corr * 0.0795775f / b_sca;
            //  b_sca on the denominator for voigt_H
            //  dimension recovery

            auto * j = prx.rad.j_cam.at( i );
            for( int k = 0; k < itg.n_chan; ++ k )
            {
                //  Camera-resonant frequency in b units
                const auto x_out
                    = ( itg.d_v_chan[ k ] + vobs_cam )
                    / b_sca;
                const auto R = itg.riia.lookup
                      ( x_out, x_pp, g_dot );
                atomicAdd( j + k, mfp_i_s * base * R );
            }
            //  mfp_i_s = mfp_i_s0 * H( a, x_pp ), Voigt at
            //  the photon's INCOMING frequency.
        }

        if( ! is_scattered )
            super_t::proc_geo( a_proc, dl, g_l, prx, itg );
        //  Absorption takes action regardless of scattering
        return;
    };

    template< class bmp_T, class itg_T >
    __device__ __forceinline__ bool proc_step
    ( type::coord_t & dl, geo_loc_t   & g_l ,
      const bmp_T & bmap, const itg_T & itg )
    {
        const auto proc_flag = super_t::proc_step
                             ( dl, g_l, bmap, itg );
        if( step <= 0 )
        {
            dest.i_rank = -1;
            return false;
        }
        if( itg.proper_min_frac > 0 &&
            proper < itg.proper_min_frac * proper_0 )
        {
            dest.todo = particle::to_rm;
            return false;
        }
        -- step;
        return proc_flag;
    }
};  //  struct line_rt_photon_t

}  //  namespace prob
