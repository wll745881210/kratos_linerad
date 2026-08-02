from dataclasses import dataclass, field
from typing   import List, Dict, Optional, NamedTuple
from numpy    import array, asarray, zeros, zeros_like, ones, full, \
                     where, interp, exp, pi, maximum, minimum, ceil, \
                     prod, repeat, arange, column_stack, \
                     random, sqrt, arccos, sin, cos, ndarray, float64, \
                     int64, mean;


h_cgs   = 6.62607015e-27;      # Planck constant [ erg s ]
c_cgs   = 2.99792458e10;       # speed of light [ cm / s ]
k_B     = 1.380649e-16;        # Boltzmann constant [ erg K^-1 ]
sqrt_pi = 1.77245385091;       # sqrt( pi )


############################################################
# Transition definitions

class Transition( NamedTuple ):
    upper: int
    lower: int
    A_ul: float
    freq_GHz: float
    E_u_K: float
    wavelength_um: float

    @classmethod
    def from_row( cls, row, levels = None ):
        upper, lower = int( row[ 0 ] ), int( row[ 1 ] );
        A_ul = float( row[ 2 ] );
        freq_GHz = float( row[ 3 ] );
        wavelength_um = 299792.458 / freq_GHz if freq_GHz > 0 \
                        else float( 'inf' );
        E_u_K = float( levels[ upper, 0 ] ) \
                if levels is not None else float( 'nan' );
        return cls( upper = upper, lower = lower, A_ul = A_ul, \
                    freq_GHz = freq_GHz, E_u_K = E_u_K, \
                    wavelength_um = wavelength_um );

    def __repr__( self ):
        return ( "Transition(upper=%d, lower=%d, A_ul=%.2e, freq=%.3f GHz, " \
                 "lambda=%.3f um, E_u/K=%.1f K)" % \
                 ( self.upper, self.lower, self.A_ul, self.freq_GHz, \
                   self.wavelength_um, self.E_u_K ) );


############################################################
# Species data class

@dataclass
class SpeciesData:
    name: str
    n_levels: int
    levels: ndarray
    n_transitions: int
    transitions: ndarray
    collision_partners: List[ Dict ] = field( default_factory = list );
    mol_mass: float = 28.0;      # [amu], used for the emission Doppler b

    @property
    def transitions_list( self ):
        return [ Transition.from_row( row, self.levels ) \
                 for row in self.transitions ];

    ############################################################
    # Transition selection & info

    def find_transition_idx( self, transition ):
        for idx in range( self.n_transitions ):
            row = self.transitions[ idx ];
            if ( int( row[ 0 ] ) == transition.upper \
                 and int( row[ 1 ] ) == transition.lower \
                 and abs( float( row[ 2 ] ) - transition.A_ul ) / \
                     max( abs( transition.A_ul ), 1e-40 ) < 1e-6 \
                 and abs( float( row[ 3 ] ) - transition.freq_GHz ) / \
                     max( abs( transition.freq_GHz ), 1e-40 ) < 1e-6 ):
                return idx;
        raise ValueError( \
            "Transition %s not found in species data. " \
            "Available: %d transitions loaded. " \
            "Candidates: %s" % ( transition, len( self.transitions ), \
                                 self.transitions_list ) );

    def show_transitions( self ):
        lines = [ "Species: %s (%d levels, %d transitions)" % \
                  ( self.name, self.n_levels, self.n_transitions ) ];
        lines.append( "%4s  %6s  %6s  %12s  %10s  %10s  %12s" % \
                      ( 'Idx', 'Upper', 'Lower', 'A_ul/s⁻¹', \
                        'freq/GHz', 'λ/µm', 'E_u/K' ) );
        lines.append( "─" * 70 );
        for idx, tr in enumerate( self.transitions_list ):
            lines.append( "%4d  %6d  %6d  %12.3e  %10.4f  %10.3f  %12.1f" \
                          % ( idx, tr.upper, tr.lower, tr.A_ul, \
                              tr.freq_GHz, tr.wavelength_um, tr.E_u_K ) );
        return "\n".join( lines );

    def get_Einstein_A( self, upper, lower ):
        mask = ( self.transitions[ :, 0 ] == upper ) & \
               ( self.transitions[ :, 1 ] == lower );
        match = self.transitions[ mask ];
        return float( match[ 0, 2 ] ) if len( match ) > 0 else 0.0;

    def get_level_energy( self, level_idx ):
        return float( self.levels[ level_idx, 0 ] );

    def get_level_weight( self, level_idx ):
        return float( self.levels[ level_idx, 1 ] );

    def get_nu( self, upper, lower ):
        mask = ( self.transitions[ :, 0 ] == upper ) & \
               ( self.transitions[ :, 1 ] == lower );
        match = self.transitions[ mask ];
        return float( match[ 0, 3 ] ) if len( match ) > 0 else 0.0;

    def get_collision_rate( self, upper, lower, T, partner = 'H2' ):
        for cp in self.collision_partners:
            if cp[ 'species' ] == partner:
                idx = where( ( cp[ 'trans_indices' ][ :, 0 ] == upper ) \
                             & ( cp[ 'trans_indices' ][ :, 1 ] == \
                                 lower ) )[ 0 ];
                if len( idx ) == 0:
                    return 0.0;
                rates = cp[ 'rates' ][ idx[ 0 ] ];
                return float( interp( T, cp[ 'temps' ], rates ) );
        return 0.0;

    ############################################################
    # Population & opacity

    def partition_function( self, T ):
        g = asarray( self.levels[ :, 1 ], dtype = float64 );
        E_cm = asarray( self.levels[ :, 0 ], dtype = float64 );
        E_erg = E_cm * h_cgs * c_cgs * 100.0;
        T_arr = asarray( T, dtype = float64 );
        exponent = E_erg[ :, None ] / ( k_B * T_arr );
        return ( g[ :, None ] * exp( -exponent ) ).sum( axis = 0 );

    def lte_populations( self, n_total, T ):
        n_t = asarray( n_total, dtype = float64 ).ravel( );
        T_arr = asarray( T, dtype = float64 );
        E_cm = asarray( self.levels[ :, 0 ], dtype = float64 );
        E_erg = E_cm * h_cgs * c_cgs * 100.0;
        g = asarray( self.levels[ :, 1 ], dtype = float64 );
        Z = self.partition_function( T_arr );
        pops = { };
        for i in range( self.n_levels ):
            pops[ 'n%d' % i ] = ( n_t * g[ i ] * \
                                  exp( -E_erg[ i ] / ( k_B * T_arr ) ) / Z );
        pops[ 'n_total' ] = n_t.copy( );
        return pops;

    def cross_section( self, transition_idx = 0, b_param = 1e5 ):
        t = self.transitions[ transition_idx ];
        upper, lower = int( t[ 0 ] ), int( t[ 1 ] );
        A_ul = t[ 2 ];
        nu = t[ 3 ] * 1e9;
        g_u = self.get_level_weight( upper );
        g_l = self.get_level_weight( lower );
        sigma = ( c_cgs * c_cgs * c_cgs ) / \
                ( 8.0 * nu * nu * nu * b_param * \
                  sqrt_pi * sqrt_pi * sqrt_pi );
        sigma *= ( g_u / g_l ) * A_ul;
        return sigma;

    def initial_populations( self, n_species, T = None, \
                             colliders = None ):
        """Build the cycle-0 level populations.

        By default (no temperature) everything sits in the ground state,
        which gives zero emissivity.  When a temperature is provided,
        the populations are thermalised to LTE via ``solve_populations``
        at zero external flux (with colliders when given), so that
        cycle-0 opacity and emissivity are physically consistent even
        without external sources.
        """
        n_species = asarray( n_species, dtype = float64 );
        shape = n_species.shape;
        if T is not None:
            from .equilibrium import solve_populations
            exc0 = zeros( shape, dtype = float64 );
            result = solve_populations( self, exc0, n_species, \
                                        T = T, colliders = colliders, \
                                        transition_idx = 0 );
            pops = { };
            for i in range( self.n_levels ):
                pops[ 'n%d' % i ] = asarray( result[ i ], \
                                             dtype = float64 ).copy( );
            pops[ 'n_total' ] = n_species.copy( );
            return pops;
        pops = { };
        for i in range( self.n_levels ):
            pops[ 'n%d' % i ] = ( n_species.copy( ) if i == 0 \
                                  else zeros( shape, dtype = float64 ) );
        pops[ 'n_total' ] = n_species.copy( );
        return pops;

    def compute_opacity( self, populations, b_sca = 1e5, \
                         transition_idx = None ):
        mfp_sca = zeros_like( populations.get( 'n0', \
                              populations.get( 'n_total', ones( 1 ) ) ), \
                              dtype = float64 );
        t_range = [ transition_idx ] if transition_idx is not None \
                  else range( self.n_transitions );
        for t_idx in t_range:
            lower = int( self.transitions[ t_idx, 1 ] );
            n_l = asarray( populations.get( 'n%d' % lower, \
                           zeros_like( mfp_sca ) ), dtype = float64 );
            sigma_s = self.cross_section( t_idx, b_sca );
            mfp_sca += n_l * sigma_s;
        return mfp_sca;

    ############################################################
    # Excitation update

    def update_populations( self, exc_flux, flx, populations, cycle, \
                            dx = 1.0, b_sca = 1e5, T = None, \
                            colliders = None, transition_idx = 0 ):
        """Update level populations from the Kratos excitation flux.

        Parameters
        ----------
        exc_flux : ndarray (nz, ny, nx)
            Overlap-integrated excitation fluence F_ext for the target
            transition (CGS, [n][l]^-2[t]^-1).
        flx : ndarray or None
            Total flux (diagnostic, not used for population update).
        populations : dict
            Current population dict (e.g. from initial_populations).
        cycle : int
            Current cycle index.
        b_sca : float
            Doppler b-parameter [cm/s] for the scattering cross-section
            sigma_0.  Must be a scalar (not per-cell array).
        T : ndarray or float or None
            Gas temperature [K].  When provided, the Planck radiation
            background at T is included in the statistical equilibrium
            (induced absorption R_abs + stimulated emission R_stim via
            the Bose-Einstein occupation number).  At zero external flux
            this thermalises the populations to the Boltzmann
            distribution.  When None, only spontaneous decay + external
            excitation Gamma are considered.
        colliders : dict or None
            Collider densities for collisional (de-)excitation.
        transition_idx : int
            Index into self.transitions for the pumped transition.
        """
        from .equilibrium import solve_populations
        n_total = populations.get( 'n_total', \
                   sum( populations.get( 'n%d' % i, \
                        zeros( 1, dtype = float64 ) ) \
                        for i in range( self.n_levels ) ) );
        n_total = asarray( n_total, dtype = float64 );
        shape = n_total.shape;
        exc_flux_arr = asarray( exc_flux, dtype = float64 ) \
                       if exc_flux is not None else \
                       zeros( shape, dtype = float64 );
        if exc_flux_arr.shape != shape:
            exc_flux_arr = zeros( shape, dtype = float64 );
        result = solve_populations( self, exc_flux_arr, n_total, \
                                    T = T, colliders = colliders, \
                                    b_param = b_sca, \
                                    transition_idx = transition_idx );
        if isinstance( result, ndarray ) and \
           result.ndim == n_total.ndim + 1:
            pops = { };
            for i in range( self.n_levels ):
                pops[ 'n%d' % i ] = result[ i ].copy( );
            pops[ 'n_total' ] = n_total.copy( );
            return pops;
        return result;

    ############################################################
    # Emission

    def compute_emissivity( self, populations, transition_idx, \
                            temperature ):
        t = self.transitions[ transition_idx ];
        upper = int( t[ 0 ] );
        A_ul = float( t[ 2 ] );
        nu = float( t[ 3 ] ) * 1e9;
        n_u = asarray( populations.get( 'n%d' % upper, \
                        ones( 1 ) ), dtype = float64 );
        emissivity = n_u * A_ul * h_cgs * nu / ( 4.0 * pi );
        return maximum( emissivity, 0.0 );

    def generate_emission_photons( self, populations, \
                                   transition_idx, temperature, mesh, \
                                   n_per_cell_max = 10, b_sca = 1e5, \
                                   rng = None ):
        if rng is None:
            rng = random.default_rng( );
        n_cell = mesh[ 'n_cell' ];
        x_min = mesh[ 'x_min' ];
        dx = mesh[ 'dx' ];
        volume = float( prod( dx ) );

        emissivity = self.compute_emissivity( populations, \
                                              transition_idx, \
                                              temperature );
        t = self.transitions[ transition_idx ];
        upper = int( t[ 0 ] );

        nz, ny, nx = int( n_cell[ 2 ] ), int( n_cell[ 1 ] ), \
                     int( n_cell[ 0 ] );
        em = asarray( emissivity, dtype = float64 );
        n_active = int( ( em > 0.0 ).sum( ) );
        if n_active == 0:
            return zeros( ( 0, 9 ), dtype = float64 );

        #  Brightness-proportional photon budget: the brightest cell gets
        #  up to n_per_cell_max photons, dimmer cells scale down (min 1).
        #  Weighting by the per-cell luminosity keeps energy conserved:
        #  weight = lum_cell / n_ph  per photon.
        active = ( em > 0.0 ).ravel( );
        em_act = em.ravel( )[ active ];
        lum_act = em_act * volume;
        lum_max = lum_act.max( );
        n_ph_cell = maximum( 1, ceil( n_per_cell_max * \
                                      lum_act / lum_max ) ).astype( int );
        n_ph_cell = minimum( n_ph_cell, n_per_cell_max );
        n_total = int( n_ph_cell.sum( ) );

        #  Map each active cell's 1D flat index back to (iz, iy, ix).
        flat_idx = where( active )[ 0 ];
        cell_of = repeat( arange( n_active ), n_ph_cell );
        flat_ph = flat_idx[ cell_of ];
        iz = ( flat_ph // ( ny * nx ) );
        iy = ( ( flat_ph // nx ) % ny );
        ix = ( flat_ph % nx );

        x = x_min[ 0 ] + ( ix + rng.random( n_total ) ) * dx[ 0 ];
        y = x_min[ 1 ] + ( iy + rng.random( n_total ) ) * dx[ 1 ];
        z = x_min[ 2 ] + ( iz + rng.random( n_total ) ) * dx[ 2 ];

        cos_theta = 2.0 * rng.random( n_total ) - 1.0;
        theta = arccos( cos_theta );
        phi = 2.0 * pi * rng.random( n_total );
        dir_x = sin( theta ) * cos( phi );
        dir_y = sin( theta ) * sin( phi );
        dir_z = cos_theta;

        temp_ph = asarray( temperature, dtype = float64 ) \
                  .ravel( )[ flat_ph ];
        b_thermal = sqrt( 1.66289e8 * temp_ph / self.mol_mass + 1e-35 );
        sigma_ph = b_thermal / sqrt( 2.0 );
        vel_draw = rng.normal( 0.0, sigma_ph, n_total );

        weight_per_ph = lum_act[ cell_of ] / n_ph_cell[ cell_of ];

        return column_stack( ( x, y, z, dir_x, dir_y, dir_z, \
                               weight_per_ph, vel_draw, sigma_ph ) );

    ############################################################
    # Field construction

    def make_fields( self, populations, step, cycle, \
                     base_fields = None, unit_l0 = 1.0, \
                     unit_t0 = 1.0, transition_idx = None ):
        n_total = populations.get( 'n_total', \
                   sum( populations.get( 'n%d' % i, ones( 1 ) ) \
                        for i in range( self.n_levels ) ) );
        n_total = asarray( n_total, dtype = float64 );
        shape = n_total.shape;
        #  Use the gas Doppler b from base_fields (CGS) for the opacity,
        #  not the hardcoded default.  Fall back only when absent.
        if base_fields and 'b_sca' in base_fields:
            b_field = asarray( base_fields[ 'b_sca' ], dtype = float64 );
            b_sca_val = float( mean( b_field ) ) if b_field.size else 1e5;
        else:
            b_sca_val = 1e5;
        mfp_i_sca = self.compute_opacity( populations, \
                                          b_sca = b_sca_val, \
                                          transition_idx = transition_idx );
        v_factor = unit_t0 / unit_l0;
        fields = { };
        if base_fields:
            for k, v in base_fields.items( ):
                arr = asarray( v, dtype = float64 ).copy( );
                if k == 'mfp_i_abs_0':
                    arr *= unit_l0;
                elif k in ( 'b_sca', ) or k.startswith( 'vel_' ):
                    arr *= v_factor;
                elif k == 'temp':
                    pass;
                else:
                    continue;   # mfp_i_sca_0 is recomputed below
                fields[ k ] = arr;
        #  mfp_i_sca_0 is ALWAYS recomputed from the (possibly evolved)
        #  populations, even if base_fields carried an earlier value.
        fields[ 'mfp_i_sca_0' ] = asarray( mfp_i_sca, \
                                           dtype = float64 ) * unit_l0;
        if 'b_sca' not in fields:
            fields[ 'b_sca' ] = full( shape, 1e5 * v_factor, \
                                      dtype = float64 );
        for a in range( 3 ):
            key = 'vel_%d' % a;
            if key not in fields:
                fields[ key ] = zeros( shape, dtype = float64 );
        for i in range( self.n_levels ):
            fields[ 'n%d' % i ] = asarray( \
                populations.get( 'n%d' % i, zeros( shape ) ), \
                dtype = float64 );
        return fields;


############################################################
# LAMDA file loading

def _find_section( lines, marker, start = 0 ):
    i = start;
    while i < len( lines ):
        line = lines[ i ].strip( );
        if line and not line.startswith( '!' ):
            return i;
        if marker in line:
            return i;
        i += 1;
    return -1;


def _skip_non_section_header( lines, i ):
    while i < len( lines ) and lines[ i ].strip( ).startswith( '!' ):
        i += 1;
    return i;


def load_lamda( content ):
    if isinstance( content, str ):
        lines = content.splitlines( );
    else:
        lines = [ ln.decode( ) if isinstance( ln, bytes ) else ln \
                  for ln in content ];

    lines = [ ln.strip( ) for ln in lines ];
    lines_upper = [ ln.upper( ) for ln in lines ];
    mol_idx = -1;
    for i, ln in enumerate( lines_upper ):
        if ln.startswith( '!MOLECULE' ):
            mol_idx = i + 1;
            break;
    name = lines[ mol_idx ] if mol_idx >= 0 and mol_idx < len( lines ) \
           else 'unknown';

    nlev_idx = -1;
    for i in range( mol_idx, len( lines ) ):
        if 'NUMBER OF ENERGY LEVELS' in lines_upper[ i ]:
            nlev_idx = i;
            break;
    n_levels = int( lines[ nlev_idx + 1 ] ) if nlev_idx >= 0 else 0;

    ntrans_idx = -1;
    for i in range( nlev_idx + 1, len( lines ) ):
        if 'NUMBER OF RADIATIVE TRANSITIONS' in lines_upper[ i ]:
            ntrans_idx = i;
            break;
    n_transitions = int( lines[ ntrans_idx + 1 ] ) \
                    if ntrans_idx >= 0 else 0;

    levels = [ ];
    lev_start = nlev_idx + 3;
    for i in range( n_levels ):
        parts = lines[ lev_start + i ].split( );
        if len( parts ) >= 3:
            levels.append( [ float( parts[ 1 ] ), float( parts[ 2 ] ) ] );
    levels = array( levels, dtype = float64 );

    transitions = [ ];
    trans_start = ntrans_idx + 3;
    for i in range( n_transitions ):
        parts = lines[ trans_start + i ].split( );
        if len( parts ) >= 4:
            transitions.append( [ int( parts[ 1 ] ) - 1, \
                                  int( parts[ 2 ] ) - 1, \
                                  float( parts[ 3 ] ), float( parts[ 4 ] ) ] );
    transitions = array( transitions, dtype = float64 );

    coll_partners = [ ];
    cp_idx = trans_start + n_transitions;
    while cp_idx < len( lines ):
        line_u = lines_upper[ cp_idx ];
        if 'NUMBER OF COLL PARTNERS' in line_u or \
           'NUMBER OF COLLISION PARTNERS' in line_u:
            break;
        cp_idx += 1;

    if cp_idx < len( lines ):
        n_coll_partners = int( lines[ cp_idx + 1 ] );
        ci = cp_idx + 2;
        for _ in range( n_coll_partners ):
            while ci < len( lines ) and (
                lines[ ci ].strip( ).startswith( '!' ) or \
                not lines[ ci ].strip( ) ):
                ci += 1;
            if ci >= len( lines ):
                break;
            partner_name = lines[ ci ].strip( );
            ci += 1;
            while ci < len( lines ) and not \
                  ( ( 'COLL' in lines_upper[ ci ] or \
                      'COLLISION' in lines_upper[ ci ] ) and \
                    'TRANS' in lines_upper[ ci ] and \
                    'NUMBER' in lines_upper[ ci ] ):
                ci += 1;
            n_coll_trans = int( lines[ ci + 1 ] );
            ci += 2;
            while ci < len( lines ) and not \
                  ( ( 'COLL' in lines_upper[ ci ] or \
                      'COLLISION' in lines_upper[ ci ] or \
                      'NUMBER' in lines_upper[ ci ] ) and \
                    'TEMP' in lines_upper[ ci ] and \
                    'NUMBER' in lines_upper[ ci ] ):
                ci += 1;
            n_coll_temps = int( lines[ ci + 1 ] );
            ci += 2;
            #  Skip any comment lines before the temperature values.
            while ci < len( lines ) and \
                  lines[ ci ].strip( ).startswith( '!' ):
                ci += 1;
            coll_temps = array( \
                [ float( x ) for x in lines[ ci ].split( ) ] );
            ci += 1;

            rates = [ ];
            #  Skip comment lines (e.g. "! TRANS + UP + LOW + ...")
            #  before the first rate line.
            while ci < len( lines ) and \
                  lines[ ci ].strip( ).startswith( '!' ):
                ci += 1;
            for _ in range( n_coll_trans ):
                vals = [ float( x ) for x in lines[ ci ].split( ) ];
                rates.append( vals );
                ci += 1;
            rates = array( rates, dtype = float64 );

            trans_indices = [ ];
            for n in range( n_coll_trans ):
                #  Collision rate lines: trans#, upper, lower, rate...
                #  upper/lower are 1-based level indices.
                trans_indices.append( \
                    [ int( rates[ n, 1 ] ) - 1, \
                      int( rates[ n, 2 ] ) - 1 ] );
            trans_indices = array( trans_indices, dtype = int64 );

            coll_partners.append( { \
                'species'      : partner_name, \
                'n_trans'      : n_coll_trans, \
                'n_temps'      : n_coll_temps, \
                'temps'        : coll_temps, \
                'rates'        : rates, \
                'trans_indices': trans_indices, \
            } );

    return SpeciesData( \
        name = name, n_levels = n_levels, levels = levels, \
        n_transitions = n_transitions, transitions = transitions, \
        collision_partners = coll_partners );


############################################################
# Transition selection helpers

def load_species_transition( filepath, *, freq_GHz = None, \
                             wavelength_um = None, E_u_K = None, \
                             upper = None, lower = None, \
                             tolerance = None ):
    """Load LAMDA file and select exactly one transition by physical property.

    Parameters
    ----------
    filepath : str or file-like
    freq_GHz : float
        Target rest frequency [GHz]. Tolerance = 5% of centre.
    wavelength_um : float
        Equivalent to freq_GHz = 299792.458 / wavelength_um.
    E_u_K : float
        Upper-level energy [K]. Tolerance = 5% of centre.
    upper : int
        Upper level J (e.g. 1 for CO J=1→0).
    lower : int
        Lower level J (e.g. 0 for CO J=1→0).
    tolerance : float, optional
        Fractional tolerance (default 0.05 = 5%). Not used for upper/lower.

    Returns
    -------
    species : SpeciesData
    transition : Transition
        The unique matching transition.

    Raises
    ------
    ValueError
        If zero or multiple transitions match the criterion.
    """
    with open( filepath ) as f:
        content = f.read( );
    return _specify_transition( content, freq_GHz = freq_GHz, \
                                wavelength_um = wavelength_um, \
                                E_u_K = E_u_K, upper = upper, \
                                lower = lower, tolerance = tolerance );


def specify_transition( species, *, freq_GHz = None, \
                        wavelength_um = None, E_u_K = None, \
                        upper = None, lower = None, tolerance = None ):
    """Select exactly one transition from an already-loaded SpeciesData.

    Same semantics as load_species_transition but uses a pre-loaded species.
    Returns (species, transition).
    """
    return species, _specify_transition_one( \
        species, freq_GHz = freq_GHz, wavelength_um = wavelength_um, \
        E_u_K = E_u_K, upper = upper, lower = lower, \
        tolerance = tolerance );


def _specify_transition( content, **kwargs ):
    species = load_lamda( content );
    transition = _specify_transition_one( species, **kwargs );
    return species, transition;


def _specify_transition_one( species, *, freq_GHz = None, \
                             wavelength_um = None, E_u_K = None, \
                             upper = None, lower = None, \
                             tolerance = None ):
    tol = tolerance if tolerance is not None else 0.05;
    criteria = [ ];
    if upper is not None or lower is not None:
        if freq_GHz is not None or wavelength_um is not None or \
           E_u_K is not None:
            raise ValueError( \
                "Provide EITHER (upper, lower) OR a physical property" );
        if upper is None or lower is None:
            raise ValueError( \
                "Both upper and lower must be specified together" );
    if freq_GHz is not None:
        if wavelength_um is not None or E_u_K is not None:
            raise ValueError( \
                "Provide exactly one of freq_GHz, wavelength_um, E_u_K" );
        criteria.append( ( 'freq_GHz', float( freq_GHz ) ) );
    elif wavelength_um is not None:
        if E_u_K is not None:
            raise ValueError( \
                "Provide exactly one of freq_GHz, wavelength_um, E_u_K" );
        centre = 299792.458 / float( wavelength_um );
        criteria.append( ( 'freq_GHz', centre ) );
    elif E_u_K is not None:
        criteria.append( ( 'E_u_K', float( E_u_K ) ) );
    elif upper is None:
        raise ValueError( \
            "Specify one of freq_GHz, wavelength_um, E_u_K, " \
            "or (upper, lower)" );

    if upper is not None and lower is not None:
        matches = [ ];
        for idx, tr in enumerate( species.transitions_list ):
            if int( tr.upper ) == int( upper ) and \
               int( tr.lower ) == int( lower ):
                matches.append( ( idx, tr, 0.0 ) );
    else:
        attr, centre = criteria[ 0 ];
        matches = [ ];
        for idx, tr in enumerate( species.transitions_list ):
            value = getattr( tr, attr );
            if value <= 0:
                continue;
            error = abs( value - centre ) / max( abs( centre ), 1e-40 );
            if error <= tol:
                matches.append( ( idx, tr, error ) );

    if len( matches ) == 0:
        table = species.show_transitions( );
        raise ValueError( \
            "No transition matches %s=%.4f ± %.1f%%.\n%s" % \
            ( attr, centre, tol * 100, table ) );
    if len( matches ) > 1:
        lines = [ "Multiple transitions match %s=%.4f ± %.1f%%:" % \
                  ( attr, centre, tol * 100 ) ];
        for idx, tr, err in matches:
            lines.append( "  idx=%d %s  (error=%.4f)" % \
                          ( idx, tr, err ) );
        raise ValueError( "\n".join( lines ) );

    idx, tr, _ = matches[ 0 ];
    species._selected_transition = tr;
    species._selected_transition_idx = idx;
    return tr;
