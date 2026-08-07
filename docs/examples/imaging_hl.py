#!/usr/bin/env python3
"""Imaging example using the high-level ``LineRt`` API.

Extends ``plane_parallel_hl.py`` with a velocity gradient and
produces a position-velocity (PV) cube via the two-step imaging
method (scattering-source-function sampling + non-scattering
ray tracing) implemented on the Kratos side.

The imaging pass runs automatically on the **final** MC cycle:
the scattering MC accumulates a per-cell source function toward
the camera, then a separate non-scattering ray tracer integrates
the transfer equation along each pixel's line of sight.

Run with temporary working directory ``/dev/shm/line_rt``:

    python3 docs/examples/imaging_hl.py

"""

############################################################
#  0. Header: Imports

import importlib.util, os;
import matplotlib;
matplotlib.use( 'Agg' );
import matplotlib.pyplot as plt;
import sys as _sys;
_sys.path.insert( 0, '/home/lilew/Seafile/seafile_sync/'
                     'current_work/kratos_linerad/Figures/code' );
from line_rt_style import use_house_style;
use_house_style(  );
from numpy import full, zeros, sqrt, arange

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

# CO J=1->0 (idx 0)
ti = line_rt.TransitionInfo( 'CO', 0 );
ti.show_transition(  );

############################################################
#  2. Configure LineRt (Group 1: species-based)

temperature = 2.7;  # Kelvin

tau0_slab = 1e1;
sigma_co  = ti.cross_section( temperature );
L_slab_cm = 10.0 * AU;   # x_min=-5, x_max=5 -> L=10 AU
n_species = ( tau0_slab / L_slab_cm ) / sigma_co; # cm^-3

# Stepped density: 2x for x > 0 (same as plane_parallel_hl)
def n_total_callable( x, y, z ):
    res = full( x.shape, n_species );
    res[ x > 0 ] *= 2;
    return res;
#
def temperature_callable( x, y, z ):
    return full( x.shape, temperature );
#
# Linear velocity gradient along x: ±v_grad across the slab.
# This makes the PV diagram show a characteristic "spin-out"
# pattern.  v_grad is in cm/s per AU.
v_grad = 5.0e4;   # 0.5 km/s per AU -> ±4 km/s across 16 AU
def vx_callable( x, y, z ):
    return v_grad * ( x / AU );
#

##############################################
# 2.2 Configure the LineRT object
#
#  imaging= enables the two-step imaging pass on the final
#  cycle.  Keys:
#    dir_cam  : (theta, phi) spherical angles of the camera
#               direction [rad].  theta=0 -> along +z,
#               theta=pi/2, phi=0 -> along +x.
#    n_chan   : number of velocity channels.
#    v_chan   : (v_min, v_max) channel velocity range [cm/s].
#               vel > 0 = redshift (same convention as the
#               MC photons).
#    img_resol: (nx, ny) image resolution (defaults to the
#               first two mesh dimensions).
#
#  theta=0 looks down the z-axis; the image plane spans x-y,
#  so a PV diagram I(x, v) is obtained by summing over y.

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

    #  proper_scale=None (default) lets the pipeline auto-compute
    #  a scale that keeps s_cam within FP32 range at high optical
    #  depth.  The readback divides it out, so the returned cube
    #  is in CGS regardless.

    imaging      = {
        'dir_cam'  : ( 0.0, 0.0 ),       # along +z
        'n_chan'   : 64,
        'v_chan'   : ( -1.0e5, 1.0e5 ),  # ±10 km/s
    },
);
rt.set_boundary( 'fre fre per per per per' );

print( '==============================' );

############################################################
#  3. Source (photon-number flux, default units)

F0_cgs = 1e6;   # photon number flux [photons cm^-2 s^-1]

rt.add_source\
( type     = 'slab', x = -5, direction = '+x',
  n_photon = 20000,
  flux     = F0_cgs,
  sigma    = ti.doppler_b( temperature ) / sqrt( 2 ) );

print( 'CO, n_species = %.2e cm^-3, T = %.2e K' %
       ( n_species, temperature ) );
print( 'v_grad = %.1e cm/s per AU' % v_grad );
rt.show_sources(  );

print( '========================================' );

############################################################
#  4. Run the iterations!

n_cycle   = 3;
print( 'Running %d MC cycles + imaging ...' % n_cycle );
rt.run( n_cycle );
print( '========================================' );

############################################################
#  5. Extract and inspect the image cube

img = rt._results.get( 'image' );
if img is None:
    print( 'No image produced (imaging disabled?)' );
    raise SystemExit( 1 );

cube  = img[ 'cube' ];          # (n_pix, n_chan)  CGS
i2d   = img[ 'i2d'  ];          # (n_pix, 2) int32
nch   = img[ 'n_chan' ];

# Build the full 2-D spatial grid from the pixel index list.
img_nx = int( i2d[ :, 0 ].max(  ) ) + 1;
img_ny = int( i2d[ :, 1 ].max(  ) ) + 1;
img2d  = zeros( ( img_nx, img_ny, nch ) );
for p in range( i2d.shape[ 0 ] ):
    img2d[ i2d[ p, 0 ], i2d[ p, 1 ], : ] = cube[ p, : ];

# Velocity axis (cell edges convention: v_k = v_min + k*dv)
v_lo, v_hi = -1.0e5, 1.0e5;
dv = ( v_hi - v_lo ) / ( nch - 1 );
v_axis = v_lo + arange( nch ) * dv;    # cm/s
v_kms  = v_axis * 1e-5;                # km/s

# Spatial axis (image plane = x-y, pixel centres)
x_lo, x_hi = -8.0, 8.0;
dx = ( x_hi - x_lo ) / img_nx;
x_axis = x_lo + ( arange( img_nx ) + 0.5 ) * dx;   # AU

# Spectrum: sum over all spatial pixels
spectrum = img2d.sum( axis = ( 0, 1 ) );

# PV diagram: sum over y, shape (img_nx, nch)
pv = img2d.sum( axis = 1 );   # (img_nx, nch)

# Channel spacing for annotation
dv_kms = dv * 1e-5;   # km/s per channel

peak_chan = int( spectrum.argmax(  ) );
print( 'Image: %d x %d pixels, %d channels' %
       ( img_nx, img_ny, nch ) );
print( 'Spectrum peak at channel %d (v = %.2f km/s)' %
       ( peak_chan, v_kms[ peak_chan ] ) );
print( 'Channel spacing Dv = %.3f km/s' % dv_kms );
print( '========================================' );

############################################################
#  6. Plot: spectrum + PV diagram + channel maps
#
#  Three-panel figure:
#    (a) integrated spectrum
#    (b) position-velocity diagram (summed over y)
#    (c) grid of single-channel spatial maps at selected
#        velocities, each annotated with its central velocity
#        and the channel spacing Dv.

# Select ~6 channels around the peak for the channel maps.
n_map = 6;
half = n_map // 2;
chan_idx = arange( peak_chan - half, peak_chan + n_map - half );
chan_idx = chan_idx.clip( 0, nch - 1 );

# Print the data slices that will be plotted (for verification
# without viewing the figure).
print( 'Channel-map data slices (sum over y, x=peak pixel):' );
xi = img_nx // 2;
for k in chan_idx:
    sl = img2d[ xi, :, k ];
    print( '  chan %2d  v=%6.2f km/s  max=%.3e  sum=%.3e' %
           ( k, v_kms[ k ], sl.max(  ), sl.sum(  ) ) );
print( '========================================' );

fig = plt.figure( figsize = ( 10, 12 ) );
gs  = fig.add_gridspec( 3, n_map,
                         height_ratios = [ 1, 2, 2 ],
                         hspace = 0.45, wspace = 0.35 );

# -- (a) Integrated spectrum --
ax1 = fig.add_subplot( gs[ 0, : ] );
ax1.plot( v_kms, spectrum, 'b-', lw = 1.5 );
ax1.set_xlabel( r'$v_{\rm chan}$  [km/s]' );
ax1.set_ylabel( 'intensity [CGS]' );
ax1.set_title( 'Integrated spectrum (sum over image)' );
ax1.axvline( 0, color = 'k', ls = '--', lw = 0.5, alpha = 0.5 );
ax1.text( 0.02, 0.95,
          'CO $J=1\\to 0$,  $T=2.7$ K,  '
          r'$\Delta v = %.3f$ km/s' % dv_kms,
          transform = ax1.transAxes, va = 'top', fontsize = 10 );

# -- (b) Position-velocity diagram --
ax2 = fig.add_subplot( gs[ 1, : ] );
im = ax2.imshow( pv.T, origin = 'lower', aspect = 'auto',
                 extent = ( x_axis[ 0 ], x_axis[ -1 ],
                            v_kms[ 0 ],  v_kms[ -1 ] ),
                 cmap = 'turbo', interpolation = 'bilinear' );
ax2.set_xlabel( r'$x$  [AU]' );
ax2.set_ylabel( r'$v_{\rm chan}$  [km/s]' );
ax2.set_title( 'Position-velocity diagram (summed over $y$)' );
ax2.axhline( 0, color = 'w', ls = '--', lw = 0.5, alpha = 0.4 );
ax2.axvline( 0, color = 'w', ls = '--', lw = 0.5, alpha = 0.4 );
# Mark the channels chosen for the maps below.
for k in chan_idx:
    ax2.axhline( v_kms[ k ], color = 'c', ls = ':', lw = 0.8,
                 alpha = 0.6 );
fig.colorbar( im, ax = ax2, label = 'intensity [CGS]',
              shrink = 0.8 );

# -- (c) Channel maps --
#  Shared color scale across all panels for comparison.
vmax = img2d[ :, :, chan_idx ].max(  );
y_lo, y_hi = -2.0, 2.0;
for i, k in enumerate( chan_idx ):
    ax = fig.add_subplot( gs[ 2, i ] );
    im = ax.imshow( img2d[ :, :, k ].T, origin = 'lower',
                    aspect = 'auto',
                    extent = ( x_axis[ 0 ], x_axis[ -1 ],
                               y_lo, y_hi ),
                    cmap = 'turbo', interpolation = 'bilinear',
                    vmin = 0, vmax = vmax );
    ax.set_title( r'$v = %.2f$ km/s' % v_kms[ k ],
                  fontsize = 12 );
    ax.set_xlabel( r'$x$ [AU]', fontsize = 11 );
    if i == 0:
        ax.set_ylabel( r'$y$ [AU]', fontsize = 11 );
    ax.tick_params( labelsize = 10 );
    # Annotate the channel spacing in the first panel.
    if i == 0:
        ax.text( 0.02, 0.02,
                 r'$\Delta v = %.3f$ km/s' % dv_kms,
                 transform = ax.transAxes, va = 'bottom',
                 fontsize = 9, color = 'w' );

fig.tight_layout(  );
outpath = os.path.join( os.path.dirname( __file__ ),
                        'imaging_hl_results.png' );
fig.savefig( outpath, dpi = 150 );
print( '\nImage saved to %s' % outpath );

############################################################
