#!/usr/bin/env python3
"""Plane-parallel slab example using the low-level ``iterate()`` API.

Same physics as ``plane_parallel_hl.py`` but using the bare loop
(``core.iterator.iterate``) directly - no ``LineRt`` orchestrator.

Run from ``/tmp/line_rt``:

    python3 docs/examples/plane_parallel_lowlevel.py
"""

import os, sys;
_PROJECT = os.path.dirname( os.path.dirname( os.path.dirname( \
                                 os.path.realpath( __file__ ) ) ) );
if _PROJECT not in sys.path:
    sys.path.insert( 0, _PROJECT );

import matplotlib;
matplotlib.use( 'Agg' );
from numpy    import full, zeros, ones, array, sqrt, max as np_max, \
                     float64;
from numpy    import random;

from core.source             import make_cartesian_mesh;
from core.iterator           import iterate;
from core.visualize          import default_plot;
from molecular.lamda_format  import load_species_transition;

############################################################
#  CGS constants

h    = 6.62607015e-27;   # Planck constant [erg s]
c    = 2.99792458e10;    # speed of light [cm/s]
Lsun = 3.828e33;         # solar luminosity [erg/s]
AU   = 1.49598e13;       # AU in cm
ma   = 1.6605e-24;       # atomic mass unit [g]

# Unit conversion
t0 = 1;
l0 = AU;
m0 = ma * l0**3;

############################################################
#  1. Mesh

x_min  = ( -5, 0,   0   );
x_max  = (  5, 0.2, 0.2 );
n_cell = ( 64, 2,   2   );
mesh   = make_cartesian_mesh\
       ( n_cell = n_cell, x_min = x_min, x_max = x_max );
n_tot  = mesh[ 'n_tot' ];

############################################################
#  2. Physical parameters

tau0_slab   = 10.0;
b_sca       = 1.0e5;
mol_mass    = 28.0;
temperature = 2;
x_cross_cm  = [ ( x_max[ a ] - x_min[ a ] ) * l0 for a in range( 3 ) ];

############################################################
#  3. Fields (line-independent only; line-dependent computed by species)

shape3d = ( n_cell[ 2 ], n_cell[ 1 ], n_cell[ 0 ] );   # (nz, ny, nx)
fields  = {
    'b_sca'       : full( shape3d, b_sca, dtype = float64 ),
    'temp'        : full( shape3d, temperature, dtype = float64 ),
    'vel_0'       : zeros( shape3d, dtype = float64 ),
    'vel_1'       : zeros( shape3d, dtype = float64 ),
    'vel_2'       : zeros( shape3d, dtype = float64 ),
    'mfp_i_abs_0' : zeros( shape3d, dtype = float64 ),   # no dust absorption
};

############################################################
#  4. Photons (9-column: x,y,z, dx,dy,dz, proper, vel, sv)

n_photon = 20000;
lam      = 2.6e-1;   # CO J=1->0 ~ 2.6 mm [cm]
sigma    = b_sca / sqrt( 2 );
F0_cgs   = 1e6;   # Photon number fluxes in photon/cm^2/s
L0       = F0_cgs * ( ( x_max[ 1 ] - x_min[ 1 ] ) *
                      ( x_max[ 2 ] - x_min[ 2 ] ) ) * l0**2 / ( t0**-1 );
ph = zeros( ( n_photon, 9 ), dtype = float64 );
ph[ :, 0 ] = -4.999;
ph[ :, 1 ] = random.uniform( x_min[ 1 ], x_max[ 1 ], n_photon );
ph[ :, 2 ] = random.uniform( x_min[ 2 ], x_max[ 2 ], n_photon );
ph[ :, 3 ] = 1.0;
ph[ :, 6 ] = L0 / n_photon;
ph[ :, 8 ] = sigma;

############################################################
#  5. Species

lamda_path = os.path.join( _PROJECT, 'molecular', 'embedded', 'co.dat' );
co, tr     = load_species_transition( lamda_path, freq_GHz = 115.271202 );
tr_idx     = co.find_transition_idx( tr );
sigma_co   = co.cross_section( 0, b_sca );
n_species  = ( tau0_slab / x_cross_cm[ 0 ] ) / sigma_co;   # cm^-3

print( 'CO J=%s->%s, n_species=%.2e cm^-3' % ( tr.upper, tr.lower, \
                                                n_species ) );

############################################################
#  6. Run

print( 'Running 3 MC cycles ...' );
results, final_pops = iterate(
    ph, co, fields, mesh, n_cycles = 3,
    n_step = 20000, n_scat = 10000,
    ph_mode = 2,           # R_IIA const-mem (production)
    work_dir = None,       # auto: /tmp/line_rt/iterate_output
    n_species = n_species,
    transition_idx = tr_idx,
    mol_mass = mol_mass,
    unit_l0 = l0, unit_t0 = t0,
    par_overrides = { 'kinds' : 'fre fre per per per per' },
);

############################################################
#  7. Plot (default multi-panel)

hl_results = {
    'results'     : results,
    'populations' : final_pops,
    'mesh'        : mesh,
    'unit_l0'     : l0,
    'unit_t0'     : t0,
    'b_sca'       : fields.get( 'b_sca', full( shape3d, b_sca ) ),
    'flx'         : results[ -1 ].get( 'flx' ),
    'spectrum'    : { 'vel' : results[ -1 ].get( 'photons', {} ) \
                              .get( 'vel', array( [ ] ) ),
                      'n'   : ones( len( results[ -1 ] \
                                            .get( 'photons', {} ) \
                                            .get( 'vel', [ ] ) ) ) },
};

outpath = os.path.join( os.path.dirname( __file__ ), \
                        'plane_parallel_lowlevel_results.png' );
default_plot( hl_results, output_path = outpath );
print( '\nResults saved to %s' % outpath );

for k, res in enumerate( results ):
    flx   = res.get( 'flx' );
    exc   = res.get( 'exc_flux_flat', res.get( 'excitation_flux' ) );
    n_esc = len( res.get( 'photons', {} ).get( 'vel', [] ) );
    if flx is not None:
        print( '  Cycle %d: flx_max=%.2e, exc_max=%.2e, n_esc=%d' \
               % ( k, np_max( flx ), np_max( exc ), n_esc ) );
    else:
        print( '  Cycle %d: flx=N/A, exc=N/A, n_esc=%d' % ( k, n_esc ) );
