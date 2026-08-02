#!/usr/bin/env python3
"""Plane-parallel slab example with a **user-defined transition**.

Same physics, geometry and workflow as ``plane_parallel_hl.py``,
but the transition is NOT taken from the LAMDA database — it is
defined from physical parameters with
``TransitionInfo.user_defined( )``.

This is the way to study a transition whose line data (A_ul,
frequency, ...) you know but that has no LAMDA entry, neither
online nor embedded.

Run with temporary working directory ``/dev/shm/line_rt``:

    python3 docs/examples/plane_parallel_user_defined.py

"""

############################################################
#  0. Header: Imports

import importlib.util, os;
import matplotlib;
matplotlib.use( 'Agg' );
from numpy import full, zeros, sqrt

##############################
#  Load the pipeline without installation (works with
#  symlinks too).  If installed (``pip install -e .``),
#  replace the 6 lines below with: import line_rt
##############################
pipeline_file = os.path.dirname\
              ( os.path.realpath( __file__ ) ) \
              + '/../../line_rt.py';
module_spec   = importlib.util.spec_from_file_location\
              ( 'line_rt', pipeline_file );
line_rt = importlib.util.module_from_spec( module_spec );
module_spec.loader.exec_module( line_rt );
##############################

#  Kratos binary location - MUST be set explicitly (no
#  default).  Either pass kratos_root=... to LineRt, or set
#  the env var: export
#  KRATOS_ROOT=/path/to/kratos_build_tree

KRATOS_ROOT = os.path.expanduser( '~/apps/kratos_line_rt' );

############################################################
#  1. Physics: CGS constants, and the concerned transition

AU   = line_rt.  AU;
Lsun = line_rt.Lsun;

#  User-defined 2-level transition (NOT in the LAMDA database).
#
#  Specify the Einstein A coefficient and the line frequency;
#  everything else has a physical default:
#    - g_u = g_l = 1            (statistical weights)
#    - E_u/K = h*nu/k_B         (upper-level energy)
#    - mol_mass from species_name when in the built-in table
#      (here 'CO' -> 28 amu), otherwise pass mol_mass=...
ti = line_rt.TransitionInfo.user_defined(
    A_ul       = 1.0e-6,      # Einstein A [s^-1]
    freq_GHz   = 115.271,     # line frequency [GHz]
    g_u        = 3,  g_l = 1, # degeneracies
    species_name = 'CO',      # in the mass table -> mol_mass=28
);

#  Show the transition information (same interface as a
#  LAMDA-derived TransitionInfo)
ti.show_transition(  );

############################################################
#  2. Configure LineRt (Group 1: species-based)
#
#  n_species derived from tau0_slab: n = tau0 / (L_slab *
#  sigma_co) LineRt computes sigma_co internally from
#  species + b_sca, so we pass n_species as a callable that
#  returns the same constant.

##############################
# 2.1 Define the fields

temperature = 2.7;  # Kelvin

tau0_slab = 1e1;
sigma_co  = ti.cross_section( temperature );
L_slab_cm = 10.0 * AU;   # x_min=-5, x_max=5 -> L=10 AU
n_species = ( tau0_slab / L_slab_cm ) / sigma_co; # cm^-3

# Or you can write n_species in cm^-3 on your own, no need
# to compute from the things above, like this:
# n_species = 1e2

def n_total_callable( x, y, z ):
    res = full( x.shape, n_species );
    res[ x > 0 ] *= 2;
    return res;
#
def temperature_callable( x, y, z ):
    return full( x.shape, temperature );
#
def vx_callable( x, y, z ):
    return zeros( x.shape );
#

##############################
# 2.2 Configure the LineRT object

rt = line_rt.LineRt(
    n_cell       = ( 64, 16,   2 ),
    x_min        = ( -8, -2,   0 ),
    x_max        = (  8,  2, 0.2 ),
    unit_l0      = AU, unit_t0 = 1.0,

    transition_info = ti,
    n_species    = n_total_callable,
    temperature  = temperature_callable,
    vel          = ( vx_callable, 0.0, 0.0 ),

    ph_mode      = 2, # R_IIA const-mem (production)
    n_step       = 20000, n_scat = 10000,
    visualize    = False,
    kratos_root  = KRATOS_ROOT,
);
rt.set_boundary( 'fre fre per per per per' );

# Uncomment to plot the configured input fields (no Kratos
# run) to verify: [ n_species, temperature, mfp_i_sca_0,
# b_sca, mfp_i_abs_0, vx, vy, vz ]:

# rt.plot_input( output_path =
#                'plane_parallel_user_defined_input.png' );

print( '==============================' );

############################################################
#  3. Source (photon-number flux, default units)
#
#  F0 = 1e6 photon/cm^2/s, sv = b_sca/sqrt(2), x = -5.
#  With default units='photon', flux is photon number
#  [photons cm^-2 s^-1], no energy conversion needed.
#  Pass units='energy' for erg cm^-2 s^-1 (uses the
#  transition photon energy automatically).

F0_cgs = 1e6;   # photon number flux [photons cm^-2 s^-1]

rt.add_source\
( type     = 'slab', x = -5, direction = '+x',
  n_photon = 20000,
  flux     = F0_cgs, # photon-number flux [cm^-2 s^-1]
  sigma    = ti.doppler_b( temperature ) / sqrt( 2 ) );

print( 'user-defined line, n_species = %.2e cm^-3, T = %.2e K' %
       ( n_species, temperature ) );
print( 'Mesh: %s, external photon sources: %d' %
       ( rt._n_cell, len( rt._sources ) ) );
rt.show_sources(  );

print( '========================================' );

############################################################
#  4. Run the iterations!
##############################

n_cycle   = 3;
print( 'Running %d MC cycles ...' % n_cycle );
rt.run( n_cycle );
print( '========================================' );

############################################################
#  5. Print run info

res_list = rt._results[ 'results' ];
for k, res in enumerate( res_list ):
    flx   = res.get( 'flx' );
    exc   = res.get( 'exc_flux_flat',
                     res.get( 'excitation_flux' ) );
    n_esc = len( res.get( 'photons', {} ).get( 'vel', [] ) );
    if flx is not None:
        print( 'Cycle %d: flx_max=%.2e, n_esc=%d' \
               % ( k, flx.max(  ), n_esc ) );
    else:
        print( '  Cycle %d: flx=N/A, n_esc=%d'
               % ( k, n_esc ) );
print( '========================================' );

############################################################
#  6. Plot (default multi-panel)

outpath = os.path.join( os.path.dirname( __file__ ), \
                        'plane_parallel_user_defined_results.png' );
rt.plot_results( output_path = outpath );
print( '\nResults saved to %s' % outpath );

############################################################
