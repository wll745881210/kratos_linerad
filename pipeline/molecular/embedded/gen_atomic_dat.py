#!/usr/bin/env python3
"""Generate the atomic-species LAMDA files: hi.dat, hei.dat, heii.dat.

HI and He II are hydrogenic: the Einstein A coefficients are computed
EXACTLY from the analytic bound-state wavefunctions (no tabulated
numbers), via

    A(nl->n'l') = (4/3) * omega^3 * (e^2 / 4 pi eps0 hbar c^3)
                  * R(n'l', nl)^2 * l_> / (2 l_u + 1)

where R is the radial dipole integral
    R = int_0^inf  R_{n'l'}(r) * r * R_{nl}(r) * r^2 dr
and l_> = max(l, l').  The formula is verified against the textbook
Lyman-alpha rate A(2p->1s) = 6.265e8 s^-1 (asserted below).

He I is NOT hydrogenic: level energies and A values are hard-coded
constants taken from NIST ASD (rounded).  The two resonance lines
(584.33 A, 537.03 A) are cross-verified via the oscillator-strength
relation A = 6.6702e15 * (g_l/g_u) * f / lambda^2[Angstrom].

All wavelengths are VACUUM.  Levels are nl-resolved (2s != 2p) with
fine structure averaged.  Each observable line appears exactly once
(the dominant nl component, e.g. Halpha = 3d->2p) so that frequency /
wavelength selection is unambiguous.  No collision partners (pure
resonant scattering, epsilon = 0).

Run:  python3 gen_atomic_dat.py   (writes .dat files next to this script)
"""

import math
import os

import numpy as np
from scipy.special import eval_genlaguerre


# ---------------------------------------------------------------- #
#  Physical constants (SI / CGS where noted)
# ---------------------------------------------------------------- #

A0 = 5.29177210903e-11        # Bohr radius [m]
HBAR = 1.054571817e-34        # hbar [J s]
C_SI = 2.99792458e8           # c [m/s]
C_CGS = 2.99792458e10         # c [cm/s]
ECHG2_OVER_4PI = 2.307077552e-28   # e^2 / (4 pi eps0) [J m]
RYD_H = 109678.7717           # Rydberg constant for H [cm^-1]
RYD_HEII = 109722.268         # Rydberg constant for He II [cm^-1]
CM1_TO_GHZ = C_CGS / 1.0e9    # 1 cm^-1 = 29.9792458 GHz


# ---------------------------------------------------------------- #
#  Hydrogenic machinery
# ---------------------------------------------------------------- #

def radial_wave( r, n, l, Z ):
    """Normalized hydrogenic radial wavefunction R_nl(r) [m^-3/2].
    Accepts scalar or ndarray r (vectorized)."""
    pref = ( 2.0 * Z / ( n * A0 ) ) ** 1.5 \
           * math.sqrt( math.factorial( n - l - 1 ) / \
                        ( 2.0 * n * math.factorial( n + l ) ) )
    rho = 2.0 * Z * r / ( n * A0 )
    return pref * np.exp( -rho / 2.0 ) * rho ** l \
           * eval_genlaguerre( n - l - 1, 2 * l + 1, rho )


#  Fixed Gauss-Legendre nodes shared by all integrals.  The dipole
#  integrands oscillate (generalized-Laguerre nodes), which defeats
#  adaptive quadrature's premature-convergence heuristics; a dense
#  fixed grid resolves every lobe deterministically.
_GL_X, _GL_W = np.polynomial.legendre.leggauss( 4096 )


def radial_integral( n, l, np_, lp, Z ):
    """R = int R_{np'lp'} r R_{nl} r^2 dr  [m] (Gauss-Legendre)."""
    r_max = ( n + np_ ) ** 2 * A0 / Z * 20.0
    r = 0.5 * r_max * ( _GL_X + 1.0 )
    w = 0.5 * r_max * _GL_W
    f = radial_wave( r, n, l, Z ) * r \
        * radial_wave( r, np_, lp, Z ) * r ** 2
    return float( np.dot( w, f ) )


def einstein_A( n_u, l_u, n_l, l_l, Z, ryd ):
    """Spontaneous emission rate A(nl -> n'l') [s^-1] (hydrogenic)."""
    dE_cm = ryd * Z ** 2 * ( 1.0 / n_l ** 2 - 1.0 / n_u ** 2 )
    nu = dE_cm * C_CGS                    # [Hz]
    omega = 2.0 * math.pi * nu            # [rad/s]
    R = radial_integral( n_u, l_u, n_l, l_l, Z )
    l_gt = max( l_u, l_l )
    return ( 4.0 / 3.0 ) * omega ** 3 * ( ECHG2_OVER_4PI ) \
           / ( HBAR * C_SI ** 3 ) * R ** 2 * l_gt / ( 2 * l_u + 1 )


def wave_check( ):
    """Assert normalization of the radial wavefunctions used."""
    for ( n, l, Z ) in [ ( 1, 0, 1 ), ( 2, 1, 1 ), ( 3, 2, 1 ),
                         ( 4, 1, 1 ), ( 5, 2, 1 ), ( 2, 1, 2 ),
                         ( 3, 2, 2 ) ]:
        r_max = n ** 2 * A0 / Z * 30.0
        r = 0.5 * r_max * ( _GL_X + 1.0 )
        w = 0.5 * r_max * _GL_W
        norm = float( np.dot( w, radial_wave( r, n, l, Z ) ** 2
                              * r ** 2 ) )
        assert abs( norm - 1.0 ) < 1e-8, \
            "R_%d%d(Z=%d) not normalized: %.10f" % ( n, l, Z, norm )
    return


# ---------------------------------------------------------------- #
#  Level / transition definitions
# ---------------------------------------------------------------- #

#  (n, l, label, g).  Energies computed from the Rydberg formula.
HI_LEVELS = [
    ( 1, 0, '1s',  2 ),
    ( 2, 0, '2s',  2 ),
    ( 2, 1, '2p',  6 ),
    ( 3, 0, '3s',  2 ),
    ( 3, 1, '3p',  6 ),
    ( 3, 2, '3d', 10 ),
    ( 4, 0, '4s',  2 ),
    ( 4, 1, '4p',  6 ),
    ( 4, 2, '4d', 10 ),
    ( 5, 1, '5p',  6 ),
    ( 5, 2, '5d', 10 ),
]

#  (upper label, lower label, line name).  One entry per observable
#  line -- the dominant nl component for the Balmer blends.
HI_LINES = [
    ( '2p', '1s', 'Lya'  ),
    ( '3p', '1s', 'Lyb'  ),
    ( '4p', '1s', 'Lyg'  ),
    ( '3d', '2p', 'Ha'   ),
    ( '4d', '2p', 'Hb'   ),
    ( '5d', '2p', 'Hg'   ),
]

HEII_LEVELS = HI_LEVELS
HEII_LINES = HI_LINES


#  He I: NOT hydrogenic.  NIST ASD energies [cm^-1] (fine-structure
#  averaged) and statistical weights g (summed over J).
HEI_LEVELS = [
    ( '1s2',     0.0,        1 ),   # 1s^2 1S0
    ( '2s3S',    159856.08,  3 ),   # 1s2s 3S1
    ( '2s1S',    166277.54,  1 ),   # 1s2s 1S0
    ( '2p3P',    169087.00,  9 ),   # 1s2p 3P
    ( '2p1P',    171135.00,  3 ),   # 1s2p 1P1
    ( '3p3P',    185570.2,   9 ),   # 1s3p 3P
    ( '3p1P',    186209.43,  3 ),   # 1s3p 1P1
]

#  (upper, lower, A [s^-1], line name).  A values from NIST ASD
#  (rounded); the 584 / 537 resonance rates are cross-verified via
#  the f-value relation in main( ).
HEI_LINES = [
    ( '2p1P', '1s2',  1.798e9, 'HeI 584.33'  ),
    ( '3p1P', '1s2',  5.65e8,  'HeI 537.03'  ),
    ( '2p3P', '2s3S', 1.02e7,  'HeI 10832'   ),
    ( '3p3P', '2s3S', 9.5e6,   'HeI 3889'    ),
]


# ---------------------------------------------------------------- #
#  .dat writers
# ---------------------------------------------------------------- #

def write_dat( path, name, levels, lines, note ):
    """levels: list of (energy_cm, g); lines: (iup, ilow, A, GHz)."""
    with open( path, 'w' ) as f:
        f.write( note )
        f.write( '!MOLECULE\n%s\n' % name )
        f.write( '!NUMBER OF ENERGY LEVELS\n%d\n' % len( levels ) )
        f.write( '!LEVEL + ENERGIES(cm^-1) + WEIGHT\n' )
        for i, ( e, g ) in enumerate( levels ):
            f.write( '%d  %12.4f  %d\n' % ( i + 1, e, g ) )
        f.write( '!NUMBER OF RADIATIVE TRANSITIONS\n%d\n' \
                 % len( lines ) )
        f.write( '!TRANSITION + UPPER + LOWER + EINSTEINA(s^-1)' \
                 ' + FREQ(GHz)\n' )
        for k, ( iu, il, a, nu ) in enumerate( lines ):
            f.write( '%d  %d  %d  %.4e  %.4f\n' \
                     % ( k + 1, iu + 1, il + 1, a, nu ) )
        f.write( '!NUMBER OF COLL PARTNERS\n0\n' )
    return


def level_of( label, levels ):
    """(n, l) of a level label in a (n, l, label, g) level list."""
    return next( ( x[ 0 ], x[ 1 ] ) for x in levels if x[ 2 ] == label )


def build_hydrogenic( name, levels, lines, Z, ryd ):
    lev_out = [ ]
    idx = { }
    for ( n, l, lab, g ) in levels:
        e_cm = ryd * Z ** 2 * ( 1.0 - 1.0 / n ** 2 )
        idx[ lab ] = len( lev_out )
        lev_out.append( ( e_cm, g ) )
    lin_out = [ ]
    for ( up, low, line_name ) in lines:
        ( nu_, lu, _, _ ) = next( x for x in levels if x[ 2 ] == up )
        ( nl_, ll, _, _ ) = next( x for x in levels if x[ 2 ] == low )
        a = einstein_A( nu_, lu, nl_, ll, Z, ryd )
        dE = ryd * Z ** 2 * ( 1.0 / nl_ ** 2 - 1.0 / nu_ ** 2 )
        ghz = dE * CM1_TO_GHZ
        lin_out.append( ( idx[ up ], idx[ low ], a, ghz ) )
        lam = 1.0e8 / dE
        print( '  %-8s %s->%s  lambda=%9.3f A  A=%.4e s^-1' \
               % ( line_name, up, low, lam, a ) )
    return lev_out, lin_out


def build_hei( ):
    idx = { lab: i for i, ( lab, _, _ ) in enumerate( HEI_LEVELS ) }
    lev_out = [ ( e, g ) for ( _, e, g ) in HEI_LEVELS ]
    lin_out = [ ]
    for ( up, low, a, line_name ) in HEI_LINES:
        eu = dict( ( l, e ) for ( l, e, _ ) in HEI_LEVELS )[ up ]
        el = dict( ( l, e ) for ( l, e, _ ) in HEI_LEVELS )[ low ]
        dE = eu - el
        lin_out.append( ( idx[ up ], idx[ low ], a, dE * CM1_TO_GHZ ) )
        print( '  %-12s %s->%s  lambda=%9.3f A  A=%.4e s^-1' \
               % ( line_name, up, low, 1.0e8 / dE, a ) )
    return lev_out, lin_out


# ---------------------------------------------------------------- #

def main( ):
    here = os.path.dirname( os.path.realpath( __file__ ) )
    wave_check( );

    #  --- Anchor verification (hydrogenic formula) ---
    #  Lyman/Balmer A from literature f-values via
    #  A = 7.4091e-22 * nu^2 * f * (g_l/g_u).  The exact nonrelativistic
    #  values are reproduced to <0.5% (2p, 3p, 3d, 4d lines); the Halpha
    #  literature number (6.465e7, NIST fine-structure component) sits
    #  ~0.9% below the exact nl-summed value.
    a_ref = { 'Lya': 6.265e8, 'Lyb': 1.672e8, 'Lyg': 6.810e7,
              'Ha':  6.465e7, 'Hb':  2.065e7, 'Hg':  9.460e6 }
    tol = { 'Lya': 5e-3, 'Lyb': 1e-2, 'Lyg': 1e-2,
            'Ha':  1.5e-2, 'Hb':  1.5e-2, 'Hg':  1.5e-2 }
    print( 'Hydrogenic anchors (HI):' )
    for ( u, l_, name ) in HI_LINES:
        n_u, l_u = level_of( u, HI_LEVELS )
        n_l, l_l = level_of( l_, HI_LEVELS )
        a = einstein_A( n_u, l_u, n_l, l_l, 1, RYD_H )
        assert abs( a / a_ref[ name ] - 1.0 ) < tol[ name ], \
            '%s anchor failed: %.4e vs %.4e' % ( name, a, a_ref[ name ] )
        print( '  %-4s A=%.4e s^-1 (ref %.3e, off %.2f%%)'
               % ( name, a, a_ref[ name ],
                   100.0 * ( a / a_ref[ name ] - 1.0 ) ) )

    #  --- He I resonance cross-check via f-values ---
    #  A = 6.6702e15 (g_l/g_u) f / lambda^2[Angstrom]
    a584 = 6.6702e15 * ( 1.0 / 3.0 ) * 0.2762 / 584.334 ** 2
    a537 = 6.6702e15 * ( 1.0 / 3.0 ) * 0.0733 / 536.98 ** 2
    assert abs( a584 / 1.798e9 - 1.0 ) < 1e-2, a584
    assert abs( a537 / 5.65e8 - 1.0 ) < 1e-2, a537
    print( 'HeI f-value cross-check OK: 584 -> %.3e, 537 -> %.3e'
           % ( a584, a537 ) )

    print( 'HI:' )
    lev, lin = build_hydrogenic( 'HI', HI_LEVELS, HI_LINES, 1, RYD_H )
    write_dat( os.path.join( here, 'hi.dat' ), 'HI', lev, lin,
        '! Atomic hydrogen (nl-resolved levels, vacuum wavelengths).\n'
        '! Energies: Rydberg R_H = 109678.7717 cm^-1 (fine structure\n'
        '! averaged).  A coefficients computed exactly from hydrogenic\n'
        '! wavefunctions (gen_atomic_dat.py).  Each observable line\n'
        '! appears once (Balmer = dominant d->p component).\n'
        '! Collision rates: none (pure resonant scattering).\n' )

    print( 'HeII:' )
    lev, lin = build_hydrogenic( 'HeII', HEII_LEVELS, HEII_LINES,
                                 2, RYD_HEII )
    write_dat( os.path.join( here, 'heii.dat' ), 'HeII', lev, lin,
        '! He+ (hydrogenic, Z=2, nl-resolved, vacuum wavelengths).\n'
        '! Energies: 4 R_HeII = 438889.07 cm^-1 (fine structure\n'
        '! averaged).  A coefficients computed exactly from hydrogenic\n'
        '! wavefunctions with Z=2 (gen_atomic_dat.py).\n'
        '! Collision rates: none (pure resonant scattering).\n' )

    print( 'HeI:' )
    lev, lin = build_hei( )
    write_dat( os.path.join( here, 'hei.dat' ), 'HeI', lev, lin,
        '! Neutral helium (LS terms, fine structure averaged,\n'
        '! vacuum wavelengths).  Level energies and A coefficients\n'
        '! from NIST ASD (rounded); see gen_atomic_dat.py.\n'
        '! Collision rates: none (pure resonant scattering).\n' )

    print( 'Wrote hi.dat, heii.dat, hei.dat in %s' % here )
    return


if __name__ == '__main__':
    main( );
