#!/usr/bin/env python3
"""Plane-parallel slab example using the low-level ``iterate()`` API.

Same physics as ``plane_parallel_hl.py`` but using the bare loop
(``core.iterator.iterate``) directly - no ``LineRt`` orchestrator.

Run from ``/dev/shm/line_rt``:

    python3 docs/examples/plane_parallel_lowlevel.py
"""
############################################################
#  Header: Imports

import importlib.util, os;

#  Load the pipeline without installation (works with symlinks too).
#  If installed (``pip install -e .``), replace the 3 lines below
#  with:  from line_rt import iterate, make_cartesian_mesh, \
#                 default_plot, TransitionInfo, AU
_PIPELINE = os.path.join( os.path.dirname( os.path.dirname( \
    os.path.dirname( os.path.realpath( __file__ ) ) ) ), 'line_rt.py' );
_spec = importlib.util.spec_from_file_location( 'line_rt', _PIPELINE );
line_rt = importlib.util.module_from_spec( _spec );
_spec.loader.exec_module( line_rt );

import matplotlib;
matplotlib.use( 'Agg' );
from numpy    import full, zeros, ones, array, sqrt, max as np_max, \
                     float64;
from numpy    import random;

make_cartesian_mesh     = line_rt.make_cartesian_mesh;
iterate                 = line_rt.iterate;
default_plot            = line_rt.default_plot;
TransitionInfo          = line_rt.TransitionInfo;

#  Kratos binary location - MUST be set explicitly (no default).
#  Either pass kratos_root=... to iterate(), or set the env var:
#    export KRATOS_ROOT=/path/to/kratos_build_tree
KRATOS_ROOT = os.path.expanduser( '~/apps/kratos_line_rt' );

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

x_min  = ( -8, -2, 0   );
x_max  = (  8,  2, 0.2 );
n_cell = ( 64, 16, 2   );
mesh   = make_cartesian_mesh\
       ( n_cell = n_cell, x_min = x_min, x_max = x_max );
n_tot  = mesh[ 'n_tot' ];

############################################################
#  2. Physical parameters

tau0_slab   = 1e1;
temperature = 2.7;   # Kelvin

############################################################
#  3. Species (TransitionInfo resolves species data, the
#     transition index, and the molecular mass automatically)

ti          = TransitionInfo( 'CO', 0 );
co          = ti.species_data;      # SpeciesData for iterate()
tr_idx      = ti.transition_idx;
mol_mass    = ti.mol_mass;          # from built-in table (28.0)

b_sca       = ti.doppler_b( temperature );
sigma_co    = ti.cross_section( temperature );
L_slab_cm   = 10.0 * AU;   # same convention as the hl example
n_species   = ( tau0_slab / L_slab_cm ) / sigma_co;   # cm^-3

ti.show_transition(  );
print( 'n_species = %.2e cm^-3' % n_species );

############################################################
#  4. Fields (line-independent only; line-dependent computed by species)

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
#  5. Photons (9-column: x,y,z, dx,dy,dz, proper, vel, sv)

n_photon = 20000;
lam      = ti.transition.wavelength_um * 1e-4;   # CO J=1->0 [cm]
sigma    = b_sca / sqrt( 2 );
F0_cgs   = 1e6;   # Photon number flux [photons cm^-2 s^-1]
#  Slab source: plane x = -5, spanning y in (-2,2), z in (0,0.2),
#  direction +x.  proper per packet = flux * area / n_photon.
source_area_cm2 = ( x_max[ 1 ] - x_min[ 1 ] ) * \
                  ( x_max[ 2 ] - x_min[ 2 ] ) * l0**2;
ph = zeros( ( n_photon, 9 ), dtype = float64 );
ph[ :, 0 ] = -5.0;
ph[ :, 1 ] = random.uniform( x_min[ 1 ], x_max[ 1 ], n_photon );
ph[ :, 2 ] = random.uniform( x_min[ 2 ], x_max[ 2 ], n_photon );
ph[ :, 3 ] = 1.0;
ph[ :, 6 ] = F0_cgs * source_area_cm2 / n_photon;
ph[ :, 8 ] = sigma;

############################################################
#  6. Run

print( 'Running 3 MC cycles ...' );
results, final_pops = iterate(
    ph, co, fields, mesh, n_cycles = 3,
    n_step = 20000, n_scat = 10000,
    ph_mode = 2,           # R_IIA const-mem (production)
    work_dir = None,       # auto: /dev/shm/line_rt/iterate_output
    n_species = n_species,
    transition_idx = tr_idx,
    mol_mass = mol_mass,
    unit_l0 = l0, unit_t0 = t0,
    par_overrides = { 'kinds' : 'fre fre per per per per' },
    kratos_root = KRATOS_ROOT,
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
default_plot( hl_results, transition_info = ti, \
              output_path = outpath );
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
