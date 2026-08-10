#pragma once

#include "../../usr/extension/algo/interp.h"

#include "voigt_table_data.h"
#include "riia_table.h"

namespace prob
{
////////////////////////////////////////////////////////////
//  Types
////////////////////////////////////////////////////////////

using type::   idx_t;
using type:: float_t;
using type:: coord_t;
using type::float2_t;

////////////////////////////////////////////////////////////
//  Integrator type
////////////////////////////////////////////////////////////

struct intg_t : particle::integrate::base_t< intg_t >
{
    ////////// Types //////////
    using super_t = particle::integrate::base_t< intg_t >;
    using intp2_t = ::extension::interp_t  < float_t, 2 >;

    ////////// Data //////////
    int         ph_mode;
    bool   free_dev_mem;  // On const mem: no need to free

    //  R_IIA + USampler (standalone struct) riia_table_t
    riia_table_t   riia;

    //  Voigt profile
    float_t voigt_a_min;
    float_t voigt_a_max;
    float_t voigt_u_min;
    float_t voigt_u_max;
    float_t     a_voigt;

    //  1D Voigt table (ph_mode=2): constant memory,
    //  log-space.  a_voigt is fixed per run, so 1D
    //  H(a_fixed, u) suffices.
    intp2_t voigt_interp{ 2 };
    float_t *   d_log_voigt_c;
    int                  n_vu;
    float_t          du_voigt;
    float_t       u_voigt_max;

    bool     imaging  = false;
    int      n_chan   = 0;
    
    float_t dir_cam[ 3 ];

    // Quaternion-based camera rotation
    float_t   q_cam[ 4 ];
    float_t   v_chan_min;
    float_t   v_chan_max;
    float_t    v_chan_dv;
    float_t   * d_v_chan;
    //  Image-plane grid (used by the imaging photon;
    //  harmless when imaging is off).
    float_t img_x0 [ 2 ];
    float_t img_dx [ 2 ];
    int     img_n  [ 2 ];
    int     img_step_max;
    //  When false, pre_proc does NOT zero j_cam (used by
    //  the imaging integrator, which must consume the j_cam
    //  accumulated by the scattering MC pass rather than
    //  wipe it).
    bool  zero_j_cam = true;
    bool  build_tables = true; // Imaging needs not builds
    bool  zero_fields  = true; // Imaging needs fields

    float_t proper_min_frac = 0.0f;
    
    bool  worker_mode = true;
    int   n_worker = 32768;

    //  Host-side interfaces
    __host__ intg_t(  ) : super_t(  )
    {
        //  riia_table_t has its own
        //  constructor with defaults.
        free_dev_mem = false;

        d_log_voigt_c = nullptr;
        n_vu          =    5000;
        du_voigt      =    0.01;
        u_voigt_max   =      50;

        voigt_a_min = VOIGT_A_MIN;
        voigt_a_max = VOIGT_A_MAX;
        voigt_u_min = VOIGT_U_MIN;
        voigt_u_max = VOIGT_U_MAX;

        //  Imaging defaults (no-op
        //  when imaging == false).
        d_v_chan   = nullptr;
        v_chan_min =       0;
        v_chan_max =       0;
        v_chan_dv  =       0;
        img_step_max = 65535;
        for( int a = 0; a < 3; ++ a )
            dir_cam[ a ] = 0;
        dir_cam[ 2 ] = 1; //  face-on by default
        for( int a = 0; a < 2; ++ a )
        {
            img_x0[ a ] = 0;
            img_dx[ a ] = 0;
            img_n [ a ] = 0;
        }
        return;
    };

    __host__ virtual void init
    ( const input & args, particle::base_t & mod ) override
    {
        ph_mode = args.get< int >
            ( "line_rt", "ph_mode", 0 );
        a_voigt = args.get< float_t >
            ( "line_rt", "a_voigt", 0.f );
        //  Proper-weight culling threshold (0 = disabled).
        proper_min_frac
            = args.get< float_t >
            ( "line_rt", "proper_min_frac", 0.f );
        //  Server-worker mode: workers fetch photons from a
        //  shared atomic counter until the pool is
        //  depleted.  Default ON (see member docstring).
        worker_mode = args.get< bool >
            ( "line_rt", "worker_mode", true );
        //  Persistent-worker grid size (default 32768).
        n_worker = args.get< int >
            ( "line_rt", "n_worker",    32768 );

        //  ---- Imaging configuration
        imaging = args.get< bool >
            ( "imaging", "enabled", false );
        n_chan = args.get< int >( "imaging", "n_chan", 0 );
        if( imaging && n_chan > 0 )
        {
            //  Camera direction (spherical theta, phi)
            float_t theta = args.get< float_t >
            ( "imaging", "dir_cam_theta",
              float_t( 0.7853981633974483 ) );
            float_t phi = args.get< float_t >
            ( "imaging", "dir_cam_phi", 0.f );
            dir_cam[ 0 ] = sinf( theta ) * cosf( phi );
            dir_cam[ 1 ] = sinf( theta ) * sinf( phi );
            dir_cam[ 2 ] = cosf( theta );

            //  Build the camera rotation quaternion q_cam
            //  that maps the camera frame (LOS = +z) onto
            //  dir_cam.  We use the minimal rotation from
            //  +z to dir_cam: axis = (z x dir_cam) / |z x
            //  dir_cam| angle = acos( z . dir_cam ) = acos(
            //  dir_cam.z ) quaternion q = (cos(a/2), axis *
            //  sin(a/2)).  Special case: dir_cam ~ +z ->
            //  identity; ~ -z -> 180-deg rotation about x.
            const float_t cz = dir_cam[ 2 ];
            const float_t half = 0.5f
                * acosf( cz > 1.f ? 1.f : ( cz < -1.f
                            ? -1.f : cz ) );
            const float_t sh = sinf( half );
            const float_t ch = cosf( half );
            float_t ax[ 3 ]
                = { - dir_cam[ 1 ], dir_cam[ 0 ], 0.f };
            float_t ax_n = sqrtf( ax[ 0 ] * ax[ 0 ] +
                                  ax[ 1 ] * ax[ 1 ] +
                                  ax[ 2 ] * ax[ 2 ] );
            if( ax_n < 1e-7f )
            {
                //  dir_cam aligned with z:
                //  identity (or 180 about x)
                q_cam[ 0 ] = cz >= 0.f ? 1.f : 0.f;
                q_cam[ 1 ] = cz >= 0.f ? 0.f : 1.f;
                q_cam[ 2 ] = 0;
                q_cam[ 3 ] = 0;
            }
            else
            {
                const float_t inv  = 1.f / ax_n;
                q_cam[ 0 ] = ch;
                q_cam[ 1 ] = ax[ 0 ] * inv * sh;
                q_cam[ 2 ] = ax[ 1 ] * inv * sh;
                q_cam[ 3 ] = ax[ 2 ] * inv * sh;
            }
            //  Velocity channel grid [code units],
            //  dv>0=redshift.
            v_chan_min = args.get< float_t >
                ( "imaging", "v_chan_min", 0.f );
            v_chan_max = args.get< float_t >
                ( "imaging", "v_chan_max", 0.f );
            v_chan_dv = n_chan > 0 ?
                ( v_chan_max - v_chan_min ) / n_chan : 0;

            //  Image-plane grid (default = mesh x/y extent,
            //  cell-centred), overridable via par.
            type::coord_t x_min, x_max;
            args( "mesh", "x_min", x_min );
            args( "mesh", "x_max", x_max );
            type::idx_t n_cell;
            args( "mesh", "n_cell_global", n_cell );
            for( int a = 0; a < 2; ++ a )
            {
                img_x0[ a ] = x_min[ a ];
                img_n[ a ] = n_cell[ a ];
            }
            args( "imaging", "img_xmin", img_x0 );
            args( "imaging", "img_xmax",  x_max );
            args( "imaging", "img_resol", img_n );
            for( int a = 0; a < 2; ++ a )
            {
                img_dx[ a ]  = ( x_max[ a ] - img_x0[ a ] )
                             /   img_n[ a ] ;
                img_x0[ a ] += img_dx[ a ] * 0.5;
            }
            img_step_max = args.get< int >
                         ( "imaging", "step_max", 65535 );

            //  Copy the channel grid to device memory.
            std::vector< float_t > h_vchan( n_chan );
            for( int k = 0; k < n_chan; ++ k )
                h_vchan[ k ] = v_chan_min + v_chan_dv
                             * float_t( k + 0.5 );
            d_v_chan = mod.p_dev->malloc_device
                     < float_t > ( n_chan );
            mod.p_dev->cp( d_v_chan,
                           h_vchan.data(  ), n_chan );
        }
        if( build_tables )
        {
            if( ph_mode <= 1 )
            {
                //  2D Voigt table for ph_mode 0 and 1
                //  (global mem).  64x512 floats = 128 KiB -
                //  too large for const mem.
                const float_t x0[ 2 ]
                    = { log( VOIGT_A_MIN ), VOIGT_U_MIN };
                const float_t dx[ 2 ]
                    = { ( log( VOIGT_A_MAX ) -
                          log( VOIGT_A_MIN ) )
                        / ( VOIGT_NA - 1 ),
                    ( VOIGT_U_MAX - VOIGT_U_MIN )
                    / ( VOIGT_NU - 1 ) };
                const int n[ 2 ] = { VOIGT_NA, VOIGT_NU };
                const size_t nb
                    = sizeof( float ) * VOIGT_NA * VOIGT_NU;
                float * copy = ( float * )std::malloc( nb );
                std::memcpy( copy, voigt_table_data, nb );
                voigt_interp.setup( x0, dx, n, copy );
                voigt_interp.to_device( * mod.p_dev );
                free_dev_mem = true;
                riia.use_const_mem = ! free_dev_mem;
                riia.build  ( * mod.p_dev, a_voigt );
            }
            else if( ph_mode == 2 )
            {
                //  Set up 2D Voigt table on HOST only (to
                //  sample the 1D table).  Not copied to
                //  device but const -- much faster than the
                //  global memory.
                const float_t x0[ 2 ]
                    = { log( VOIGT_A_MIN ), VOIGT_U_MIN };
                const float_t dx[ 2 ]
                    = { ( log( VOIGT_A_MAX ) -
                          log( VOIGT_A_MIN ) )
                    / ( VOIGT_NA - 1 ),
                    ( VOIGT_U_MAX - VOIGT_U_MIN )
                    / ( VOIGT_NU - 1 ) };
                const int n[ 2 ] = { VOIGT_NA, VOIGT_NU };
                const size_t nb
                    = sizeof( float ) * VOIGT_NA * VOIGT_NU;
                float * copy = ( float * )std::malloc( nb );
                std::memcpy( copy, voigt_table_data, nb );
                voigt_interp.setup( x0, dx, n, copy );

                free_dev_mem       =          false;
                riia.use_const_mem = ! free_dev_mem;
                riia.build( * mod.p_dev,  a_voigt );
                build_voigt_1d( * mod.p_dev );
            }
            else if( ph_mode == 3 )
            {   //  Const-mem USampler only; transport uses
                //  photon.h voigt_H approx.
                free_dev_mem        =          false;
                riia.use_const_mem  = ! free_dev_mem;
                riia.build( * mod.p_dev,   a_voigt );
            }
        }
        // else: imaging integrator reuses the scattering
        // intg_t's tables (separate instance); voigt_H
        // falls back to the analytic form when a_voigt~0
        return super_t::init( args, mod );
    }

    __host__ void finalize( particle::base_t & mod )
    {
        if( d_v_chan != nullptr )
        {
            mod.p_dev->free_device( d_v_chan );
            d_v_chan  = nullptr ;
        }
        return riia.free( * mod.p_dev );
    };

    template< class pol_T, class map_T, class com_T >
    __host__ void pre_proc
    ( pol_T & pool, map_T & bmap,
      com_T & comm, particle::base_t & mod )
    {
        auto & dev( * mod.p_dev );
        for( auto & d : mod )
        {
            using        prx_t = typename   map_T::prx_t;
            const auto & rad   = prx_t::d( d.d(  ) ).rad;
            if( zero_fields )
            {
                dev.f_mset ( rad.flx.dat, 0, rad.flx.n_size,
                             d.stream );
                dev.f_mset( rad.excitation_flux.dat, 0,
                            rad.excitation_flux.n_size,
                            d.stream );
            }
            if( rad.imaging && zero_j_cam )
                dev.f_mset( rad.j_cam.dat, 0,
                            rad.j_cam.n_size, d.stream );
            mod.p_dev->event_record( d.event, d.stream );
        }
        return;
    };

    template< class f_T > __host__ __device__
    f_T voigt_H( const f_T & a, const f_T & u ) const
    {
        if( a < 1e-10f )
            return expf( -u * u );
        if( ph_mode == 2 && d_log_voigt_c )
        {
            const auto x = utils::min
                ( utils::abs( u ), u_voigt_max );
            int k = utils::max( x / du_voigt, 0 );
            k = utils::min( k, n_vu - 2 );
            const auto f  = ( x - k * du_voigt ) / du_voigt;
            const auto lh = d_log_voigt_c[ k ]
                          + f * ( d_log_voigt_c[ k + 1 ] -
                                  d_log_voigt_c[ k ] ) ;
            return expf( utils::min( lh, 0 ) );
        }
        if( voigt_interp )
        {
            const float_t x[ 2 ]
                = { logf( utils::max( a, voigt_a_min ) ),
                          utils::max( u, voigt_u_min ) };
            return voigt_interp( x );
        }
        //  Fallback (imaging module without Voigt table):
        //  blend Gaussian Core with Lorentzian wing.
        const auto au    = utils::abs ( u );
        const auto gauss = expf( -au * au );
        const auto lor   = a
            / ( 1.7724539f * ( au * au + a * a ) );
        return utils::max( gauss, lor );
    }

    //  Rotate a camera-frame vector v_cam into the domain
    //  frame using q_cam: v_dom = q_cam * v_cam *
    //  q_cam.conj( ) (active rotation).  v_cam and v_dom
    //  may be the same array.
    template< class v_T > __device__ __forceinline__
    void rot3vec_cam( v_T & v_dom, const v_T & v_cam ) const
    {
        //  Treat v_cam as pure quaternion (0, vx, vy, vz).
        const float_t q0 = q_cam[ 0 ];
        const float_t q1 = q_cam[ 1 ];
        const float_t q2 = q_cam[ 2 ];
        const float_t q3 = q_cam[ 3 ];
        const float_t vx = v_cam[ 0 ];
        const float_t vy = v_cam[ 1 ];
        const float_t vz = v_cam[ 2 ];
        //  q * v
        const float_t a1 =  q0 * vx + q2 * vz - q3 * vy;
        const float_t a2 =  q0 * vy + q3 * vx - q1 * vz;
        const float_t a3 =  q0 * vz  + q1 * vy - q2 * vx;
        const float_t a0 = -q1 * vx - q2 * vy - q3 * vz;
        //  (q*v) * q.conj( ) (conj = (q0,-q1,-q2,-q3))
        v_dom[ 0 ] = a0 * q1 + a1 * q0
                   + a2 * q3 - a3 * q2;
        v_dom[ 1 ] = a0 * q2 - a1 * q3
                   + a2 * q0 + a3 * q1;
        v_dom[ 2 ] = a0 * q3 + a1 * q2
                   - a2 * q1 + a3 * q0;
        return;
    }

    //  1D Voigt table (ph_mode=2): log-space
    __host__ void build_voigt_1d( device::base_t & dev )
    {
        float_t * h_log_voigt = new float_t[ n_vu ];

        const float_t a_eff = a_voigt > float_t( 1e-10 )
                            ? a_voigt : float_t( 0.f   );

        for( int k = 0; k < n_vu; ++ k )
        {
            const float_t u = k * du_voigt;
            float_t h( 0 );
            if( a_eff < float_t( 1e-10 ) )
                h = expf( -u * u );
            else
            {   //  Sample the 2D Voigt table (host-side) at
                //  the fixed a_voigt for this run.
                const float2_t x[ 2 ]
                    = { log( fmax( a_eff, VOIGT_A_MIN ) ),
                        fmax( fmin( u, VOIGT_U_MAX - 1e-5 ),
                              VOIGT_U_MIN ) };
                h = voigt_interp( x );
            }
            h_log_voigt[ k ] = logf( fmaxf( h, 1e-38f ) );
        }
        d_log_voigt_c = dev.malloc_const< float_t >( n_vu );
        dev.f_cc( d_log_voigt_c, h_log_voigt,
                  n_vu * sizeof( float_t ) );
        delete [  ] h_log_voigt;
    }

    template< class pol_T >
    __host__ std::tuple< dim3, dim3, int >
    resource( const pol_T & pool ) const
    {
        int n_launch = pool.n_par_eff(  );
        if( worker_mode )
        {   //  n_worker <= 0 falls back to 32768
            int cap( n_worker > 0 ? n_worker : 32768 );
            if( n_launch > cap )
                n_launch = cap ;
        }
        if( n_launch < 1 )
            n_launch = 1 ;
        dim3 n_bl( ( n_launch + n_th - 1 ) / n_th );
        return std::make_tuple( n_bl, dim3 ( n_th ), 0 );
    }

    //  Device-side interface
    template< class pol_T, class map_T, class com_T >
    __device__ __forceinline__ void operator(  )
    ( const pol_T & pool , const map_T & bmap,
      const com_T & comm ) const
    {
        bool flag( true );
        typename pol_T::par_t par;

        if( worker_mode )
            while( true )
            {
                auto i_par = pool.load_next( par, flag );
                if( ! flag ||
                    par.dest.todo != particle::to_keep )
                    return;
                par.id = i_par;
                const auto i_rank
                    = par.proc( bmap, get_self(  ) );
                if( i_rank >= 0 )
                    comm.reg( i_par, i_rank );
                else
                    par.save( pool[ i_par ] );
            }
        else
        {
            auto i_par = pool.load( par, flag );
            par.id     = i_par;
            if( ! flag )
                return;
            auto i_rank = par.proc( bmap, get_self(  ) );
            if( i_rank >= 0 )
                comm.reg( i_par, i_rank );
            else
                par.save( pool[ i_par ] );
        }
        return;
    };
};

}  //  namespace prob
