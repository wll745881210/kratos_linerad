# line_rt_pipeline Python Style Guide

This document is the authoritative style reference for all Python code
under `line_rt_pipeline/`.  Every new file must follow it; existing files
should be brought into compliance when touched.

---

## 1. Line length

**79 characters** per line (PEP 8 default), with a hard ceiling of 99
for unavoidable cases (long URLs in docstrings, deep-nested data
access).  If you exceed 99, restructure the expression.

---

## 2. Imports

### 2.1 Order

```python
import os
import sys
from pathlib import Path

import numpy as np

from pipeline.kratos_io import write_field_data, read_output
from core.line_rt import LineRt
from docs.reference_mcrt.mcrt import mcrt_slab
```

1. Standard library
2. Third-party (`numpy`, `scipy`)
3. Project-internal (relative imports)

### 2.2 Style

- Use `from X import Y` for frequently-used names.
- Use `import X` only when the module itself is the primary namespace
  (`import numpy as np`).
- Never use `from X import *`.

---

## 3. Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Modules | `snake.py` | `kratos_io.py`, `lamda_format.py` |
| Classes | `PascalCase` | `LineRt`, `ConsistencyError` |
| Functions | `snake_case` | `make_fields()`, `write_field_data()` |
| Variables | `snake_case` | `mfp_i_sca_0`, `b_sca_code` |
| Constants | `UPPER_SNAKE` | `UNIT_L0`, `UNIT_T0`, `KRATOS_BIN` |
| Private | `_snake` | `_build_usampler()`, `_transport_photon()` |
| Parameters | `snake_case` | `tau0`, `n_photons`, `a_voigt` |
| Dict keys | `snake_with_suffix` | `'mfp_i_sca_0_'`, `'vel_0_'` |
| CLI flags | `--kebab-case` | `--tau0`, `--no-kratos`, `--n-cell` |

### 3.1 Suffix conventions

- `_i_` = inverse (reciprocal): `mfp_i_sca_0` is σ₀ × n_lower (cm⁻¹),
  NOT mean free path.
- `_0_` = at line centre.
- `_code` = in code units (after dividing by `UNIT_L0` / `UNIT_T0`).
- `_cgs` = in CGS units.
- `_bin` = binary file path.

---

## 4. Function signatures

Limit to **4 parameters per line**; break before the closing paren:

```python
def update_populations(
    exc_flux, flx, pops, cycle, dx, b_sca, T,
    colliders, transition_idx,
):
    ...
```

Trailing comma after the last parameter is mandatory when breaking.

---

## 5. Spacing

```python
#  ✓
x = a + b
y = func( arg1, arg2 )
d = { 'key': value }
a_list = [ 1, 2, 3 ]

#  ✗
x=a+b
y=func(arg1,arg2)
d={'key':value}
```

- Spaces around binary operators (`=`, `+`, `-`, `*`, `/`, `==`, `!=`).
- Spaces after commas in argument lists.
- Spaces after `#` in comments.
- No space between function name and `(` in calls: `func( x )` not
  `func (x)`.

---

## 6. Docstrings

Use NumPy-style docstrings:

```python
def compute_opacity(pops, b_sca, transition_idx):
    """Compute scattering mean free path from population data.

    Parameters
    ----------
    pops : dict
        Population dict with 'n_lower', 'n_upper', etc.
    b_sca : float
        Doppler b parameter for scattering (cm/s).
    transition_idx : int
        Index of the transition.

    Returns
    -------
    mfp_sca : np.ndarray
        Scattering MFP per cell (cm).
    """
    ...
```

---

## 7. Comments

- One blank line before a comment block.
- `# ` followed by a space and a capital letter (for sentence-level).
- No trailing comments on code lines unless very short.
- Use `# TODO(name):` or `# FIXME(name):` for actionable markers.

---

## 8. Type hints

Use type hints on public function signatures when the type is not
obvious from the name:

```python
def make_fields(
    pops: dict,
    step: int,
    cycle: int,
    base_fields: dict,
    unit_l0: float,
    unit_t0: float,
    transition_idx: int,
) -> dict:
    ...
```

For internal/private helpers, type hints are optional but encouraged
when the signature is complex.

---

## 9. Error handling

```python
#  ✓ — specific exception, informative message
if n_cell < 2:
    raise ValueError(
        f"n_cell_global must be >= 2, got {n_cell}"
    )

#  ✗ — bare except, silent
try:
    ...
except:
    pass
```

- Never use bare `except:`.
- Catch specific exceptions.
- Include the invalid value in the message when raising `ValueError`.

---

## 10. File organization

Each module file should follow this order:

1. Module docstring
2. Imports
3. Constants
4. Private helpers
5. Public functions
6. Classes
7. `if __name__ == '__main__':` block

---

## 11. Test files

Test files live under `tests/` and follow the pattern `test_*.py`.

```python
#!/usr/bin/env python3
"""Short description of what this test validates."""

import argparse
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tau0', type=float, default=10000)
    parser.add_argument('--a', dest='a_voigt', type=float, default=0.01)
    args = parser.parse_args()
    ...


if __name__ == '__main__':
    main()
```

---

## 12. Kratos binary I/O conventions

### 12.1 Field dict keys

```python
fields = {
    'mfp_i_sca_0_': np.ndarray,   # inverse MFP at line centre
    'mfp_i_abs_0_': np.ndarray,   # inverse absorption MFP
    'b_sca_':        np.ndarray,   # Doppler b for scattering
    'vel_0_':        np.ndarray,   # bulk velocity x
    'vel_1_':        np.ndarray,   # bulk velocity y
    'vel_2_':        np.ndarray,   # bulk velocity z
}
```

### 12.2 Photon binary columns

```
0: x, 1: y, 2: z,
3: dir_x, 4: dir_y, 5: dir_z,
6: proper,
7: vel (optional, CGS→code before write, code→CGS after read),
8: sv  (optional, Gaussian σ = b_sca / sqrt(2))
```

### 12.3 Unit conversion

| Quantity | Python → Kratos | Kratos → Python |
|----------|----------------|-----------------|
| Positions | `/ UNIT_L0` | `× UNIT_L0` |
| Velocities | `× UNIT_T0 / UNIT_L0` | `× UNIT_L0 / UNIT_T0` |
| Inverse lengths | `× UNIT_L0` | `/ UNIT_L0` |

### 12.4 Par file `[cycle]` section

Canonical pattern:

```ini
[cycle]
prefix_output  = test
n_cycle_lim    = 0
t_lim          = 600.0
t_output_next  = 1e32
dt_output      = 1e32
final_output   = 1
```

This guarantees exactly one output file: `{prefix}_00000.bin`.

---

## 13. Common patterns

### 13.1 Generating Kratos inputs

```python
from pipeline.kratos_io import write_field_data, write_photon_data

fields = { ... }    # dict of field arrays
mesh = {             # mesh metadata
    'n_cell': np.array([nx, ny, nz], dtype=np.int32),
    'x_min':  np.array([xmin, ymin, zmin], dtype=np.float32),
    'dx':     np.array([dx, dy, dz], dtype=np.float32),
}
write_field_data('fields.bin', fields, mesh)
write_photon_data('photons.bin', photon_array, n_col=9)
```

### 13.2 Running Kratos

```python
import subprocess
result = subprocess.run(
    [KRATOS_BIN, 'par_file.par'],
    cwd=WORKDIR,
    capture_output=True,
    text=True,
    timeout=600,
)
```

### 13.3 Reading Kratos output

```python
from pipeline.kratos_io import read_output
out = read_output('test_00000.bin')
# out = {
#   'photons': {'pos': ..., 'dir': ..., 'proper': ..., 'vel': ..., 'sv': ...},
#   'n_cell': (nx, ny, nz),
#   ...
# }
```

---

## 14. Physics conventions

- All quantities are in photon-number units (not erg/s).
- `mfp_i_sca_0` = σ₀ × n_lower (inverse MFP at line centre).
- `b_sca` = Doppler b for scattering overlap integral (cm/s).
- Half-slab convention: `mfp_i_sca_0 = 2 × tau0 / L_slab`.
- `ph_mode=0` = CFR (Gaussian), `ph_mode=1` = R_IIA (USampler).
- The Neufeld mean-depth τ convention: `tau_fid = sqrt(π) × tau0_LC`.
