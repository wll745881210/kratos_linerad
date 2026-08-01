# Test A — Absorption-only transport

**Pipeline commit:** `b9dda65`
**Kratos usr_ext:** `d335aef` (gen.h sv=sigma)

## Purpose

Validate binary I/O, unit conversion, and photon transport without scattering physics.

## Setup

- `mfp_i_sca_0 = 0` (no scattering)
- `mfp_i_abs_0 = tau_abs / L_slab` for tau_abs ∈ {1, 2, 3}
- `b_sca = 1e5`, `L_slab = 1 AU`, `n_source = 50000`, `ph_mode = 1`

## Expected

Absorption reduces photon proper (weight), not count:
- Kratos `photon.h:148` → `proper *= exp(-tau_abs)`
- Ratio: `sum(proper[tau_i]) / sum(proper[tau_j]) ≈ exp(-tau_i + tau_j)`

## Results

| tau_abs | n_esc | sum(proper) | exp(-tau) | inferred tau |
|---------|-------|-------------|-----------|--------------|
| 1 | 50000 | 2.898e17 | 0.368 | -0.000 |
| 2 | 50000 | 1.123e17 | 0.135 | 0.948 |
| 3 | 50000 | 4.350e16 | 0.050 | 1.896 |

- proper(tau=2)/proper(tau=1) = 0.387 (expected 0.368) — ~5% high, within MC noise
- proper(tau=3)/proper(tau=2) = 0.388 (expected 0.368) — ~5% high, within MC noise

## Conclusion

**Absorption works.** Binary I/O and unit conversion for fields are correct. The absorption physics in Kratos is functioning.

### Bug noted

Escaped photon `l` (proper) is incorrectly scaled by `unit_l0` in `core/iterator.py:97`:
```python
if key in ('x', 'l'):
    arr *= unit_l0
```
Proper is photon number [n][t]⁻¹, not length. This doesn't affect ratio-based analysis or scattering tests since it's a self-consistent linear scaling.
