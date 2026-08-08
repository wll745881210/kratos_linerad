#!/usr/bin/env python3
"""
Standalone thin-slab imaging spectrum test.

Self-contained: no pipeline imports.  Uses binary_io from the Kratos
repo (like test_scaling_wide.py / test_absorption_scattering.py).

Geometry (rotated to match slab-source API which only supports +x/-x):
  Domain:  [-L, L]^3  (code units), free boundaries all 6 faces
  Source:  slab at x=-L, direction +x, flux F [photons cm^-2 s^-1]
  Camera:  dir_cam = (0, 0, 1)  (along +z, theta=0 phi=0)
  Slab:    -L/2 < z < L/2  (scattering medium, thickness L_slab = L*unit_l0)
  vel:     (0, 0, v_z)  bulk velocity along camera direction
  g = dir_source . dir_cam = (1,0,0).(0,0,1) = 0  (perpendicular)

For a->0, g=0:  R(x_out; x_pp, 0) = exp(-x_out^2) / sqrt(pi)
  (perpendicular scattering => no frequency memory, purely thermal)
The emissivity uses the line-CENTRE opacity (sigma at the incoming
frequency, not the outgoing): j = mfp_s * s_cam.  No extra phi(x_out).
Intensity (thin):  I(k) = F * mfp_s * L_slab * exp(-x_out^2)
                                / (4*pi * b * sqrt(pi))
Total:  int I dv = F * mfp_s * L_slab / (4*pi)

Usage:
  python3 usr_ext/line_rt/tests/test_imaging_spectrum.py \
      --kratos-root ~/apps/kratos_line_rt
  python3 usr_ext/line_rt/tests/test_imaging_spectrum.py \
      --kratos-root ~/apps/kratos_line_rt --plots
"""
import argparse, importlib, os, subprocess, sys, tempfile;
from pathlib import Path;
from numpy import array, asarray, zeros, full, ones, exp, sqrt, pi, \
                  float32, float64, int32, arange, where, abs as abso;

UNIT_L0 = 1.49597870691e13;
UNIT_T0 = 1.0;
B_SCA_CGS = 1.0e5;
DEFAULT_KRATOS_ROOT = Path( os.path.expanduser(
    '~/apps/kratos_line_rt' ) );
WORKDIR = Path( '/tmp/line_rt' );


############################################################
#  Kratos root resolution

def resolve_kratos_root( kratos_root ):
    kratos_root = Path( kratos_root ).expanduser();
    kratos_bin = kratos_root / 'bin' / 'kratos';
    bio_path = kratos_root / 'visual' / 'binary_io.py';
    if not kratos_bin.exists():
        raise FileNotFoundError(
            'kratos binary not found: %s' % kratos_bin );
    if not bio_path.exists():
        raise FileNotFoundError(
            'binary_io.py not found: %s' % bio_path );
    if str( kratos_root / 'visual' ) not in sys.path:
        sys.path.insert( 0, str( kratos_root / 'visual' ) );
    binary_io = importlib.import_module( 'binary_io' ).binary_io;
    return kratos_root, kratos_bin, binary_io;


############################################################
#  Binary I/O (inline, mirrors pipeline/kratos_io.py)

def write_fields( filename, fields, mesh, binary_io ):
    bio = binary_io( filename );
    n_cell = asarray( mesh[ 'n_cell' ], dtype = int32 );
    x_min = asarray( mesh[ 'x_min' ], dtype = float32 );
    dx = asarray( mesh[ 'dx' ], dtype = float32 );
    n_pts = n_cell.copy();
    x0_nodes = x_min + 0.5 * dx;
    ijkl_flag = array( 0, dtype = int32 );
    for prefix in [ 'mfp_i_sca_0_', 'mfp_i_abs_0_', 'b_sca_',
                     'vel_0_', 'vel_1_', 'vel_2_' ]:
        if prefix not in fields:
            continue;
        raw = asarray( fields[ prefix ], dtype = float32 );
        bio.cache( '%sijkl' % prefix, ijkl_flag, dtype = 'int32' );
        bio.cache( '%sn_pts' % prefix, n_pts, dtype = 'int32' );
        bio.cache( '%sx0' % prefix, x0_nodes, dtype = 'float32' );
        bio.cache( '%sdx' % prefix, dx, dtype = 'float32' );
        bio.cache( '%sdata' % prefix, raw, dtype = 'float32' );
    bio.save();
    return filename;


def write_photons( filename, photons, binary_io ):
    ph = asarray( photons, dtype = float32 );
    bio = binary_io( filename );
    bio.cache( 'par_n_col', ph.shape[ 1 ], dtype = 'int32' );
    bio.cache( 'par_n_par', ph.shape[ 0 ], dtype = 'int64' );
    bio.cache( 'par_par_dat', ph, dtype = 'float32' );
    bio.save();
    return filename;


def read_image( filename, n_chan, binary_io ):
    """Read imaging output: _l_img (intensity), _i2d_img (pixel idx)."""
    bio = binary_io( filename );
    bio.open();
    l_img = None;
    i2d = None;
    n_par = None;
    for raw_key in bio.hmap:
        if raw_key.endswith( '_l_img' ):
            l_img = bio.as_array( raw_key, 'f' );
        elif raw_key.endswith( '_i2d_img' ):
            i2d = bio.as_array( raw_key, 'i' );
        elif raw_key.endswith( '_n_par' ) and 'img' not in raw_key:
            pass;
    bio.close();
    if l_img is None:
        return None, None;
    n_pix = l_img.size // n_chan;
    l_img = l_img.reshape( n_pix, n_chan );
    if i2d is not None:
        i2d = i2d.reshape( n_pix, 2 );
    return l_img, i2d;


############################################################
#  Analytic

def analytic_spectrum( v_chans, v_bulk, b, mfp_s, L_slab, F ):
    x = ( v_chans + v_bulk ) / b;
    return F * mfp_s * L_slab * exp( -1.0 * x ** 2 ) \
           / ( 4.0 * pi * sqrt( pi ) * b );


def analytic_total( b, mfp_s, L_slab, F ):
    return F * mfp_s * L_slab / ( 4.0 * pi );


def channel_centers( n_chan, v_lo, v_hi ):
    dv = ( v_hi - v_lo ) / n_chan;
    return v_lo + ( arange( n_chan ) + 0.5 ) * dv, dv;


############################################################
#  Par template

PAR_TEMPLATE = """# Kratos imaging spectrum test - auto-generated

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
worker_mode = 1
n_worker    = 32768
proper_min_frac = 0

[boundary]
kinds = fre fre fre fre fre fre

[imaging]
enabled         = 1
n_chan          = {n_chan}
dir_cam_theta   = {dir_cam_theta}
dir_cam_phi     = {dir_cam_phi}
v_chan_min      = {v_chan_min}
v_chan_max      = {v_chan_max}
"""


def generate_inputs( v_z_cgs, n_radiation, out_dir, tag,
                     ph_mode = 2, n_cell = ( 8, 8, 16 ),
                     L_au = 1.0, tau0 = 0.01, b_sca = B_SCA_CGS,
                     n_chan = 32, v_lo_cgs = -5e5, v_hi_cgs = 5e5,
                     F = 1e6, proper_scale = 1e-10,
                     binary_io = None ):
    L_code = L_au;
    L_slab_cgs = L_au * UNIT_L0;
    mfp_s_cgs = tau0 / L_slab_cgs;
    mfp_s_code = mfp_s_cgs * UNIT_L0;
    b_sca_code = b_sca * UNIT_T0 / UNIT_L0;
    v_z_code = v_z_cgs * UNIT_T0 / UNIT_L0;
    v2c = UNIT_T0 / UNIT_L0;

    nx, ny, nz = n_cell;
    dx = 2.0 * L_code / nx;
    dy = 2.0 * L_code / ny;
    dz = 2.0 * L_code / nz;
    n_tot = nx * ny * nz;

    mfp = zeros( n_tot, dtype = float32 );
    mfp3d = mfp.reshape( nz, ny, nx );
    iz_lo = int( ( -0.5 * L_code - ( -L_code ) ) / dz );
    iz_hi = int( (  0.5 * L_code - ( -L_code ) ) / dz );
    mfp3d[ iz_lo:iz_hi, :, : ] = float32( mfp_s_code );
    mfp_flat = mfp3d.ravel();

    fields = {
        'mfp_i_sca_0_': mfp_flat,
        'mfp_i_abs_0_': zeros( n_tot, dtype = float32 ),
        'b_sca_'      : full( n_tot, float32( b_sca_code ) ),
        'vel_0_'      : zeros( n_tot, dtype = float32 ),
        'vel_1_'      : zeros( n_tot, dtype = float32 ),
        'vel_2_'      : full( n_tot, float32( v_z_code ) ),
    };
    mesh = {
        'n_cell': array( [ nx, ny, nz ], dtype = int32 ),
        'x_min': array( [ -L_code, -L_code, -L_code ],
                         dtype = float32 ),
        'dx': array( [ dx, dy, dz ], dtype = float32 ),
    };

    field_file = os.path.join( out_dir, 'fields_%s.bin' % tag );
    write_fields( field_file, fields, mesh, binary_io );

    x_min_arr = [ -L_code, -L_code, -L_code ];
    x_max_arr = [ x_min_arr[ i ] + n_cell[ i ] * [ dx, dy, dz ][ i ]
                  for i in range( 3 ) ];
    fmt3 = lambda v: ' '.join( '%.6f' % x for x in v );
    fmt3i = lambda v: ' '.join( str( int( x ) ) for x in v );

    v_chan_min_code = v_lo_cgs * v2c;
    v_chan_max_code = v_hi_cgs * v2c;

    par_path = os.path.join( out_dir, 'img_%s.par' % tag );
    par_content = PAR_TEMPLATE.format(
        unit_l0 = UNIT_L0, unit_t0 = UNIT_T0,
        x_min = fmt3( x_min_arr ), x_max = fmt3( x_max_arr ),
        n_cells = fmt3i( n_cell ),
        n_radiation = n_radiation, ph_mode = ph_mode,
        a_voigt = 0.01,
        field_file = os.path.basename( field_file ),
        photon_file = 'photons_%s.bin' % tag,
        b_sca_code = b_sca_code, tag = tag,
        n_chan = n_chan,
        dir_cam_theta = 0.0, dir_cam_phi = 0.0,
        v_chan_min = '%.10e' % v_chan_min_code,
        v_chan_max = '%.10e' % v_chan_max_code,
    );
    with open( par_path, 'w' ) as fp:
        fp.write( par_content );

    from numpy.random import default_rng;
    rng = default_rng( 42 );
    ph = zeros( ( n_radiation, 8 ), dtype = float32 );
    ph[ :, 0 ] = -L_code + 1e-6;
    ph[ :, 1 ] = rng.uniform( -L_code, L_code, n_radiation );
    ph[ :, 2 ] = rng.uniform( -L_code, L_code, n_radiation );
    ph[ :, 3 ] = 1.0;
    ph[ :, 4 ] = 0.0;
    ph[ :, 5 ] = 0.0;
    area_cgs = ( 2.0 * L_au * UNIT_L0 ) ** 2;
    proper_cgs = F * area_cgs / n_radiation;
    ph[ :, 6 ] = float32( proper_cgs * proper_scale );
    ph[ :, 7 ] = 0.0;
    photon_file = os.path.join( out_dir, 'photons_%s.bin' % tag );
    write_photons( photon_file, ph, binary_io );

    info = {
        'mfp_s_cgs': mfp_s_cgs,
        'mfp_s_code': mfp_s_code,
        'b_sca_cgs': b_sca,
        'b_sca_code': b_sca_code,
        'L_slab_cgs': L_slab_cgs,
        'F': F,
        'proper_scale': proper_scale,
        'n_chan': n_chan,
        'v_lo_cgs': v_lo_cgs,
        'v_hi_cgs': v_hi_cgs,
        'v_z_cgs': v_z_cgs,
        'i_conv': 1.0 / ( UNIT_L0 ** 3 * UNIT_T0 ),
        'iz_lo': iz_lo, 'iz_hi': iz_hi,
    };
    return par_path, info;


def run_one( v_z_cgs, n_radiation, out_dir, tag,
             kratos_bin = None, binary_io = None, **kw ):
    par_path, info = generate_inputs(
        v_z_cgs, n_radiation, out_dir, tag,
        binary_io = binary_io, **kw );
    result = subprocess.run(
        [ str( kratos_bin ), os.path.basename( par_path ) ],
        cwd = out_dir, capture_output = True, text = True,
        timeout = 300,
    );
    if result.returncode != 0:
        print( '  FAILED: %s' % result.stderr[ -300: ] );
        return None;

    out_files = sorted( Path( out_dir ).glob(
        'test_%s_*.bin' % tag ) );
    if not out_files:
        print( '  No output file' );
        return None;

    l_img, i2d = read_image(
        str( out_files[ -1 ] ), info[ 'n_chan' ], binary_io );
    if l_img is None:
        print( '  No _l_img in output' );
        return None;

    ps = info[ 'proper_scale' ];
    i_conv = info[ 'i_conv' ];
    cube_cgs = ( l_img.astype( float64 ) / ps ) * i_conv;

    v_chans, dv = channel_centers(
        info[ 'n_chan' ], info[ 'v_lo_cgs' ], info[ 'v_hi_cgs' ] );

    return {
        'cube_cgs': cube_cgs,
        'i2d': i2d,
        'v_chans': v_chans,
        'dv': dv,
        'info': info,
    };


############################################################
#  Tests

def check_normalization( result, label = '' ):
    info = result[ 'info' ];
    spec = result[ 'cube_cgs' ];
    valid = spec.any( axis = 1 );
    avg = spec[ valid ].mean( axis = 0 );
    dv = result[ 'dv' ];
    sim = float( avg.sum() ) * dv;
    expected = analytic_total(
        info[ 'b_sca_cgs' ], info[ 'mfp_s_cgs' ],
        info[ 'L_slab_cgs' ], info[ 'F' ] );
    rel = abso( sim - expected ) / expected;
    print( '  [%s] norm: sim=%.4e, expected=%.4e, rel=%.1f%%' %
           ( label, sim, expected, rel * 100 ) );
    assert rel < 0.20, \
        '[%s] norm %.1f%% > 20%%' % ( label, rel * 100 );
    print( '  [%s] norm PASS' % label );


def check_shape( result, label = '' ):
    info = result[ 'info' ];
    spec = result[ 'cube_cgs' ];
    valid = spec.any( axis = 1 );
    avg = spec[ valid ].mean( axis = 0 );
    v_chans = result[ 'v_chans' ];
    analytic = analytic_spectrum(
        v_chans, info[ 'v_z_cgs' ], info[ 'b_sca_cgs' ],
        info[ 'mfp_s_cgs' ], info[ 'L_slab_cgs' ], info[ 'F' ] );
    if avg.max() <= 0 or analytic.max() <= 0:
        assert False, '[%s] spectrum all zeros' % label;
    sim_n = avg / avg.max();
    an_n = analytic / analytic.max();
    max_rel = float( abso( sim_n - an_n ).max() );
    print( '  [%s] shape: max_rel=%.1f%%' % ( label, max_rel * 100 ) );
    assert max_rel < 0.20, \
        '[%s] shape %.1f%% > 20%%' % ( label, max_rel * 100 );
    print( '  [%s] shape PASS' % label );


def check_doppler( result, label = '' ):
    info = result[ 'info' ];
    spec = result[ 'cube_cgs' ];
    valid = spec.any( axis = 1 );
    avg = spec[ valid ].mean( axis = 0 );
    v_chans = result[ 'v_chans' ];
    analytic = analytic_spectrum(
        v_chans, info[ 'v_z_cgs' ], info[ 'b_sca_cgs' ],
        info[ 'mfp_s_cgs' ], info[ 'L_slab_cgs' ], info[ 'F' ] );
    k_sim = int( avg.argmax() );
    k_an = int( analytic.argmax() );
    print( '  [%s] doppler: peak sim chan %d (v=%.1e), '
           'an chan %d (v=%.1e)' %
           ( label, k_sim, v_chans[ k_sim ],
             k_an, v_chans[ k_an ] ) );
    assert abso( k_sim - k_an ) <= 1, \
        '[%s] peak mismatch sim=%d an=%d' % ( label, k_sim, k_an );
    if avg.max() > 0 and analytic.max() > 0:
        sim_n = avg / avg.max();
        an_n = analytic / analytic.max();
        max_rel = float( abso( sim_n - an_n ).max() );
        print( '  [%s] doppler shape: %.1f%%' %
               ( label, max_rel * 100 ) );
        assert max_rel < 0.20, \
            '[%s] doppler shape %.1f%% > 20%%' % \
            ( label, max_rel * 100 );
    print( '  [%s] doppler PASS' % label );


def make_figure( results, out_path ):
    try:
        import matplotlib;
        matplotlib.use( 'Agg' );
        import matplotlib.pyplot as plt;
    except ImportError:
        print( '  matplotlib not installed, skipping figure' );
        return;
    fig, axes = plt.subplots( 1, len( results ),
                              figsize = ( 6 * len( results ), 5 ),
                              squeeze = False );
    for ax, ( title, res ) in zip( axes[ 0 ], results ):
        info = res[ 'info' ];
        spec = res[ 'cube_cgs' ];
        valid = spec.any( axis = 1 );
        avg = spec[ valid ].mean( axis = 0 );
        v_chans = res[ 'v_chans' ];
        an = analytic_spectrum(
            v_chans, info[ 'v_z_cgs' ], info[ 'b_sca_cgs' ],
            info[ 'mfp_s_cgs' ], info[ 'L_slab_cgs' ], info[ 'F' ] );
        x = v_chans / info[ 'b_sca_cgs' ];
        ax.plot( x, an, 'b-', lw = 2, label = 'Analytic' );
        ax.plot( x, avg, 'ro', ms = 5, label = 'Simulation' );
        ax.set_xlabel( r'$v_{\rm chan} \,/\, b_{\rm sca}$' );
        ax.set_ylabel(
            r'$I$ [photons cm$^{-2}$ s$^{-1}$ sr$^{-1}$]' );
        ax.set_title( title );
        ax.legend();
        ax.set_xlim( -5, 5 );
    fig.suptitle(
        'Thin-slab imaging spectrum: '
        r'$I(v) \propto \exp(-x_{\rm out}^2)$' );
    fig.tight_layout();
    fig.savefig( out_path, dpi = 150 );
    plt.close( fig );
    print( '  figure saved to %s' % out_path );


############################################################
#  Main

def main():
    parser = argparse.ArgumentParser( description = __doc__ );
    parser.add_argument( '--kratos-root', default = str(
        DEFAULT_KRATOS_ROOT ) );
    parser.add_argument( '--n', type = int, default = 100000,
                         help = 'number of photons' );
    parser.add_argument( '--plots', action = 'store_true' );
    args = parser.parse_args();

    kratos_root, kratos_bin, binary_io = resolve_kratos_root(
        args.kratos_root );

    WORKDIR.mkdir( parents = True, exist_ok = True );
    out_dir = str( tempfile.mkdtemp( dir = str( WORKDIR ) ) );

    all_pass = True;

    print( '=== Test A: normalization (v_z = 0) ===' );
    res_a = run_one( 0.0, args.n, out_dir, 'norm',
                     kratos_bin = kratos_bin,
                     binary_io = binary_io );
    if res_a is None:
        print( '  FAILED' ); all_pass = False;
    else:
        try:
            check_normalization( res_a, 'norm' );
            check_shape( res_a, 'norm' );
        except AssertionError as e:
            print( '  %s' % e ); all_pass = False;

    print( '=== Test B: Doppler shift (v_z = b_sca) ===' );
    res_b = run_one( B_SCA_CGS, args.n, out_dir, 'doppler',
                     kratos_bin = kratos_bin,
                     binary_io = binary_io );
    if res_b is None:
        print( '  FAILED' ); all_pass = False;
    else:
        try:
            check_doppler( res_b, 'doppler' );
        except AssertionError as e:
            print( '  %s' % e ); all_pass = False;

    if args.plots and res_a and res_b:
        fig_path = os.path.join(
            os.path.dirname( __file__ ), 'imaging_spectrum.png' );
        make_figure(
            [ ( r'$v_z = 0$', res_a ),
              ( r'$v_z = b_{\rm sca}$', res_b ) ],
            fig_path );

    import shutil;
    shutil.rmtree( out_dir );

    if all_pass:
        print( '\n=== All imaging spectrum tests PASSED ===' );
    else:
        print( '\n=== Some tests FAILED ===' );
        sys.exit( 1 );


if __name__ == '__main__':
    main();
