############################################################
# TransitionInfo: high-level species + transition descriptor
#
#  Bundles the species, the transition and the molecular mass
#  into one object consumed by the LineRt high-level interface.
#
#  The transition can be specified by index, or by a physical
#  quantity (frequency, wavelength or photon energy) with an
#  explicit unit; every specification is converted to a
#  frequency and matched by the existing specify_transition
#  machinery.

import os;
from math import sqrt;

from numpy import array, float64, int64, where;

from .lamda_format import SpeciesData, load_lamda, specify_transition;
from .lamda_fetcher import CACHE_DIR, get_cached_species;


############################################################
# Molecular mass table (amu)

class MolecularMassError( ValueError ):
    """Species not in the built-in mass table and no mol_mass given."""

_MOL_MASS = { 'CO'    : 28.0, 'OH'    : 17.0, 'H2O'   : 18.0, \
              'NH3'   : 17.0, 'CH3OH' : 32.0, 'CS'    : 44.0, \
              'SIO'   : 44.0, 'HCN'   : 27.0, 'HCO+'  : 29.0, \
              'N2H+'  : 29.0, 'SO'    : 48.0, 'SO2'   : 64.0, \
              'H2CO'  : 30.0, 'H2S'   : 34.0, 'CN'    : 26.0, \
              'NO'    : 30.0, 'C2H'   : 25.0, 'HNC'   : 27.0, \
              'C3H2'  : 38.0 };  # amu (keys uppercased for case-insensitive lookup)


############################################################
# Unit specification: value + unit -> freq_GHz

_C_CGS = 2.99792458e10;      # speed of light [cm/s]
_H_CGS = 6.62607015e-27;     # Planck constant [erg s]
_K_B   = 1.380649e-16;       # Boltzmann constant [erg/K]
_M_P   = 1.67262192e-24;     # proton mass [g]

_FREQ_UNITS    = { 'GHz' : 1.0e0, 'THz' : 1.0e3 };  # multiplier to GHz
_WAVE_TO_CM    = { 'cm' : 1.0e0, 'mm' : 1.0e-1, 'um' : 1.0e-4, \
                   'nm' : 1.0e-7, 'angstrom' : 1.0e-8 };  # to cm
_ENERGY_TO_ERG = { 'eV' : 1.602176634e-12, 'erg' : 1.0e0 };  # to erg

def _value_to_freq_GHz( value, unit ):
    """Convert a (value, unit) transition specification to GHz.

    Frequency (GHz/THz), wavelength (cm/mm/um/nm/angstrom) and photon
    energy (eV/erg) are all accepted; the unit string selects the
    physical quantity.  Raises ValueError for unknown units.
    """
    if unit in _FREQ_UNITS:
        return float( value ) * _FREQ_UNITS[ unit ];
    if unit in _WAVE_TO_CM:
        lam_cm = float( value ) * _WAVE_TO_CM[ unit ];
        return _C_CGS / lam_cm / 1.0e9;
    if unit in _ENERGY_TO_ERG:
        e_erg = float( value ) * _ENERGY_TO_ERG[ unit ];
        return e_erg / _H_CGS / 1.0e9;
    raise ValueError( "Unknown unit '%s'. Accepted: GHz, THz, cm, mm, " \
                      "um, nm, angstrom, eV, erg" % unit );


############################################################
# Species resolution: embedded -> LAMDA cache -> user path

_EMBEDDED_DIR = os.path.join( os.path.dirname( os.path.realpath( __file__ ) ), \
                              'embedded' );

def _embedded_names( ):
    names = [ f[ : -4 ] for f in os.listdir( _EMBEDDED_DIR ) \
              if f.endswith( '.dat' ) ];
    return sorted( names );

def _available_species( ):
    names = set( _embedded_names( ) ) | set( get_cached_species( ) );
    return sorted( names );

def _find_species_path( name ):
    """Resolve a species name to a file path.

    Prefers the full LAMDA cache (written by ``fetch_species`` with
    collision rates) over the stripped embedded copy.  Falls back to
    embedded for offline use.
    """
    cached = os.path.join( CACHE_DIR, name.lower( ) + '.dat' );
    if os.path.exists( cached ):
        return cached;
    if name.lower( ) in _embedded_names( ):
        return os.path.join( _EMBEDDED_DIR, name.lower( ) + '.dat' );
    if os.path.exists( name ):
        return name;
    raise FileNotFoundError( \
        "Species '%s' not found. Available: %s" \
        % ( name, ', '.join( _available_species( ) ) ) );


############################################################
# TransitionInfo class

class TransitionInfo:
    """Species + transition + molecular mass for high-level runs."""

    def __init__( self, species, transition_idx = 0, *, \
                  value = None, unit = None, freq_GHz = None, \
                  mol_mass = None, transition_name = '' ):
        #  Load species data: embedded -> cache -> user path, or accept
        #  a pre-loaded SpeciesData object directly.
        if isinstance( species, SpeciesData ):
            self._species_data = species;
        else:
            path = _find_species_path( species );
            self._species_data = load_lamda( open( path ).read( ) );
        self.species = species;

        #  Resolve the transition: an explicit physical quantity
        #  (value + unit) wins; freq_GHz is a backward-compatible
        #  alias for unit='GHz'.  Otherwise use transition_idx.
        if value is not None or freq_GHz is not None:
            if freq_GHz is not None:
                if value is not None:
                    raise ValueError( \
                        "Give either ( value, unit ) or freq_GHz, not both" );
                freq = float( freq_GHz );
            else:
                if unit is None:
                    raise ValueError( "unit is required when value is given" );
                freq = _value_to_freq_GHz( value, unit );
            species_obj, transition = specify_transition( \
                self._species_data, freq_GHz = freq );
            self._transition_idx = self._species_data.find_transition_idx( \
                transition );
        else:
            idx = int( transition_idx );
            if not ( 0 <= idx < self._species_data.n_transitions ):
                raise ValueError( \
                    "transition_idx=%d out of range [0, %d).\n%s" \
                    % ( idx, self._species_data.n_transitions, \
                        self._species_data.show_transitions( ) ) );
            self._transition_idx = idx;

        self.transition = self._species_data.transitions_list[ \
            self._transition_idx ];

        #  Molecular mass: explicit arg wins, else built-in table.
        #  Look up by the user-provided species name first (e.g. "H2O"),
        #  then by the LAMDA file's molecule name.  Case-insensitive.
        if mol_mass is None:
            mass = None;
            for cand in ( self.species if isinstance( self.species, str ) \
                          else '', self._species_data.name ):
                if cand.upper( ) in _MOL_MASS:
                    mass = _MOL_MASS[ cand.upper( ) ];
                    break;
            if mass is None:
                raise MolecularMassError( \
                    "No molecular mass for '%s'. Pass mol_mass (amu)." \
                    % self._species_data.name );
            self.mol_mass = mass;
            self._mol_mass_source = 'built-in table';
        else:
            self.mol_mass = float( mol_mass );
            self._mol_mass_source = 'explicit';

        #  Propagate the resolved mass onto the species data so emission
        #  photon generation uses the correct thermal Doppler width.
        self._species_data.mol_mass = self.mol_mass;

        #  Optional human-readable label for the transition (used by
        #  show_transition); set by user_defined, blank otherwise.
        self._transition_name = str( transition_name ) if transition_name \
                                else '';

    @property
    def transition_name( self ):
        """Human-readable transition label (blank for LAMDA species)."""
        return self._transition_name;

    @property
    def transition_idx( self ):
        """0-based index into species_data.transitions."""
        return self._transition_idx;

    @property
    def species_data( self ):
        """The resolved SpeciesData object."""
        return self._species_data;

    def cross_section( self, temperature ):
        """Line-centre cross section σ₀ at a given temperature.

        Computes the Doppler b-parameter from ``temperature`` and the
        molecular mass, then delegates to
        ``species_data.cross_section(transition_idx, b)``.

        Parameters
        ----------
        temperature : float
            Gas temperature [K].

        Returns
        -------
        float
            Line-centre cross section σ₀ [cm²].
        """
        b = self.doppler_b( temperature );
        return self._species_data.cross_section( self._transition_idx, b );

    def doppler_b( self, temperature ):
        """Doppler b-parameter from temperature and molecular mass.

        b = sqrt(2 * k_B * T / (mol_mass * m_p))  [cm/s]

        Parameters
        ----------
        temperature : float
            Gas temperature [K].

        Returns
        -------
        float
            Doppler b-parameter [cm/s].
        """
        return sqrt( 2.0 * _K_B * float( temperature ) / \
                     ( self.mol_mass * _M_P ) );

    def show_transition( self ):
        """Print the resolved transition in detail."""
        tr = self.transition;
        sp_name = self.species if isinstance( self.species, str ) \
                  else getattr( self._species_data, 'name', '?' );
        print( '========================================' );
        print( 'Species     : %s' % sp_name );
        if self._transition_name:
            print( 'Transition  : %s' % self._transition_name );
        else:
            print( 'Transition  : idx=%d  %d -> %d' \
                   % ( self._transition_idx, tr.upper, tr.lower ) );
        print( '  A_ul      : %.3e s^-1' % tr.A_ul );
        print( '  freq      : %.4f GHz' % tr.freq_GHz );
        print( '  lambda    : %.4f um' % tr.wavelength_um );
        print( '  E_u       : %.4f cm^-1 (%.1f K)' \
               % ( tr.E_u_cm, tr.E_u_cm * _H_CGS * _C_CGS * 100.0 / _K_B ) );
        print( '  mol_mass  : %.1f amu (%s)' \
               % ( self.mol_mass, self._mol_mass_source ) );
        cps = getattr( self._species_data, 'collision_partners', [ ] );
        if cps:
            upper = tr.upper;
            lower = tr.lower;
            print( '  Coll. partners (for transition %d -> %d):' \
                   % ( upper, lower ) );
            for cp in cps:
                temps = cp.get( 'temps', array( [ ] ) );
                idxs = cp.get( 'trans_indices', array( [ [ ] ] ) );
                #  Find the collision transition matching our (upper,lower)
                match = where( ( idxs[ :, 0 ] == upper ) & \
                               ( idxs[ :, 1 ] == lower ) )[ 0 ];
                src = cp.get( 'source', 'LAMDA' );
                if len( match ) > 0:
                    src = cp.get( 'source', 'LAMDA' );
                    if 'callable' in cp:
                        print( '    %-20s : C_ul=f(T) (callable), %s' \
                               % ( cp.get( 'species', '?' ), src ) );
                    elif 'const' in cp:
                        print( '    %-20s : C_ul=%.3e cm^3/s (const), %s' \
                               % ( cp.get( 'species', '?' ),
                                   cp[ 'const' ], src ) );
                    else:
                        rates = cp.get( 'rates', array( [ [ ] ] ) );
                        r = rates[ match[ 0 ] ];
                        r_lo = float( r.min( ) );
                        r_hi = float( r.max( ) );
                        print( '    %-20s : C_ul=%.3e..%.3e cm^3/s, '
                               'T=[%.0f..%.0f] K (%s)' \
                               % ( cp.get( 'species', '?' ),
                                   r_lo, r_hi,
                                   float( temps[ 0 ] ) if temps.size else 0,
                                   float( temps[ -1 ] ) if temps.size else 0,
                                   src ) );
                else:
                    print( '    %-20s : (no rate for %d->%d) '
                           '(%d trans total, %s)' \
                           % ( cp.get( 'species', '?' ),
                               upper, lower,
                               cp.get( 'n_trans', 0 ), src ) );
        else:
            print( '  Coll. partners: (none)' );
        print( '========================================' );        

    def show_transitions( self ):
        """Print the full transition table of this species."""
        print( 'Available : %s' % ', '.join( _available_species( ) ) );
        print( self._species_data.show_transitions( ) );

    @classmethod
    def user_defined( cls, *, A_ul, freq_GHz = None, value = None, \
                      unit = None, g_u = 1.0, g_l = 1.0, \
                      E_u_K = None, mol_mass = None, \
                      collision_rates = None, \
                      species_name = 'user_defined', transition_name = '' ):
        """Build a TransitionInfo for a user-defined 2-level transition.

        Use this when the transition of interest is not in the LAMDA
        database (neither online nor embedded): specify the physical
        transition parameters directly and get a fully functional
        ``TransitionInfo`` object, ready to pass to ``LineRt``.

        Parameters
        ----------
        A_ul : float
            Einstein A coefficient [s⁻¹].
        freq_GHz : float, optional
            Line frequency [GHz]. Mutually exclusive with (value, unit).
        value, unit : float, str, optional
            Alternative frequency specification: wavelength (cm/mm/um/nm/
            angstrom) or photon energy (eV/erg).  ``unit`` is required
            whenever ``value`` is given.
        g_u, g_l : float
            Statistical weights of the upper and lower level (default 1/1).
        E_u_K : float, optional
            Upper-level energy [K].  Defaults to the photon energy
            h·ν/k_B above the ground state (2-level convention).
        mol_mass : float, optional
            Molecular mass [amu].  Optional if ``species_name`` is in the
            built-in mass table (e.g. ``'CO'``), required otherwise.
        collision_rates : dict or None
            Collisional de-excitation rate coefficients for one or more
            partners, keyed by partner name.  Each value is either a
            float (temperature-independent C_ul [cm³ s⁻¹]) or a callable
            ``f(T) -> float`` returning C_ul at temperature T [K].
            The collider **number density** is NOT specified here - it
            is a spatial field and must be supplied via
            ``LineRt(colliders=...)``.  Example::

                collision_rates = {
                    'H2': 1e-12,
                    'e':  lambda T: 1e-9 * sqrt(T/300),
                }
        species_name : str
            Name stored on the synthetic species; used for the built-in
            molecular-mass lookup.
        transition_name : str
            Optional human-readable label for the transition (e.g.
            ``'P(8)'``), shown by ``show_transition`` / ``show``.

        Returns
        -------
        TransitionInfo
            A species-based Group 1 configuration.

        Examples
        --------
        >>> ti = TransitionInfo.user_defined( A_ul = 1e-6, \
                freq_GHz = 115.271, species_name = 'CO' )
        """
        if float( A_ul ) <= 0.0:
            raise ValueError( "A_ul must be positive (got %g)" % A_ul );

        if value is not None or freq_GHz is not None:
            if freq_GHz is not None:
                if value is not None:
                    raise ValueError( \
                        "Give either (value, unit) or freq_GHz, not both" );
                freq = float( freq_GHz );
            else:
                if unit is None:
                    raise ValueError( "unit is required when value is given" );
                freq = _value_to_freq_GHz( value, unit );
        else:
            raise ValueError( \
                "Specify the line frequency via freq_GHz or (value, unit)" );

        #  levels[:,0] follows the LAMDA convention: energy in cm^-1
        #  (so partition_function / detailed-balance formulae that do
        #  ``E_cm * h*c*100`` work uniformly for LAMDA and user species).
        if E_u_K is None:
            E_u_cm = ( freq * 1.0e9 ) / ( _C_CGS * 100.0 );
        else:
            #  E_u_K [K] -> E_u_cm via E[erg] = k_B * E_u_K = h * c * 100 * E_u_cm
            E_u_cm = E_u_K * _K_B / ( _H_CGS * _C_CGS * 100.0 );

        coll_partners = [ ];
        if collision_rates is not None:
            if not isinstance( collision_rates, dict ):
                raise TypeError( "collision_rates must be a dict keyed by "
                                 "partner name (e.g. {'H2': 1e-12})" );
            for pname, rate_spec in collision_rates.items( ):
                if callable( rate_spec ):
                    #  Store the callable directly - evaluated at the
                    #  local gas temperature at runtime (no grid
                    #  restriction, user controls the range).
                    coll_partners.append( {
                        'species'      : str( pname ),
                        'n_trans'      : 1,
                        'n_temps'      : 0,
                        'temps'        : array( [ ], dtype = float64 ),
                        'rates'        : array( [ [ ] ], dtype = float64 ),
                        'trans_indices': array( [ [ 1, 0 ] ], dtype = int64 ),
                        'source'       : 'user',
                        'callable'     : rate_spec,
                    } );
                else:
                    c = float( rate_spec );
                    if c < 0:
                        raise ValueError( "collision rate for '%s' must be "
                                          "non-negative (got %g)" % (pname, c) );
                    coll_partners.append( {
                        'species'      : str( pname ),
                        'n_trans'      : 1,
                        'n_temps'      : 0,
                        'temps'        : array( [ ], dtype = float64 ),
                        'rates'        : array( [ [ ] ], dtype = float64 ),
                        'trans_indices': array( [ [ 1, 0 ] ], dtype = int64 ),
                        'source'       : 'user',
                        'const'        : c,
                    } );

        species = SpeciesData(
            name          = str( species_name ),
            n_levels      = 2,
            n_transitions = 1,
            levels        = array( [ [ 0.0, float( g_l ) ], \
                                     [ float( E_u_cm ), float( g_u ) ] ], \
                                   dtype = float64 ),
            transitions   = array( [ [ 1, 0, float( A_ul ), freq ] ], \
                                   dtype = float64 ),
            collision_partners = coll_partners,
            mol_mass      = float( mol_mass ) if mol_mass is not None \
                            else _MOL_MASS.get( \
                                str( species_name ).upper( ), 28.0 ),
        );

        ti = cls( species, transition_idx = 0, mol_mass = mol_mass,
                  transition_name = transition_name );
        return ti;

    def show( self ):
        """show_transition( ) then show_transitions( )."""
        self.show_transition (  );
        self.show_transitions(  );


############################################################
# Module-level queries (no TransitionInfo object needed)

def show_available_species( ):
    """Print and return the list of known species (embedded + cached)."""
    names = _available_species( );
    print( 'Available species: %s' % ', '.join( names ) );
    return names;

def show_available_transitions( species ):
    """Load a species (embedded/cache/path) and print its table."""
    path = _find_species_path( species );
    sp = load_lamda( open( path ).read( ) );
    print( sp.show_transitions( ) );
