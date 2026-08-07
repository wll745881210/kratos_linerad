#!/usr/bin/env python3
"""Neufeld (1990) imaging validation test for line_rt_pipeline.

Group 2 configuration: external slab source at -x boundary, camera along +x.
No internal emission (no species).  Pure scattering slab.

Checks:
  1.  Escaped spectrum:  med|x|  matches Neufeld (1990) eq (2.24).
  2.  Imaging spectrum:  double-peaked structure (dip at x = 0).
  3.  Imaging vs escaped:  similar peak positions.
"""

import sys, os, argparse, numpy as np

# ----------------------------------------------------------------------- #
#  Physical constants (CGS)                                               #
# ----------------------------------------------------------------------- #
AU_CGS        = 1.49598e13
K_B           = 1.380649e-16
H_PLANCK      = 6.62607015e-27
C_LIGHT       = 2.99792458e10
M_PROTON      = 1.67262192e-24

# ----------------------------------------------------------------------- #
#  Line parameters (CO J=1->0, representative)                             #
# ----------------------------------------------------------------------- #
A_UL      = 7.2e-8
FREQ_GHZ  = 115.27
G_U       = 3.0
G_L       = 1.0
MOL_MASS  = 28.0

# ----------------------------------------------------------------------- #
#  Neufeld test parameters                                                #
# ----------------------------------------------------------------------- #
A_VOIGT  = 0.149
TEMP_K   = 1684.0          # gives b = 1.0e5 cm/s
B_SCA    = np.sqrt( 2.0 * K_B * TEMP_K / ( MOL_MASS * M_PROTON ) )
L_SLAB   = 2.0 * AU_CGS    # full slab (x from -1 to +1 code units)

KRATOS_ROOT = os.path.expanduser( '~/apps/kratos_line_rt' )
PIPELINE    = os.path.dirname( os.path.dirname( os.path.abspath( __file__ ) ) )

sys.path.insert( 0, PIPELINE )
from line_rt import LineRt

# ----------------------------------------------------------------------- #
#  Helper formulas                                                        #
# ----------------------------------------------------------------------- #
def compute_sigma0( ):
    """Line-centre cross section [cm^2] (Hjerting convention H(0)=1)."""
    nu = FREQ_GHZ * 1e9
    return ( G_U / G_L ) * A_UL * C_LIGHT**3 / \
           ( 8.0 * np.pi**1.5 * nu**3 * B_SCA )

def compute_mfp_cgs( tau0 ):
    """Inverse mean free path [cm^-1] for mean optical depth tau0.

    tau0 = mfp * sqrt(pi) * L_SLAB / 2   (half-slab mean-depth convention)
    => mfp = 2 * tau0 / (sqrt(pi) * L_SLAB)
    """
    return 2.0 * tau0 / ( np.sqrt( np.pi ) * L_SLAB )

# ----------------------------------------------------------------------- #
#  Neufeld (1990) predictions                                            #
# ----------------------------------------------------------------------- #
def neufeld_peak( a_tau0 ):
    """Peak position of the Neufeld J(x) distribution."""
    return 0.881 * ( a_tau0 )**( 1.0 / 3.0 )

def neufeld_J( x, a_tau0 ):
    """Neufeld (1990) eq (2.24) — angle-averaged emergent intensity."""
    return np.sqrt( 6.0 / np.pi ) * x**2 / \
           np.cosh( np.sqrt( np.pi**3 / 54.0 ) * np.abs( x )**3 / a_tau0 )

def neufeld_med_x( a_tau0 ):
    """Median |x| of the Neufeld J(x) distribution (numerical)."""
    from scipy.integrate import quad
    dx = 0.01
    xs = np.arange( dx, 200, dx )
    Js = neufeld_J( xs, a_tau0 )
    total = np.sum( Js ) * dx
    cdf = np.cumsum( Js ) * dx / total
    idx = np.searchsorted( cdf, 0.5 )
    return xs[ idx ] if idx < len( xs ) else xs[ -1 ]

# Golden table: tau0 -> (x_peak, med_x)
GOLDEN = {
    200:   dict( x_peak = 2.73,  med_x = 1.80  ),
    500:   dict( x_peak = 3.71,  med_x = 2.30  ),
    2000:  dict( x_peak = 5.89,  med_x = 4.40  ),
    8000:  dict( x_peak = 9.33,  med_x = 6.90  ),
    32000: dict( x_peak = 14.82, med_x = 11.50 ),
}

# ----------------------------------------------------------------------- #
#  Run one configuration                                                   #
# ----------------------------------------------------------------------- #
def run_one( tau0, n_photon = 51200, keep = False ):
    """Run a Neufeld slab with external source, return results dict."""
    mfp_cgs = compute_mfp_cgs( tau0 )
    n_sc_est = max( 100, int( 2.857 * tau0 ) )
    n_step = max( 5_000_000, int( n_photon * n_sc_est * 3 ) )
    t_lim = max( 0.12, float( n_photon ) * n_sc_est * 3e-9 )

    rt = LineRt(
        n_cell = ( 64, 2, 2 ),
        x_min = ( -1.0, -0.5, -0.5 ),
        x_max = (  1.0,  0.5,  0.5 ),
        unit_l0 = AU_CGS,
        unit_t0 = 1.0,
        b_sca = B_SCA,
        mfp_i_sca_0 = mfp_cgs,
        mfp_i_abs_0 = 0.0,
        vel = ( 0.0, 0.0, 0.0 ),
        a_voigt = A_VOIGT,
        ph_mode = 2,
        n_step = n_step,
        n_scat = max( 10000, n_sc_est * 3 ),
        n_cycles = 1,
        t_lim = t_lim,
        n_emission_max = 0,
        keep_intermediate = keep,
        kratos_root = KRATOS_ROOT,
        imaging = dict(
            dir_cam  = ( -1.0, 0.0, 0.0 ),
            n_chan   = 32,
            v_chan   = ( -1e6, 1e6 ),
        ),
    )
    rt.set_boundary( 'fre fre per per per per' )
    rt.add_source(
        type = 'slab',
        n_photon = n_photon,
        flux = 1e6,
        x = -1.0,
        direction = '+x',
    )
    out = rt.run( )
    return out

# ----------------------------------------------------------------------- #
#  Spectrum extraction                                                    #
# ----------------------------------------------------------------------- #
def extract_imaging_spectrum( out ):
    """Return (v_chan_centers, I_chan) from the imaging cube (pixel-averaged)."""
    img = out[ 'image' ]
    cube = img.get( 'cube_cgs', img.get( 'cube', None ) )  # (n_pix, n_chan)
    if cube is None:
        return None, None
    v_lo, v_hi = img[ 'v_chan' ]
    n_chan = img.get( 'n_chan', cube.shape[ -1 ] )
    dv = ( v_hi - v_lo ) / n_chan
    v = v_lo + dv * ( np.arange( n_chan ) + 0.5 )
    I = np.mean( cube, axis = 0 ) if cube.ndim > 1 else cube
    return v, I

def extract_escaped_spectrum( out ):
    """Return (vel, w) from escaped-photon spectrum."""
    spec = out.get( 'spectrum', None )
    if spec is None or len( spec.get( 'vel', [ ] ) ) == 0:
        return None, None
    vel = np.asarray( spec[ 'vel' ] )
    w   = np.asarray( spec[ 'n' ] )     # proper-weighted
    return vel, w

# ----------------------------------------------------------------------- #
#  Checks                                                                  #
# ----------------------------------------------------------------------- #
def check_escaped_spectrum( tau0, out, verbose = True ):
    """Check med|x| of escaped spectrum against Neufeld."""
    vel, w = extract_escaped_spectrum( out )
    if vel is None or w is None:
        print( "  [SKIP] No escaped-photon spectrum" )
        return False

    x = np.abs( np.asarray( vel ) ) / B_SCA
    w  = np.asarray( w )
    # proper-weighted median |x|
    idx = np.argsort( x )
    cw  = np.cumsum( w[ idx ] ) / np.sum( w )
    med_x = x[ idx[ np.searchsorted( cw, 0.5 ) ] ]

    a_tau0 = A_VOIGT * tau0
    target = neufeld_med_x( a_tau0 )
    golden = GOLDEN.get( tau0, {} ).get( 'med_x', target )

    ok = med_x >= 0.75 * target
    tag = "PASS" if ok else "FAIL"
    print( f"  [{tag}] escaped med|x| = {med_x:.3f}  "
           f"(Neufeld {target:.3f}, golden {golden:.3f})" )
    return ok

def check_imaging_double_peak( tau0, out, verbose = True ):
    """Check that imaging spectrum is double-peaked (dip at x=0)."""
    v, I = extract_imaging_spectrum( out )
    if v is None or I is None:
        print( "  [SKIP] No imaging cube" )
        return False

    x = v / B_SCA
    a_tau0 = A_VOIGT * tau0
    x_peak = neufeld_peak( a_tau0 )

    # Check for a dip at x=0: I(0) < max(I)
    I_center = np.interp( 0.0, x, np.abs( I ) )
    I_max    = np.max( np.abs( I ) )
    x_at_max = x[ np.argmax( np.abs( I ) ) ]

    has_dip = I_center < 0.5 * I_max
    tag = "PASS" if has_dip else "FAIL"
    print( f"  [{tag}] imaging: I(0)/I_max = {I_center/I_max:.3f}  "
           f"(dip at center), peak at x={x_at_max:.2f} "
           f"(Neufeld x_peak={x_peak:.2f})" )
    return has_dip

def check_imaging_vs_escaped( tau0, out, verbose = True ):
    """Compare imaging spectrum peak to escaped spectrum peak."""
    v_img, I_img = extract_imaging_spectrum( out )
    vel_esc, w_esc = extract_escaped_spectrum( out )
    if I_img is None or w_esc is None:
        print( "  [SKIP] Missing spectrum" )
        return False

    x_img = v_img / B_SCA
    x_esc = np.abs( np.asarray( vel_esc ) ) / B_SCA
    w_esc_arr = np.asarray( w_esc )

    # imaging peak (absolute value)
    x_img_peak = x_img[ np.argmax( np.abs( I_img ) ) ]
    # escaped peak (proper-weighted histogram peak)
    n_bin = 64
    x_bins = np.linspace( 0, 15, n_bin + 1 )
    hist, _ = np.histogram( x_esc, bins = x_bins, weights = w_esc_arr )
    x_esc_peak = 0.5 * ( x_bins[ np.argmax( hist ) ] +
                         x_bins[ np.argmax( hist ) + 1 ] )

    a_tau0 = A_VOIGT * tau0
    x_peak_n = neufeld_peak( a_tau0 )

    ratio = x_img_peak / x_esc_peak if x_esc_peak > 0 else 0
    ok = 0.5 < ratio < 2.0  # within factor 2
    tag = "PASS" if ok else "FAIL"
    print( f"  [{tag}] imaging peak x={x_img_peak:.2f}  vs  "
           f"escaped peak x={x_esc_peak:.2f}  (ratio {ratio:.2f}, "
           f"Neufeld {x_peak_n:.2f})" )
    return ok

# ----------------------------------------------------------------------- #
#  Main                                                                    #
# ----------------------------------------------------------------------- #
def main( ):
    p = argparse.ArgumentParser( description = "Neufeld imaging validation" )
    p.add_argument( '--tau0-list', type = int, nargs = '+',
                    default = [ 2000 ],
                    help = 'tau0 values to test (default: 2000)' )
    p.add_argument( '--n-photon', type = int, default = 51200 )
    p.add_argument( '--keep', action = 'store_true' )
    p.add_argument( '--verbose', action = 'store_true' )
    args = p.parse_args( )

    all_pass = True
    for tau0 in args.tau0_list:
        print( f"\n=== tau0 = {tau0}  (a*tau0 = {A_VOIGT*tau0:.1f}) ===" )
        out = run_one( tau0, n_photon = args.n_photon, keep = args.keep )
        ok1 = check_escaped_spectrum( tau0, out, args.verbose )
        ok2 = check_imaging_double_peak( tau0, out, args.verbose )
        ok3 = check_imaging_vs_escaped( tau0, out, args.verbose )
        if not ( ok1 and ok2 and ok3 ):
            all_pass = False

    print( )
    if all_pass:
        print( "ALL TESTS PASSED" )
        sys.exit( 0 )
    else:
        print( "SOME TESTS FAILED" )
        sys.exit( 1 )

if __name__ == '__main__':
    main( )
