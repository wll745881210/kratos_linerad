#!/usr/bin/env python3
"""
Kratos-based population-updating radiative transfer pipeline.

Key insight from mc_ph:
  excitation_flux → excited population → updated opacity → next RT cycle

Flow:
  1. Generate initial field + photon files
  2. Run Kratos(line_rt)
  3. Read output (flx + excitation_flux)
  4. Update populations from excitation_flux
  5. Generate new field + photon files
  6. Repeat until convergence
"""

import subprocess, sys, os, time, shutil
import numpy as np

from kratos_io import (
    write_field_data, write_photon_data, read_output, write_par_file
)

KRATOS_EXE = os.path.expanduser('~/apps/kratos_line_rt/bin/kratos')
_PAR_TEMPLATE = os.path.join(os.path.dirname(__file__), 'line_rt_pipeline.par')


class PopulationModel:
    """
    Abstract base: maps population arrays to Kratos fields and back.

    Each derived class defines:
      - initial_populations() -> dict of arrays
      - make_fields(populations, step, cycle) -> dict of field arrays
      - update_populations(exc_flux, flx, populations, cycle) -> dict of arrays
      - generate_photons(populations, mesh, cycle) -> ndarray
    """

    def initial_populations(self, n_tot):
        raise NotImplementedError

    def make_fields(self, populations, step, cycle):
        raise NotImplementedError

    def update_populations(self, exc_flux, flx, populations, cycle):
        raise NotImplementedError

    def generate_photons(self, populations, mesh, cycle):
        raise NotImplementedError


def make_cartesian_mesh(n_cell, x_min, x_max):
    """Create a uniform Cartesian mesh dictionary."""
    n_cell = np.asarray(n_cell, dtype=np.int32)
    x_min  = np.asarray(x_min,  dtype=np.float32)
    x_max  = np.asarray(x_max,  dtype=np.float32)
    dx     = (x_max - x_min) / n_cell.astype(np.float32)
    return {'n_cell': n_cell, 'x_min': x_min, 'dx': dx,
            'n_tot': int(n_cell.prod())}


def run_kratos_cycle(work_dir, cycle, field_file, photon_file,
                     prefix, par_template, par_overrides):
    """
    Run one Kratos cycle.

    Returns
    -------
    output : dict from read_output()
    log_text : str
    elapsed : float
    """
    par_path = os.path.join(work_dir, f'{prefix}.par')
    log_path = os.path.join(work_dir, f'{prefix}.txt')

    overrides = dict(par_overrides)
    overrides.update({
        'field_file': field_file,
        'photon_file': photon_file,
        'prefix_output': prefix,
    })

    write_par_file(par_path, par_template, overrides)

    t0 = time.time()
    result = subprocess.run(
        [KRATOS_EXE, par_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=3600, cwd=work_dir
    )
    elapsed = time.time() - t0
    log_text = result.stdout.decode('utf-8', errors='replace')

    if result.returncode != 0:
        print(f'[cycle {cycle}] Kratos FAILED after {elapsed:.0f}s')
        print(log_text[-500:])
        return None, log_text, elapsed

    out_bin = os.path.join(work_dir, f'{prefix}_00000.bin')
    if not os.path.exists(out_bin):
        print(f'[cycle {cycle}] No output file: {out_bin}')
        return None, log_text, elapsed

    output = read_output(out_bin)
    output['_bin_path'] = out_bin
    output['_log'] = log_text
    output['_elapsed'] = elapsed

    print(f'[cycle {cycle}] Done in {elapsed:.0f}s, '
          f'bin={os.path.basename(out_bin)}')
    return output, log_text, elapsed


def run_pipeline(model, mesh, work_dir, n_cycles=3,
                 n_photon=10000, n_step=1000, n_scat=100,
                 n_fld=2, ph_mode=0, par_overrides=None,
                 keep_intermediate=True):
    """
    Run the full population-updating pipeline.

    Parameters
    ----------
    model : PopulationModel
    mesh : dict from make_cartesian_mesh()
    work_dir : str
    n_cycles : int
    n_photon : int
    n_step, n_scat : int
    n_fld : int  Number of flux/field components
    ph_mode : int  0=coherent, 1=CFR
    par_overrides : dict  Additional par file overrides

    Returns
    -------
    results : list of dicts (one per cycle)
    final_populations : dict
    """
    os.makedirs(work_dir, exist_ok=True)
    n_tot = mesh['n_tot']

    if par_overrides is None:
        par_overrides = {}

    base_overrides = {
        'n_cell_global': ' '.join(str(v) for v in mesh['n_cell']),
        'x_min': ' '.join(str(v) for v in mesh['x_min']),
        'x_max': ' '.join(
            str(mesh['x_min'][i] + mesh['dx'][i] * mesh['n_cell'][i])
            for i in range(3)),
        'n_step': str(n_step),
        'n_scat': str(n_scat),
        'n_photon': str(n_photon),
        'ph_mode': str(ph_mode),
        'n_fld': str(n_fld),
        'n_cycle_lim': '0',
    }
    base_overrides.update(par_overrides)

    populations = model.initial_populations(n_tot)
    results = []

    for cycle in range(n_cycles):
        print(f'\n=== Cycle {cycle} / {n_cycles} ===')

        # Generate fields
        fields = model.make_fields(populations, step='pre', cycle=cycle)
        field_file = os.path.join(work_dir, f'fields_cycle{cycle}.bin')
        write_field_data(field_file, fields, mesh)

        # Generate photons
        photons = model.generate_photons(populations, mesh, cycle)
        photon_file = os.path.join(work_dir, f'photons_cycle{cycle}.bin')
        write_photon_data(photon_file, photons)

        # Run Kratos
        prefix = f'cycle{cycle}'
        output, log_text, elapsed = run_kratos_cycle(
            work_dir, cycle, field_file, photon_file,
            prefix, _PAR_TEMPLATE, base_overrides
        )

        if output is None:
            print(f'Pipeline stopped at cycle {cycle}')
            break

        # Extract exc_flux and flx — keep as flat arrays (include ghosts)
        # The model's make_fields uses the same field size as Kratos output,
        # so we don't need to strip ghost cells.
        if 'excitation_flux' in output:
            output['exc_flux_flat'] = output['excitation_flux']
        elif 'fab' in output:
            output['exc_flux_flat'] = output['fab']
        if 'flx' in output:
            output['flx_flat'] = output['flx']

        output['cycle'] = cycle
        output['populations'] = {k: v.copy() for k, v in populations.items()}
        results.append(output)

        # Update populations
        new_pops = model.update_populations(
            output.get('exc_flux_flat', None),
            output.get('flx_flat', None),
            populations, cycle
        )
        populations = new_pops

    # Save final populations to output
    if output is not None and 'fab_3d' in output:
        output['_final_populations'] = populations

    return results, populations
