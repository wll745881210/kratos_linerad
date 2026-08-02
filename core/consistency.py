"""Consistency checks for LineRt.run() before launching Kratos.

Implements the two-group rule:
  Group 1: species + n_species + temperature (complete if all present)
  Group 2: b_sca + mfp_i_sca_0 (complete if both present)

Logic:
  - If Group 1 is complete, use Group 1 (species takes precedence).
  - If Group 1 is incomplete and Group 2 is complete, use Group 2.
  - If neither group is complete, raise an error.
  - If both are complete, use Group 1.

Reports all problems at once (collected, not fail-fast).
"""

from numpy import ndarray, mean, sqrt


h_cgs    = 6.62607015e-27;    # Planck constant [ erg s ]
c_cgs    = 2.99792458e10;     # speed of light [ cm / s ]
k_B      = 1.380649e-16;      # Boltzmann constant [ erg / K ]
mp       = 1.67262192e-24;    # proton mass [ g ]
sqrt_pi  = 1.77245385091;     # sqrt( pi )


class ConsistencyError( Exception ):
    """Raised when required parameters are missing or inconsistent."""
    pass;


def _is_callable( x ):
    return callable( x ) and not isinstance( x, ( int, float, ndarray ) );


def _fmt_field( value ):
    if _is_callable( value ):
        return "<callable %s>" % \
            ( value.__name__ if hasattr( value, '__name__' ) else 'lambda' );
    if isinstance( value, ndarray ):
        return "ndarray shape=%s mean=%.2e" % ( value.shape, mean( value ) );
    return repr( value );


def check_consistency( *, species = None, transition_idx = 0, \
                       n_species = None, temperature = None, \
                       b_sca = None, mfp_i_sca_0 = None, \
                       sources = None, mol_mass = 28.0, \
                       unit_l0 = 1.49598e13, unit_t0 = 1.0 ):
    """Run full consistency check, print report, raise on failure.

    Parameters
    ----------
    species : SpeciesData or None
    transition_idx : int
    n_species : float | callable or None
        Number density [cm⁻³]. If callable, receives (n_tot, 3) CGS coords.
    temperature : float | callable or None (K)
        If callable, receives (n_tot, 3) CGS coords.
    b_sca : float | callable or None
        Doppler b [cm/s]. If callable, receives (n_tot, 3) CGS coords.
    mfp_i_sca_0 : float | callable or None
        Inverse scattering MFP [cm⁻¹]. If callable, receives
        (n_tot, 3) CGS coords.
    sources : list[dict] or None
    mol_mass : float (g/mol)
    unit_l0, unit_t0 : float

    Returns
    -------
    dict
        'group': 1 or 2
        'b_sca_val': float (CGS value, resolved)
        'cross_section': float or None
    """
    print( "=== Consistency check ===" );

    problems = [ ];
    info = { };
    g1_ok = False;
    g2_ok = False;

    ############################################################
    # Group 1: species-based
    g1_species   = species is not None
    g1_n_species = n_species is not None
    g1_temp      = temperature is not None

    if g1_species:
        print( "  species  : %s " % species.name + \
               "(%d levels, %d transitions)" % \
               ( species.n_levels, species.n_transitions ) );
        if g1_n_species:
            print( "  n_species: %s cm⁻³" % _fmt_field( n_species ) );
        else:
            print( "  n_species: ✗ NOT PROVIDED" );
            problems.append( "n_species is required when species is " \
                             "specified" );
        if g1_temp:
            print( "  temperature: %s K" % temperature );
        else:
            print( "  temperature: ✗ NOT PROVIDED" );
            problems.append( "temperature is required when species is " \
                             "specified" );

        #  b_sca is redundant in Group 1: it is derived from temperature
        #  and molecular mass.  Reject it to avoid silent inconsistency.
        if g1_temp and b_sca is not None:
            print( "  b_sca    : %s cm/s  ✗ REDUNDANT" \
                   % _fmt_field( b_sca ) );
            problems.append( \
                "b_sca is redundant when species + temperature are " \
                "given (b_sca is derived from T and mol_mass). " \
                "Remove b_sca to use Group 1." );

        if g1_n_species and g1_temp:
            g1_ok = True;

            if species.n_transitions > 0:
                t_idx = max( 0, min( transition_idx, \
                                     species.n_transitions - 1 ) );
                upper = int( species.transitions[ t_idx, 0 ] );
                lower = int( species.transitions[ t_idx, 1 ] );
                A_ul = float( species.transitions[ t_idx, 2 ] );
                nu_GHz = float( species.transitions[ t_idx, 3 ] );
                nu = nu_GHz * 1e9;
                g_u = species.get_level_weight( upper );
                g_l = species.get_level_weight( lower );
                E_u_K = float( species.levels[ upper, 0 ] );
                E_l_K = float( species.levels[ lower, 0 ] );
                lam_um = 299792.458 / nu_GHz if nu_GHz > 0 else float( 'inf' );

                print( "  Transition #%d: J=%d->%d, " \
                       "E_u=%.1f K, E_l=%.1f K, g_u=%.0f, g_l=%.0f, " \
                       "A_ul=%.2e s⁻¹, ν=%.3f GHz, λ=%.1f µm" % \
                       ( t_idx, upper, lower, E_u_K, E_l_K, g_u, g_l, \
                         A_ul, nu_GHz, lam_um ) );
                if _is_callable( temperature ):
                    b_val = None;    # cannot evaluate without mesh coords
                    print( "  σ₀ = (b_sca to be resolved from callable " \
                           "at runtime)" );
                else:
                    b_val = _compute_b( float( temperature ), mol_mass );
                    sigma = species.cross_section( t_idx, b_val );
                    info[ 'b_sca_val' ] = b_val;
                    info[ 'cross_section' ] = sigma;
                    print( "  σ₀ (b=%.1e cm/s) = %.2e cm²" % \
                           ( b_val, sigma ) );
            else:
                info[ 'cross_section' ] = None;
    else:
        print( "  species  : (not provided)" );

    ############################################################
    # Group 2: explicit opacity
    g2_b   = b_sca is not None
    g2_mfp = mfp_i_sca_0 is not None
    if g2_b:
        print( "  b_sca    : %s cm/s" % _fmt_field( b_sca ) );
    else:
        print( "  b_sca    : (not provided)" );
    if g2_mfp:
        print( "  mfp_i_sca_0: %s cm⁻¹" % _fmt_field( mfp_i_sca_0 ) );
    else:
        print( "  mfp_i_sca_0: (not provided)" );
    g2_ok = g2_b and g2_mfp;

    ############################################################
    # Determine effective group
    if g1_ok:
        info[ 'group' ] = 1;
        print( "  ── Using Group 1 (species-based) ──" );
    elif g2_ok:
        info[ 'group' ] = 2;
        print( "  ── Using Group 2 (explicit opacity) ──" );
        info[ 'b_sca_val' ] = b_sca if not _is_callable( b_sca ) else None;
        info[ 'cross_section' ] = None;
    else:
        if not g1_ok and not g2_ok:
            problems.append( \
                "Neither group is complete. "
                "Provide either (species + n_species + temperature) "
                "or (b_sca + mfp_i_sca_0)." );

    ############################################################
    # Sources
    if sources:
        print( "  sources  : %d source(s)" % len( sources ) );
        for i, src in enumerate( sources ):
            t = src.get( 'type', '?' );
            n_ph = src.get( 'n_photon', '?' );
            flux = src.get( 'flux', None );
            lum = src.get( 'luminosity', None );
            units = src.get( 'units', 'photon' );
            if flux is not None:
                unit_str = 'erg cm⁻² s⁻¹' if units == 'energy' else \
                           'photons cm⁻² s⁻¹';
                v_str = "%s %s" % ( flux, unit_str );
            elif lum is not None:
                unit_str = 'erg/s' if units == 'energy' else 'photons/s';
                v_str = "%s %s" % ( lum, unit_str );
            else:
                v_str = "(no luminosity/flux)";
            wl = src.get( 'wavelength', None );
            if units == 'energy' and wl is not None:
                v_str += " (λ=%s cm)" % wl;
            print( "    [%d] %s, %s photons, %s" % ( i, t, n_ph, v_str ) );
    else:
        print( "  sources  : (none)" );
        problems.append( "No sources added. Use add_source() before run()." );

    ############################################################
    # Report
    if problems:
        print( "\n*** CONSISTENCY ERROR (%d problems) ***" % len( problems ) );
        for p in problems:
            print( "  ✗  %s" % p );
        raise ConsistencyError( "\n".join( problems ) );

    print( "=== All checks passed ===\n" );
    return info;


def _compute_b( temperature, mol_mass = 28.0 ):
    """Compute Doppler b-parameter from temperature and molecular mass.

    b = sqrt(2 * k_B * T / (mol_mass * m_p))  [cm/s]
    """
    return float( sqrt( 2.0 * k_B * temperature / ( mol_mass * mp ) ) );
