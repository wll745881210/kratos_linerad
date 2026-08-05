#!/usr/bin/env python3
"""Build synthetic molecular species for analytic testing (Neufeld, etc.).

Note
----
``make_synthetic_2level`` is deprecated.  Use
``TransitionInfo.user_defined(...)`` instead — it builds the same
2-level species from physical transition parameters (A_ul, frequency,
g_u/g_l, E_u) and returns a fully functional ``TransitionInfo`` for the
high-level interface.
"""

import warnings;

from numpy    import array, sqrt, pi, float64; \
from .lamda_format import SpeciesData;

h_cgs   = 6.62607015e-27;      # Planck constant [ erg s ]
c_cgs   = 2.99792458e10;       # speed of light [ cm s^-1 ]
k_B     = 1.380649e-16;        # Boltzmann constant [ erg K^-1 ]
sqrt_pi = 1.77245385091;       # sqrt( pi )


############################################################
# 2-level synthetic species (deprecated)

def make_synthetic_2level( b, nu, a, *, transition_idx = 0, \
                           species_name = 'synthetic' ):
    """Create a synthetic 2-level species.

    .. deprecated::
       Use ``TransitionInfo.user_defined( A_ul = ..., freq_GHz = ... )``
       instead.

    Parameters
    ----------
    b : float
        Doppler b [cm/s].
    nu : float
        Line frequency [Hz].
    a : float
        Voigt damping parameter a = A_ul / ( 4 pi Delta_nu_D ).
    transition_idx : int
        Index of the pumped transition.
    species_name : str

    Returns
    -------
    species : SpeciesData
    transition : Transition
    """
    warnings.warn( \
        'make_synthetic_2level is deprecated; use '
        'TransitionInfo.user_defined( A_ul=..., freq_GHz=... ) instead.',
        DeprecationWarning, stacklevel = 2 );

    if not ( 1e-50 < a < 100.0 ):
        raise ValueError( 'a = %g outside valid range (1e-50, 100)' % a );

    sigma_th   = b / sqrt( 2.0 );
    delta_nu_D = nu * sigma_th / c_cgs;
    A_ul       = a * 4.0 * pi * delta_nu_D;
    nu_GHz     = nu / 1.0e9;
    E_u_K      = h_cgs * nu / k_B;
    E_u_cm     = nu / ( c_cgs * 100.0 );   # cm^-1 (LAMDA convention)
    g_u, g_l   = 3.0, 1.0;

    species = SpeciesData(
        name          = species_name,
        n_levels      = 2,
        n_transitions = 1,
        levels        = array( [ [ 0.0, g_l ], [ E_u_cm, g_u ] ], \
                               dtype = float64 ),
        transitions   = array( [ [ 1, 0, A_ul, nu_GHz ] ], \
                               dtype = float64 ),
    );

    print( '  Synthetic %s: A_ul=%.2e, nu=%.2f GHz, '
           'E_u/K=%.1f, g_u=%.0f, g_l=%.0f'
           % ( species_name, A_ul, nu_GHz, E_u_K, g_u, g_l ) );

    return species, species.transitions_list[ transition_idx ];


############################################################
# N-level synthetic species

def make_synthetic_nlevel( co_levels_raw, b, nu, a, *, transition_idx = 0 ):
    """Create a synthetic N-level species from raw CO-like data.

    parameters_from : dict
        Maps 'b', 'nu', 'a' to the synthetic species.  The embedded CO
        data is used as a template for the level structure; only the
        target transition is modified to match the requested a and nu.
    transition_idx : int
    """
    raise NotImplementedError( \
        'N-level synthetic species not yet implemented' );
