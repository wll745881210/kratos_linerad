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

from .lamda_format import SpeciesData, load_lamda, specify_transition;
from .lamda_fetcher import CACHE_DIR, get_cached_species;


############################################################
# Molecular mass table (amu)

class MolecularMassError( ValueError ):
    """Species not in the built-in mass table and no mol_mass given."""

_MOL_MASS = { 'CO'   : 28.0, 'OH'   : 17.0, 'H2O'  : 18.0, \
              'NH3'  : 17.0, 'CH3OH': 32.0, 'CS'   : 44.0, \
              'SiO'  : 44.0, 'HCN'  : 27.0, 'HCO+' : 29.0, \
              'N2H+' : 29.0, 'SO'   : 48.0, 'SO2'  : 64.0, \
              'H2CO' : 30.0, 'H2S'  : 34.0, 'CN'   : 26.0, \
              'NO'   : 30.0, 'C2H'  : 25.0, 'HNC'  : 27.0 };  # amu


############################################################
# Unit specification: value + unit -> freq_GHz

_C_CGS = 2.99792458e10;      # speed of light [cm/s]
_H_CGS = 6.62607015e-27;     # Planck constant [erg s]

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
    if name.lower( ) in _embedded_names( ):
        return os.path.join( _EMBEDDED_DIR, name.lower( ) + '.dat' );
    cached = os.path.join( CACHE_DIR, name.lower( ) + '.dat' );
    if os.path.exists( cached ):
        return cached;
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
                  mol_mass = None ):
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
        if mol_mass is None:
            name = self._species_data.name.upper( );
            if name not in _MOL_MASS:
                raise MolecularMassError( \
                    "No molecular mass for '%s'. Pass mol_mass (amu)." % name );
            self.mol_mass = _MOL_MASS[ name ];
            self._mol_mass_source = 'built-in table';
        else:
            self.mol_mass = float( mol_mass );
            self._mol_mass_source = 'explicit';

    @property
    def transition_idx( self ):
        """0-based index into species_data.transitions."""
        return self._transition_idx;

    @property
    def species_data( self ):
        """The resolved SpeciesData object."""
        return self._species_data;

    def show_transition( self ):
        """Print the resolved transition in detail."""
        tr = self.transition;
        print( 'Species     : %s' % self.species );
        print( 'Transition  : idx=%d  %d -> %d' \
               % ( self._transition_idx, tr.upper, tr.lower ) );
        print( '  A_ul      : %.3e s^-1' % tr.A_ul );
        print( '  freq      : %.4f GHz' % tr.freq_GHz );
        print( '  lambda    : %.4f um' % tr.wavelength_um );
        print( '  E_u/K     : %.2f K' % tr.E_u_K );
        print( '  mol_mass  : %.1f amu (%s)' \
               % ( self.mol_mass, self._mol_mass_source ) );
        print( 'Available   : %s' % ', '.join( _available_species( ) ) );

    def show_transitions( self ):
        """Print the full transition table of this species."""
        print( self._species_data.show_transitions( ) );

    def show( self ):
        """show_transition( ) then show_transitions( )."""
        self.show_transition( );
        self.show_transitions( );


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
