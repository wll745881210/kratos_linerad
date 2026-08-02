#!/usr/bin/env python3
"""Line RT CLI - command-line launcher for the LineRt high-level API.

Examples
--------
# Group-2 (explicit opacity) run, no species data needed:
line-rt --mfp-i-sca-0 1e-13 --b-sca 1e5 --ph-mode 2 --n-photon 20000

# CO J=1->0 with species data:
line-rt --species CO --n-species 1e4 --temperature 100 --ph-mode 2

# Slab source with energetic flux:
line-rt --species CO --n-species 1e4 --temperature 100 \
    --source-type slab --source-x -5.0 --flux 1e-3 --source-units energy
"""

############################################################
#  Header: Imports

import argparse; \
import os; \
import sys; \

from numpy import max as np_max; \


from line_rt import LineRt, TransitionInfo, \
    show_available_species, show_available_transitions;


############################################################
# CLI main entry

def main( ):
    parser = argparse.ArgumentParser(
        description = 'Line radiative-transfer CLI (Kratos backend).' );

    ############################################################
    # Geometry
    g = parser.add_argument_group( 'Geometry' );
    g.add_argument( '--n-cell', default = '64 2 2', \
                    help = 'Cells per dimension: nx ny nz (default: 64 2 2)' );
    g.add_argument( '--x-min', default = '-5 0 0', \
                    help = 'Domain lower bounds in code units ' \
                           '(default: -5 0 0)' );
    g.add_argument( '--x-max', default = '5 0.2 0.2', \
                    help = 'Domain upper bounds in code units ' \
                           '(default: 5 0.2 0.2)' );
    g.add_argument( '--unit-l0', type = float, default = 1.49598e13, \
                    help = 'Length unit [cm] (default: 1 AU)' );
    g.add_argument( '--unit-t0', type = float, default = 1.0, \
                    help = 'Time unit [s] (default: 1.0)' );
    g.add_argument( '--boundary', default = 'fre fre per per per per', \
                    help = '6 boundary kinds: -x +x -y +y -z +z (fre|per)' );

    ############################################################
    # Species (Group 1)
    s = parser.add_argument_group( 'Species (Group 1)' );
    s.add_argument( '--species', default = None, \
                    help = 'Species name (e.g. CO) or LAMDA .dat path' );
    s.add_argument( '--transition-idx', type = int, default = 0, \
                    help = 'Transition index (default: 0)' );
    s.add_argument( '--freq-ghz', type = float, default = None, \
                    help = 'Select transition by frequency [GHz] ' \
                           '(overrides --transition-idx)' );
    s.add_argument( '--n-species', type = float, default = None, \
                    help = 'Number density [cm^-3]' );
    s.add_argument( '--temperature', type = float, default = None, \
                    help = 'Gas temperature [K]' );
    s.add_argument( '--mol-mass', type = float, default = None, \
                    help = 'Molecular mass [amu] ' \
                           '(default: built-in species table)' );
    s.add_argument( '--list-species', action = 'store_true', \
                    help = 'List available species and exit' );
    s.add_argument( '--list-transitions', default = None, \
                    help = 'List transitions of a species and exit' );

    ############################################################
    # Explicit opacity (Group 2)
    o = parser.add_argument_group( 'Explicit opacity (Group 2)' );
    o.add_argument( '--b-sca', type = float, default = None, \
                    help = 'Doppler b-parameter [cm/s]' );
    o.add_argument( '--mfp-i-sca-0', type = float, default = None, \
                    help = 'Inverse scattering MFP [cm^-1]' );
    o.add_argument( '--mfp-i-abs-0', type = float, default = 0.0, \
                    help = 'Inverse absorption MFP [cm^-1] (default: 0)' );
    o.add_argument( '--vel', default = '0 0 0', \
                    help = 'Bulk velocity vx vy vz [cm/s]' );

    ############################################################
    # Source
    src = parser.add_argument_group( 'Source' );
    src.add_argument( '--source-type', default = 'slab', \
                      choices = [ 'slab', 'point' ], \
                      help = 'Source geometry' );
    src.add_argument( '--source-x', type = float, default = None, \
                      help = 'Slab source x-coordinate [code units]' );
    src.add_argument( '--source-pos', default = None, \
                      help = 'Point source position: x y z [code units]' );
    src.add_argument( '--source-dir', default = '+x', \
                      help = 'Slab direction: +x or -x (default: +x)' );
    src.add_argument( '--n-photon', type = int, default = 20000, \
                      help = 'Number of photon packets' );
    src.add_argument( '--luminosity', type = float, default = None, \
                      help = 'Point-source luminosity: photon-number ' \
                             '[ph/s] (or erg/s with --source-units energy)' );
    src.add_argument( '--flux', type = float, default = None, \
                      help = 'Slab-source flux: photon-number ' \
                             '[ph cm^-2 s^-1] (or erg cm^-2 s^-1 with ' \
                             '--source-units energy)' );
    src.add_argument( '--source-units', default = 'photon', \
                      choices = [ 'photon', 'energy' ], \
                      help = 'Units of --flux/--luminosity: ' \
                             'photon (default) or energy (erg-based; ' \
                             'requires a species transition for the ' \
                             'wavelength)' );

    ############################################################
    # RT parameters
    rt = parser.add_argument_group( 'Radiative transfer' );
    rt.add_argument( '--ph-mode', type = int, default = 0, \
                     choices = [ 0, 1, 2, 3 ], \
                     help = '0=CFR, 1/2/3=R_IIA (default: 0)' );
    rt.add_argument( '--a-voigt', type = float, default = None, \
                     help = 'Voigt damping parameter ' \
                            '(default: pure Gaussian or auto from species)' );
    rt.add_argument( '--n-step', type = int, default = 10000, \
                     help = 'Max path segments per photon (default: 10000)' );
    rt.add_argument( '--n-scat', type = int, default = 10000, \
                     help = 'Max scattering events per photon ' \
                            '(default: 10000)' );
    rt.add_argument( '--n-fld', type = int, default = 1, \
                     help = 'Number of flux components (default: 1)' );
    rt.add_argument( '--n-cycles', type = int, default = 3, \
                     help = 'MC->population->MC cycles (default: 3)' );
    rt.add_argument( '--n-emission-max', type = int, default = 10, \
                      help = 'Max internal emission photons per cell ' \
                             'per cycle' );
    rt.add_argument( '--proper-scale', type = float, default = 1.0, \
                     help = 'Rescale every photon proper weight by this ' \
                            'factor before writing (default: 1.0 = no ' \
                            'rescale). Use < 1 for very high-flux runs ' \
                            'whose FP32 flux maps would overflow ' \
                            '(>= 3.4e38); the read-back flux is divided ' \
                            'back automatically.' );

    ############################################################
    # Output
    out = parser.add_argument_group( 'Output' );
    out.add_argument( '--work-dir', default = None, \
                      help = 'Working directory (default: auto under ' \
                             '/dev/shm/line_rt, fall back to /tmp/line_rt)' );
    out.add_argument( '--kratos-root', default = None, \
                      help = 'Kratos build tree root (must contain ' \
                             'bin/kratos). Default: KRATOS_ROOT env ' \
                             'var or ~/apps/kratos_line_rt' );
    out.add_argument( '--no-plot', action = 'store_true', \
                      help = 'Disable matplotlib visualisation' );
    args = parser.parse_args( );

    ############################################################
    # Parse multi-value args
    n_cell = tuple( int( v ) for v in args.n_cell.split( ) );
    x_min  = tuple( float( v ) for v in args.x_min.split( ) );
    x_max  = tuple( float( v ) for v in args.x_max.split( ) );
    vel    = tuple( float( v ) for v in args.vel.split( ) );

    ############################################################
    # Species helpers (Group 1)
    if args.list_species:
        show_available_species( );
        return;
    if args.list_transitions:
        show_available_transitions( args.list_transitions );
        return;

    ti = None;
    if args.species is not None:
        ti = TransitionInfo(
            args.species,
            transition_idx = args.transition_idx,
            freq_GHz       = args.freq_ghz,
            mol_mass       = args.mol_mass, );

    ############################################################
    # Build LineRt
    rt_obj = LineRt(
        n_cell          = n_cell, x_min = x_min, x_max = x_max,
        unit_l0         = args.unit_l0, unit_t0 = args.unit_t0,
        transition_info = ti,
        n_species       = args.n_species, temperature = args.temperature,
        b_sca           = args.b_sca, mfp_i_sca_0 = args.mfp_i_sca_0,
        mfp_i_abs_0     = args.mfp_i_abs_0,
        vel             = vel,
        a_voigt         = args.a_voigt,
        ph_mode         = args.ph_mode,
        n_step          = args.n_step, n_scat = args.n_scat,
        n_fld           = args.n_fld, n_cycles = args.n_cycles,
        path            = args.work_dir,
        visualize       = not args.no_plot,
        n_emission_max  = args.n_emission_max,
        proper_scale    = args.proper_scale,
        kratos_root     = args.kratos_root,
    );
    rt_obj.set_boundary( args.boundary );

    ############################################################
    # Add source
    src_kwargs = dict( type = args.source_type, n_photon = args.n_photon, \
                       luminosity = args.luminosity, flux = args.flux, \
                       units = args.source_units );
    if args.source_type == 'slab':
        src_kwargs[ 'x' ]         = args.source_x;
        src_kwargs[ 'direction' ] = args.source_dir;
    else:
        if args.source_pos:
            src_kwargs[ 'position' ] = tuple( float( v ) \
                for v in args.source_pos.split( ) );
    rt_obj.add_source( **src_kwargs );

    ############################################################
    # Run
    print( 'ph_mode=%d, n_photon=%d, n_cycles=%d' \
           % ( args.ph_mode, args.n_photon, args.n_cycles ) );
    results = rt_obj.run( );

    ############################################################
    # Summary
    print( '\n=== Summary ===' );
    for k, res in enumerate( results.get( 'results', [ ] ) ):
        flx  = res.get( 'flx' );
        exc  = res.get( 'exc_flux_flat', res.get( 'excitation_flux' ) );
        phot = res.get( 'photons', { } );
        n_esc = len( phot.get( 'vel', [ ] ) ) if phot else 0;
        if flx is not None:
            print( '  Cycle %d: flx_max=%.2e' % ( k, np_max( flx ) ), \
                   end = '  ' );
        else:
            print( '  Cycle %d: flx=N/A' % k, end = '  ' );
        if exc is not None:
            print( 'exc_max=%.2e' % np_max( exc ), end = '  ' );
        else:
            print( 'exc=N/A', end = '  ' );
        print( 'n_esc=%d' % n_esc );

    print( '\nWork dir: %s' % rt_obj._path );


if __name__ == '__main__':
    main( );
