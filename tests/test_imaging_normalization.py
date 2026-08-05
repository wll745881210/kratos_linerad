"""Quantitative imaging tests: thin slab + scattering + absorbing.

Three tests, all using 1 channel at line centre:

1. Thin thermal slab (Group 1, emission-only):
   I(0) = S * (1 - exp(-tau0))  where  S = emiss/(mfp_sca*sqrt(pi)*b)

2. Scattering slab (Group 2, external source perpendicular to camera):
   I(0) = mfp_sca_0 * F * L_z / (4*pi * sqrt(pi) * b)
   (single-scattering: source beam at 90 deg to camera LOS)

3. Absorbing slab (Group 1, strong absorption, thin scattering):
   I(0) = (mfp_sca/(mfp_sca+mfp_abs)) * S_th * (1-exp(-(mfp_sca+mfp_abs)*L))
   (absorption is a pure sink — no B_nu emission)

Kratos-integration tests: invoke the real binary.  Skip if absent.
"""

import os;
import sys;
from numpy import sqrt, exp, pi;
import pytest;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

KRATOS_ROOT = os.environ.get( 'KRATOS_ROOT', \
                              os.path.expanduser( '~/apps/kratos_line_rt' ) );
KRATOS_BIN = os.path.join( KRATOS_ROOT, 'bin', 'kratos' );

AU = 1.49598e13;     # cm
k_B = 1.380649e-16;  # erg/K
m_p = 1.67262192e-24;  # g
h_cgs = 6.62607015e-27;
c_cgs = 2.99792458e10;


def _run_or_skip( ):
    if not os.path.isfile( KRATOS_BIN ):
        pytest.skip( "Kratos binary not found at %s" % KRATOS_BIN );


def _load_lr( ):
    import importlib.util;
    spec = importlib.util.spec_from_file_location( \
        'line_rt', os.path.join( os.path.dirname( os.path.dirname( \
            os.path.abspath( __file__ ) ) ), 'line_rt.py' ) );
    lr = importlib.util.module_from_spec( spec );
    spec.loader.exec_module( lr );
    return lr;


def _slab_analytic( n_species, T, L_z_au, mol_mass = 28.0,
                    A_ul = 7.203e-8, freq_GHz = 115.271,
                    g_u = 3.0, g_l = 1.0 ):
    """Return analytic quantities for a uniform CO J=1->0 slab in LTE."""
    nu = freq_GHz * 1e9;
    dE_K = h_cgs * nu / k_B;
    n_ratio = ( g_u / g_l ) * exp( -dE_K / T );
    n_u = n_species * n_ratio / ( 1.0 + n_ratio );
    n_l = n_species / ( 1.0 + n_ratio );

    b_cgs = sqrt( 2.0 * k_B * T / ( mol_mass * m_p ) );

    sigma0 = ( g_u / g_l ) * A_ul * c_cgs ** 3 \
             / ( 8.0 * pi ** 1.5 * nu ** 3 * b_cgs );

    mfp_cgs = n_l * sigma0;                 # 1/cm  (inverse mfp)
    emiss_cgs = n_u * A_ul / ( 4.0 * pi );  # photons cm^-3 s^-1 sr^-1
    S_cgs = emiss_cgs / ( mfp_cgs * sqrt( pi ) * b_cgs );

    L_z_cgs = L_z_au * AU;
    tau0 = mfp_cgs * L_z_cgs;

    return dict( S_cgs = S_cgs, tau0 = tau0, b_cgs = b_cgs,
                 n_u = n_u, n_l = n_l, sigma0 = sigma0,
                 mfp_cgs = mfp_cgs, emiss_cgs = emiss_cgs,
                 L_z_cgs = L_z_cgs );


def _check_center_pixel( cube, i2d, expected, label, tol = 0.30 ):
    """Check the centre-pixel, line-centre value against expected."""
    center_pix = None;
    for p in range( i2d.shape[ 0 ] ):
        if i2d[ p, 0 ] == 4 and i2d[ p, 1 ] == 4:
            center_pix = p; break;
    assert center_pix is not None, "no centre pixel found";
    actual = float( cube[ center_pix, 0 ] );
    rel = abs( actual - expected ) / expected if expected > 0 else 1e99;
    print( "  [%s] actual=%.6e, expected=%.6e, rel=%.1f%%" \
           % ( label, actual, expected, rel * 100 ) );
    assert rel < tol, \
        "[%s] imaging cube %.6e deviates from expected %.6e by %.1f%%" \
        % ( label, actual, expected, rel * 100 );
    print( "  [%s] PASS" % label );


# ------------------------------------------------------------------ #
#  Test 1: thin thermal slab (emission-only)
# ----------------------------------------------------------------- #

def _run_slab_imaging( n_species, T, L_x_au, L_z_au, n_chan, v_lo, v_hi,
                       mfp_abs = 1e-20 ):
    """Run a face-on imaging simulation of a uniform slab."""
    lr = _load_lr( );
    from molecular.transition_info import TransitionInfo;

    ti = TransitionInfo.user_defined( \
        A_ul = 7.203e-8, freq_GHz = 115.271, species_name = 'CO',
        g_u = 3.0, g_l = 1.0 );

    rt = lr.LineRt( \
        kratos_root = KRATOS_ROOT,
        n_cell = ( 8, 8, 4 ),
        x_min = ( -L_x_au / 2, -L_x_au / 2, -L_z_au / 2 ),
        x_max = (  L_x_au / 2,  L_x_au / 2,  L_z_au / 2 ),
        unit_l0 = AU,
        transition_info = ti,
        n_species = n_species,
        temperature = T,
        mfp_i_abs_0 = mfp_abs,
        ph_mode = 0,
        n_step = 2000,
        n_scat = 1000,
        n_emission_max = 4,
        proper_scale = 1e-20,
        imaging = { \
            'dir_cam'    : ( 0.0, 0.0 ),
            'n_chan'     : n_chan,
            'v_chan'     : ( v_lo, v_hi ) },
        visualize = False,
        keep_intermediate = False );

    out = rt.run( n_cycles = 1 );
    assert 'image' in out, "no image in output";
    img = out[ 'image' ];
    assert 'cube_cgs' in img, "no cube_cgs in image";
    return img[ 'cube_cgs' ], img[ 'i2d' ];


def test_imaging_thin_slab( ):
    """Thin slab: I(0) = S*(1-exp(-tau0)) ~ emiss*phi_norm*L."""
    _run_or_skip( );
    n_species = 1e-4;  T = 20.0;
    L_x = 2.0;  L_z = 0.5;
    n_chan = 1;  v_lo = 0.0;  v_hi = 0.0;

    a = _slab_analytic( n_species, T, L_z );
    expected = a[ 'S_cgs' ] * ( 1.0 - exp( -a[ 'tau0' ] ) );
    print( "  thin: tau0=%.4e, S=%.4e, expected I(0)=%.4e" \
           % ( a[ 'tau0' ], a[ 'S_cgs' ], expected ) );

    cube, i2d = _run_slab_imaging( \
        n_species, T, L_x, L_z, n_chan, v_lo, v_hi );
    _check_center_pixel( cube, i2d, expected, "thin" );


# ------------------------------------------------------------------ #
#  Test 2: scattering slab (external source, perpendicular to camera)
# ----------------------------------------------------------------- #

def _run_scattering_imaging( mfp_sca_0_cgs, b_sca_cgs, flux,
                             L_x_au, L_z_au, n_chan, v_lo, v_hi ):
    """Run imaging with Group 2 (no species) + slab source in +x,
    camera along +z (perpendicular geometry)."""
    lr = _load_lr( );

    rt = lr.LineRt( \
        kratos_root = KRATOS_ROOT,
        n_cell = ( 8, 8, 4 ),
        x_min = ( -L_x_au / 2, -L_x_au / 2, -L_z_au / 2 ),
        x_max = (  L_x_au / 2,  L_x_au / 2,  L_z_au / 2 ),
        unit_l0 = AU,
        b_sca = b_sca_cgs,
        mfp_i_sca_0 = mfp_sca_0_cgs,
        mfp_i_abs_0 = 0.0,
        ph_mode = 0,
        n_step = 2000,
        n_scat = 1,
        proper_scale = 1e-20,
        imaging = { \
            'dir_cam'    : ( 0.0, 0.0 ),
            'n_chan'     : n_chan,
            'v_chan'     : ( v_lo, v_hi ) },
        visualize = False,
        keep_intermediate = False );

    rt.set_boundary( 'fre fre per per fre fre' );
    rt.add_source( type = 'slab', direction = '+x',
                   x = -L_x_au / 2, flux = flux, n_photon = 10000 );

    out = rt.run( n_cycles = 1 );
    assert 'image' in out, "no image in output";
    img = out[ 'image' ];
    assert 'cube_cgs' in img, "no cube_cgs in image";
    return img[ 'cube_cgs' ], img[ 'i2d' ];


def test_imaging_scattering_slab( ):
    """Scattering slab: source perpendicular to camera, single scattering.

    I(0) = mfp_sca_0 * F * L_z / (4*pi * sqrt(pi) * b)
    (single-scattering intensity at line centre).
    """
    _run_or_skip( );
    n_species = 1e-4;  T = 20.0;
    L_x = 2.0;  L_z = 0.5;
    n_chan = 1;  v_lo = 0.0;  v_hi = 0.0;
    flux = 1e6;  # photons cm^-2 s^-1

    a = _slab_analytic( n_species, T, L_z );
    mfp = a[ 'mfp_cgs' ];  b = a[ 'b_cgs' ];  L_z_cgs = a[ 'L_z_cgs' ];

    # Single-scattering: I = alpha_s(0) * J_bar * L_z
    # J_bar = F / (4*pi * sqrt(pi) * b)  (profile-averaged mean intensity
    # of a monochromatic beam at line centre)
    expected = mfp * flux * L_z_cgs / ( 4.0 * pi * sqrt( pi ) * b );
    print( "  scattering: mfp=%.4e, F=%.1e, L_z=%.4e, b=%.4e" \
           % ( mfp, flux, L_z_cgs, b ) );
    print( "  expected I(0) = %.6e" % expected );

    cube, i2d = _run_scattering_imaging( \
        mfp, b, flux, L_x, L_z, n_chan, v_lo, v_hi );
    _check_center_pixel( cube, i2d, expected, "scattering", tol = 0.50 );


# ------------------------------------------------------------------ #
#  Test 3: absorbing slab (strong absorption, thin scattering)
# ----------------------------------------------------------------- #

def test_imaging_absorbing_slab( ):
    """Absorbing slab: absorption is a pure sink (no B_nu emission).

    With thin scattering (tau_sca << 1) and thick absorption
    (tau_abs >> 1), the thermal seed dominates and:
      I(0) = (alpha_s/alpha_t) * S_th * (1 - exp(-alpha_t * L))
    """
    _run_or_skip( );
    n_species = 1e-4;  T = 20.0;
    L_x = 2.0;  L_z = 0.5;
    n_chan = 1;  v_lo = 0.0;  v_hi = 0.0;

    a = _slab_analytic( n_species, T, L_z );
    mfp_sca = a[ 'mfp_cgs' ];
    S_th = a[ 'S_cgs' ];
    L_z_cgs = a[ 'L_z_cgs' ];

    # Set absorption so tau_abs ~ 10 (thick), tau_sca ~ 1e-6 (thin)
    mfp_abs = 10.0 / L_z_cgs;
    alpha_t = mfp_sca + mfp_abs;
    expected = ( mfp_sca / alpha_t ) * S_th * ( 1.0 - exp( -alpha_t * L_z_cgs ) );
    print( "  absorbing: tau_sca=%.4e, tau_abs=%.3f, S_th=%.4e" \
           % ( mfp_sca * L_z_cgs, mfp_abs * L_z_cgs, S_th ) );
    print( "  expected I(0) = %.6e" % expected );

    cube, i2d = _run_slab_imaging( \
        n_species, T, L_x, L_z, n_chan, v_lo, v_hi,
        mfp_abs = mfp_abs );
    _check_center_pixel( cube, i2d, expected, "absorbing", tol = 0.30 );


if __name__ == '__main__':
    test_imaging_thin_slab( );
    test_imaging_scattering_slab( );
    test_imaging_absorbing_slab( );
    print( "Imaging tests passed." );
