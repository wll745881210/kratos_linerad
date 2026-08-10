#pragma once

#include "../../src/types.h"
#include "../../src/device/device.h"

using type::float_t;
using type::float2_t;

////////////////////////////////////////////////////////////
//  riia_table_t: standalone R_IIA
//  redistribution table.
//
//  Owns ALL R_IIA + USampler data:
//    - 3-D table R(delta; |x_pp|, g),
//      io-fastest layout
//    - USampler log(CDF) + x grid
//      (device-resident)
//    - GPU construction kernel (float_t,
//      reads d_cdf + d_xg)
//
//  Device methods:
//    operator()  -- table indexing
//    invcdf      -- USampler inverse CDF
//    sample_upar -- USampler sampling
//    lookup      -- R_IIA trilinear lookup
//
//  Host methods:
//    build       -- full construction
//    free        -- device memory cleanup
//
//  intg_t holds a single riia_table_t riia;
//  member and delegates:
//    riia.sample_upar(), riia.lookup(),
//    riia.build(), riia.free().
//
//  Future: _build_usampler() can be
//    replaced by a GPU kernel;
//    _build_riia_gpu() stays unchanged
//    (reads d_cdf + d_xg from device,
//    never touches host arrays).
////////////////////////////////////////////////////////////

struct riia_table_t
{
    ////////// Data //////////
    bool use_const_mem;  //  true -> const mem (ph_mode 2/3)
    
    float_t          *   dat; //  R_IIA table grid
    int      n_xo, n_xp, n_g;
    float_t  xo_max,  xp_max;
    float_t  dxo,    dxp, dg;

    float_t *    d_cdf;  //  USampler log(CDF) (n_xg, n_u)
    float_t *     d_xg;  //  USampler x grid (n_xg)    
    int      n_u, n_xg;
    float_t  du, u_max;
    float_t    a_voigt;

    ////////// Functions //////////
    __host__ riia_table_t(  )
        : dat( nullptr ), d_cdf( nullptr ), d_xg( nullptr ),
          use_const_mem( false ),  n_xo( 200 ), n_xp( 200 ),
          n_g( 40 ), xo_max( 10.f ), xp_max( 120.f ),
          dxo( 0 ), dxp( 0 ), dg( 0 ), n_u( 251 ),
          n_xg( 40 ),  du( 0.048f ), u_max( 6.f ),
          a_voigt( 0.f )
    {
        return;
    };

    //  Indexing (device, io-fastest) io-fastest layout: io
    //  + n_xo * ( jp + n_xp * ig ) (better GPU coalescing
    //  than the old io-slowest)
    __device__ __forceinline__ float_t & operator(  )
        ( int io, int jp, int ig ) const
    {
        return dat[ io + n_xo * ( jp + n_xp * ig ) ];
    };

    // USampler inverse CDF (device, private). Binary
    // search on log(CDF) row for log(r)
    __device__ __forceinline__ float_t invcdf
    ( const float_t * log_cdf, const float_t & r ) const
    {
        const float_t log_r = logf( fmaxf( r, 1e-38f ) );
        int k = 0;
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

        auto  denom = log_cdf[ k ] - log_cdf[ k - 1 ];
        denom = utils::max( denom, 1e-35f );
        auto frac = ( log_r - log_cdf  [ k - 1 ] )  / denom;
        auto u    = frac * du + ( du * ( k - 1 ) -  u_max );
        return utils::max( utils::min( u, u_max ), -u_max );
    };

    //  Sample u_par for a given xa (|xa| with sign
    //  restored): binary search on the xg grid, then interp
    //  between adjacent rows of the log(CDF) table.
    __device__ __forceinline__
    float_t sample_upar( const float_t & xa ) const
    {
        const float_t sgn = ( xa >= 0.f ) ? 1.f : -1.f;
        const float_t ax = fabsf( xa );

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
        j = utils::max( utils::min( j, n_xg - 2 ), 0 );

        const auto f = ( ax - d_xg[ j ] )
                     / ( d_xg[ j + 1 ] - d_xg[ j ] );
        const auto r = device::rand_dev(  );

        const float_t u0 = invcdf( d_cdf + j * n_u, r );
        const float_t u1
            = invcdf( d_cdf + ( j + 1 ) * n_u, r );
        return sgn * ( u0 + f * ( u1 - u0 ) );
    };

    //  R_IIA trilinear lookup (device).  R(x_out; x_pp, g)
    //  [x-space, integral R dx = 1] Uses the 3-D table
    //  built by the GPU kernel.  The table is parametrised
    //  in delta = x_out - x_pp (symmetry: R(delta; -x_pp,
    //  g) = R(-delta; x_pp, g)), so the device lookup
    //  computes t_delta = delta * sgn.
    //
    //  For |x_pp| >= xp_max the USampler CDF has converged
    //  to the asymptotic form pdf_inf ~ exp(-u^2), giving
    //  the analytic kernel: R_inf(delta; g) = exp(-delta^2
    //  / ((g-1)^2 + sin^2_g)) / (sqrt(pi) *
    //  sqrt((g-1)^2+sin^2_g)) which is used directly (no
    //  table lookup needed).
    //
    //  For |g| > 0.99f: Trilinear interpolation between a
    //  broad Gaussian (g=0.949, sigma~0.22) and a delta
    //  spike (g=1.0, sigma~0) cannot capture the
    //  qualitative shape change, so use the analytic form R
    //  = Gauss(delta; sigma=sin_g/ sqrt(pi)).
    __device__ __forceinline__ float_t lookup
    ( const float_t & x_out, const float_t & x_pp,
      const float_t &    g ) const
    {
        const float_t ax_pp = fabsf( x_pp );
        //  Asymptotic for |x_pp| >= xp_max
        const auto  sin_g
            = sqrtf( fmaxf( 1.f - g * g, 1e-6f ) );        
        if( ax_pp >= xp_max )
        {
            float_t gm1   = g - 1;
            float_t denom = gm1 * gm1 + sin_g * sin_g;
            float_t Delta = x_out - x_pp;
            return expf( - Delta * Delta / denom )
                / ( 1.7724538509f * sqrtf( denom ) );
        }
        //  g ~ +/-1 fallback (last 2 grid points each side)
        if( fabsf( g ) > 0.99f )
        {
            float_t Delta = x_out - x_pp;
            return expf( - Delta * Delta
                         / ( sin_g * sin_g ) )
                   / ( sin_g * 1.7724538509f );
        }
        //  Kernel negligible for |delta| > xo_max
        const auto sgn    ( x_pp >= 0 ? 1 : -1 );
        const auto t_delta( ( x_out - x_pp ) * sgn );
        if( fabsf( t_delta ) > xo_max )
            return 0;

        int   ixp = ax_pp / dxp;
        ixp = utils::max( utils::min( ixp, n_xp - 2 ), 0 );
        auto  fxp = ( ax_pp - ixp * dxp ) / dxp;
        fxp = utils::max( utils::min( fxp, 1 ),   0 );

        int   ixo = int( ( t_delta + xo_max ) / dxo );
        ixo = utils::max( utils::min( ixo, n_xo - 2 ), 0 );
        auto  fxo = ( t_delta + xo_max - ixo * dxo ) / dxo;
        fxo = utils::max( utils::min( fxo, 1 ),   0 );

        int     ig = int( ( g + 1.f ) / dg );
        ig = utils::max( utils::min( ig, n_g - 2 ), 0 );
        float_t fg = ( g + 1 - ig * dg ) / dg;
        fg = utils::max( utils::min( fg, 1 ),  0 );

        // Multi-linear interpolation
        const auto & self( * this );
        const auto c00 
            = self( ixo, ixp,     ig     ) * ( 1 - fg )
            + self( ixo, ixp,     ig + 1 ) * fg;
        const auto c01
            = self( ixo, ixp + 1, ig     ) * ( 1 - fg )
            + self( ixo, ixp + 1, ig + 1 ) * fg;
        const auto c10
            = self( ixo + 1, ixp, ig     ) * ( 1 - fg )
            + self( ixo + 1, ixp, ig + 1 ) * fg;
        const auto c11
            = self( ixo + 1, ixp + 1, ig     ) * ( 1 - fg )
            + self( ixo + 1, ixp + 1, ig + 1 ) * fg;

        const auto c0 = c00 * ( 1 - fxp ) + c01 * fxp;
        const auto c1 = c10 * ( 1 - fxp ) + c11 * fxp;
        return c0 * ( 1 - fxo ) + c1 * fxo;
    }

    //  Host method declarations
    __host__ void build( device::base_t & dev,
                         const  float_t & a_voigt );
    __host__ void free ( device::base_t & dev );
    __host__ void _build_usampler
    ( device::base_t & dev, const float_t & a_voigt );
    __host__ void _build_riia_gpu( device::base_t & dev );
};

////////////////////////////////////////////////////////////
//  GPU kernel: build USampler log(CDF) on device.  Each
//  thread computes one row (one xg value) of the CDF:
//  P(u|x) ~ exp(-u^2) / (a^2 + (x-u)^2), cumulative sum,
//  normalize, log.  All float_t (single precision).  Grid:
//  1 block of n_xg (40) threads.
////////////////////////////////////////////////////////////

static __global__ void build_usampler_gpu_kernel
( riia_table_t riia )
{
    const int j = blockIdx.x * blockDim.x + threadIdx.x;
    if( j >= riia.n_xg )
        return;

    float_t xg    = riia.d_xg[ j ];
    float_t a_eff = utils::max( riia.a_voigt, 1e-6f );
    float_t a2    = a_eff * a_eff;

    float_t cdf[ 251 ];
    float_t cum    = 0;
    for( int k = 0; k < riia.n_u; ++ k )
    {
        float_t uk = - riia.u_max + riia.du * float_t( k );
        float_t diff = xg - uk;
        cum += expf( - uk * uk ) / ( a2 + diff * diff );
        cdf[ k ] = cum;
    }
    float_t inv_sum = 1.f / cum;
    float_t *   row = riia.d_cdf + j * riia.n_u;
    for( int k = 0; k < riia.n_u; ++ k )
        row[ k ] = logf
                 ( fmaxf( cdf[ k ] * inv_sum, 1e-38f ) );
    return;
}

////////////////////////////////////////////////////////////
//  GPU kernel: build R_IIA table from device-resident
//  USampler log(CDF) + x grid.  Uses float_t (single
//  precision) throughout.  Each thread computes one (io,
//  jp, ig) entry.
//
//  Grid: block (64, 1, 1), grid (ceil(n_xo/64), n_xp, n_g).
//  Threads in the same warp (same jp, different io) read
//  the same USampler CDF row -> broadcast access (L2
//  cache).
////////////////////////////////////////////////////////////

static __global__ void build_riia_gpu_kernel
( riia_table_t riia )
{
    const int io = blockIdx.x * blockDim.x + threadIdx.x;
    const int jp = blockIdx.y;
    const int ig = blockIdx.z;
    if( io >= riia.n_xo || jp >= riia.n_xp
                        || ig >= riia.n_g )
        return;

    float_t xpp = jp * riia.dxp;
    float_t g   = - 1.f + ig * riia.dg;
    float_t xo  = - riia.xo_max + io * riia.dxo;

    float_t sin_g = sqrtf( fmaxf( 1.f - g * g, 0.f ) );
    sin_g = fmaxf( sin_g, 1e-3f );
    float_t gm1 = g - 1.f;
    float_t inv_sg = 1.f / sin_g;
    float_t inv_pi = 1.f / 1.7724538509f;

    //  Binary search d_xg for jxg matching xpp
    int jxg = 0;
    for( int lo = 0, hi = riia.n_xg - 1; lo <= hi; )
    {
        int mid = ( lo + hi ) >> 1;
        if( riia.d_xg[ mid ] <= xpp )
        {
            jxg = mid;
            lo = mid + 1;
        }
        else
            hi = mid - 1;
    }
    jxg = utils::max( jxg,             0 );
    jxg = utils::min( jxg, riia.n_xg - 2 );

    //  Read log(CDF) row, convert via expf to raw CDF,
    //  compute pdf on the fly, accumulate R.
    const float_t * row = riia.d_cdf + jxg * riia.n_u;

    float_t cdf_prev = expf( row[ 0 ] );
    float_t R = 0;
    {
        float_t uk = - riia. u_max;
        float_t  y = xo - uk * gm1;
        R += cdf_prev * expf( - y * y * inv_sg * inv_sg )
            * inv_sg * inv_pi;
    }
    for( int k = 1; k < riia.n_u; ++ k )
    {
        float_t cdf_curr = expf( row[ k ] );
        float_t pdf_k = cdf_curr - cdf_prev;
        cdf_prev = cdf_curr;

        float_t uk = - riia.u_max + riia.du * float_t( k );
        float_t y = xo - uk * gm1;
        R += pdf_k * expf( - y * y * inv_sg * inv_sg )
           * inv_sg * inv_pi;
    }
    riia( io, jp, ig ) = R;
    return;
}

////////////////////////////////////////////////////////////
//  Host method definitions
////////////////////////////////////////////////////////////

inline __host__ void riia_table_t::build
( device::base_t & dev, const float_t & a_voigt )
{
    this->a_voigt = a_voigt;
    _build_usampler( dev, a_voigt );
    _build_riia_gpu( dev );
    return;
}

////////////////////////////////////////////////////////////
//  _build_usampler: USampler CDF construction on HOST.
//  (Future: replace with a GPU kernel -- _build_riia_gpu
//  stays unchanged, it reads d_cdf + d_xg from device.)
//
//  P(u|x) ~ exp(-u^2) / (a^2 + (x-u)^2).  log(CDF) is
//  stored for smooth interpolation in the tails (where the
//  CDF is nearly flat).  use_const_mem: global (freed in
//  free()) or const (system-managed pool, never freed).
////////////////////////////////////////////////////////////

inline __host__ void riia_table_t::_build_usampler
( device::base_t & dev, const float_t & a_voigt )
{
    //  Build xg grid on host (40 values, trivial).
    float_t * h_xg  = new float_t[ n_xg ];
    const int n_lin = 18;
    const int n_log = n_xg - n_lin;
    const float_t x_lin_max = 8.f;
    const float_t x_max = 300.f;
    for( int j = 0; j < n_lin; ++ j )
        h_xg[ j ] = j / float_t( n_lin - 1 ) * x_lin_max;
    for( int j = 0; j < n_log; ++ j )
        h_xg[ n_lin + j ] = x_lin_max * powf
            ( x_max / x_lin_max, float_t( j + 1 ) / n_log );

    //  Allocate d_cdf + d_xg in global memory.
    const size_t n_total = size_t( n_u ) * n_xg;
    d_cdf = dev.malloc_device< float_t >( n_total );
    d_xg  = dev.malloc_device< float_t >( n_xg    );
    dev.cp( d_xg, h_xg, n_xg );

    //  Launch GPU kernel to build CDF (40 threads, each
    //  computes one row of 251 values).
    dim3 block( n_xg, 1, 1 );
    dim3 grid( 1, 1, 1 );
    dev.launch( build_usampler_gpu_kernel,
        grid, block, 0,
        ( const void * )0, * this );
    dev.sync_all_streams(  );

    //  Option B: copy USampler CDF + xg to const memory for
    //  broadcast-cache reads in the MCRT hot path.  R_IIA
    //  table (dat) stays in global (too large).
    if( use_const_mem )
    {
        float_t * d_cdf_c
            = dev.malloc_const< float_t >( n_total );
        float_t * d_xg_c
            = dev.malloc_const< float_t >( n_xg    );
        dev.f_cc( d_cdf_c, d_cdf,
                  n_total * sizeof( float_t ) );
        dev.f_cc( d_xg_c, d_xg, n_xg * sizeof( float_t ) );
        dev.free_device( d_cdf );
        dev.free_device( d_xg  );
        d_cdf = d_cdf_c;
        d_xg  =  d_xg_c;
    }
    delete [  ] h_xg;
    return;
}

////////////////////////////////////////////////////////////
//  _build_riia_gpu: allocate R_IIA
//  table on device + launch GPU
//  construction kernel.  Reads d_cdf +
//  d_xg (already on device from
//  _build_usampler).  All float_t.
////////////////////////////////////////////////////////////

inline __host__ void riia_table_t::_build_riia_gpu
( device::base_t & dev )
{
    dxo = ( 2.f * xo_max ) / float_t( n_xo - 1 );
    dxp = xp_max / float_t( n_xp - 1 );
    dg  = 2.f / float_t( n_g - 1 );

    const size_t n_tab = size_t( n_xo ) * n_xp * n_g;
    dat = dev.malloc_device< float_t >( n_tab );

    dim3 block( 64, 1, 1 );
    dim3 grid( ( n_xo + 63 ) / 64, n_xp, n_g );

    dev.launch( build_riia_gpu_kernel, grid, block, 0,
                ( const void * )0, * this );
    return dev.sync_all_streams(  );
}

////////////////////////////////////////////////////////////
//  free: release device memory.  dat: always freed (always
//    global memory).  d_cdf, d_xg: freed only if
//    !use_const_mem (global).  Const-mem pointers are NOT
//    freed (system-managed pool).
////////////////////////////////////////////////////////////

inline __host__ void riia_table_t::free
( device::base_t & dev )
{
    if( dat )
    {
        dev.free_device( dat );
        dat = nullptr;
    }
    if( ! use_const_mem )
    {
        if( d_cdf != nullptr )
        {
            dev.free_device( d_cdf );
            d_cdf  = nullptr ;
        }
        if( d_xg  != nullptr )
        {
            dev.free_device( d_xg );
            d_xg   = nullptr ;
        }
    }
    return;
};

