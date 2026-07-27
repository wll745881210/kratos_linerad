#!/usr/bin/env python3
"""
Binary I/O helpers for Kratos line_rt.
Thin wrappers around the kratos visual/binary_io module.
"""

import sys, os
sys.path.insert(0, os.path.expanduser('~/Seafile/seafile_sync/code/kratos/visual'))
from binary_io import binary_io
import numpy as np


def write_field_data(filename, fields, mesh):
    """
    Write Kratos field binary.

    Parameters
    ----------
    filename : str
    fields : dict
        Keys: 'mfp_i_sca_0', 'mfp_i_abs_0', 'b_sca',
              'vel_0', 'vel_1', 'vel_2'
        Values: flat float32 arrays of length n_tot
    mesh : dict
        'n_cell' : ndarray[int32], 'x_min' : ndarray[float32],
        'dx' : ndarray[float32]
    """
    bio = binary_io(filename)
    n_cell = np.asarray(mesh['n_cell'], dtype=np.int32)
    x_min  = np.asarray(mesh['x_min'],  dtype=np.float32)
    dx     = np.asarray(mesh['dx'],     dtype=np.float32)

    for prefix in ['mfp_i_sca_0_', 'mfp_i_abs_0_',
                   'b_sca_', 'temp_',
                   'vel_0_', 'vel_1_', 'vel_2_']:
        key = prefix.strip('_')
        if key not in fields:
            continue
        bio.cache(f'{prefix}n_pts', n_cell, dtype='int32')
        bio.cache(f'{prefix}x0',    x_min,  dtype='float32')
        bio.cache(f'{prefix}dx',    dx,     dtype='float32')
        bio.cache(f'{prefix}data',
                  np.asarray(fields[key], dtype=np.float32),
                  dtype='float32')
    bio.save()
    print(f'Wrote fields: {filename}')


def write_photon_data(filename, photons, n_col=None):
    """
    Write Kratos photon binary.

    Parameters
    ----------
    filename : str
    photons : ndarray (n_ph, n_col)
        Columns: x, y, z, dir_x, dir_y, dir_z, proper, [vel], [sigma, amplitude]
    n_col : int, optional
        Default: photons.shape[1]. Must be 7, 8, 9, or 10.
    """
    ph = np.asarray(photons, dtype=np.float64)
    proper_max = abs(ph[:, 6].max()) if ph.shape[1] >= 7 else 0.0
    scale = 1.0
    if proper_max > 1e38:
        scale = 1.0 / proper_max
        ph[:, 6] *= scale
        print(f"Warning: proper weight scaled by {scale:.2e} to fit float32")
    ph = ph.astype(np.float32)
    if n_col is None:
        n_col = ph.shape[1]
    if n_col not in (7, 8, 9, 10, 11):
        raise ValueError(f'n_col must be 7, 8, 9, or 10, got {n_col}')

    bio = binary_io(filename)
    bio.cache('par_n_col', n_col, dtype='int32')
    bio.cache('par_n_par', ph.shape[0], dtype='int64')
    bio.cache('par_par_dat', ph, dtype='float32')
    bio.save()
    print(f'Wrote photons: {filename} ({ph.shape[0]} photons, {n_col} cols)')
    return scale


def read_output(filename):
    """
    Read Kratos mesh output binary.

    Returns
    -------
    dict with keys:
      'n_cell', 'x_min', 'dx' — mesh metadata
      'flx' — effective flux array (n_tot + ghosts stripped to n_tot, float32)
      'excitation_flux' — flux for excitation array (n_tot, float32)
      'photons' — dict with keys 'x', 'dir', 'l', 'vel' (escaped photons only)
    """
    import numpy as np

    bio = binary_io(filename)
    bio.open()
    result = {}

    # Read all metadata from first block
    n_cell = None
    n_gh   = None
    n_int  = 1
    for prefix in ['', 'block_0|']:
        for key in bio.hmap:
            if not key.startswith(prefix):
                continue
            base = key[len(prefix):]
            if base == 'n_ceff':
                n_cell = bio.as_array(key, 'i')
            elif base == 'xf0':
                result['x_min'] = bio.as_array(key, 'f')
            elif base == 'dx0':
                result['dx'] = bio.as_array(key, 'f')

    # Read ghost cells and n_fl d from any field
    for key in bio.hmap:
        if key.startswith('block_') and key.endswith('|rad_flx_n_gh'):
            n_gh = bio.as_array(key, 'i')
            break
    for key in bio.hmap:
        if key.startswith('block_') and key.endswith('|rad_flx_n_int'):
            n_int = int(bio.as_array(key, 'i')[0])
            break

    if n_cell is not None:
        result['n_cell'] = n_cell
        n_tot = int(np.prod(n_cell))

        def _strip_ghosts(full_arr, n_cell, n_gh, n_int):
            """Extract effective cells from Kratos field including ghosts.

            Kratos stores fields in C++ row-major order: cells[nz][ny][nx],
            so nx varies fastest in memory.  Reshape accordingly to match
            hydro_data.get_field() convention.
            """
            if n_gh is None or np.all(n_gh == 0):
                return full_arr[:n_tot * n_int]

            nz_w = int(n_cell[2]) + 2 * int(n_gh[2])
            ny_w = int(n_cell[1]) + 2 * int(n_gh[1])
            nx_w = int(n_cell[0]) + 2 * int(n_gh[0])
            rsh = full_arr.reshape(nz_w, ny_w, nx_w, n_int)
            gh2, gh1, gh0 = int(n_gh[2]), int(n_gh[1]), int(n_gh[0])
            eff = rsh[gh2:gh2+int(n_cell[2]),
                       gh1:gh1+int(n_cell[1]),
                       gh0:gh0+int(n_cell[0]), :]
            return eff.reshape(-1).copy()

        for key in bio.hmap:
            if key.startswith('block_') and key.endswith('|rad_flx_field'):
                full = bio.as_array(key, 'f')
                result['flx'] = _strip_ghosts(full, n_cell, n_gh, n_int)
            elif key.startswith('block_') and key.endswith('|rad_excitation_flux_field'):
                full = bio.as_array(key, 'f')
                result['excitation_flux'] = _strip_ghosts(full, n_cell, n_gh, n_int)
            elif key.startswith('block_') and key.endswith('|rad_exc_rate_field'):
                full = bio.as_array(key, 'f')
                result['exc_rate'] = _strip_ghosts(full, n_cell, n_gh, n_int)
            elif key.startswith('block_') and key.endswith('|rad_ray_flx_field'):
                full = bio.as_array(key, 'f')
                result['ray_flx'] = _strip_ghosts(full, n_cell, n_gh, n_int)
            elif key.startswith('block_') and key.endswith('|rad_ray_exc_flux_field'):
                full = bio.as_array(key, 'f')
                result['ray_exc_flux'] = _strip_ghosts(full, n_cell, n_gh, n_int)

    # Escaped photons
    phot = {}
    for raw_key in bio.hmap:
        if '_rank_' in raw_key and raw_key.endswith('_x'):
            phot['x'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_dir'):
            phot['dir'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_l'):
            phot['l'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_vel'):
            phot['vel'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_sigma'):
            phot['sigma'] = bio.as_array(raw_key, 'f')
        elif '_rank_' in raw_key and raw_key.endswith('_amplitude'):
            phot['amplitude'] = bio.as_array(raw_key, 'f')
    if phot:
        result['photons'] = phot

    bio.close()
    return result


def write_par_file(par_path, template_path, overrides):
    """
    Write a Kratos .par file from a template with key-value overrides.

    Parameters
    ----------
    par_path : str
    template_path : str
    overrides : dict
        Key-value pairs to override in the par file.
    """
    with open(template_path) as f:
        lines = f.readlines()

    with open(par_path, 'w') as f:
        for line in lines:
            written = False
            for key, val in overrides.items():
                if key in line and '=' not in line[:line.index(key) if key in line else 0]:
                    pass
                # Simple key-based replacement
            f.write(line)

    # Better: rewrite with explicit key matching
    with open(par_path, 'w') as f_out:
        for line in lines:
            matched = False
            for key, val in overrides.items():
                # Match lines like "key  = value" or "key = value" or "key value"
                stripped = line.strip()
                if stripped.startswith(key) and not stripped.startswith(key + '_'):
                    leading = line[:len(line) - len(line.lstrip())]
                    # Preserve format: keyword + space + value
                    parts = stripped.split(None, 1)
                    if len(parts) >= 2:
                        rest = parts[1]
                        if '=' in rest:
                            eq_pos = rest.index('=')
                            f_out.write(f'{leading}{key}  = {val}\n')
                        else:
                            f_out.write(f'{leading}{key}  {val}\n')
                    else:
                        f_out.write(f'{leading}{key}  = {val}\n')
                    matched = True
                    break
            if not matched:
                f_out.write(line)

    print(f'Wrote par file: {par_path}')
