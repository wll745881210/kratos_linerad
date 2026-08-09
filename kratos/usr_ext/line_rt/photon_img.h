#pragma once

//  Line-RT imaging photon: a non-scattering
//  ray that marches from the far boundary toward
//  the camera and integrates the scalar transfer
//  equation
//      dI_k / dtau_k = -I_k + S_k
//  per velocity channel k, with
//      tau_k = ( mfp_i_sca_0 * H(a, dv_cam/b)
//              + mfp_i_abs_0 ) * dl,
//      S_k   = ( mfp_i_sca_0 * H(a, dv_cam/b)
//               / alpha_tot )
//               * j_cam[ i, k ],
//  where dv_cam = v_chan[k] + dir_cam . v_bulk(i)
//  is the gas-frame offset that resonates at
//  cell i for channel k.
//
//  j_cam carries the SCATTERING source
//  (accumulated during the MC pass with
//  sigma(v_in) * R * J).  The thermal (line
//  emission) source is added directly here as
//  a per-channel emissivity
//  j_thermal(v) = emiss * H(a, v) / (sqrt(pi) * b),
//  using the Voigt profile at the OUTGOING
//  (channel) frequency.  This ensures
//  frequency-dependent imaging even for
//  optically thin lines (where the scattering
//  source is negligible).
//
//  The imaging photon reuses the scattering
//  integrator's camera / channel configuration
//  (intg_t.dir_cam, d_v_chan, n_chan, img_*).
//  It does NOT scatter and does NOT accumulate
//  flx / excitation_flux / j_cam.

#include "../../src/modules/particle/radiation/photon.h"

namespace prob
{

constexpr int MAX_N_CHAN = 256;

template< class derived_T = crtp::dummy_t >
struct line_img_t
    : particle::radiation::photon::cart_t
    < crtp::helper< line_img_t, derived_T > >
{
    //  Types
    using super_t
        = particle::radiation::photon::cart_t
        < crtp::helper< line_img_t, derived_T > >;
    using geo_loc_t = particle::geo_loc_t;
    __crtp_def_self__( line_img_t, derived_T );

    //  Data
    using super_t::x;
    using super_t::i;
    using super_t::dir;
    using super_t::ib_l;
    using super_t::step;
    using super_t::dest;
    using super_t::proper;

    //  pixel index (ix, iy)
    int        i2d[ 2 ];
    //  per-channel intensity (per unit
    //  velocity)
    float_t    I_chan[ MAX_N_CHAN ];
    //  cached n_chan for save/load
    int        n_chan_local;

    __host__ __device__ __forceinline__
    void load( line_img_t & src )
    { ( * this ) = src; }
    __host__ __device__ __forceinline__
    void save( line_img_t & tgt )
    { tgt = ( * this ); }
    __host__ __device__ __forceinline__
    void move( line_img_t & tgt )
    { tgt = ( * this ); }

    //  Transfer integration (replaces the
    //  scattering proc_phys).  No flx /
    //  excitation_flux / j_cam accumulation;
    //  only the per-channel formal solution.
    template< class x_T, class prx_T,
              class itg_T >
    __device__ __forceinline__
    void proc_phys
    ( const int & a_proc,
      const x_T & dl,
      const geo_loc_t & g_l,
      const prx_T & prx,
      const itg_T & itg )
    {
        const auto b = prx.rad.b_sca.at( i )[ 0 ];
        auto mfp_i_s0
            = prx.rad.mfp_i_sca_0.at( i )[ 0 ];
        auto mfp_i_a0
            = prx.rad.mfp_i_abs_0.at( i )[ 0 ];
        const auto * v_cc
            = prx.rad.vel.at( i );

        //  dir_cam . v_bulk : the gas bulk
        //  projected onto the camera LOS
        //  (dir_cam points INTO the domain).
        float_t vobs_cam( 0 );
        for( int a = 0; a < 3; ++ a )
            vobs_cam
                += itg.dir_cam[ a ] * v_cc[ a ];

        const auto dl_seg = dl[ a_proc ];
        const auto * j
            = prx.rad.j_cam.at( i );
        const auto emiss_v
            = prx.rad.emiss.at( i )[ 0 ];
        //  1 / ( sqrt( pi ) * b )
        const auto inv_pb
            = 0.5641895835477563f / b;

        const int nch = itg.n_chan;
        for( int k = 0; k < nch; ++ k )
        {
            auto dv_cam
                = itg.d_v_chan[ k ] + vobs_cam;
            auto u       = dv_cam / b;
            auto H       = itg.voigt_H
                ( itg.a_voigt, u );
            auto alpha_t = mfp_i_s0 * H
                + mfp_i_a0;
            if( alpha_t <= 0 )
                continue;  //  negligible
            const auto dtau
                = alpha_t * dl_seg;
            //  Intrinsic line emissivity in
            //  Voigt profile:
            //  j = emiss * H(a, x_out)
            //      / (sqrt(pi) * b)
            const auto j_rad
                = emiss_v * H * inv_pb;
            const auto j_tot
                = j[ k ] + j_rad;
            if( dtau < 1e-4f )
                I_chan[ k ] += j_tot * dl_seg;
            else
            {
                const auto edtau
                    = expf( - dtau );
                I_chan[ k ]
                    = I_chan[ k ] * edtau
                    + j_tot / alpha_t
                    * ( 1 - edtau );
            }
        }
    }

    //  proc_geo: pure geometric move (base
    //  cart_t).  No scattering.  Inherited
    //  as-is.

    //  Per-pixel entry: set up the camera ray
    //  and run the ray-march loop (mirrors
    //  polarized_img_t::proc).
    template< class map_T, class itg_T >
    __device__
    int proc( const map_T & bmap,
              const itg_T & itg )
    {
        const auto j
            = utils::th_id< int >(  );
        //  Pixel index from the linear
        //  thread id.
        i2d[ 1 ] = j / itg.img_n[ 0 ];
        i2d[ 0 ] = j - i2d[ 1 ]
            * itg.img_n[ 0 ];
        if( i2d[ 1 ] >= itg.img_n[ 1 ] )
        {
            dest.i_rank = -2;  //  off-image
            return -2;
        }
        n_chan_local = itg.n_chan;

        //  Pixel centre in the camera frame
        //  (z = 0), then rotated into the
        //  domain frame by q_cam.
        type::coord_t x0_z, x0;
        x0_z[ 2 ] = 0;
        for( int a = 0; a < 2; ++ a )
            x0_z[ a ]
                = i2d[ a ] * itg.img_dx[ a ]
                + itg.img_x0[ a ];
        itg.rot3vec_cam( x0, x0_z );

        //  Ray direction = camera LOS (into
        //  the domain).  In the camera frame
        //  the LOS is +z, which q_cam maps to
        //  dir_cam in the domain frame.
        for( int a = 0; a < 3; ++ a )
            dir[ a ] = itg.dir_cam[ a ];

        //  Initialise per-channel intensities.
        for( int k = 0; k < n_chan_local; ++ k )
            I_chan[ k ] = 0.f;
        proper = 0.f;
        dest.todo = particle::to_keep;

        //  Start position: the far boundary
        //  along dir_cam.
        const auto & x_min( bmap.xlim[ 0 ] );
        const auto & x_max( bmap.xlim[ 1 ] );
        float_t dl_min( 1e32f );
        for( int a = 0; a < 3; ++ a )
        {
            if( dir[ a ] == 0 )
                continue;
            const auto x_tgt
                = ( dir[ a ] < 0 )
                  ? x_max[ a ] : x_min[ a ];
            const auto dl_a
                = ( x0[ a ] - x_tgt ) / dir[ a ];
            if( dl_a >= 0 && dl_a < dl_min )
                dl_min = dl_a;
        }
        for( int a = 0; a < 3; ++ a )
            x[ a ] = x0[ a ] - dl_min
                * dir[ a ] * 0.9999f;

        //  Find the containing block.
        ib_l = -1;
        for( int ib = 0; ib < bmap.n_prx; ++ ib )
        {
            const auto & geo = bmap[ ib ].geo;
            bool inside( true );
            for( int a = 0; a < 3; ++ a )
            {
                const auto xa
                    = geo.x_fc( a, 0 );
                const auto xb = geo.x_fc
                    ( a, geo.n_ceff[ a ] );
                if( x[ a ] < xa
                    || x[ a ] > xb )
                { inside = false; break; }
            }
            if( inside )
            {
                ib_l = ib;
                break;
            }
        }
        if( ib_l < 0 )
        {
            dest.i_rank = -2;
            return -2;
        }
        //  Cell index within the block.
        const auto & geo0
            = bmap[ ib_l ].geo;
        for( int a = 0; a < 3; ++ a )
            i[ a ] = int
                ( ( x[ a ] - geo0.x_fc( a, 0 ) )
                  / geo0.dx0[ a ] );
        step = itg.img_step_max;
        //  Run the inherited ray-march loop.
        return super_t::proc( bmap, itg );
    }
};

}  //  namespace prob
