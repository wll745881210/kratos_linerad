"""Quantitative tests for emission-photon normalization.

Audit finding: emission photon proper weights must be photon-number per
unit time, and their sum over all packets from one cell must equal the
cell volume times the photon-number emissivity
n_u * A_ul (photons cm^-3 s^-1, integrated over 4*pi).

The proposed test (mfp_i_abs = 0, sum of all proper weights vs the
volume integral of n_u*A_ul) is implemented here.  It is pure Python -
Kratos is not invoked.
"""

import os;
import sys;
import tempfile;

from numpy import zeros, ones, full, float64, sum as np_sum;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

from core.pipeline import make_cartesian_mesh;  # noqa: E402
from molecular.transition_info import TransitionInfo;  # noqa: E402


AU = 1.49598e13;   # cm


def _make_species( ):
    """CO J=1->0: A_ul = 7.203e-8 s^-1, nu = 115.271 GHz, with H2 collider."""
    return TransitionInfo.user_defined( \
        A_ul = 7.203e-8, freq_GHz = 115.271, \
        species_name = 'CO',
        collision_rates = { 'H2': 1e-10 } ).species_data;


def _make_fields( mesh, n_species, T ):
    shape = ( int( mesh[ 'n_cell' ][ 2 ] ), \
              int( mesh[ 'n_cell' ][ 1 ] ), \
              int( mesh[ 'n_cell' ][ 0 ] ) );
    return { \
        'b_sca'       : full( shape, 3.99e3, dtype = float64 ), \
        'temp'        : full( shape, T,    dtype = float64 ), \
        'vel_0'       : zeros( shape, dtype = float64 ), \
        'vel_1'       : zeros( shape, dtype = float64 ), \
        'vel_2'       : zeros( shape, dtype = float64 ), \
        'mfp_i_sca_0' : full( shape, 1e-9, dtype = float64 ), \
        'mfp_i_abs_0' : zeros( shape, dtype = float64 ) };


def test_emission_proper_sum_equals_volume_times_emissivity( ):
    """Sum of emission photon propers = n_u * A_ul * V_cgs (per cell).

    With unit_l0 = AU and a uniform slab, every cell has the same
    emissivity, so the total sum of propers should equal
    n_cells * n_u * A_ul * V_cgs.
    """
    n_cell = ( 8, 4, 4 );
    mesh = make_cartesian_mesh( n_cell, ( -4, -1, -1 ), ( 4, 1, 1 ) );
    species = _make_species( );
    n_species = 1e4;
    T = 20.0;
    fields = _make_fields( mesh, n_species, T );
    unit_l0 = AU;

    # LTE populations at T=20 K.
    from numpy import asarray, broadcast_to;
    shape3d = ( int( n_cell[ 2 ] ), int( n_cell[ 1 ] ), \
                int( n_cell[ 0 ] ) );
    n_arr = broadcast_to( asarray( n_species, dtype = float64 ), \
                          shape3d ).copy( );
    pops = species.initial_populations( n_arr, T = fields[ "temp" ], colliders = { "H2": 1e6 } );

    # Photon-number emissivity per sr = n_u * A_ul / (4*pi).
    em = species.compute_emissivity( pops, 0, fields[ 'temp' ] );
    n_u = asarray( pops.get( 'n1', ones( 1 ) ), dtype = float64 );
    A_ul = float( species.transitions[ 0, 2 ] );

    # Expected total photon production rate = n_u * A_ul * V_cgs (per
    # cell, integrated over 4*pi).  Sum over all cells.
    dx = mesh[ 'dx' ];
    V_cgs = float( dx[ 0 ] * dx[ 1 ] * dx[ 2 ] ) * ( unit_l0 ** 3 );
    n_cells = int( mesh[ 'n_tot' ] );
    expected_rate = float( np_sum( n_u ) ) * A_ul * V_cgs;

    # Generate emission photons with a large budget so every active cell
    # gets many packets (reduces quantization noise).
    ph = species.generate_emission_photons( \
        pops, 0, fields[ 'temp' ], mesh, \
        n_per_cell_max = 200, unit_l0 = unit_l0,
        vel_fields = fields );

    total_proper = float( ph[ :, 6 ].sum( ) );

    # The sum of propers must match the total photon production rate
    # to within the per-cell packet quantization (each cell gets an
    # integer number of packets; weight = rate/n_ph, so sum = rate
    # exactly regardless of n_ph).
    assert abs( total_proper - expected_rate ) / expected_rate < 1e-10, \
        "sum of propers (%.6e) != n_u*A_ul*V_cgs (%.6e), " \
        "ratio = %.6e" % ( total_proper, expected_rate, \
                           total_proper / expected_rate );
    print( "OK: sum of propers = %.6e, expected = %.6e" \
           % ( total_proper, expected_rate ) );


def test_emission_proper_no_h_nu_factor( ):
    """Ensure emissivity is photon-number, not energy.

    The energy emissivity would be n_u*A_ul*h*nu/(4*pi); the photon
    emissivity is n_u*A_ul/(4*pi).  Check the ratio is ~1 (not ~h*nu).
    """
    species = _make_species( );
    from numpy import asarray, broadcast_to, full;
    n_cell = ( 2, 2, 2 );
    n_arr = full( ( 2, 2, 2 ), 1e4, dtype = float64 );
    T = full( ( 2, 2, 2 ), 20.0, dtype = float64 );
    pops = species.initial_populations( n_arr, T = T, colliders = { "H2": 1e6 } );
    em = species.compute_emissivity( pops, 0, T );
    n_u = float( asarray( pops[ 'n1' ] ).ravel( )[ 0 ] );
    A_ul = float( species.transitions[ 0, 2 ] );
    expected_photon = n_u * A_ul / ( 4.0 * 3.14159265358979 );
    h_nu = 6.62607015e-27 * 115.271e9;
    expected_energy = expected_photon * h_nu;
    actual = float( em.ravel( )[ 0 ] );
    assert abs( actual - expected_photon ) / expected_photon < 1e-10, \
        "emissivity is energy-based (h*nu = %.3e), not photon-based" \
        % h_nu;
    assert abs( actual - expected_energy ) / expected_energy > 0.99, \
        "emissivity matches energy value -- should be photon-number";
    print( "OK: emissivity = %.6e (photon-number, not energy %.6e)" \
           % ( actual, expected_energy ) );


def test_emission_vel_includes_bulk_doppler( ):
    """Emission photon vel = thermal_draw - v_bulk . dir.

    With a uniform bulk velocity v_x and T -> 0 (negligible thermal),
    the stored vel should be approximately -v_x * dir_x for every
    photon, so that dv = vel + vel_obs = 0 in the emitting cell.
    """
    species = _make_species( );
    from numpy import asarray, broadcast_to, full, zeros;
    n_cell = ( 4, 2, 2 );
    mesh = make_cartesian_mesh( n_cell, ( -2, -1, -1 ), ( 2, 1, 1 ) );
    unit_l0 = AU;
    v_bulk = 5e4;   # cm/s
    shape = ( 2, 2, 4 );
    fields = { \
        'temp'  : full( shape, 0.1, dtype = float64 ), \
        'vel_0' : full( shape, v_bulk, dtype = float64 ), \
        'vel_1' : zeros( shape, dtype = float64 ), \
        'vel_2' : zeros( shape, dtype = float64 ) };
    n_arr = full( shape, 1e4, dtype = float64 );
    pops = species.initial_populations( n_arr, T = fields[ "temp" ], colliders = { "H2": 1e6 } );

    ph = species.generate_emission_photons( \
        pops, 0, fields[ 'temp' ], mesh, \
        n_per_cell_max = 50, unit_l0 = unit_l0,
        vel_fields = fields );

    # vel = thermal_draw - v_bulk*dir_x.  With T=0.1K the thermal draw
    # is tiny (b ~ 250 cm/s, sigma ~ 180 cm/s) compared to v_bulk=5e4.
    # So vel ~ -v_bulk * dir_x to within the thermal scatter.
    dir_x = ph[ :, 3 ];
    vel = ph[ :, 7 ];
    expected = -v_bulk * dir_x;
    residual = vel - expected;
    # residual is the thermal draw, sigma ~ 180 cm/s; check it's small
    # relative to the bulk term (allow up to 10 sigma for 200 photons).
    assert abs( residual ).max( ) < 3000.0, \
        "vel does not track -v_bulk*dir_x (max residual %.1f cm/s)" \
        % abs( residual ).max( );
    print( "OK: emission vel includes bulk Doppler "
           "(max thermal residual %.1f cm/s)" \
           % abs( residual ).max( ) );


if __name__ == '__main__':
    test_emission_proper_no_h_nu_factor( );
    test_emission_proper_sum_equals_volume_times_emissivity( );
    test_emission_vel_includes_bulk_doppler( );
    print( "All emission-weight tests passed." );
