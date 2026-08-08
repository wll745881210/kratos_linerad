#pragma once

#include "../../usr/extension/algo/interp.h"
#include "voigt_table_data.h"

namespace prob
{
////////////////////////////////////////////////////////////
// Types

using type::   idx_t;
using type:: float_t;
using type:: coord_t;
using type::float2_t;

////////////////////////////////////////////////////////////
// Integrator type

struct intg_t : particle::integrate::base_t< intg_t >
{
    ////////// Types //////////
    using super_t  = particle::integrate::base_t< intg_t >;
    using intp2_t  = ::extension::interp_t< float_t,   2 >;

    ////////// Data //////////
    int        ph_mode;
    bool  free_dev_mem;   // On const mem--no need to free

    ////////// CDF sampler //////////
    // USampler: P(u|x) ~ exp(-u^2) / (a^2 + (x-u)^2).
    // log( CDF ) is stored for smooth interpolation.
    // ph_mode=1: global device memory (freed in finalize);
    // ph_mode=2/3: constant memory (pool, never freed).
    int                   n_u;
    int                  n_xg;
    float_t                du;    
    float_t             u_max;
    float_t *            d_xg;
    float_t *           d_cdf;

    ////////// Voigt profile //////////
    float_t       voigt_a_min;
    float_t       voigt_a_max;
    float_t       voigt_u_min;
    float_t       voigt_u_max;
    float_t           a_voigt;
    
    // 1D Voigt table (ph_mode=2): constant memory,
    // log-space.  a_voigt is fixed per run, so 1D
    // H(a_fixed, u) suffices.
    intp2_t voigt_interp{ 2 };
    float_t *   d_log_voigt_c;
    int                  n_vu;
    float_t          du_voigt;
    float_t       u_voigt_max;

    ////////// R_IIA redistribution kernel //////////
    // 3-D table R(x_out; |x_pp|, g) giving the
    // probability density of scattering from incoming
    // frequency x_pp (b units, sign restored via
    // symmetry R(-xo;-xp,g)=R(xo;xp,g)) and direction
    // angle g=cos(theta) to outgoing frequency x_out.
    // Built from the USampler CDF + Gaussian (u_perp)
    // at the end of build_usampler().  Stored in
    // global device memory; ∫R dx_out = 1.
    float_t *         d_riia;
    int          n_riia_xo;        // # x_out points
    int          n_riia_xp;        // # |x_pp| points
    int           n_riia_g;        // # g points
    float_t      riia_xo_max;      // x_out range [−xo,xo]
    float_t      riia_xp_max;      // |x_pp| range [0,xp]
    float_t        riia_dxo;
    float_t        riia_dxp;
    float_t          riia_dg;

    ////////// Imaging (camera + velocity channels) //////////
    //   dir_cam : camera LOS direction, pointing INTO the
    //             domain (imaging photons march along +dir_cam
    //             from the far boundary toward the camera).
    //             Spherical (theta, phi) read from par, stored
    //             as a unit Cartesian vector.
    //   v_chan  : observed-velocity channel grid [code units],
    //             dv>0 = redshift.  Linear grid from
    //             v_chan_min to v_chan_max, n_chan points
    //             (inclusive).  Allocated on host and copied to
    //             device constant memory (d_v_chan) for the MC
    //             pass and the imaging pass.
    //   img_x0 / img_dx / img_n : image-plane grid (first two
    //             mesh axes by default), cell-centred.
    bool           imaging = false;
    int             n_chan =        0;
    float_t        dir_cam[ 3 ];
    // Camera rotation quaternion q_cam: rotates a vector in the
    // camera frame (LOS = +z, image plane = x-y) into the
    // domain frame, so that q_cam.rot3vec(v_domain, v_camera).
    // Built from dir_cam (the LOS) in init().
    float_t         q_cam[ 4 ];
    float_t        v_chan_min;
    float_t        v_chan_max;
    float_t        v_chan_dv;
    float_t *      d_v_chan;        // device copy of channel grid
    // Image-plane grid (used by the imaging photon; harmless
    // when imaging is off).
    float_t        img_x0[ 2 ];
    float_t        img_dx[ 2 ];
    int            img_n[ 2 ];
    int            img_step_max;
    // When false, pre_proc does NOT zero s_cam (used by the
    // imaging integrator, which must consume the s_cam
    // accumulated by the scattering MC pass rather than wipe
    // it).
    bool       zero_s_cam = true;
    // When false, skip building the USampler / Voigt tables
    // (used by the imaging integrator, which only needs
    // voigt_H for the per-channel source/opacity evaluation
    // and can reuse the analytical voigt_H fallback for
    // a_voigt ~ 0; the scattering integrator's tables are on
    // a separate instance).  Avoids a duplicate device alloc
    // that overflows the const pool.
    bool       build_tables = true;
    // When false, pre_proc does NOT zero flx / excitation_flux
    // (used by the imaging integrator, which must leave the
    // scattering-accumulated flx intact instead of wiping it;
    // the imaging pass never re-accumulates flx).
    bool       zero_fields = true;

    // Proper-weight culling threshold (0 = disabled).  When
    // a photon's proper drops below proper_min_frac * proper_0
    // (initial weight at generation), the photon is removed.
    // Read from par [line_rt] proper_min_frac.
    float_t  proper_min_frac = 0.0f;

    // Server-worker mode (0 = classic 1-thread-per-photon,
    // 1 = workers fetch photons from a shared atomic counter
    // until the pool is depleted).  Read from par
    // [line_rt] worker_mode.  Default ON: it gives ~1.9x
    // speedup over classic for photon-dominated workloads
    // (high tau0, many photons) by balancing the highly
    // variable per-photon lifetimes across a fixed worker
    // grid.  Bit-identical to classic when n_worker >= n_par
    // (each thread then grabs exactly one photon).
    bool       worker_mode = true;

    // Number of persistent worker threads launched in
    // worker_mode.  Must be SMALLER than n_par for work
    // stealing to occur (otherwise each thread grabs exactly
    // one photon and the mode degenerates to classic).
    // Default 32768 (empirically optimal on the RTX 30xx
    // GPUs: ~6 blocks/SM x 82 SMs x 64 threads).  Read from
    // par [line_rt] n_worker.
    int        n_worker = 32768;

    //////////////////////////////////////////////////
    // Host-side interfaces

    __host__ intg_t(  ) : super_t(  )
    {
        d_cdf         =    nullptr;
        d_xg          =    nullptr;
        n_u           =        251;
        n_xg          =         40;
        u_max         =          6;
        du            =      0.048;
        free_dev_mem  =      false;

        d_riia        =    nullptr;
        n_riia_xo     =        200;
        n_riia_xp     =        200;
        n_riia_g      =         40;
        riia_xo_max   =         10.f;
        riia_xp_max   =        120.f;

        d_log_voigt_c =    nullptr;
        n_vu          =       5000;
        du_voigt      =       0.01;
        u_voigt_max   =         50;

        voigt_a_min  = VOIGT_A_MIN;
        voigt_a_max  = VOIGT_A_MAX;
        voigt_u_min  = VOIGT_U_MIN;
        voigt_u_max  = VOIGT_U_MAX;

        // Imaging defaults (no-op when imaging == false).
        d_v_chan     =    nullptr;
        v_chan_min   =          0;
        v_chan_max   =          0;
        v_chan_dv    =          0;
        for( int a = 0; a < 3; ++ a ) dir_cam[ a ] = 0;
        dir_cam[ 2 ] = 1.f;            // face-on by default
        for( int a = 0; a < 2; ++ a )
        { img_x0[ a ] = 0; img_dx[ a ] = 0; img_n[ a ] = 0; }
        img_step_max =      65535;
        return;
    };

    __host__ virtual void init
    ( const input & args, particle::base_t & mod ) override
    {
        ph_mode   = args.get< int >
                  ( "line_rt",  "ph_mode", 0 );
        a_voigt   = args.get< float_t >
                  ( "line_rt", "a_voigt", 0.f );
        // Proper-weight culling threshold (0 = disabled).
        proper_min_frac = args.get< float_t >
                        ( "line_rt", "proper_min_frac", 0.f );
        // Server-worker mode: workers fetch photons from a
        // shared atomic counter until the pool is depleted.
        // Default ON (see member docstring).
        worker_mode = args.get< bool >
                    ( "line_rt", "worker_mode", true );
        // Persistent-worker grid size (default 32768).
        n_worker    = args.get< int >
                    ( "line_rt", "n_worker", 32768 );

        // ---- Imaging configuration ----
        imaging   = args.get< bool >
                  ( "imaging", "enabled", false );
        n_chan    = args.get< int  >
                  ( "imaging", "n_chan",         0 );
        if( imaging && n_chan > 0 )
        {
            // Camera direction (spherical theta, phi [rad]).
            float_t theta = args.get< float_t >
                          ( "imaging", "dir_cam_theta",
                            float_t( 0.7853981633974483 ) );
            float_t phi   = args.get< float_t >
                          ( "imaging", "dir_cam_phi", 0.f );
            dir_cam[ 0 ] = sinf( theta ) * cosf( phi );
            dir_cam[ 1 ] = sinf( theta ) * sinf( phi );
            dir_cam[ 2 ] = cosf( theta );

            // Build the camera rotation quaternion q_cam that
            // maps the camera frame (LOS = +z) onto dir_cam.
            // We use the minimal rotation from +z to dir_cam:
            //   axis  = (z x dir_cam) / |z x dir_cam|
            //   angle = acos( z . dir_cam ) = acos( dir_cam.z )
            // quaternion q = (cos(a/2), axis * sin(a/2)).
            // Special case: dir_cam ~ +z  -> identity; ~ -z ->
            // 180-deg rotation about x.
            const float_t cz = dir_cam[ 2 ];
            const float_t half = 0.5f * acosf
                ( cz > 1.f ? 1.f : ( cz < -1.f ? -1.f : cz ) );
            const float_t sh = sinf( half ), ch = cosf( half );
            float_t ax[ 3 ] = { -dir_cam[ 1 ], dir_cam[ 0 ], 0.f };
            float_t ax_n = sqrtf( ax[ 0 ]*ax[ 0 ]
                                + ax[ 1 ]*ax[ 1 ]
                                + ax[ 2 ]*ax[ 2 ] );
            if( ax_n < 1e-7f )
            {   // dir_cam aligned with z: identity (or 180 about x)
                q_cam[ 0 ] = cz >= 0.f ? 1.f : 0.f;
                q_cam[ 1 ] = cz >= 0.f ? 0.f : 1.f;
                q_cam[ 2 ] = 0.f;
                q_cam[ 3 ] = 0.f;
            }
            else
            {
                const float_t inv = 1.f / ax_n;
                q_cam[ 0 ] = ch;
                q_cam[ 1 ] = ax[ 0 ] * inv * sh;
                q_cam[ 2 ] = ax[ 1 ] * inv * sh;
                q_cam[ 3 ] = ax[ 2 ] * inv * sh;
            }

            // Velocity channel grid [code units], dv>0=redshift.
            v_chan_min = args.get< float_t >
                       ( "imaging", "v_chan_min", 0.f );
            v_chan_max = args.get< float_t >
                       ( "imaging", "v_chan_max", 0.f );
            v_chan_dv  = n_chan > 0
                ? ( v_chan_max - v_chan_min )
                    / float_t( n_chan ) : 0.f;

            // Image-plane grid (default = mesh x/y extent,
            // cell-centred), overridable via par.
            type::coord_t x_min, x_max;
            args( "mesh", "x_min", x_min );
            args( "mesh", "x_max", x_max );
            type::idx_t n_cell;
            args( "mesh", "n_cell_global", n_cell );
            for( int a = 0; a < 2; ++ a )
            {
                img_x0[ a ] = x_min[ a ];
                img_n [ a ] = n_cell[ a ];
            }
            args( "imaging", "img_xmin", img_x0 );
            args( "imaging", "img_xmax", x_max   );
            args( "imaging", "img_resol", img_n  );
            for( int a = 0; a < 2; ++ a )
            {
                img_dx[ a ] = ( x_max[ a ] - img_x0[ a ] )
                            / float_t( img_n[ a ] );
                img_x0[ a ] += img_dx[ a ] * 0.5f;
            }
            img_step_max = args.get< int >
                         ( "imaging", "step_max", 65535 );

            // Copy the channel grid to device memory.
            std::vector< float_t > h_vchan( n_chan );
            for( int k = 0; k < n_chan; ++ k )
                h_vchan[ k ] = v_chan_min
                             + v_chan_dv * float_t( k + 0.5 );
            d_v_chan = mod.p_dev->malloc_device< float_t >
                       ( n_chan );
            mod.p_dev->cp( d_v_chan, h_vchan.data(  ),
                           n_chan );
        }

        if( build_tables )
        {
        if( ph_mode <= 1 )
        {   // 2D Voigt table for ph_mode 0 and 1 (global
            // mem).  64x512 floats = 128 KiB - too large
            // for const mem.
            const float_t x0[ 2 ]
                = { log( VOIGT_A_MIN ), VOIGT_U_MIN };
            const float_t dx[ 2 ] = {
                ( log( VOIGT_A_MAX ) - log( VOIGT_A_MIN ) )
                    / ( VOIGT_NA - 1 ),
                ( VOIGT_U_MAX - VOIGT_U_MIN )
                    / ( VOIGT_NU - 1 )
            };
            const int n[ 2 ] = { VOIGT_NA, VOIGT_NU };
            const size_t nb = sizeof( float )
                * VOIGT_NA * VOIGT_NU;
            float * copy = ( float * )std::malloc( nb );
            std::memcpy( copy, voigt_table_data, nb );
            voigt_interp.setup( x0, dx, n, copy );
            voigt_interp.to_device( * mod.p_dev );
            free_dev_mem = true;
            build_usampler  ( * mod.p_dev );
        }
        else if( ph_mode == 2 )
        {   // Set up 2D Voigt table on HOST only (to sample
            // the 1D table).  Not copied to device but
            // const -- much faster than the global memory.
            const float_t x0[ 2 ]
                = { log( VOIGT_A_MIN ), VOIGT_U_MIN };
            const float_t dx[ 2 ] = {
                ( log( VOIGT_A_MAX ) - log( VOIGT_A_MIN ) )
                    / ( VOIGT_NA - 1 ),
                ( VOIGT_U_MAX - VOIGT_U_MIN )
                    / ( VOIGT_NU - 1 )
            };
            const int n[ 2 ] = { VOIGT_NA, VOIGT_NU };
            const size_t nb = sizeof( float )
                * VOIGT_NA * VOIGT_NU;
            float * copy = ( float * )std::malloc( nb );
            std::memcpy( copy, voigt_table_data, nb );
            voigt_interp.setup( x0, dx, n, copy );

            free_dev_mem = false;
            build_usampler( * mod.p_dev );
            build_voigt_1d( * mod.p_dev );
        }   // NO to_device() - host-only for 1D sampling.
        else if( ph_mode == 3 )
        {   // Const-mem USampler only;
            // transport uses photon.h voigt_H approx.
            free_dev_mem = false;
            build_usampler( * mod.p_dev );
        }
        }
        // else: imaging integrator reuses the scattering
        // intg_t's tables (separate instance); voigt_H falls
        // back to the analytic form when a_voigt ~ 0.
        return super_t::init( args, mod );
    }
    
    __host__ void finalize( particle::base_t & mod )
    {
        auto & dev = * mod.p_dev;
        if( free_dev_mem )
        {
            if( d_cdf )
            {
                dev.free_device( d_cdf );
                d_cdf = nullptr;
            }
            if( d_xg )
            {
                dev.free_device( d_xg  );
                d_xg  = nullptr;
            }
        } // Const-mem pointers ( free_dev_mem == false )
          // are NOT freed: the const is a system-managed
          // pool ( device.cpp : 45--54 ).
        if( d_v_chan )
        {
            dev.free_device( d_v_chan );
            d_v_chan = nullptr;
        }
        if( d_riia )
        {
            dev.free_device( d_riia );
            d_riia = nullptr;
        }
        return;
    };

    template< class pol_T, class map_T, class com_T >
    __host__ void pre_proc
    ( pol_T & pool, map_T & bmap,
      com_T & comm, particle::base_t & mod )
    {
        auto & dev( * mod.p_dev );
        for( auto & d : mod )
        {
            using prx_t = typename map_T :: prx_t;
            const auto & rad = prx_t::d( d.d(  ) ).rad;
            if( zero_fields )
            {
                dev.f_mset
                    ( rad.flx.dat, 0,
                      rad.flx.n_size, d.stream );
                dev.f_mset
                    ( rad.excitation_flux.dat, 0,
                      rad.excitation_flux.n_size, d.stream );
            }
            if( rad.imaging && zero_s_cam )
                dev.f_mset
                    ( rad.s_cam.dat, 0,
                      rad.s_cam.n_size, d.stream );
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
            k     = utils::min( k, n_vu -     2 );
            const auto f  = ( x - k * du_voigt ) / du_voigt;
            const auto lh = d_log_voigt_c[ k ]
                          + f * ( d_log_voigt_c[ k + 1 ]
                                - d_log_voigt_c[ k ] ) ;
            return expf( utils::min( lh, 0 ) );
        }
        if( voigt_interp )
        {
            const float_t x[ 2 ]
                = { logf( utils::max( a, voigt_a_min ) ),
                          utils::max( u, voigt_u_min ) };
            return voigt_interp( x );
        }
        // Fallback (imaging module without Voigt table):
        // blend Gaussian core with Lorentzian wing.
        const auto au = utils::abs( u );
        const auto gauss = expf( -au * au );
        const auto lor = a / ( 1.7724539f
                             * ( au * au + a * a ) );
        return utils::max( gauss, lor );
    }

    // Rotate a camera-frame vector v_cam into the domain frame
    // using q_cam: v_dom = q_cam * v_cam * q_cam.conj()  (active
    // rotation).  v_cam and v_dom may be the same array.
    template< class v_T > __device__ __forceinline__
    void rot3vec_cam( v_T & v_dom, const v_T & v_cam ) const
    {
        // Treat v_cam as pure quaternion (0, vx, vy, vz).
        const float_t q0 = q_cam[ 0 ], q1 = q_cam[ 1 ],
                      q2 = q_cam[ 2 ], q3 = q_cam[ 3 ];
        const float_t vx = v_cam[ 0 ], vy = v_cam[ 1 ],
                      vz = v_cam[ 2 ];
        // q * v
        const float_t a1 = q0*vx + q2*vz - q3*vy;
        const float_t a2 = q0*vy + q3*vx - q1*vz;
        const float_t a3 = q0*vz + q1*vy - q2*vx;
        const float_t a0 = -q1*vx - q2*vy - q3*vz;
        // (q*v) * q.conj()  (conj = (q0,-q1,-q2,-q3))
        v_dom[ 0 ] = a0*q1 + a1*q0 + a2*q3 - a3*q2;
        v_dom[ 1 ] = a0*q2 - a1*q3 + a2*q0 + a3*q1;
        v_dom[ 2 ] = a0*q3 + a1*q2 - a2*q1 + a3*q0;
        return;
    }

    //////////////////////////////////////////////////
    // USampler: log(CDF) table.  Allocated in global
    // device memory (free_dev_mem) or constant memory
    // (bump pool, never freed).

    __host__ void build_usampler( device::base_t & dev )
    {
        const size_t n_total = size_t( n_u ) * n_xg;
        float2_t * h_cdf = new float2_t [ n_total ];
        float_t  * h_xg  = new float_t  [ n_xg    ];

        const int n_lin = 18;
        const int n_log = n_xg - n_lin;
        const float_t x_lin_max = 8.f;
        const float_t x_max     = 300.f;

        for( int j = 0; j < n_lin; ++ j )
            h_xg[ j ] = j
                      / float_t( n_lin - 1 ) * x_lin_max;
        for( int j = 0; j < n_log; ++ j )
            h_xg[ n_lin + j ] = x_lin_max
                * pow( x_max  / x_lin_max,
                       float_t( j + 1 ) / n_log );

        // Clamp a > 0: at a = 0 the xg = 0 row is
        // 1/(0+0)=NaN.
        const float_t a_eff = a_voigt > float_t( 1e-6 )
            ? a_voigt : float_t( 1e-6 );
        const float2_t a2 = float2_t( a_eff * a_eff );
        for( int j = 0; j < n_xg; ++ j )
        {
            const float2_t xg = float2_t( h_xg[ j ] );
            float2_t * row_cdf = h_cdf + j * n_u;
            for( int k = 0; k < n_u; ++ k )
            {
                const float2_t uk = float2_t
                    ( -u_max + du * float_t( k ) );
                const float2_t diff = xg - uk;
                row_cdf[ k ] = exp( -double( uk * uk ) )
                    / ( a2 + double( diff * diff ) );
            }
            float2_t cum = 0;
            for( int k = 0; k < n_u; ++ k )
            {
                cum += row_cdf[ k ];
                row_cdf[ k ] = cum;
            }
            const float2_t inv_sum = 1.0 / cum;
            for( int k = 0; k < n_u; ++ k )
                row_cdf[ k ] *= inv_sum;
        }

        // Store log(CDF) in float for smooth interpolation
        // in the tails (where the CDF is nearly flat).
        float_t * h_logcdf = new float_t[ n_total ];
        for( size_t i = 0; i < n_total; ++ i )
            h_logcdf[ i ] = log( fmax
                    ( float_t( h_cdf[ i ] ), 1e-38f ) );

        if( free_dev_mem )
        {
            d_cdf = dev.malloc_device< float_t >( n_total );
            d_xg  = dev.malloc_device< float_t >( n_xg    );            
            dev.cp( d_cdf, h_logcdf, n_total );
            dev.cp( d_xg,  h_xg,        n_xg );
        }
        else
        {
            d_cdf = dev.malloc_const< float_t >( n_total );
            d_xg  = dev.malloc_const< float_t >( n_xg    );
            dev.f_cc( d_cdf, h_logcdf,
                      n_total * sizeof( float_t ) );
            dev.f_cc( d_xg, h_xg,
                      n_xg    * sizeof( float_t ) );
        }
        build_riia_kernel( dev, h_cdf, h_xg );

        delete[  ] h_logcdf;
        delete[  ] h_cdf;
        delete[  ] h_xg;
        return;
    }

    //////////////////////////////////////////////////
    // R_IIA redistribution kernel 3-D table:
    // R(x_out; |x_pp|, g) = Σ_k pdf[k]
    // * G(x_out-x_pp-u_k(g-1); sin_g/√2)
     // where pdf is the discrete USampler PDF
    //   and G is a Gaussian.  ∫R dx_out = 1 (normalised
    //   probability density in x-space).

    __host__ void build_riia_kernel
    ( device::base_t & dev,
      const float2_t * h_cdf,
      const float_t  * h_xg )
    {
        const int n_xo = n_riia_xo;
        const int n_xp = n_riia_xp;
        const int n_g  = n_riia_g;
        const float_t xo_max = riia_xo_max;
        const float_t xp_max = riia_xp_max;
        riia_dxo = ( 2.f * xo_max ) / float_t( n_xo - 1 );
        riia_dxp = xp_max / float_t( n_xp - 1 );
        riia_dg  = 2.f / float_t( n_g - 1 );

        const size_t n_tab = size_t( n_xo ) * n_xp * n_g;
        float_t * h_tab = new float_t[ n_tab ]();
        const float_t sqrt_pi = float_t( 1.7724538509 );
        const float_t u_min = -u_max;

        for( int jp = 0; jp < n_xp; ++ jp )
        {
            const float_t xpp = jp * riia_dxp;

            int jxg = 0;
            for( int lo = 0, hi = n_xg - 1; lo <= hi; )
            {
                int mid = ( lo + hi ) >> 1;
                if( h_xg[ mid ] <= xpp )
                {
                    jxg = mid ;
                    lo  = mid + 1;
                }
                else hi = mid - 1;
            }
            if( jxg < 0 ) jxg = 0;
            if( jxg >= n_xg - 1 ) jxg = n_xg - 2;
            const float2_t * row = h_cdf + jxg * n_u;

            float_t pdf[ 256 ];
            pdf[ 0 ] = float_t( row[ 0 ] );
            for( int k = 1; k < n_u; ++ k )
                pdf[ k ] = float_t( row[ k ] )
                         - float_t( row[ k - 1 ] );
            float_t pdf_sum = 0;
            for( int k = 0; k < n_u; ++ k )
                pdf_sum += pdf[ k ];

            for( int ig = 0; ig < n_g; ++ ig )
            {
                const float_t g = -1.f + ig * riia_dg;
                float_t sin_g = sqrtf
                    ( fmaxf( 1.f - g * g, 0.f ) );
                sin_g = fmaxf( sin_g, 1e-3f );
                const float_t gm1 = g - 1.f;
                const float_t inv_sg = 1.f / sin_g;

                for( int io = 0; io < n_xo; ++ io )
                {
                    const float_t xo = -xo_max
                        + io * riia_dxo;
                    float_t R = 0;
                    for( int k = 0; k < n_u; ++ k )
                    {
                        const float_t uk = u_min
                            + du * float_t( k );
                        const float_t y = xo - uk * gm1;
                        R += pdf[ k ]
                            * expf( -y * y * inv_sg * inv_sg )
                            * inv_sg / sqrt_pi;
                    }
                    h_tab[ ( ( io * n_xp ) + jp ) * n_g + ig ]
                        = R;
                }
            }
        }

        d_riia = dev.malloc_device< float_t >( n_tab );
        dev.cp( d_riia, h_tab, n_tab );
        delete[  ] h_tab;
        return;
    }

    //////////////////////////////////////////////////
    // 1D Voigt table (ph_mode=2): constant memory,
    // log-space

    __host__ void build_voigt_1d( device::base_t & dev )
    {
        float_t * h_log_voigt = new float_t[ n_vu ];

        const float_t a_eff = a_voigt > float_t( 1e-10 )
            ? a_voigt : float_t( 0.f );

        for( int k = 0; k < n_vu; ++ k )
        {
            const float_t u = k * du_voigt;
            float_t h;
            if( a_eff < float_t( 1e-10 ) )
                h = expf( -u * u );
            else
            {   // Sample the 2D Voigt table (host-side) at
                // the fixed a_voigt for this run.
                const float2_t x[ 2 ] = {
                    log( fmax( a_eff, VOIGT_A_MIN ) ),
                    fmax( fmin( u, VOIGT_U_MAX - 1e-5 ),
                          VOIGT_U_MIN ) };
                h = voigt_interp( x );
            }
            h_log_voigt[ k ] = logf
                ( fmaxf( h, 1e-38f ) );
        }
        d_log_voigt_c = dev.malloc_const< float_t >( n_vu );
        dev.f_cc( d_log_voigt_c, h_log_voigt,
                  n_vu * sizeof( float_t ) );
        delete[  ] h_log_voigt;
    }

    //////////////////////////////////////////////////
    // Inverse CDF: log-space (table stores log(CDF))

    __device__ __forceinline__ float_t _invcdf
    ( const float_t * log_cdf, const float_t & r ) const
    {
        const float_t log_r = logf( fmaxf( r, 1e-38f ) );
        int  k = 0;
        for( int lo = 0, hi = n_u - 1; lo <= hi; )
        {
            const int mid = ( lo + hi ) >> 1;
            if( log_cdf[ mid ] <= log_r )
            {
                k  = mid ;
                lo = mid + 1;
            }
            else
                hi = mid - 1;
        }
        k = utils::max( utils::min( k, n_u - 2 ), 1 );
        const float_t denom = utils::max
            ( log_cdf[ k ] - log_cdf[ k - 1 ], 1e-35f ) ;
        const float_t frac = ( log_r - log_cdf[ k - 1 ] )
                           / denom;
        float_t u = ( -u_max + du * float_t( k - 1 ) )
                  + frac * du;
        return utils::max( utils::min( u, u_max ), -u_max );
    };  // Clamp to table range to avoid NaN

    //////////////////////////////////////////////////
    // Sample u_par for a given xa (|xa| with sign
    // restored): binary search on the xg grid, then
    // interp between adjacent rows of the log(CDF) table.
    __device__ __forceinline__
    float_t sample_upar( const float_t & xa ) const
    {
        const float_t sgn = ( xa >= 0.f ) ? 1.f : -1.f;
        const float_t ax  = fabsf( xa );

        int j = n_xg - 2;
        for( int lo = 0, hi = n_xg - 1; lo <= hi; )
        {
            const int mid = ( lo + hi ) >> 1;
            if( d_xg[ mid ] <= ax )
            {
                j = mid;
                lo = mid + 1;
            }
            else
                hi = mid - 1;
        }
        if( j < 0 )
            j = 0;
        else if( j >= n_xg - 1 )
            j = n_xg - 2;

        const float_t f = ( ax - d_xg[ j ] )
            / ( d_xg[ j + 1 ] - d_xg[ j ] );
        const float_t r = device::rand_dev(  );

        const float_t u0 = _invcdf
            ( d_cdf + j * n_u, r );
        const float_t u1 = _invcdf
            ( d_cdf + ( j + 1 ) * n_u, r );
        return sgn * ( u0 + f * ( u1 - u0 ) );
    };

    //////////////////////////////////////////////////
    // R_IIA redistribution kernel density lookup:
    //   R(x_out; x_pp, g)  [x-space, ∫R dx = 1]
    // Uses the 3-D table built by build_riia_kernel().
    // The table is parametrised in Δ = x_out - x_pp
    // (symmetry: R(Δ; -x_pp, g) = R(-Δ; x_pp, g)),
    // so the device lookup computes t_delta = Δ*sgn.
    //
    // For |x_pp| >= riia_xp_max the USampler CDF has
    // converged to the asymptotic form pdf_∞ ∝ exp(-u²),
    // giving the analytic kernel:
    //   R_∞(Δ; g) = exp(-Δ²/((g-1)²+sin²_g)) /
    //               (√π × √((g-1)²+sin²_g))
    // which is used directly (no table lookup needed).
    __device__ __forceinline__
    float_t riia_kernel
    ( float_t x_out, float_t x_pp, float_t g ) const
    {
        const float_t ax_pp = fabsf( x_pp );

        // Asymptotic for |x_pp| >= riia_xp_max
        if( ax_pp >= riia_xp_max )
        {
            float_t sin_g = sqrtf
                ( fmaxf( 1.f - g * g, 1e-6f ) );
            float_t gm1 = g - 1.f;
            float_t denom = gm1 * gm1 + sin_g * sin_g;
            float_t Delta = x_out - x_pp;
            return expf( -Delta * Delta / denom )
                 / ( 1.7724538509f * sqrtf( denom ) );
        }

        const float_t sgn = ( x_pp >= 0.f ) ? 1.f : -1.f;
        const float_t t_delta = ( x_out - x_pp ) * sgn;

        // Kernel negligible for |Δ| > xo_max
        if( fabsf( t_delta ) > riia_xo_max )
            return 0.f;

        const float_t xo_max = riia_xo_max;

        int ixp = int( ax_pp / riia_dxp );
        ixp = utils::max( utils::min( ixp, n_riia_xp - 2 ), 0 );
        float_t fxp = ( ax_pp - ixp * riia_dxp ) / riia_dxp;
        fxp = utils::max( utils::min( fxp, 1.f ), 0.f );

        int ixo = int( ( t_delta + xo_max ) / riia_dxo );
        ixo = utils::max( utils::min( ixo, n_riia_xo - 2 ), 0 );
        float_t fxo = ( t_delta + xo_max - ixo * riia_dxo ) / riia_dxo;
        fxo = utils::max( utils::min( fxo, 1.f ), 0.f );

        int ig = int( ( g + 1.f ) / riia_dg );
        ig = utils::max( utils::min( ig, n_riia_g - 2 ), 0 );
        float_t fg = ( g + 1.f - ig * riia_dg ) / riia_dg;
        fg = utils::max( utils::min( fg, 1.f ), 0.f );

        const int n_xp = n_riia_xp, n_g = n_riia_g;
        #define _RIIA(io,jp,ig)  d_riia[ ((io)*n_xp+(jp))*n_g + (ig) ]
        const auto c00 = _RIIA(ixo,ixp,ig)*(1.f-fg)
                          + _RIIA(ixo,ixp,ig+1)*fg;
        const auto c01 = _RIIA(ixo,ixp+1,ig)*(1.f-fg)
                          +_RIIA(ixo,ixp+1,ig+1)*fg;
        const auto c10 = _RIIA(ixo+1,ixp,ig)*(1.f-fg)
                          + _RIIA(ixo+1,ixp,ig+1)*fg;
        const auto c11 = _RIIA(ixo+1,ixp+1,ig)*(1.f-fg)
                          +_RIIA(ixo+1,ixp+1,ig+1)*fg;
        #undef _RIIA
        const auto c0 = c00 * ( 1.f - fxp ) + c01 * fxp;
        const auto c1 = c10 * ( 1.f - fxp ) + c11 * fxp;
        return c0 * ( 1.f - fxo ) + c1 * fxo;
    };
    
    //////////////////////////////////////////////////
    // Launch-grid override (host).  In classic mode this
    // matches the trunk (one thread per active photon).  In
    // worker_mode the grid is capped at a fixed number of
    // persistent workers so that, when n_par_eff exceeds the
    // cap, threads loop over the shared atomic work counter
    // (load_next) and process multiple photons each.
    template< class pol_T >
    __host__ std::tuple< dim3, dim3, int >
    resource( const pol_T & pool ) const
    {
        int n_launch = pool.n_par_eff( );
        if( worker_mode )
        {
            // n_worker <= 0 falls back to 32768
            int cap( n_worker > 0 ? n_worker : 32768 );
            if( n_launch > cap )
                n_launch = cap ;
        }
        if( n_launch < 1 )
            n_launch = 1;
        dim3 n_bl( ( n_launch + n_th - 1 ) / n_th );
        return std::make_tuple( n_bl, dim3( n_th ), 0 );
    };

    //////////////////////////////////////////////////
    // Device-side interface
    template< class pol_T, class map_T, class com_T >
    __device__ __forceinline__ void operator(  )
    ( const pol_T & pool, const map_T & bmap,
      const com_T & comm ) const
    {
        bool flag( true );
        typename pol_T :: par_t par;

        if( worker_mode )
        {
            // Server-worker: keep fetching photons from the
            // shared atomic counter until the pool is
            // depleted.  Each worker processes photons in a
            // loop instead of the classic 1-thread-1-photon.
            while( true )
            {
                const auto i_par = pool.load_next( par, flag );
                if( ! flag || par.dest.todo != particle::to_keep )
                    return;
                par.id = i_par;
                const auto i_rank = par.proc( bmap, get_self(  ) );
                if( i_rank >= 0 )
                    comm.reg( i_par, i_rank );
                else
                    par.save( pool[ i_par ] );
            }
        }
        else
        {
            auto i_par = pool.load( par, flag );
            par.id = i_par;
            if( ! flag )
                return;
            const auto i_rank = par.proc( bmap, get_self(  ) );
            if( i_rank >= 0 )
                comm.reg( i_par, i_rank );
            else
                par.save( pool[ i_par ] );
        }
        return;
    };
};

}
