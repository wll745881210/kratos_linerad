# Plan: update AGENTS.md / README.md / iterator.py for collisional-only thermalization

## Context

Commit c3a9f32 removed the Planck/blackbody (T_rad) term from
`solve_populations`. Thermalization now comes ONLY from collisional
detailed balance. The docs still claim "initial populations are ALWAYS
thermalised to LTE" — that is now wrong: without colliders there is no
excitation mechanism, so at zero external flux the upper level is empty
(zero emissivity, zero emission photons). The user confirmed
"The AGENTS.md is outdated."

## Files to update

1. `AGENTS.md` line 350 (item 18b) — rewrite the LTE claim:

   Current text (wrong):
   > Initial populations are ALWAYS thermalised to LTE — even with
   > external sources. `SpeciesData.initial_populations(n_species, T=None,
   > colliders=None)` calls `solve_populations` at zero external flux when
   > a temperature is provided, so cycle-0 opacity and emissivity are
   > physically consistent (all-ground-state would give zero emissivity).

   New text:
   > Initial populations come from `solve_populations` at zero external
   > flux: with colliders the gas relaxes to collisional equilibrium at
   > the gas temperature (cycle-0 opacity and emissivity consistent);
   > WITHOUT colliders there is no excitation mechanism, so the upper
   > level stays empty (all-in-ground-state -> zero emissivity). There is
   > NO blackbody/Planck (T_rad) term anymore — thermalization is purely
   > collisional.

   (Keep the rest of item 18b unchanged: colliders wiring, destruction
   opacity eps formula, emission-only mode, check_consistency note.)

2. `README.md` lines 186-189 — same correction:

   Current:
   > Initial populations are ALWAYS thermalised to LTE at the gas
   > temperature (`SpeciesData.initial_populations(n_species, T=...)`),
   > even when external sources are present, so cycle-0 opacity and
   > emissivity are physically consistent.

   New:
   > Initial populations relax to collisional equilibrium at the gas
   > temperature when colliders are provided
   > (`SpeciesData.initial_populations(n_species, T=..., colliders=...)`);
   > without colliders there is no excitation mechanism and the upper
   > level stays empty (zero emissivity). There is no blackbody (T_rad)
   > term — thermalization is purely collisional.

3. `core/iterator.py` lines 141-145 comment — same correction (see the
   exact replacement text used in the first edit attempt above).

## Not a code change

`solve_populations` behavior itself is correct and stays as-is. This is
a documentation-only alignment. Both notebook TEST cells returning 0.0
is EXPECTED given the commented-out colliders/collision_rates — the
user's notebook must re-enable a collision mechanism to get non-zero
emission.
