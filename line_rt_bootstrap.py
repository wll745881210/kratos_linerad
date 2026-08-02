"""Bootstrap loader for line_rt_pipeline - run WITHOUT installation.

Allows scripts and notebooks to use the pipeline by pointing at the
pipeline directory, with no ``pip install`` and no manual
``sys.path`` manipulation:

.. code-block:: python

    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'line_rt_bootstrap',
        os.path.expanduser( '~/Seafile/seafile_sync/code/line_rt_pipeline/line_rt_bootstrap.py' ) );
    lr = importlib.util.module_from_spec( spec );
    spec.loader.exec_module( lr );

    rt = lr.LineRt( ... )             # high-level orchestrator
    ti = lr.TransitionInfo( 'CO', 0 ) # species selection
    res = rt.run()

The bootstrap adds its own directory to ``sys.path`` once, then
re-exports the most-used classes/functions for convenience.

If the pipeline IS installed (``pip install -e .``), the bootstrap is
not needed - ``from core.line_rt import LineRt`` works directly from
any directory.
"""

import os, sys

_PIPELINE_DIR = os.path.dirname( os.path.realpath( __file__ ) );
if _PIPELINE_DIR not in sys.path:
    sys.path.insert( 0, _PIPELINE_DIR );

#  Re-export the public API so callers can use ``lr.LineRt`` etc.
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

#  CGS constants (also exported for convenience)
AU   = 1.49598e13;   # cm
Lsun = 3.828e33;     # erg/s
