"""Species database — explicit loading of molecular/atomic data.

Each species requires an explicit load call. This is not an auto-discovery
system — users must call load_species() to load from a LAMDA file.

Data files are stored in molecular/embedded/ (shipped with the pipeline)
or can be loaded from a user-provided path.

Usage:
    co = load_species("CO")
    oh = load_species("/path/to/oh.dat")
"""

import os


_PROJECT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_EMBEDDED_DIR = os.path.join(_PROJECT, "molecular", "embedded")

_SPECTRA = {
    "CO": os.path.join(_EMBEDDED_DIR, "co.dat"),
    "OH": os.path.join(_EMBEDDED_DIR, "oh.dat"),
}


def load_species(name_or_path, *, freq_GHz=None):
    """Load species data from a LAMDA file.

    Parameters
    ----------
    name_or_path : str
        Species name (e.g. "CO", "OH") to load from molecular/embedded/,
        OR a full path to a .dat file.
    freq_GHz : float or None
        If provided, return (species, transition) using the transition
        closest to this frequency. If None, return only the SpeciesData.

    Returns
    -------
    SpeciesData | (SpeciesData, Transition)
    """
    from molecular.lamda_format import load_lamda, load_species_transition, \
        SpeciesData, Transition

    if name_or_path in _SPECTRA:
        path = _SPECTRA[name_or_path]
    else:
        path = name_or_path

    if not os.path.exists(path):
        available = ", ".join(_SPECTRA.keys())
        raise FileNotFoundError(
            f"Species file not found: {path}\n"
            f"Known species: {available}")

    if freq_GHz is not None:
        return load_species_transition(path, freq_GHz=freq_GHz)
    else:
        with open(path) as f:
            return load_lamda(f.read())


def list_species():
    """Return list of short names for known embedded species."""
    return list(_SPECTRA.keys())
