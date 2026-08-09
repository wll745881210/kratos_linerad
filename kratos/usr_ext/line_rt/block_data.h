#pragma once

namespace prob
{

////////////////////////////////////////////////////////////
//  Types
////////////////////////////////////////////////////////////

using type::idx_t;
using type::float_t;
using type::coord_t;
using type::float2_t;

using mesh::f_cp_t;
using mesh::f_new_t;
using mesh::f_free_t;
using mesh::f_read_t;
using mesh::f_write_t;

////////////////////////////////////////////////////////////
//  Radiation internal data holder
////////////////////////////////////////////////////////////

struct rad_t
{
    //  Data
    mesh::dat_3d_t< float_t > mfp_i_sca_0;
    mesh::dat_3d_t< float_t > mfp_i_abs_0;
    mesh::dat_3d_t< float_t > b_sca;
    mesh::dat_3d_t< float_t > flx;
    mesh::dat_3d_t< float_t > excitation_flux;
    mesh::dat_3d_t< float_t > vel;

    //  Imaging-related
    //  j_cam : per-cell, per-velocity-channel
    //  scattering equivalent emissivity.
    //  emiss : per-cell line-center intrinsic
    //  emissivity
    //  j0 = n_u * A_ul
    //      / ( 4 * pi * sqrt( pi ) * b ),
    //  The imaging pass forms
    //  j(dv) = emiss * H(a, dv/b).
    mesh::dat_3d_t< float_t > j_cam;
    mesh::dat_3d_t< float_t > emiss;

    bool ray_output = false;
    int  ray_id     = -1;

    //  Imaging configuration (mirrored on
    //  host & device blocks via block_yield;
    //  rad.imaging gates j_cam zeroing /
    //  accumulation / write so non-imaging
    //  runs pay no cost).
    bool imaging = false;
    int  n_chan  = 0;

    //  Functions
    __host__ __device__ __forceinline__
    int & order(  )
    {
        return mfp_i_sca_0.n_gh[ 0 ];
    }
    __host__ __device__ __forceinline__
    const int & n_fld(  ) const
    {
        return flx.n_int;
    }
    __host__ int & n_fld(  )
    {
        return flx.n_int;
    }
    __host__ std::string prefix(  ) const
    {
        return "rad_";
    }
};

////////////////////////////////////////////////////////////
//  Radiation block data type
////////////////////////////////////////////////////////////

struct block_data_t : mesh::block::base_data_t
{
    //  Data
    rad_t rad;
    bool  output;

    //  Functions
    __host__ virtual void set_output
    ( const bool & output = true )
    {
        this->output = output;
    }

    __host__ virtual void setup
    ( const f_new_t & f_n )
    {
        auto n_gh( type::idx_t::null(  ) );
        for( int a = 0; a < geo.n_dim; ++ a )
            n_gh[ a ] = rad.order(  );
        const auto & n_fld( rad.n_fld(  ) );
        rad.mfp_i_sca_0.init
            ( f_n, geo.n_ceff, n_gh, 1 );
        rad.mfp_i_abs_0.init
            ( f_n, geo.n_ceff, n_gh, 1 );
        rad.b_sca.init
            ( f_n, geo.n_ceff, n_gh, 1 );
        rad.vel.init
            ( f_n, geo.n_ceff, n_gh, 3 );
        rad.flx.init
            ( f_n, geo.n_ceff, n_gh, n_fld );
        rad.excitation_flux.init
            ( f_n, geo.n_ceff, n_gh, n_fld );
        //  Line-centre emissivity (always
        //  allocated; read from the field
        //  file, used only by the imaging
        //  pass).
        rad.emiss.init
            ( f_n, geo.n_ceff, n_gh, 1 );
        //  Per-channel scattering source
        //  toward the camera; only
        //  allocated when imaging is
        //  enabled (n_chan > 0).
        const int n_chan_img
            = rad.imaging ? rad.n_chan : 0;
        rad.j_cam.init
            ( f_n, geo.n_ceff, n_gh,
              n_chan_img );
    }

    __host__ virtual void free
    ( const f_free_t & f_f )
    {
        rad.mfp_i_sca_0.free( f_f );
        rad.mfp_i_abs_0.free( f_f );
        rad.b_sca.free( f_f );
        rad.flx.free( f_f );
        rad.excitation_flux.free( f_f );
        rad.emiss.free( f_f );
        rad.j_cam.free( f_f );
        rad.vel.free( f_f );
    }

    __host__ virtual void copy_input
    ( const f_cp_t & f_cp,
      mesh::block::base_data_t & tgt_ )
    {
        //  Intentionally blank -- init on
        //  the GPU side
    }

    __host__ virtual void copy_output
    ( const f_cp_t & f_cp,
      mesh::block::base_data_t & tgt_ )
    {
        auto & tgt
            = dynamic_cast< block_data_t & >
              ( tgt_ );
        tgt.output = this->output;
        rad.mfp_i_sca_0.cp_to
            ( tgt.rad.mfp_i_sca_0, f_cp );
        rad.mfp_i_abs_0.cp_to
            ( tgt.rad.mfp_i_abs_0, f_cp );
        rad.excitation_flux.cp_to
            ( tgt.rad.excitation_flux, f_cp );
        rad.b_sca.cp_to
            ( tgt.rad.b_sca, f_cp );
        rad.flx.cp_to
            ( tgt.rad.flx, f_cp );
        rad.vel.cp_to
            ( tgt.rad.vel, f_cp );
        rad.emiss.cp_to
            ( tgt.rad.emiss, f_cp );
        if( rad.imaging )
            rad.j_cam.cp_to
                ( tgt.rad.j_cam, f_cp );
    }

    __host__ virtual void read( const f_read_t & f_r )
    {
        rad.b_sca.read
            ( f_r, rad.prefix(  )
              + "b_sca_" );
        rad.flx.read
            ( f_r, rad.prefix(  )
              + "flx_" );
        rad.mfp_i_sca_0.read
            ( f_r, rad.prefix(  )
              + "mfp_i_sca_0_" );
        rad.mfp_i_abs_0.read
            ( f_r, rad.prefix(  )
              + "mfp_i_abs_0_" );
        rad.excitation_flux.read
            ( f_r, rad.prefix(  )
              + "excitation_flux_" );
        rad.vel.read
            ( f_r, rad.prefix(  )
              + "vel_" );
        rad.emiss.read
            ( f_r, rad.prefix(  )
              + "emiss_" );
    }

    __host__ virtual void write( const f_write_t & f_w )
    {
        if( ! output )
            return;
        rad.mfp_i_sca_0.write
            ( f_w, rad.prefix(  ) + "mfp_i_sca_0_" );
        rad.mfp_i_abs_0.write
            ( f_w, rad.prefix(  ) + "mfp_i_abs_0_" );
        rad.b_sca.write( f_w, rad.prefix(  ) + "b_sca_" );
        rad.  flx.write( f_w, rad.prefix(  ) + "flx_"   );
        rad.excitation_flux.write
            ( f_w, rad.prefix(  ) + "excitation_flux_"  );
        rad.  vel.write( f_w, rad.prefix(  ) + "vel_"   );
        rad.emiss.write( f_w, rad.prefix(  ) + "emiss_" );
        if( rad.ray_output )
        {
            rad.flx.write
                ( f_w, rad.prefix(  ) + "ray_flx_"      );
            rad.excitation_flux.write
                ( f_w, rad.prefix(  ) + "ray_exc_flux_" );
        }
        if( rad.imaging )
            rad.j_cam.write
                ( f_w, rad.prefix(  ) + "j_cam_" );
        //  Diagnostic: dump the per-cell,
        //  per-channel scattering equivalent
        //  emissivity ( to camera )
        return;
    }
};

////////////////////////////////////////////////////////////
//  Proxy for access
////////////////////////////////////////////////////////////

struct prx_t
    : particle::radiation::proxy_t< block_data_t >
{
    //  Type and data
    using bdt_t = typename prx_t::bdt_t;
    rad_t rad;

    //  Functions
    prx_t(  ) = default;

    template< class bdt_T > __forceinline__
    static auto d( const bdt_T & bdt )
    {
        const auto & b_d
            = dynamic_cast< const bdt_t & > ( bdt );
        prx_t res;
        res.rad = b_d.rad;
        res.geo = b_d.geo;
        return res;
    }

    __host__ virtual void setup
    ( const mesh::block::dual_t & d,
      const std::map< int, int > & m_rank,
      ::particle::base_t & mod ) override
    {
        auto & b_d( ref( d.d(  ) ) );
        rad = b_d.rad;
        particle::proxy_base_t::setup( d, m_rank, mod );
    }
};

}  //  namespace prob
