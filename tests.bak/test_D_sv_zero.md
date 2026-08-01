# Test D — gen.h sv=0 patch

**Pipeline commit:** `b9dda65`
**Kratos usr_ext:** `d335aef` + uncommitted patch (`par.sv = 0.f`)

## Patch

`usr_ext/line_rt/gen.h` line 107:
```diff
-        par.sv  = par.sigma;
+        par.sv  = 0.f;       // set sv=0 for first cell crossing before scatter
```

Kratos rebuilt. Photon's intrinsic Gaussian width sv now starts at 0 (same as old code behavior).

## Test

Reran ph_mode=2 (old Gaussian CFR) at tau0 ∈ {10, 100, 1000}, comparing HWHM before vs after.

## Results

| tau0 | HWHM(before) | HWHM(after) | Change |
|------|-------------|-------------|--------|
| 10   | 1.26        | 1.16        | -8.0%  |
| 100  | 1.60        | 1.58        | -1.5%  |
| 1000 | 2.39        | 2.34        | -1.9%  |

## Conclusion

**sv init is NOT the primary cause of the Neufeld failure.** The patch has ≤8% effect at τ₀=10 (where few scattering events dominate) and <2% at τ₀≥100. The initial sv value is quickly washed out by scattering events.

The root cause lies elsewhere — likely in the b_sca field value, profile function normalization, or the overlap integral scaling. Since both ph_mode=1 and ph_mode=2 show the same HWHM vs τ₀ scaling failure (β ≈ 0.12-0.17 instead of 1/3), the bug is in code common to both modes.
