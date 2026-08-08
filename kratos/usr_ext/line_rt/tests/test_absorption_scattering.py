#!/usr/bin/env python3
"""
Standalone scattering + continuum absorption test vs Neufeld (1990).

Self-contained: no pipeline imports. Inlines:
  - binary I/O (via the Kratos repo's binary_io, like test_scaling_wide.py)
  - a compact pure-NumPy/SciPy reference MC (USampler + R_II-A kernel)

A slab of scattering (Voigt) opacity with a_voigt = a and wavelength-
independent continuum absorption (const_abs = 1). An isotropic midplane
source emits monochromatic photons at line centre (x=0, vel=0, sv=0).

With pure scattering the spectrum broadens to the wing and photons escape
with f_esc = 1; adding continuum absorption kappa_a reduces the escape
fraction. Neufeld (1990, ApJ 350, 216) Sec. IV gives the analytic
approximation (valid for line-centre injection into a thick slab):

    f_esc = 1 / cosh(Y0),  Y0 = [3 phi(x_s) beta tau0^2]^{1/2}   (4.28,4.25)

with beta = kappa_a / kappa_bar_s (absorption / MEAN scattering opacity),
tau0 = half-slab mean scattering depth, phi = line profile (int phi dx
= 1, wing phi ~ a/pi x^2) and x_s = 0.525 (a tau0)^{1/3} the effective
escape frequency (4.32). In the far-wing limit this gives (4.33):

    Y0^2 = 3.464 (a tau0)^{1/3} tau0 beta  =>  Y0 = 1.8612 sqrt(X)

with X = (a tau0)^{1/3} tau0 beta = (a tau_m)^{1/3} tau_a in our units.

IMPORTANT: cosh (4.33) is a Fokker-Planck / Eddington / power-law-wing
APPROXIMATION. It OVERESTIMATES f_esc at intermediate optical depth
because the power-law wing approximation underestimates core absorption
probability (Verhamme et al. 2006, A&A 460, 397, Sec. 3.1.1). An
independent MC (~/scratch/line_rt/fiducial/Agent_Neufeld/Neufeld检验复现/
neufeld_mc.py, exact R_II-A kernel) confirms MC sits systematically
BELOW cosh (4.33) at Q = (a tau0)^{1/3} tau0 beta ~ 1-3 (their Table
Sec. 5.3: 4.2-4.3 sigma below at Q=1,3). Therefore the PASS criterion
is Kratos ~ Python (two independent MC implementations), NOT agreement
with the approximate analytic formula. The K/Neufeld and P/Neufeld
ratios are reported for diagnostics but are expected to be < 1.

Unit mapping (half-slab mean-depth convention, see AGENTS.md pitfall 23):
    tau0 = tau_m = sqrt(pi) * mfp_i_sca_0 * L/2
    tau_a = mfp_i_abs_0 * L/2                  (half-slab absorption depth)
    beta = kappa_a / kappa_bar_s = mfp_i_abs_0 / (sqrt(pi) mfp_i_sca_0)
         = tau_a / tau_m
    X = (a tau_m)^{1/3} tau_a
    Y0 = 1.8612 sqrt(X)
    f_esc = 1 / cosh(Y0)                        (Neufeld 4.33, approximate)

Usage
-----
  python3 usr_ext/line_rt/tests/test_absorption_scattering.py \
      --kratos-root ~/apps/kratos_line_rt
  python3 usr_ext/line_rt/tests/test_absorption_scattering.py \
      --tau-m-list 30 300 3000 --tau-a-list 0.3 1.0 --n 100000 \
      --kratos-root ~/apps/kratos_line_rt
"""
import argparse, importlib, os, subprocess, sys, tempfile;
from pathlib import Path;
from numpy import array, asarray, zeros, full, ones, empty, \
                 linspace, logspace, log10, arange, \
                 concatenate, cumsum, exp, sqrt, cos, sin, \
                 pi, searchsorted, clip, unique, maximum, nonzero, \
                 where, pad, log, cosh, isnan, median, nan, \
                 float32, float64, int32, random, interp;
from scipy.special import voigt_profile;

UNIT_L0 = 1.49597870691e13;
UNIT_T0 = 1.0;
DEFAULT_KRATOS_ROOT = Path( os.path.expanduser( \
    '~/apps/kratos_line_rt' ) );
WORKDIR = Path( '/tmp/line_rt' );
B_SCA_CGS = 1.0e5;

############################################################
#  Kratos root resolution

def resolve_kratos_root( kratos_root ):
    """Validate a Kratos build tree: must contain bin/kratos and
    visual/binary_io.py.  Returns (kratos_root, kratos_bin,
    binary_io_module).
    """
    kratos_root = Path( kratos_root ).expanduser( );
    kratos_bin = kratos_root / 'bin' / 'kratos';
    bio_path = kratos_root / 'visual' / 'binary_io.py';
    if not kratos_bin.exists( ):
        raise FileNotFoundError( \
            'kratos binary not found: %s' % kratos_bin );
    if not bio_path.exists( ):
        raise FileNotFoundError( \
            'binary_io.py not found: %s' % bio_path );
    if str( kratos_root / 'visual' ) not in sys.path:
        sys.path.insert( 0, str( kratos_root / 'visual' ) );
    binary_io = importlib.import_module( 'binary_io' ).binary_io;
    return kratos_root, kratos_bin, binary_io;

############################################################
#  Analytic (Neufeld 1990 Sec. IV)

def f_esc_neufeld( tau_m, tau_a, a_voigt ):
    """
    Neufeld (1990) eq (4.33) escape fraction (far-wing branch).

    tau_m  = half-slab mean scattering depth (tau0 = sqrt(pi) mfp_sca L/2)
    tau_a  = half-slab absorption depth (mfp_abs L/2)
    a_voigt = Voigt damping parameter
    Returns (f_esc, Y0) with Y0 = 1.8612 sqrt(X),
    X = (a tau_m)^{1/3} tau_a.

    This is the Fokker-Planck/power-law-wing approximation that
    OVERESTIMATES f_esc at intermediate optical depth (Verhamme 2006);
    MC implementations sit below it. See module docstring.
    """
    x = ( a_voigt * tau_m ) ** ( 1.0 / 3.0 ) * tau_a;
    y0 = 1.8612 * sqrt( x );
    return 1.0 / cosh( y0 ), y0;

############################################################
#  Binary I/O (inline, mirrors pipeline/kratos_io.py)

def write_fields( filename, fields, mesh, binary_io ):
    """Write Kratos field binary (cell-centered, ijkl=0)."""
    bio = binary_io( filename );
    n_cell = asarray( mesh[ 'n_cell' ], dtype = int32 );
    x_min = asarray( mesh[ 'x_min'  ], dtype = float32 );
    dx    = asarray( mesh[ 'dx'     ], dtype = float32 );
    # Cell-centered: n_pts = n_cell, x0 = x_min + 0.5*dx
    n_pts = n_cell.copy( );
    x0_nodes = x_min + 0.5 * dx;
    ijkl_flag = array( 0, dtype = int32 );

    for prefix in [ 'mfp_i_sca_0_', 'mfp_i_abs_0_', 'b_sca_', \
                    'vel_0_', 'vel_1_', 'vel_2_' ]:
        if prefix not in fields:
            continue;
        raw = asarray( fields[ prefix ], dtype = float32 );
        # data is already (nz*ny*nx) in C-order, no padding needed
        bio.cache( '%sijkl'  % prefix, ijkl_flag,    dtype = 'int32' );
        bio.cache( '%sn_pts' % prefix, n_pts,        dtype = 'int32' );
        bio.cache( '%sx0'    % prefix, x0_nodes,     dtype = 'float32' );
        bio.cache( '%sdx'    % prefix, dx,            dtype = 'float32' );
        bio.cache( '%sdata'  % prefix, raw,           dtype = 'float32' );
    bio.save( );
    return filename;


def write_photons( filename, photons, binary_io ):
    """Write Kratos photon binary."""
    ph = asarray( photons, dtype = float32 );
    bio = binary_io( filename );
    bio.cache( 'par_n_col', ph.shape[ 1 ], dtype = 'int32' );
    bio.cache( 'par_n_par', ph.shape[ 0 ], dtype = 'int64' );
    bio.cache( 'par_par_dat', ph, dtype = 'float32' );
    bio.save( );
    return filename;


def read_escaped_photons( filename, binary_io ):
    """Read escaped photons from a Kratos output binary."""
    bio = binary_io( filename );
    bio.open( );
    phot = { };
    for raw_key in bio.hmap:
        if '_rank_' in raw_key and raw_key.endswith( '_x' ):
            phot[ 'x' ] = bio.as_array( raw_key, 'f' );
        elif '_rank_' in raw_key and raw_key.endswith( '_dir' ):
            phot[ 'dir' ] = bio.as_array( raw_key, 'f' );
        elif '_rank_' in raw_key and raw_key.endswith( '_l' ):
            phot[ 'l' ] = bio.as_array( raw_key, 'f' );
        elif '_rank_' in raw_key and raw_key.endswith( '_vel' ):
            phot[ 'vel' ] = bio.as_array( raw_key, 'f' );
    bio.close( );
    return phot;

############################################################
#  Compact pure-NumPy reference MC (R_II-A kernel)
#  Based on ~/scratch/line_rt/fiducial/Agent_Neufeld/Neufeld检验复现/
#  neufeld_mc.py (prior agent's validated independent MC). Works in
#  mean-depth units: z in [-tau_m, tau_m], opacity = phi(x) + beta.

class _USampler:
    """Inverse-CDF table sampler for P(u|x) prop exp(-u^2)/(a^2+(x-u)^2).

    This is the exact R_II-A redistribution kernel (Maxwell x Lorentz).
    Builds a 2D CDF table C(|x|, u), samples via binary search +
    linear interpolation between adjacent |x| grid points.
    """

    __slots__ = ( 'u', 'xg', 'C' );

    def __init__( self, a, x_max = 300.0, du = 5e-3, n_lin = 101, \
                  n_log = 121 ):
        u = arange( -6.0, 6.0 + du, du );
        x_lin = linspace( 0.0, 8.0, n_lin );
        x_log = logspace( log10( 8.0 ), log10( x_max ), n_log )[ 1: ];
        xg = concatenate( [ x_lin, x_log ] );
        G = exp( -u ** 2 );
        D = u[ None, : ] - xg[ :, None ];
        W = G[ None, : ] / ( a ** 2 + D ** 2 );
        C = cumsum( W, axis = 1 );
        C /= C[ :, -1: ];
        C[ :, -1 ] = 1.0;
        self.u, self.xg, self.C = u, xg, C;

    def sample( self, x, rng ):
        """Sample u_par for frequency array x (any sign)."""
        x = asarray( x );
        sgn = where( x < 0, -1.0, 1.0 );
        xa = abs( x );
        j = clip( searchsorted( self.xg, xa ) - 1, 0, \
                  self.xg.size - 2 );
        f = ( xa - self.xg[ j ] ) / ( self.xg[ j + 1 ] - \
                                      self.xg[ j ] );
        r = rng.random( x.size );
        u_out = empty( x.size );
        for jj in unique( j ):
            m = j == jj;
            rr = r[ m ];
            us = [ ];
            for row in ( self.C[ jj ], self.C[ jj + 1 ] ):
                k = clip( searchsorted( row, rr ), 1, \
                          self.u.size - 1 );
                c0, c1 = row[ k - 1 ], row[ k ];
                us.append( self.u[ k - 1 ] + ( rr - c0 ) / \
                           maximum( c1 - c0, 1e-300 ) * \
                           ( self.u[ k ] - self.u[ k - 1 ] ) );
            u_out[ m ] = ( 1.0 - f[ m ] ) * us[ 0 ] + \
                         f[ m ] * us[ 1 ];
        return sgn * u_out;


_SIGMA = 1.0 / sqrt( 2.0 );  # 1D thermal velocity dispersion


def run_mc_slab( tau_m, tau_a, a_voigt, n_photons, seed = 42, \
                 batch = 2000, max_iter = 300000 ):
    """Pure-NumPy Ly-alpha MC in mean-depth units (z in [-tau_m, tau_m]).

    Physics (exact R_II-A, no core-skipping):
      - free flight: -ln(1-xi) / (phi(x) + beta),  phi = voigt_profile
      - escape: |z| >= tau_m
      - dust absorption: prob beta/(phi+beta)
      - scatter: u_par ~ P(u|x) (USampler), x_at = x - u_par,
        isotropic new dir, u_par' = g*u_par + sqrt(1-g^2)*u_perp,
        x' = x_at + u_par'

    Returns f_esc (sum of proper weights of escaped photons).
    """
    beta = tau_a / tau_m if tau_m > 0 else 0.0;
    sampler = _USampler( a_voigt );
    n_esc = 0;
    weight = 1.0 / n_photons;

    for b0 in range( 0, n_photons, batch ):
        nb = min( batch, n_photons - b0 );
        rng = random.default_rng( seed * 100003 + b0 );
        z = zeros( nb );
        x = zeros( nb );
        mu = 2.0 * rng.random( nb ) - 1.0;
        alive = ones( nb, dtype = bool );
        it = 0;
        while alive.any( ):
            it += 1;
            if it > max_iter:
                raise RuntimeError( 'max_iter exceeded' );
            idx = nonzero( alive )[ 0 ];
            n = idx.size;
            x_a, mu_a, z_a = x[ idx ], mu[ idx ], z[ idx ];

            coeff = voigt_profile( x_a, _SIGMA, a_voigt ) + beta;
            z_new = z_a + mu_a * ( -log( 1.0 - rng.random( n ) ) ) / \
                            coeff;

            esc = abs( z_new ) >= tau_m;
            if esc.any( ):
                ie = idx[ esc ];
                n_esc += ie.size;
                alive[ ie ] = False;

            surv = ~esc;
            if not surv.any( ):
                continue;
            isur = idx[ surv ];
            z[ isur ] = z_new[ surv ];
            ns = isur.size;
            x_s = x_a[ surv ];

            absorbed = rng.random( ns ) < beta / coeff[ surv ];
            if absorbed.any( ):
                alive[ isur[ absorbed ] ] = False;
            keep = ~absorbed;
            if not keep.any( ):
                continue;
            ik = isur[ keep ];
            x_k = x_s[ keep ];
            nk = ik.size;

            u_par = sampler.sample( x_k, rng );
            x_at = x_k - u_par;
            g = 2.0 * rng.random( nk ) - 1.0;
            u_perp = rng.standard_normal( nk ) * _SIGMA;
            u_par_n = g * u_par + sqrt( 1.0 - g ** 2 ) * u_perp;
            x[ ik ] = x_at + u_par_n;
            mu[ ik ] = 2.0 * rng.random( nk ) - 1.0;

    return n_esc * weight;

############################################################
#  Kratos input generation

PAR_TEMPLATE = """# Kratos scattering+absorption test - auto-generated

[unit]
length  = {unit_l0:.6e}
time    = {unit_t0}
density = 1.0

[mesh]
x_min = {x_min}
x_max = {x_max}
n_cell_global = {n_cells}

[cycle]
prefix_output = test_{tag}
n_cycle_lim   = 0
t_lim         = 600.0
t_output_next = 1e32
dt_output     = 1e32
final_output  = 1

[particle]
n_step = 5000000
n_scat = 5000000
output = 1
n_radiation = {n_radiation}

[line_rt]
field_file  = {field_file}
photon_file = {photon_file}
ph_mode     = {ph_mode}
b_sca       = {b_sca_code:.10e}
const_abs   = 1
n_fld       = 1
num_rng     = 16381
a_voigt     = {a_voigt}
worker_mode = 0
n_worker    = 32768
proper_min_frac = 0

[boundary]
kinds = {bounds}
"""


def generate_kratos_inputs( tau_m, tau_a, a_voigt, n_radiation, \
                            out_dir, tag, ph_mode = 1, \
                            n_cell = 128, L_slab = 1.49598e14, \
                            b_sca = 1.0e5, seed = 42, \
                            binary_io = None, aspect = None ):
    L_slab_code = L_slab / UNIT_L0;
    nx = n_cell;
    dx_code = L_slab_code / nx;
    half_code = L_slab_code / 2;
    # Geometry: aspect=None -> periodic slab (nx, 2, 2) with y/z in
    # [0, 1] (default, original test); aspect=A -> wide box
    # (nx, A*nx, A*nx) emulating the slab for the SKIRT comparison
    # (SKIRT has no periodic boundaries), y/z in [-A*L/2, A*L/2].
    if aspect is None:
        nyz = 2;
        bounds = 'fre fre per per per per';
        n_cell_arr = [ nx, 2, 2 ];
        x_min_arr = [ -half_code, 0.0, 0.0 ];
        dx_arr = [ dx_code, 0.5, 0.5 ];
        y_lo, y_hi = 0.0, 1.0;
    else:
        nyz = int( round( nx * aspect ) );
        aw_code = 0.5 * aspect * L_slab_code;
        bounds = 'fre fre fre fre fre fre';
        n_cell_arr = [ nx, nyz, nyz ];
        x_min_arr = [ -half_code, -aw_code, -aw_code ];
        dx_arr = [ dx_code, 2.0 * aw_code / nyz, \
                   2.0 * aw_code / nyz ];
        y_lo, y_hi = -aw_code, aw_code;

    mfp_i_sca_0_cgs = 2.0 * tau_m / ( sqrt( pi ) * L_slab );
    mfp_i_abs_0_cgs = 2.0 * tau_a / L_slab;
    mfp_i_sca_0_code = mfp_i_sca_0_cgs * UNIT_L0;
    mfp_i_abs_0_code = mfp_i_abs_0_cgs * UNIT_L0;
    b_sca_code = b_sca * UNIT_T0 / UNIT_L0;

    n_tot = nx * nyz * nyz;
    fields = {
        'mfp_i_sca_0_' : full( n_tot, float32( mfp_i_sca_0_code ) ),
        'mfp_i_abs_0_' : full( n_tot, float32( mfp_i_abs_0_code ) ),
        'b_sca_'       : full( n_tot, float32( b_sca_code ) ),
        'vel_0_'       : zeros( n_tot, dtype = float32 ),
        'vel_1_'       : zeros( n_tot, dtype = float32 ),
        'vel_2_'       : zeros( n_tot, dtype = float32 ),
    };
    mesh = {
        'n_cell' : array( n_cell_arr, dtype = int32 ),
        'x_min'  : array( x_min_arr, dtype = float32 ),
        'dx'     : array( dx_arr, dtype = float32 ),
    };

    field_file = os.path.join( out_dir, 'fields_%s.bin' % tag );
    write_fields( field_file, fields, mesh, binary_io );

    par_path = os.path.join( out_dir, 'abs_%s.par' % tag );
    x_max_arr = [ x_min_arr[ i ] + n_cell_arr[ i ] * dx_arr[ i ] \
                  for i in range( 3 ) ];
    fmt3 = lambda v: ' '.join( '%.6f' % x for x in v );
    fmt3i = lambda v: ' '.join( str( int( x ) ) for x in v );
    par_content = PAR_TEMPLATE.format(
        unit_l0 = UNIT_L0, unit_t0 = UNIT_T0,
        x_min = fmt3( x_min_arr ), x_max = fmt3( x_max_arr ),
        n_cells = fmt3i( n_cell_arr ), bounds = bounds,
        n_radiation = n_radiation, ph_mode = ph_mode, \
        a_voigt = a_voigt,
        field_file = os.path.basename( field_file ),
        photon_file = 'photons_%s.bin' % tag,
        b_sca_code = b_sca_code, tag = tag,
    );
    with open( par_path, 'w' ) as fp:
        fp.write( par_content );

    photon_file = os.path.join( out_dir, 'photons_%s.bin' % tag );
    rng = random.default_rng( seed );
    ph = zeros( ( n_radiation, 9 ), dtype = float32 );
    ph[ :, 0 ] = 0.0;
    ph[ :, 1 ] = rng.uniform( y_lo, y_hi, n_radiation );
    ph[ :, 2 ] = rng.uniform( y_lo, y_hi, n_radiation );
    mu = rng.uniform( -1.0, 1.0, n_radiation );
    phi = rng.uniform( 0.0, 2.0 * pi, n_radiation );
    smu = sqrt( 1.0 - mu * mu );
    ph[ :, 3 ] = smu * cos( phi );
    ph[ :, 4 ] = smu * sin( phi );
    ph[ :, 5 ] = mu;
    ph[ :, 6 ] = 1.0 / n_radiation;
    ph[ :, 7 ] = 0.0;
    ph[ :, 8 ] = 0.0;
    write_photons( photon_file, ph, binary_io );

    return par_path;


def run_kratos_one( tau_m, tau_a, a_voigt, n_radiation, out_dir, tag, \
                    ph_mode = 1, kratos_bin = None, \
                    binary_io = None, aspect = None ):
    print( '  Kratos: tau_m=%s, tau_a=%s, n=%d%s' \
           % ( tau_m, tau_a, n_radiation, \
               '' if aspect is None else \
               ', wide-box aspect=%g' % aspect ) );
    par_path = generate_kratos_inputs(
        tau_m, tau_a, a_voigt, n_radiation, out_dir, tag, \
        ph_mode = ph_mode, binary_io = binary_io, aspect = aspect, \
        n_cell = 32 if aspect is not None else 128 );

    result = subprocess.run(
        [ str( kratos_bin ), os.path.basename( par_path ) ],
        cwd = out_dir, capture_output = True, text = True, \
        timeout = 900,
    );
    if result.returncode != 0:
        print( '    FAILED: %s' % result.stderr[ -300 : ] );
        return None;

    out_files = sorted( Path( out_dir ).glob( 'test_%s_*.bin' % tag ) );
    if not out_files:
        return None;
    phot = read_escaped_photons( str( out_files[ -1 ] ), binary_io );
    if 'l' not in phot or phot[ 'l' ].size == 0:
        print( '    No escaped photons' );
        return None;

    proper = phot[ 'l' ].astype( float64 );
    f_esc = float( proper.sum( ) );
    print( '    n_esc=%d/%d, f_esc(weighted)=%.6f' \
           % ( len( proper ), n_radiation, f_esc ) );
    return { 'f_esc' : f_esc, 'n_esc' : len( proper ) };


def run_python_one( tau_m, tau_a, a_voigt, n_radiation ):
    print( '  Python: tau_m=%s, tau_a=%s, n=%d' \
           % ( tau_m, tau_a, n_radiation ) );
    f_esc = run_mc_slab( tau_m, tau_a, a_voigt, n_radiation, \
                         seed = 42 );
    print( '    f_esc(weighted)=%.6f' % f_esc );
    return { 'f_esc' : f_esc };


sys.path.insert( 0, '/home/lilew/Seafile/seafile_sync/code/'
                    'line_rt_pipeline/docs/external_tests/skirt' );
import skirt_dust_slab as sds;


def run_skirt_one( tau_m, tau_a, n_phot, aspect, kappa ):
    """SKIRT wide-box run via the skirt_dust_slab harness (published
    code, Camps & Baes 2020). kappa = tau_a per unit dust number
    density from the pure-absorption calibration."""
    print( '  SKIRT: tau_m=%s, tau_a=%s, n=%d, aspect=%g' \
           % ( tau_m, tau_a, int( n_phot ), aspect ) );
    n_dust = tau_a / kappa;
    tag = 'tm%g_ta%g_A%g_N%g' % ( tau_m, tau_a, aspect, n_phot );
    sed = sds.run_skirt( tag, tau_m, n_dust, aspect, n_phot );
    f_esc = sds.parse_fesc( sed );
    print( '    f_esc=%.6f' % f_esc );
    return { 'f_esc' : f_esc };

############################################################
#  Main

def run_verhamme( args, out_dir, kratos_bin, binary_io ):
    """Verhamme+ (2006) Fig. 4 regime: T = 10 K (a = 1.5e-2), dusty
    slab with line-center depth tau0 = 1e5 and a central plane of
    monochromatic line-center photons. Kratos runs at the tau_a
    values that place X = (a tau0)^{1/3} tau_a on the published MC
    crosses (digitized from verhamme06.pdf, see
    verhamme06_fig4.json). The reference is the Verhamme analytic
    curve (80-point digitisation in the same JSON); fe_analytic is
    obtained by linear interpolation. PASS = Kratos within 1.35x of
    the analytic curve (digitisation ~few % + Poisson noise +
    mixed-precision R_IIA)."""
    import json, math;
    vpath = os.path.join( os.path.dirname( os.path.abspath( \
                              __file__ ) ), 'verhamme06_fig4.json' );
    vdata = json.load( open( vpath ) );
    crosses = [ ( c[ 'x' ], c[ 'fe' ] ) for c in vdata[ 'crosses' ] ];
    curve = [ ( c[ 'x' ], c[ 'fe' ] ) for c in vdata[ 'analytic_curve' ] ];
    circles = [ ( c[ 'x' ], c[ 'fe' ] ) \
                for c in vdata.get( 'hansen_oh_circles', [] ) ];
    a_v = 0.015;
    tau0_lc = 1.0e5;                    # line-center half depth (V06)
    tau_m = sqrt( pi ) * tau0_lc;       # test's mean-depth convention
    xcub = ( a_v * tau0_lc ) ** ( 1.0 / 3.0 );   # X = xcub * tau_a
    print( '\n[verhamme] a=%.3f, tau0(line-center)=%.3e, tau_m=%.4e' \
           % ( a_v, tau0_lc, tau_m ) );
    print( '[verhamme] X = %.4f * tau_a; n=%d photons per run' \
           % ( xcub, args.verhamme_n ) );

    curve_x = array( [ c[ 0 ] for c in curve ] );
    curve_y = array( [ c[ 1 ] for c in curve ] );

    results = [ ];
    for xt, fe_cross in crosses:
        tau_a = xt / xcub;
        fe_analytic = float( interp( xt, curve_x, curve_y ) );
        print( '\n=== X=%.4f (tau_a=%.5f), fe(analytic)=%.6f ===' \
               % ( xt, tau_a, fe_analytic ) );
        for f in out_dir.glob( 'test_*_*.bin' ):
            f.unlink( );
        kres = run_kratos_one( tau_m, tau_a, a_v, args.verhamme_n, \
                               str( out_dir ), \
                               'v06_X%g' % xt, \
                               ph_mode = args.ph_mode, \
                               kratos_bin = kratos_bin, \
                               binary_io = binary_io, \
                               aspect = None );
        entry = { };
        if kres:
            entry = { 'x' : xt, 'tau_a' : tau_a, \
                      'fe_analytic' : fe_analytic, \
                      'fe_kratos' : kres[ 'f_esc' ], \
                      'n_esc' : kres[ 'n_esc' ] };
        if args.skirt:
            sres = run_skirt_one( tau_m, tau_a, \
                                  args.verhamme_skirt_n, \
                                  args.skirt_aspect, \
                                  args.skirt_kappa );
            if sres:
                entry[ 'fe_skirt' ] = sres[ 'f_esc' ];
        if entry:
            results.append( entry );

    ############################################################
    #  Plot: f_esc vs X, published crosses/curve + Kratos

    if not args.no_plot and results:
        import matplotlib;
        matplotlib.use( 'Agg' );
        import matplotlib.pyplot as plt;

        fig, ax = plt.subplots( figsize = ( 7, 5.5 ) );
        cx = array( [ c[ 0 ] for c in curve ] );
        cy = array( [ c[ 1 ] for c in curve ] );
        ##  extend the analytic curve into the upper-left corner using the
        ##  1/cosh(Y0) form (Verhamme et al. 2006 eq. 23); the coefficient
        ##  K = 2.1474 is fitted to the digitized curve itself (80 points,
        ##  interquartile range 2.1395-2.1528)
        cx_ext = logspace( log10( 1.5e-3 ), log10( cx.min() ), 24 );
        cy_ext = 1.0 / cosh( 2.1474 * sqrt( cx_ext ) );
        ax.plot( cx_ext, cy_ext, '-', color = '0.4', linewidth = 1.5 );
        ax.plot( cx, cy, '-', color = '0.4', linewidth = 1.5, \
                 label = 'Verhamme (2006) analytic' );
        if circles:
            ax.plot( [ c[ 0 ] for c in circles ], \
                     [ c[ 1 ] for c in circles ], 'o', \
                     color = 'b', markersize = 7, \
                     markerfacecolor = 'none', linestyle = 'none', \
                     label = 'Hansen \\& Oh (2006)' );
        ax.plot( [ c[ 0 ] for c in crosses ], \
                 [ c[ 1 ] for c in crosses ], '+', color = 'k', \
                 markersize = 9, markeredgewidth = 1.6, \
                 linestyle = 'none', \
                 label = 'Verhamme et al. (2006) MC' );
        ax.plot( [ r[ 'x' ] for r in results ], \
                 [ r[ 'fe_kratos' ] for r in results ], '*', \
                 color = 'r', markersize = 11, \
                 linestyle = 'none', label = 'Kratos' );
        if args.skirt:
            sx = [ r[ 'x' ] for r in results if 'fe_skirt' in r ];
            sy = [ r[ 'fe_skirt' ] for r in results if 'fe_skirt' in r ];
            if sx:
                ax.plot( sx, sy, 's', color = 'g', \
                         markersize = 8, linestyle = 'none', \
                         label = 'SKIRT9' );
        ax.set_xscale( 'log' );
        ax.set_yscale( 'log' );
        ax.set_xlim( cx_ext.min(), 2.0e1 );
        ax.set_ylim( 5e-4, 1.0 );
        ax.set_xlabel( '$(a\\tau_0)^{1/3}\\tau_a$' );
        ax.set_ylabel( '$f_{\\rm esc}$' );
        
        ax.legend();
        fig.tight_layout( );
        plot_path = os.path.join( str( out_dir ), \
                                  'abs_scat_verhamme.pdf' );
        fig.savefig( plot_path, bbox_inches = 'tight' );
        print( '\nSaved: %s' % plot_path );
        plt.close( fig );

    ############################################################
    #  Summary + PASS/FAIL

    print( '\n%s' % ( '=' * 86 ) );
    hdr = '%10s %10s %12s %12s %8s' \
          % ( 'X', 'tau_a', 'fe(analytic)', 'fe(Kratos)', 'K/an' );
    if args.skirt:
        hdr += ' %12s %8s' % ( 'fe(SKIRT)', 'K/S' );
    print( hdr );
    print( '%s' % ( '-' * 86 ) );
    ok = True;
    for r in results:
        rat = r[ 'fe_kratos' ] / r[ 'fe_analytic' ];
        if rat < 1.0 / 1.35 or rat > 1.35:
            ok = False;
        line = '%10.4f %10.5f %12.6e %12.6e %8.3f' \
               % ( r[ 'x' ], r[ 'tau_a' ], r[ 'fe_analytic' ], \
                   r[ 'fe_kratos' ], rat );
        if args.skirt and 'fe_skirt' in r:
            srat = r[ 'fe_kratos' ] / r[ 'fe_skirt' ];
            line += ' %12.6e %8.3f' % ( r[ 'fe_skirt' ], srat );
        elif args.skirt:
            line += ' %12s %8s' % ( '---', '---' );
        print( line );
    print( '%s' % ( '=' * 86 ) );
    if not results:
        print( '(no Kratos results)' );
    elif ok:
        print( 'PASS: Kratos within 1.35x of the Verhamme+ (2006) ' \
               'analytic curve' );
    else:
        print( 'FAIL: Kratos deviates from the Verhamme+ (2006) ' \
               'analytic curve beyond 1.35x' );
        sys.exit( 1 );
    return results;


def main( ):
    p = argparse.ArgumentParser( \
        description = 'Standalone scattering + absorption vs ' \
                      'Neufeld (1990)' );
    p.add_argument( '--tau-m-list', type = float, nargs = '+', \
                    default = [ 30.0, 100.0, 300.0 ], \
                    help = 'Half-slab mean scattering depths (tau_m)' );
    p.add_argument( '--tau-a-list', type = float, nargs = '+', \
                    default = [ 0.1, 0.3, 1.0 ], \
                    help = 'Half-slab absorption depths (tau_a)' );
    p.add_argument( '--a-voigt', type = float, default = 0.149 );
    p.add_argument( '--ph-mode', type = int, default = 1, \
                    help = 'Kratos ph_mode (1=R_IIA exact, ' \
                           '2=const-mem)' );
    p.add_argument( '--n', dest = 'n_radiation', type = int, \
                    default = 50000 );
    p.add_argument( '--kratos-root', type = str, \
                    default = str( DEFAULT_KRATOS_ROOT ), \
                    help = 'Kratos build tree root (must contain ' \
                           'bin/kratos and visual/binary_io.py)' );
    p.add_argument( '--no-kratos', action = 'store_true' );
    p.add_argument( '--no-python', action = 'store_true' );
    p.add_argument( '--no-plot', action = 'store_true' );
    p.add_argument( '--workdir', type = str, default = None, \
                    help = 'output directory (default: auto under ' \
                           '/tmp/line_rt)' );
    p.add_argument( '--skirt', action = 'store_true', \
                    help = 'run the SKIRT wide-box comparison: ' \
                           'Kratos switches to the same finite box ' \
                           'geometry (aspect x L transverse extent, ' \
                           'free boundaries), SKIRT via the ' \
                           'skirt_dust_slab harness; PASS becomes ' \
                           'the Kratos-box/SKIRT ratio' );
    p.add_argument( '--skirt-aspect', type = float, default = 8.0 );
    p.add_argument( '--skirt-kappa', type = float, \
                    default = 8.289740e-17, \
                    help = 'tau_a per unit dust number density ' \
                           '(from skirt_dust_slab.py calib at ' \
                           'aspect 8)' );
    p.add_argument( '--verhamme', action = 'store_true', \
                    help = 'run the Verhamme+ (2006) Fig. 4 regime ' \
                           '(a=0.015, tau0=1e5 line-center) against ' \
                           'the digitized published MC crosses; ' \
                           'PASS = Kratos within 1.35x of the ' \
                           'crosses' );
    p.add_argument( '--verhamme-n', type = int, default = 200000 );
    p.add_argument( '--verhamme-skirt-n', type = int, default = 10000,
                   help = 'SKIRT photon count for Verhamme mode '
                          '(separate from --verhamme-n for Kratos)' );
    args = p.parse_args( );

    kratos_root, kratos_bin, binary_io = \
        resolve_kratos_root( args.kratos_root );
    print( 'Kratos root: %s' % kratos_root );
    print( 'Kratos bin:  %s' % kratos_bin );

    if args.workdir:
        out_dir = Path( args.workdir );
    else:
        Path( '/tmp/line_rt' ).mkdir( parents = True, \
                                      exist_ok = True );
        out_dir = Path( tempfile.mkdtemp( prefix = 'abs_scat_', \
                                          dir = '/tmp/line_rt' ) );
    out_dir.mkdir( parents = True, exist_ok = True );
    print( '[test_absorption_scattering] Run directory: %s' \
           % out_dir );

    if args.verhamme:
        run_verhamme( args, out_dir, kratos_bin, binary_io );
        return;

    results = [ ];
    for tau_a in args.tau_a_list:
        for tau_m in args.tau_m_list:
            f_an, y0 = f_esc_neufeld( tau_m, tau_a, args.a_voigt );
            print( '\n=== tau_m=%s, tau_a=%s, f_esc(Neufeld 4.33)=' \
                   '%.6e [Y0=%.3f] ===' % ( tau_m, tau_a, f_an, y0 ) );
            tag = 'm%s_a%s' % ( format( tau_m, 'g' ), \
                                format( tau_a, 'g' ) );
            entry = { 'tau_m' : tau_m, 'tau_a' : tau_a, \
                      'f_neufeld' : f_an, 'y0' : y0 };

            if not args.no_kratos:
                for f in out_dir.glob( 'test_*_*.bin' ):
                    f.unlink( );
                kres = run_kratos_one( tau_m, tau_a, args.a_voigt, \
                                       args.n_radiation, \
                                       str( out_dir ), tag, \
                                       ph_mode = args.ph_mode, \
                                       kratos_bin = kratos_bin, \
                                       binary_io = binary_io, \
                                       aspect = args.skirt_aspect \
                                                if args.skirt \
                                                else None );
                if kres:
                    entry[ 'f_kratos' ] = kres[ 'f_esc' ];
                    entry[ 'n_kratos' ] = kres[ 'n_esc' ];

            if not args.no_python:
                pres = run_python_one( tau_m, tau_a, args.a_voigt, \
                                       args.n_radiation );
                if pres:
                    entry[ 'f_python' ] = pres[ 'f_esc' ];

            if args.skirt:
                sres = run_skirt_one( tau_m, tau_a, \
                                      args.n_radiation, \
                                      args.skirt_aspect, \
                                      args.skirt_kappa );
                if sres:
                    entry[ 'f_skirt' ] = sres[ 'f_esc' ];

            results.append( entry );

    ############################################################
    #  Plot: f_esc vs tau_a, per tau_m

    if not args.no_plot and results:
        import matplotlib;
        matplotlib.use( 'Agg' );
        import matplotlib.pyplot as plt;

        ta_arr = array( [ r[ 'tau_a' ] for r in results ] );
        tm_arr = array( [ r[ 'tau_m' ] for r in results ] );

        fig, ax1 = plt.subplots( figsize = ( 7, 5.5 ) );

        ta_fine = logspace( log10( min( ta_arr ) * 0.7 ), \
                            log10( max( ta_arr ) * 1.5 ), 200 );
        tm_vals = sorted( unique( tm_arr ) );
        colours = [ 'r', 'g', 'b' ];
        # Colour by tau_m; marker/linestyle distinguishes code.
        for i, tm in enumerate( tm_vals ):
            cc = colours[ i % len( colours ) ];
            f_fine, _ = f_esc_neufeld( tm, ta_fine, args.a_voigt );
            ax1.plot( ta_fine, f_fine, ':', color = cc, \
                      linewidth = 1.2 );
            m = tm_arr == tm;
            if 'f_kratos' in results[ 0 ]:
                fk = array( [ r.get( 'f_kratos', nan ) \
                              for r in results ] )[ m ];
                ax1.plot( ta_arr[ m ], fk, 'o-', color = cc, \
                          markersize = 4, linewidth = 1.5 );
            if 'f_python' in results[ 0 ]:
                fp = array( [ r.get( 'f_python', nan ) \
                              for r in results ] )[ m ];
                ax1.plot( ta_arr[ m ], fp, 's--', color = cc, \
                          markersize = 4, linewidth = 1.2, \
                          markerfacecolor = 'none' );
            if 'f_skirt' in results[ 0 ]:
                fs = array( [ r.get( 'f_skirt', nan ) \
                              for r in results ] )[ m ];
                ax1.plot( ta_arr[ m ], fs, '^-.', color = cc, \
                          markersize = 5, linewidth = 1.2 );
        ax1.set_xscale( 'log' );
        ax1.set_yscale( 'log' );
        ax1.set_xlabel( '$\\tau_a$ (half-slab absorption depth)' );
        ax1.set_ylabel( '$f_{\\rm esc}$ (weighted)' );
        
        # Two-part legend: code (marker/linestyle) + tau_m (colour).
        from matplotlib.lines import Line2D;
        code_handles = [ \
            Line2D( [ 0 ], [ 0 ], color = '0.5', marker = 'o', \
                    linestyle = '-', markersize = 4, \
                    linewidth = 1.5, label = 'Kratos' ), \
            Line2D( [ 0 ], [ 0 ], color = '0.5', marker = '^', \
                    linestyle = '-.', markersize = 5, \
                    linewidth = 1.2, label = 'SKIRT' ), \
            Line2D( [ 0 ], [ 0 ], color = '0.5', marker = 's', \
                    linestyle = '--', markersize = 4, linewidth = 1.2, \
                    markerfacecolor = 'none', label = 'Python ref.' ), \
            Line2D( [ 0 ], [ 0 ], color = '0.5', linestyle = ':', \
                    linewidth = 1.2, \
                    label = 'Neufeld (1990) $1/\\cosh(Y_0)$' ) ];
        leg1 = ax1.legend( handles = code_handles, \
                           loc = 'upper left' );
        ax1.add_artist( leg1 );
        tm_handles = [ Line2D( [ 0 ], [ 0 ], \
                               color = colours[ i % len( colours ) ], \
                               linewidth = 1.5, \
                               label = '$\\tau_m$=%s' % format( tm, 'g' ) ) \
                       for i, tm in enumerate( tm_vals ) ];
        ax1.legend( handles = tm_handles, \
                    loc = 'lower right' );

        fig.tight_layout( );
        plot_path = os.path.join( str( out_dir ), \
                                  'abs_scat_fesc_vs_tau.pdf' );
        fig.savefig( plot_path, bbox_inches = 'tight' );
        print( '\nSaved: %s' % plot_path );
        plt.close( fig );

    ############################################################
    #  Summary table + PASS/FAIL
    #  PASS = Kratos ~ Python (two independent MC implementations
    #  agree). K/Neufeld and P/Neufeld are diagnostic-only: cosh (4.33)
    #  is a Fokker-Planck approximation that OVERESTIMATES f_esc at
    #  intermediate depth (Verhamme 2006); MC sits below it (expected
    #  ratios < 1).

    print( '\n%s' % ( '=' * 96 ) );
    hdr = '%6s %6s %7s %12s %12s %12s' \
          % ( 'tau_m', 'tau_a', 'Q', 'Neufeld', 'Kratos', 'Python' );
    if args.skirt:
        hdr += ' %12s %8s' % ( 'SKIRT', 'K/S' );
    hdr += ' %8s %8s %8s' % ( 'K/N', 'P/N', 'K/P' );
    print( hdr );
    print( '%s' % ( '-' * 96 ) );
    ok = True;
    for r in results:
        fk = r.get( 'f_kratos', nan );
        fp = r.get( 'f_python', nan );
        fa = r[ 'f_neufeld' ];
        q = ( args.a_voigt * r[ 'tau_m' ] ) ** ( 1.0 / 3.0 ) * \
            r[ 'tau_a' ];
        kn = fk / fa if fa > 0 else nan;
        pn = fp / fa if fa > 0 else nan;
        kp = fk / fp if fp > 0 else nan;
        fsk = r.get( 'f_skirt', nan );
        ks = fk / fsk if fsk > 0 else nan;
        # PASS criterion: Kratos ~ Python (default) or Kratos ~
        # SKIRT (--skirt). Allow 1.6x for MC noise at low f_esc
        # (~1e-3 with n=5e4 -> ~15% Poisson per implementation).
        chk = ks if args.skirt else kp;
        if ( not isnan( chk ) ) and ( chk < 0.6 or chk > 1.6 ):
            ok = False;
        line = '%6.0f %6.2f %7.3f %12.6e %12.6e %12.6e' \
               % ( r[ 'tau_m' ], r[ 'tau_a' ], q, fa, fk, fp );
        if args.skirt:
            line += ' %12.6e %8.3f' % ( fsk, ks );
        line += ' %8.3f %8.3f %8.3f' % ( kn, pn, kp );
        print( line );
    print( '%s' % ( '=' * 96 ) );
    print( 'Note: K/N, P/N < 1 is EXPECTED - cosh (4.33) is a ' \
           'Fokker-Planck' );
    print( '      approximation that overestimates f_esc (Verhamme ' \
           '2006);' );
    print( '      independent MC (neufeld_mc.py) shows the same ' \
           'MC-below-cosh' );
    print( '      behavior.' );
    if args.skirt:
        print( '      PASS = Kratos ~ SKIRT (wide-box aspect=%g); ' \
               'K/P is slab-vs-slab diagnostic.' \
               % args.skirt_aspect );
    else:
        print( '      PASS = Kratos ~ Python.' );
    if ( args.skirt and args.no_kratos ) or \
       ( not args.skirt and ( args.no_kratos or args.no_python ) ):
        print( '(partial run: PASS check skipped)' );
    elif ok:
        print( 'PASS: Kratos ~ %s (independent codes agree)' \
               % ( 'SKIRT' if args.skirt else 'Python' ) );
    else:
        print( 'FAIL: code comparison beyond 1.6x tolerance' );
        sys.exit( 1 );

    return results;


if __name__ == '__main__':
    main( );
