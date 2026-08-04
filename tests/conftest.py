"""Shared test fixtures for the line_rt_pipeline test suite.

Several test modules monkeypatch ``core.iterator.run_kratos_cycle``
(and ``resolve_kratos_bin``) to inject a fake Kratos.  Without
restoration the patch leaks into later tests that need the real
binary.  This autouse fixture saves and restores both symbols around
every test, regardless of which module set them.
"""

import sys;
import os;
import pytest;

sys.path.insert( 0, os.path.dirname( os.path.dirname( \
    os.path.abspath( __file__ ) ) ) );

import core.iterator as _it_mod;  # noqa: E402


@pytest.fixture( autouse = True )
def _restore_kratos_cycle( ):
    orig_cycle = _it_mod.run_kratos_cycle;
    orig_bin   = _it_mod.resolve_kratos_bin;
    yield;
    _it_mod.run_kratos_cycle = orig_cycle;
    _it_mod.resolve_kratos_bin = orig_bin;
