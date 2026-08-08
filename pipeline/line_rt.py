"""Public facade for line_rt_pipeline.

This module re-exports the most-used classes and functions so that
users need a single import regardless of whether the pipeline is
installed or loaded via ``importlib``.

Installed (``pip install -e .``)::

    from line_rt import LineRt, TransitionInfo

Without installation (works with symlinks too)::

    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'line_rt', '/path/to/line_rt_pipeline/line_rt.py' )
    line_rt = importlib.util.module_from_spec( spec )
    spec.loader.exec_module( line_rt )
    from line_rt import LineRt, TransitionInfo

In both cases the import syntax is identical after loading.
"""

import os, sys

#  When loaded via importlib (not installed), this file's directory
#  is NOT on sys.path yet - add it so ``import core`` works.
_PIPELINE_DIR = os.path.dirname( os.path.realpath( __file__ ) );
if _PIPELINE_DIR not in sys.path:
    sys.path.insert( 0, _PIPELINE_DIR );

#  Re-export the public API.
from core.line_rt              import LineRt;
from core.iterator             import iterate;
from core.pipeline             import run_pipeline, resolve_kratos_bin;
from core.kratos_io            import write_field_data, write_photon_data, \
                                      read_output;
from core.source               import make_cartesian_mesh;
from core.visualize            import default_plot, plot_emergent_spectrum;
from molecular.transition_info import TransitionInfo, \
                                      show_available_species, \
                                      show_available_transitions;
from molecular.lamda_format    import load_lamda, load_species_transition;

#  CGS constants (exported for convenience).
AU   = 1.49598e13;   # cm
Lsun = 3.828e33;     # erg/s
