"""Quantitative imaging test: uniform slab (thin + thick).

The slab has a known emissivity and opacity, so the emergent
intensity along a face-on ray has the closed-form solution

    I(v) = S * ( 1 - exp( -tau(v) ) )

where
    S   = emiss / mfp_i_sca_0            (source function)
    tau(v) = mfp_i_sca_0 * phi(v) * L    (optical depth)
    phi(v) = exp( -(v/b)^2 )             (unnormalised Gaussian)

At line centre (v = 0):  I(0) = S * ( 1 - exp(-tau0) ),
tau0 = mfp_i_sca_0 * L.

Two regimes are tested:
  * optically thin  (tau0 ~ 0.01):  I ~ S * tau0 * phi  =  emiss * phi * L
  * optically thick (tau0 ~ 5):     I -> S  (saturated core)

This is a Kratos-integration test: it invokes the real Kratos binary.
Skip if KRATOS_ROOT is not set or the binary is absent.
"""

import os;
import sys;
from numpy import sqrt, exp, pi;

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
        import pytest;
        pytest.skip( "Kratos binary not found at %s" % KRATOS_BIN );


def _slab_analytic( n_species, T, L_z_au, mol_mass = 28.0,
                    A_ul = 7.203e-8, freq_GHz = 115.271,
                    g_u = 3.0, g_l = 1.0 ):
    """Return ( S_cgs, tau0, b_cgs, n_u, n_l, sigma0 ) for a uniform
    CO J=1->0 slab in LTE."""
    nu = freq_GHz * 1e9;
    dE_K = h_cgs * nu / k_B;
    n_ratio = ( g_u / g_l ) * exp( -dE_K / T );
    n_u = n_species * n_ratio / ( 1.0 + n_ratio );
    n_l = n_species / ( 1.0 + n_ratio );

    b_cgs = sqrt( 2.0 * k_B * T / ( mol_mass * m_p ) );

    # Line-centre cross section (unnormalised profile, peak = 1):
    #   sigma0 = (g_u/g_l) * A_ul * c^3 / (8 pi^(3/2) nu^3 b)
    sigma0 = ( g_u / g_l ) * A_ul * c_cgs ** 3 \
             / ( 8.0 * pi ** 1.5 * nu ** 3 * b_cgs );

    mfp_cgs = n_l * sigma0;                 # 1/cm  (inverse mfp)
    emiss_cgs = n_u * A_ul / ( 4.0 * pi );  # photons cm^-3 s^-1 sr^-1
    S_cgs = emiss_cgs / mfp_cgs;            # photons cm^-2 s^-1 sr^-1

    L_z_cgs = L_z_au * AU;
    tau0 = mfp_cgs * L_z_cgs;

    return dict( S_cgs = S_cgs, tau0 = tau0, b_cgs = b_cgs,
                 n_u = n_u, n_l = n_l, sigma0 = sigma0,
                 mfp_cgs = mfp_cgs, emiss_cgs = emiss_cgs,
                 L_z_cgs = L_z_cgs );


def _run_slab_imaging( n_species, T, L_x_au, L_z_au, n_chan, v_lo, v_hi ):
    """Run a face-on imaging simulation of a uniform slab and return
    (cube_cgs, i2d, n_chan)."""
    import importlib.util;
    spec = importlib.util.spec_from_file_location( \
        'line_rt', os.path.join( os.path.dirname( os.path.dirname( \
            os.path.abspath( __file__ ) ) ), 'line_rt.py' ) );
    lr = importlib.util.module_from_spec( spec );
    spec.loader.exec_module( lr );
    from molecular.transition_info import TransitionInfo;

    ti = TransitionInfo.user_defined( \
        A_ul = 7.203e-8, freq_GHz = 115.271, species_name = 'CO',
        g_u = 3.0, g_l = 1.0 );   # CO J=1->0: g_u=3, g_l=1

    rt = lr.LineRt( \
        kratos_root = KRATOS_ROOT,
        n_cell = ( 8, 8, 4 ),
        x_min = ( -L_x_au / 2, -L_x_au / 2, -L_z_au / 2 ),
        x_max = (  L_x_au / 2,  L_x_au / 2,  L_z_au / 2 ),
        unit_l0 = AU,
        transition_info = ti,
        n_species = n_species,
        temperature = T,
        mfp_i_abs_0 = 1e-20,      # negligible absorption
        ph_mode = 0,
        n_step = 2000,
        n_scat = 1000,
        n_emission_max = 4,
        proper_scale = 1e-20,
        imaging = { \
            'dir_cam'    : ( 0.0, 0.0 ),   # face-on along +z
            'n_chan'     : n_chan,
            'v_chan'     : ( v_lo, v_hi ) },
        visualize = False,
        keep_intermediate = False );

    out = rt.run( n_cycles = 1 );
    assert 'image' in out, "no image in output";
    img = out[ 'image' ];
    assert 'cube_cgs' in img, "no cube_cgs in image";
    return img[ 'cube_cgs' ], img[ 'i2d' ], n_chan;


def _check_slab( cube, i2d, n_chan, analytic, v_lo, v_hi,
                 label, tol = 0.30 ):
    """Compare the centre-pixel spectrum to I(v) = S*(1-exp(-tau0*phi))."""
    S = analytic[ 'S_cgs' ];
    tau0 = analytic[ 'tau0' ];
    b = analytic[ 'b_cgs' ];
    dv = ( v_hi - v_lo ) / ( n_chan - 1 );

    # Find the centre pixel (face-on, uniform -> all pixels equal,
    # but pick the centre for safety).
    center_pix = None;
    for p in range( i2d.shape[ 0 ] ):
        if i2d[ p, 0 ] == 4 and i2d[ p, 1 ] == 4:
            center_pix = p; break;
    assert center_pix is not None, "no centre pixel found";
    spec_pix = cube[ center_pix, : ];

    max_rel_err = 0.0;
    worst_k = -1;
    for k in range( n_chan ):
        v_k = v_lo + k * dv;
        phi_k = exp( -( v_k / b ) ** 2 );
        tau_k = tau0 * phi_k;
        expected = S * ( 1.0 - exp( -tau_k ) );
        actual = float( spec_pix[ k ] );
        if expected > 1e-30:
            rel = abs( actual - expected ) / expected;
            if rel > max_rel_err:
                max_rel_err = rel; worst_k = k;

    k0 = n_chan // 2;
    print( "  [%s] tau0=%.3f, S=%.3e, I(0)=%.3e (expected %.3e)" \
           % ( label, tau0, S, float( spec_pix[ k0 ] ),
               S * ( 1 - exp( -tau0 ) ) ) );
    assert max_rel_err < tol, \
        "[%s] imaging cube deviates from analytic S*(1-exp(-tau*phi)) " \
        "by %.1f%% at channel %d" \
        % ( label, max_rel_err * 100, worst_k );
    print( "  [%s] PASS: max relative error %.1f%% (channel %d)" \
           % ( label, max_rel_err * 100, worst_k ) );


def test_imaging_thin_slab( ):
    """Optically thin slab: I ~ emiss * phi * L."""
    _run_or_skip( );
    n_species = 1e-4;   # very thin
    T = 20.0;
    L_x = 2.0;  L_z = 0.5;   # AU
    n_chan = 32;  v_lo = -2e5;  v_hi = 2e5;

    analytic = _slab_analytic( n_species, T, L_z );
    print( "  thin slab: tau0 = %.4e" % analytic[ 'tau0' ] );

    cube, i2d, nch = _run_slab_imaging( \
        n_species, T, L_x, L_z, n_chan, v_lo, v_hi );
    _check_slab( cube, i2d, nch, analytic, v_lo, v_hi, "thin" );


def test_imaging_thick_slab( ):
    """Optically thick slab: I -> S (line-core saturation)."""
    _run_or_skip( );
    # tau0 ~ 5: n_l * sigma0 * L = 5
    # n_l = n_species / (1 + n_ratio), n_ratio = 3*exp(-5.53/20) = 2.28
    # n_l = 0.305 * n_species
    # sigma0 = 2.62e-15 cm^2, L = 0.5 AU = 7.48e12 cm
    # n_species = 5 / (0.305 * 2.62e-15 * 7.48e12) ~ 836
    n_species = 836.0;
    T = 20.0;
    L_x = 2.0;  L_z = 0.5;   # AU
    n_chan = 32;  v_lo = -2e5;  v_hi = 2e5;

    analytic = _slab_analytic( n_species, T, L_z );
    print( "  thick slab: tau0 = %.3f" % analytic[ 'tau0' ] );
    assert analytic[ 'tau0' ] > 3.0, "test requires tau0 > 3";

    cube, i2d, nch = _run_slab_imaging( \
        n_species, T, L_x, L_z, n_chan, v_lo, v_hi );
    _check_slab( cube, i2d, nch, analytic, v_lo, v_hi, "thick" );


if __name__ == '__main__':
    test_imaging_thin_slab( );
    test_imaging_thick_slab( );
    print( "Imaging slab tests passed." );
