# Pipeline Python Style Guide + Regulation Plan

## Goal

1. Write `docs/STYLE_GUIDE.md` — a Python style guide for `line_rt_pipeline`,
   mirroring `~/apps/kratos_line_rt/docs/STYLE_GUIDE.md` (C++) and codifying
   the actual hand-written style of `~/apps/kratos_line_rt/visual/*.py`.
2. Regulate ALL Python files + Python cells in Jupyter notebooks under the
   pipeline directory to that style.
3. Delete stale `tests.bak/` (per user decision); regulate `tests/archive/`.
4. Verify (run tests), then git commit (per user instruction).

## User decisions (asked & answered)

| Question | Decision |
|----------|----------|
| tests.bak/ + tests/archive/ | Delete tests.bak/, regulate tests/archive/ |
| Column limit | **79 chars** |
| Docstrings | **Keep docstrings** (pipeline keeps NumPy-style docstrings; visual/ files don't have them — deliberate deviation) |

## Observed style of ~/apps/kratos_line_rt/visual/*.py (the reference)

- Selective imports: `from numpy import array, frombuffer, ndarray` — NOT `import numpy as np`
  (exception: matplotlib rcParams, as in cart_analyses.py)
- Semicolons at end of every simple statement: `self.file_name = file_name;`
- Spaced parens: `( arg )`, `if( cond ):`, empty parens `(  )` / `dict(   )`
- Spaced brackets/slices: `self.hmap[ key ]`, `x_int[ : -1 ]`, `[ : : -1 ]`
- Line continuation with backslash, break AFTER operator:
  `sst = int.from_bytes \` + newline `( self.stream.read( 1 ), 'little' );`
- Multi-line calls break BEFORE `(` (mirrors C++ guide §2.3):
  `pcm = slice_basic \` + newline `( xs0, xs1, ds, args, aux_ax, norm );`
- Column-aligned `=` and def params; spaced named args `dtype = 'f'`, `indexing = 'ij'`
- `%` formatting, no f-strings: `'<%s%d' %  ( dtype, u_size )`
- 60-char `####...` section separators + `#  Label` lines; bare `#` block terminators
- Constants at top of module, aligned `=`, trailing `# CGS ...` unit comments
- 4-space indent; one blank line between functions; snake_case everywhere
- if/elif aligned: `if   axis == 0:` / `elif axis == 1:`
- Measured: max line 67 chars, 0 lines >79, ~896 semicolons across 7 files

## Style guide content (draft for docs/STYLE_GUIDE.md)

Sections (mirroring C++ guide structure):

1. **Column limit** — 79 chars (user decision; reference files max at 67).
2. **Parentheses/brackets spacing** — space inside `( )` and `[ ]` incl. slices;
   empty parens `(  )`; break-before-`(` for multi-line calls with backslash.
3. **Operators & control flow** — spaced binary ops; backslash continuation
   breaking AFTER operator; `if   a:` / `elif b:` aligned; `if not 'x' in args:`.
4. **Declarations & alignment** — column-aligned `=`; module constants block
   with trailing `# CGS` comments; 60-char `####` section separators with
   `#  Label`; bare `#` block terminator; one blank line between functions.
5. **Naming** — snake_case modules/classes/functions/methods/variables; private
   helpers `_snake`; no `_t` suffix (C++ only).
6. **Imports** — selective `from numpy import ...` (no `import numpy as np`);
   aligned backslash continuation for long lists; stdlib → third-party → local.
7. **String formatting** — `%`-style, NO f-strings; double quotes for
   print/format strings, single quotes otherwise.
8. **Comments** — `#` with space; comment above code same indent; `#  Label`
   two spaces; trailing comments only for short lines.
9. **Semicolons** — every simple statement ends with `;`; compound statements
   (`if:`, `for:`, `def:`, `class:`) do NOT.
10. **Class/function style** — 4-space indent, one blank line between methods,
    `self` first param, spaced defaults `dtype = 'f'`.
11. **Docstrings** — ALLOWED and encouraged for public functions (pipeline
    deviation from visual/, per maintainer decision).
12. **Complete example** — regulated sample of write_field_data.
13. **Conformance** — visual inspection; reference files listed.

Full text ready to write to `docs/STYLE_GUIDE.md` (see §Draft below).

## Regulation checklist (all files, ~10,000 lines)

Order: pipeline/ → core/ → molecular/ → cli/setup → ui/web → docs/examples →
docs/reference_mcrt → tests/ + tests/archive/ → notebooks.

| # | File | Lines | Notes |
|---|------|-------|-------|
| 1 | pipeline/kratos_io.py | 261 | binary_io wrapper; has ijkl fix |
| 2 | pipeline/pipeline.py | 254 | run_pipeline() |
| 3 | pipeline/__init__.py | 2 | |
| 4 | core/line_rt.py | 529 | LineRt orchestrator |
| 5 | core/iterator.py | 222 | iterate() |
| 6 | core/fields.py | 161 | field builders, slice_plot_2d |
| 7 | core/consistency.py | 202 | check_consistency() |
| 8 | core/source.py | 104 | photon source gen |
| 9 | core/species_db.py | 65 | |
| 10 | core/visualize.py | 493 | default_plot() |
| 11 | core/__init__.py | 29 | |
| 12 | molecular/lamda_format.py | 558 | compute_opacity etc. |
| 13 | molecular/equilibrium.py | 157 | |
| 14 | molecular/lamda_fetcher.py | 66 | |
| 15 | molecular/synthetic_molecule.py | 66 | |
| 16 | molecular/__init__.py | 3 | |
| 17 | cli.py | 176 | |
| 18 | setup.py | 22 | |
| 19 | ui/panels.py | 151 | |
| 20 | ui/widgets.py | 101 | |
| 21 | ui/__init__.py | 0 | |
| 22 | web/app.py | 33 | |
| 23 | web/__init__.py | 0 | |
| 24 | docs/examples/plane_parallel_hl.py | 107 | |
| 25 | docs/examples/plane_parallel_lowlevel.py | 130 | |
| 26 | docs/reference_mcrt/mcrt.py | 528 | numba reference MCRT |
| 27 | docs/reference_mcrt/mcrt_fp32.py | 528 | |
| 28 | docs/reference_mcrt/plot_neufeld.py | 272 | |
| 29 | docs/reference_mcrt/__init__.py | 1 | |
| 30 | tests/test_absorption.py | 352 | |
| 31 | tests/test_scaling_wide.py | 492 | standalone, --kratos-root |
| 32 | tests/test_absorption_scattering.py | 605 | standalone |
| 33 | tests/archive/compare_escaped.py | 313 | regulate |
| 34 | tests/archive/test_neufeld.py | 370 | regulate |
| 35 | tests/archive/test_ph_mode1_vs_python.py | 245 | regulate |
| 36 | tests/archive/test_scaling.py | 347 | regulate |
| — | tests.bak/ (9 files) | 776 | **DELETE** (user decision) |
| 37 | docs/examples/plane_parallel_hl.ipynb | cells | regulate Python cells |
| 38 | ui/notebook.ipynb | cells | regulate Python cells |
| 39 | docs/reference_mcrt/test_reference.py.bak | — | already deleted, commit |

Regulation transforms per file (mechanical):
- `import numpy as np` → selective `from numpy import ...` (collect used names)
- Add `;` to simple statements (NOT after `:`, `def`, `class`, compound heads)
- Space inside all `( )` and `[ ]` (incl. slices `[ : : -1 ]`)
- Backslash continuation at 79-col overflow, breaking after operator
- Multi-line calls: break before `(` with backslash
- `f'...'` → `%`-style formatting
- Column-align groups of related `=`
- Insert `####...` section separators + `#` block terminators
- Keep docstrings; convert inline comments to above-line where >79 cols
- Keep shebangs, module docstrings, AGENTS.md-referenced API names/returns

Critical: do NOT change any function signature, return value, or behavior.
AGENTS.md pitfall #9: `write_photon_data` returns scale; keep all contracts.

## Verification

1. `python3 -c "import sys; sys.path.insert(0,'.'); import cli, core.line_rt, core.fields, pipeline.kratos_io, molecular.lamda_format"` (syntax + import check)
2. `python3 -m py_compile` on every regulated file
3. Notebooks: `python3 -m json.tool` validate; nbformat load check
4. Run `tests/test_absorption.py` (pure Python MCRT, no Kratos needed if standalone)
5. Run `tests/test_scaling_wide.py --kratos-root ~/apps/kratos_line_rt` (PASS/FAIL exit code) — Kratos binary untouched, regression check
6. `tests/test_absorption_scattering.py` similarly
7. `python3 docs/reference_mcrt/plot_neufeld.py` (quick smoke, may need /tmp/line_rt)

## Commit

Single commit (user: "Please git commit after you finish that."):
- `docs/STYLE_GUIDE.md` (new)
- all regulated .py files + 2 notebooks
- delete tests.bak/ (9 files)
- commit ` D docs/reference_mcrt/test_reference.py.bak` deletion
- Message style: `style: add Python STYLE_GUIDE.md; regulate all pipeline files`

## Execution mode note

Current session permission rules deny edits outside `.opencode/plans/*.md`
and `~/.local/share/opencode/plans/*.md`. After approving this plan, the
execution phase needs edit permission for the pipeline tree (or run in a
mode where edits are allowed).
