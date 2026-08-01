# line_rt_pipeline Python Style Guide

This document is the authoritative style reference for all Python files
and Jupyter-notebook Python cells under the `line_rt_pipeline` repository
(`core/`, `molecular/`, `pipeline/`, `ui/`, `web/`, `cli.py`, `setup.py`,
`docs/examples/`, `docs/reference_mcrt/`, `tests/`).

It is the Python counterpart of `~/apps/kratos_line_rt/docs/STYLE_GUIDE.md`
(the C++/CUDA typesetting guide for `usr_ext/line_rt/`) and follows the
same principles, adapted to Python syntax.  The reference implementation
of this style is `~/apps/kratos_line_rt/visual/*.py` (e.g. `binary_io.py`,
`hydro_data.py`, `slice_plot.py`).

Every new file must follow this guide; existing files must be brought into
compliance before any unrelated edit touches them.

---

## 1. Column limit

**79 characters** per line (excluding trailing whitespace).  When a line
would exceed 79 columns, break it using the rules in § 2–3.  The column
count includes indentation.

```python
#  OK - 71 columns
key = key.rstrip( '_' ) if key.endswith( '_' ) else key;

#  VIOLATION - 88 columns
result[ 'excitation_flux' ] = _strip_ghosts_3d( bio.as_array( key, 'f' ), n_cell, n_gh, n_int );
```

If an expression truly cannot fit, split it into multiple statements or
extract a local variable.

---

## 2. Parentheses, brackets — spacing and line-breaking

### 2.1 Spaces inside parentheses

Always put a **space** after `(` and before `)`:

```python
#  ✓
f( x )
if( a > 0 ):
range( n )
zip( func, prefix )
dict(   )

#  ✗
f(x)
if (a > 0):
range(n)
```

### 2.2 Empty parentheses

Empty parentheses get **two or three spaces** inside (both occur in the
reference files; pick one and stay consistent within a file):

```python
#  ✓
dict(   )
bio.save(  );
```

### 2.3 Spaces inside brackets

Always put a **space** after `[` and before `]`, including in slices:

```python
#  ✓
self.hmap[ key ]
x_int[ : -1 ]
d_v[ :, :, idx ]
dat.shape[ : : -1 ]

#  ✗
self.hmap[key]
x_int[:-1]
```

### 2.4 Line continuation — backslash

Long lines continue with a **backslash** at the end of the line.  When
the continuation is part of a call, the opening parenthesis goes on the
**next** line, indented one level — break BEFORE `(`:

```python
#  ✓
pcm = slice_basic \
    ( xs0, xs1, ds, args, aux_ax, norm );

#  ✓
sst = int.from_bytes \
    ( self.stream.read( 1 ), 'little' );

#  ✗  (paren on same line as the call)
pcm = slice_basic(
    xs0, xs1, ds, args, aux_ax, norm );
```

When the continuation is an operator expression, break **after** the
operator (mirroring the C++ guide):

```python
#  ✓
sst = int.from_bytes \
    ( self.stream.read( 1 ), 'little' );

#  ✓
print( "file: %s; time = %g" \
       % ( file_name, res.globals[ 'time' ] ) );

#  ✓
if len( x_int ) > 2 and \
   ( loc > x_int[ -1 ] or loc < x_int[ 0 ] ):
```

### 2.5 Multi-line argument lists

Column-align multi-line argument lists; trailing commas are permitted and
align with the closing paren on its own line:

```python
def interp_reg_save( file_name, x0, dx, dat, prefix = '', \
                     int_type   =   'int32' ,\
                     float_type = 'float32' ):
```

---

## 3. Operators and control flow

### 3.1 Binary operators

Space on both sides:

```python
n_total * sizeof( float )
( lo + hi ) >> 1
```

### 3.2 if / elif / else

Spaced parens (§ 2.1); the body on the next line at the normal indent.
Align `if` / `elif` conditions by padding the keyword:

```python
if   axis == 0:
    ...
elif axis == 1:
    ...
elif axis == 2:
```

Use `if not 'xlim' in args:` (the `not ... in` form) as in the reference
files.

### 3.3 for / while

```python
for i_hmap in range( self.s_hmap  ):
    x_int[ i ] = self.get_entry( 'x_int' )[ i ];
```

---

## 4. Declarations and alignment

### 4.1 Column-aligned assignments

Group related assignments and align the `=` signs:

```python
self. file_name =  file_name;
self.      dmap =  dict(   );
self.      hmap =  dict(   );
self. s_hmap    =  0;
```

### 4.2 Module-level constants

Constants live at the top of the module, one per line, aligned, with a
trailing unit comment:

```python
h      = 6.62607e-27;   # CGS Planck constant
kb     = 1.38065e-16;   # CGS Boltzmann constant
c_0    = 2.99792e10;    # CGS speed of light
```

### 4.3 Section separators

Use a full-width comment line (60 `#` characters) plus a `# Label` line
(one space) directly below; no closing `####` line:

```python
############################################################
# Basic binary output reader
############################################################

class binary_io:
```

Inside classes, the separator is 56 `#` characters:

```python
class binary_io:
    ########################################################
    # Initialization and finalization
    def __init__( self,    file_name, cache_used = True ):
```

### 4.4 Blank lines

One blank line between functions.  No blank lines inside short blocks.

---

## 5. Naming

| Element         | Convention    | Example                     |
|-----------------|---------------|-----------------------------|
| Modules         | `snake`       | `kratos_io.py`              |
| Classes         | `snake`       | `binary_io`, `hydro_data`   |
| Functions       | `snake`       | `write_field_data`          |
| Methods         | `snake`       | `as_array`, `get_entry`     |
| Private helpers | `_snake`      | `_strip_ghosts_3d`          |
| Local variables | `snake`       | `n_cell`, `pcm`             |
| Constants       | `snake`       | `n_total`, `s_size_t`       |
| Keywords / dunders | as Python | `__init__`, `__getitem__`   |

(No `snake_t` suffixes — that is C++ only.)

---

## 6. Imports

### 6.1 Selective imports — no `import numpy as np`

Import only the names actually used, directly from the module:

```python
#  ✓
from numpy import array, frombuffer, ndarray
from numpy import zeros, ones, linspace, meshgrid, transpose

#  ✗
import numpy as np
```

For long import lists, align the module names and use a backslash
continuation:

```python
from binary_io   import binary_io
from numpy       import frombuffer, zeros, array, meshgrid,\
                        sqrt, log2, sum, minimum, maximum, \
                        copy, log10, arange, cbrt, unique,\
                        concatenate
from glob        import glob
from bisect      import bisect
from collections import OrderedDict
```

`import numpy as np` is permitted only in modules that legitimately need
the namespace (e.g. `matplotlib` rcParams configuration) — see
`cart_analyses.py` for the sanctioned exception.

### 6.2 Import order

1. Standard library (`sys`, `os`, `math`, ...)
2. Third party (`numpy`, `matplotlib`, `numba`, ...)
3. Local modules (`binary_io`, `kratos_io`, ...)

One blank line between groups.  No blank line between the module
docstring and the first import.

### 6.3 Implicit paths

`core/fields.py`, `core/iterator.py`, `pipeline/kratos_io.py` use a
`sys.path` hack to reach `~/Seafile/seafile_sync/code/kratos/visual`
(or `../pipeline`) — keep it, it is load-bearing (AGENTS.md pitfall 21).

---

## 7. String formatting

Use `%`-style formatting — **no f-strings**:

```python
#  ✓
'<%s%d' %  ( dtype, u_size )
'%s|%s'  % ( block, field )

#  ✗
f'{prefix}data'
```

Use double quotes for strings that contain single quotes or appear in
`print`/format context; single quotes otherwise (as in the reference
files).

---

## 8. Comments

- `#` for single-line comments, with a **space after** `#`.
- Comment **above** the line it explains, at the same indent level.
- Use `#  Label` (two spaces) under a section-separator line (§ 4.3).
- A bare `#` line marks the end of a logical block (after a function, a
  loop, or an `if` body):

```python
        #
        return;
    #
```

- **Docstrings are allowed and encouraged** for public functions and
  classes (NumPy-style, as already used in the pipeline); the pipeline
  keeps docstrings where the `visual/` reference files do not — this is
  a deliberate deviation per maintainer decision.
- Do NOT use `#` on the same line as code unless the comment is short
  and the code line is well under 79 columns.

---

## 9. Semicolons

Every simple statement ends with a semicolon:

```python
self.file_name = file_name;
return;
```

**Import statements are the single exception** — they carry no semicolon
(as in the reference files):

```python
from numpy import array, frombuffer, ndarray
import types
```

Compound statements (`if ...:`, `for ...:`, `def ...:`, `class ...:`)
do NOT get a semicolon after the colon.

---

## 10. Class and function style

```python
class binary_io:
    ########################################################
    # Initialization and finalization
    def __init__( self,    file_name, cache_used = True ):
        self. file_name =  file_name;
        self.      dmap =  dict(   );
        self.      hmap =  dict(   );
        self.cache_used = cache_used;
        #
        self._write_header(  );

    def as_array( self, key, dtype = 'f' ):
        return self._entries[ key ].astype( dtype );
```

- 4-space indent.
- One blank line between methods.
- `self` is the first parameter.
- Default arguments use spaces around `=` (e.g. `dtype = 'f'`).
- Aligned `self.` attribute assignments pad after the dot
  (`self. file_name`, `self.      dmap`); column-align the `=` signs.
- Method calls with a spaced dot are also seen
  (`self.bin_data . open(  );`) — keep whichever reads better, but be
  consistent within a file.

---

## 11. Complete example

```python
#!/usr/bin/env python3
"""
Binary I/O helpers for Kratos line_rt.
Thin wrappers around the kratos visual/binary_io module.
"""

import sys, os
sys.path.insert( 0, os.path.expanduser( \
    '~/Seafile/seafile_sync/code/kratos/visual' ) );
from binary_io import binary_io
from numpy import asarray, int32, float32, pad, array, ravel, float64


############################################################
# Field prefixes
############################################################

_LINE_FIELD_PREFIXES  = [ 'mfp_i_sca_0_', 'mfp_i_abs_0_', 'temp_' ];
_FIXED_FIELD_PREFIXES = [ 'b_sca_', 'vel_0_', 'vel_1_', 'vel_2_' ];


def write_field_data( filename, fields, mesh, unit_l0 = 1.0, group = 'all' ):
    """
    Write Kratos field binary.

    Split into two groups (Task 2): line-dependent fields
    (mfp_i_sca_0, mfp_i_abs_0) that change per cycle / per line,
    and line-independent fields (b_sca, vel) that stay fixed
    across lines.

    Parameters
    ----------
    filename : str
    fields : dict
        Keys: 'mfp_i_sca_0', 'mfp_i_abs_0', 'b_sca',
              'vel_0', 'vel_1', 'vel_2'
        Values: 3D float32 arrays of shape (nz, ny, nx)
    group : {'all', 'line', 'fixed'}
        'line'  - write only line-dependent fields
        'fixed' - write only line-independent fields
    """
    bio = binary_io( filename );
    n_cell = asarray( mesh[ 'n_cell' ], dtype = int32 );
    #
    bio.cache( 'par_n_col', n_cell, dtype = 'int32' );
    bio.save(  );
    print( 'Wrote fields (%s): %s' % ( group, filename ) );
```

---

## 12. Conformance

Compliance is verified by **visual inspection** during review (there is
no automated linter configured for this style).  When in doubt, consult:

- `~/apps/kratos_line_rt/visual/binary_io.py` — spacing, semicolons,
  sections
- `~/apps/kratos_line_rt/visual/interp_gen.py` — aligned signatures,
  backslash continuation
- `~/apps/kratos_line_rt/visual/cart_analyses.py` — constants block,
  rcParams exception
- `~/apps/kratos_line_rt/docs/STYLE_GUIDE.md` — the C++ guide this
  document mirrors
