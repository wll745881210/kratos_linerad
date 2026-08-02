# Plan: TransitionInfo class + LineRt integration

## Goal

Make species+transition a first-class object `TransitionInfo` that the high-level
interface (LineRt, add_source, plotting) consumes. User decisions:

1. Class name: **`TransitionInfo`** (CamelCase, matches `SpeciesData`/`LineRt`).
2. LineRt: `transition_info` is **required for species use** — `species` and
   `transition_idx` are REMOVED from the LineRt constructor (Group-2-only runs,
   i.e. `b_sca`+`mfp_i_sca_0` without any species, still need no object).
3. `add_source`: auto-λ — `wavelength` defaults to the transition's λ when
   `transition_info` is passed and `wavelength` is None; explicit wins.

## 1. New module `molecular/transition_info.py`

```python
class MolecularMassError( ValueError ):
    """Species not in the built-in mass table and no mol_mass given."""

_MOL_MASS = { 'CO': 28.0, 'OH': 17.0, 'H2O': 18.0, 'NH3': 17.0,
              'CH3OH': 32.0, 'CS': 44.0, 'SiO': 44.0, 'HCN': 27.0,
              'HCO+': 29.0, 'N2H+': 29.0, 'SO': 48.0, 'SO2': 64.0,
              'H2CO': 30.0, 'H2S': 34.0, 'CN': 26.0, 'NO': 30.0,
              'C2H': 25.0, 'HNC': 27.0 }   # amu

class TransitionInfo:
    species: str            # 'CO', 'OH', ... (name or .dat path)
    transition_idx: int     # 0-based index into species_data.transitions
    species_data: SpeciesData
    transition: Transition  # resolved from species_data + idx/value
    mol_mass: float         # amu

    def __init__( self, species, transition_idx = 0, *, \
                  value = None, unit = None, freq_GHz = None, \
                  mol_mass = None ):
        # 1. load species_data: name in _SPECTRA -> embedded; else search
        #    LAMDA cache dir (~/.line_rt_interface/lamda_cache/<name>.dat);
        #    else os.path.exists -> user path; else raise FileNotFoundError
        #    listing available species (embedded + cached).
        # 2. resolve transition: by transition_idx, or by value+unit
        #    (frequency / wavelength / photon energy; see _VALUE_TO_GHZ)
        #    via the existing specify_transition freq-GHz matching machinery;
        #    freq_GHz is a backward-compat alias for value+unit='GHz'.
        # 3. mol_mass: explicit arg wins; else _MOL_MASS.get( species );
        #    else raise MolecularMassError telling the user to pass mol_mass.

Unit specification (user requirement 2026-08-02):
- The transition is specified by ONE of: (1) frequency, (2) wavelength,
  (3) photon energy — via a `value` + `unit` pair. The unit string decides
  the physical quantity:
  - frequency units:  'GHz', 'THz'
  - wavelength units: 'cm', 'mm', 'um' (micron), 'nm', 'angstrom'
  - energy units:     'eV', 'erg'
- Conversion to freq_GHz (then existing machinery):
  - GHz: nu = value;  THz: nu = value * 1e3
  - wavelength: nu_GHz = c_cgs / ( value * to_cm( unit ) ) / 1e9
  - energy: nu_GHz = value * to_erg( unit ) / h_cgs / 1e9

    def show_transition( self ):
        # detailed print: species, idx, upper/lower level (E_u/K, g), A_ul,
        # freq/GHz, wavelength/um, mol_mass + availability note.

    def show_transitions( self ):
        # brief table of ALL transitions of this species
        # (reuse SpeciesData.show_transitions format, index column).

    def show( self ):
        # show_transition() + show_transitions().

def show_available_species( ):
    # print embedded species (_SPECTRA keys) + cached names
    # (get_cached_species from lamda_fetcher). Returns list.

def show_available_transitions( species ):
    # load species (embedded/cache/path) and print show_transitions table
    # without requiring a TransitionInfo object.
```

Design notes:
- No auto-download from LAMDA in the constructor (per user point 0: user decides).
- `value` + `transition_idx` both given -> transition_idx wins; value used to
  auto-find the closest transition (existing `specify_transition` logic).
- Module stays in `molecular/` so it can reach embedded + cache without
  importing `core/` (no cycles). `core/line_rt.py` imports it.

## 2. `core/line_rt.py` changes

- Constructor: remove `species`, `transition_idx` params; add
  `transition_info = None`. Store `self._transition_info`.
  - `_resolve_species( )`: `self._species_obj = ti.species_data` when given.
  - `self._transition_idx` derived from `ti.transition_idx` (needed by
    `_resolve_mfp_species`, `_resolve_a_voigt`, iterator calls).
  - `self._mol_mass` defaults to `ti.mol_mass` when transition_info given
    (explicit `mol_mass` arg still overrides).
- `add_source( ..., transition_info = None, ... )`: if `transition_info` given
  and `wavelength is None` -> `wavelength = c_cgs / ( freq_GHz * 1e9 )`.
- `check_consistency( )` call: pass species_obj + transition_idx sourced from
  transition_info (Group-1 check unchanged in spirit).
- Update class docstring examples to use TransitionInfo.

## 3. Plotting (`core/visualize.py`)

- `default_plot( results, transition_info = None, **kwargs )`: when given, use
  `ti.transition` in plot titles (e.g. `'CO J=2->1'` instead of generic label);
  no behavior change when None. Keep positional-compat with current callers.

## 4. Callers updated

- `cli.py`: build `TransitionInfo` from `--species`/`--transition-idx`/
  `--freq-ghz`/`--mol-mass` args; pass to LineRt; `--list-species` prints
  `show_available_species( )`; add `--list-transitions <species>`.
- `docs/examples/plane_parallel_hl.py`, `plane_parallel_lowlevel.py`
  (lowlevel: `iterate( )` still takes raw `species` object — unchanged; only
  high-level examples change), `plane_parallel_hl.ipynb`, `ui/notebook.ipynb`:
  construct `TransitionInfo` and pass it.
- `ui/panels.py`/`ui/widgets.py`: species/transition widgets build a
  `TransitionInfo` (mol_mass auto from table; error surfaced in widget).
- `web/app.py`: same via panels.

## 5. Tests

- New smoke test in `tests/` (standalone, e.g. `tests/test_transition_info.py`):
  - `show_available_species( )` lists CO, OH.
  - `TransitionInfo( 'CO', 0 )`: transition J=1->0 (115.271 GHz, A=7.2e-08),
    mol_mass == 28.0; `show_transition( )`/`show_transitions( )` run.
  - `freq_GHz = 230.538` resolves transition_idx 1 (J=2->1).
  - Unknown species raises FileNotFoundError listing available.
  - Unknown mass species (e.g. fake name via temp .dat) raises
    `MolecularMassError`; with `mol_mass = 44.0` works.
  - LineRt smoke: `LineRt( transition_info = ti, n_species, temperature )` +
    `add_source( transition_info = ti )` auto-λ run (short n_step) matches
    previous `species = 'CO'` behavior.
  - cli.py `--list-species` and full run via FakeLineRt stub.
- Re-run `test_scaling_wide.py` smoke to confirm no regression.

## 6. Docs

- AGENTS.md: update high-level API description (LineRt takes TransitionInfo),
  pitfall note that species-group requires TransitionInfo.
- README examples if they use `species = ...`.

## Order of implementation

1. `molecular/transition_info.py` + smoke test.
2. `core/line_rt.py` + `core/visualize.py` integration, keep old path working
   via Group-2 tests; update `docs/examples/*.py`, run them.
3. `cli.py` + tests.
4. Notebooks + ui/web.
5. Full test sweep + git commit.
