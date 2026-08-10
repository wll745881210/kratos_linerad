#pragma once

#include "block_data.h"
#include "../../src/device/general.h"

namespace prob
{
////////////////////////////////////////////////////////////
//  Photon generating ( reading-in )
////////////////////////////////////////////////////////////

struct gen_t : particle::generate::base_t< gen_t >
{
    ////////// Types //////////    
    using super_t = particle::generate::base_t< gen_t >;
    enum { read, gen_read } mode;

    ////////// Data //////////
    int        n_scat;
    int        n_step;
    int       ncol_ph;
    int     n_ph_read;
    void *     data_h;
    size_t     s_data;

    ////////// Functions //////////
    __host__ gen_t(  ) : data_h( nullptr ) {  };

    __host__ virtual void init
    ( const input & args, particle::base_t & mod ) override
    {
        super_t::init( args, mod );
        n_scat    = args.get< int >
            ( "particle", "n_scat", 0 );
        n_step    = args.get< int >
            ( "particle", "n_step", 1000 );
        n_ph_read = args.get< int >
            ( "line_rt", "n_ph_read", -1 );
        try_read_photon( args );
        mode = gen_read;
        return;
    };

    __host__ virtual void finalize
    ( particle::base_t & mod ) override
    {
        if( data_h != nullptr )
            mod.p_dev->free_host( data_h );
        return;
    };

    __host__ bool try_read_photon( const input & args )
    {
        const auto file = args.get< std::string >
                 ( "line_rt", "photon_file", "" );
        if( file.empty(  ) )
            return false;

        const auto pref = args.get< std::string >
                      ( "line_rt", "photon_pref", "par" );
        binary_io::default_t bio;
        try
        {
            bio.open( file, "r" );
            bio.load(  );
        }
        catch( ... )
        {
            std::cerr << "Unable to open particle file "
                      << file << '\n';
            bio.close(  );
            return false;
        }
        bio.read( & ncol_ph, pref + "_n_col" );
        bio.read( & n_par,   pref + "_n_par" );
        if( ncol_ph != 7 && ncol_ph != 8 && ncol_ph != 9 )
        {
            std::cerr << "ncol_ph = " << ncol_ph << '\n';
            throw std::runtime_error
            ( "Invalid column number for photon reading" );
        }
        if( n_ph_read > 0 && n_ph_read < n_par )
            n_par = n_ph_read;

        data_h = malloc
            ( size_t( ncol_ph ) * n_par * sizeof( float ) );
        if( bio.read( data_h, pref + "_par_dat" )
            != n_par * ncol_ph )
            throw std::runtime_error
                ( "Incorrect particle data stride." );

        bio.close(  );
        std::cout << "Read " << n_par << " photons from "
                  << "file : " << file << '\n';
        return true;
    };

    template< class par_T > __host__
    void  load_par( par_T & par, const size_t & i_par )
    {
        auto * d_ph = ( float * )( data_h )
            + i_par * ncol_ph;
        for( int a = 0; a < 3; ++ a )
        {
            par.x  [ a ] = d_ph[     a ];
            par.dir[ a ] = d_ph[ 3 + a ];
        }
        par.n_scat   =   n_scat;
        par.step     =   n_step;        
        par.proper   = d_ph[ 6 ];
        par.vel      = ( ncol_ph >= 8 ) ? d_ph[ 7 ] : 0.f;
        par.sv       = ( ncol_ph >= 9 ) ? d_ph[ 8 ] : 0.f;
        par.proper_0 = par.proper;
        for( int a = 0; a < 3; ++ a )
            par.x_last_scat[ a ] = par.x[ a ];
        //  Initial last-scatter position = init position

        par.tau_remain = -logf
            ( 1e-4f + 0.9999f * ( float( std::rand(  ) )
                         / ( float( RAND_MAX ) + 1 ) ) );
        par.dest.todo = particle::to_keep;
        return;
    };

    template< class pol_T, class map_T > __host__
    void generate( pol_T & pool, const map_T & bmap,
                   particle::base_t & mod )
    {
        using par_t = typename pol_T::par_t;
        generate_once( pool, mod );
        if( data_h != nullptr )
            mod.p_dev->a_cp
                ( & pool[ 0 ], data_h, s_data, mod.stream );
        return mod.p_dev->sync_all_streams(  );
    };

    template< class pol_T > __host__ void
    generate_once( pol_T & pool, particle::base_t & mod )
    {
        if( mod.p_mesh->p_com->is_root(  ) )
            std::cout
                << "Generating/copying photons "
                << "once ... " << std::flush;

        using par_t = typename pol_T::par_t;
        std::vector< par_t > pool_h;
        pool_h.reserve( n_par );

        par_t par;
        for( size_t i = 0; i < n_par; ++ i )
        {
            load_par( par, i );

            mesh::region_logic_t r;
            par.ib_l = -1;
            for( auto & b : ( * mod.p_mesh ) )
                if( b.reg.inside( par.x ) )
                {
                    par.ib_l = b.id_l;
                    r = b.reg;
                    break;
                }
            if( par.ib_l < 0 )
                continue;

            const auto & geo
                ( mod.p_mesh->block( r ).geo );
            for( int a = 0; a < 3; ++ a )
                par.i[ a ] = 1. / geo.dx0[ a ]
                      * ( par.x[ a ] - geo.x_fc( a, 0 ) );
            pool_h.push_back( par );
        }
        free( data_h );
        data_h = nullptr;

        pool.set_mem( mod, pool_h.size(  ) );
        s_data = pool_h.size(  ) * sizeof(  par_t );
        data_h = mod.p_dev->f_malloc_host( s_data );
        memcpy( data_h, pool_h.data(  ),   s_data );

        if( mod.p_mesh->p_com->is_root(  ) )
            std::cout << " Done." << std::endl;
        return;
    }
};  //  class gen_t

}  //  namespace prob
