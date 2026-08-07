"""Reader for Athena++ ISM diffuse-cloud simulation data (fiducial dump).

Stitches the 512 meshblocks (16^3 each, 8^3 root layout) into 128^3 arrays.
Units: l0 = parsec, rho0 = m_p, t0 = year.  Species abundances are in
[particle cm^-3] directly (the simulation stores number density).

Usage:
    from read_ism import load_ism_data
    grids = load_ism_data()          # returns dict of 128^3 CGS arrays
    # grids['n_OH'], grids['n_CO'], grids['T'], grids['vel0'], grids['vel1'], grids['vel2']
"""
import h5py
import numpy as np

# --- physical constants ---
PC  = 3.0857e18       # parsec in cm
MP  = 1.6726e-24      # proton mass in g
YR  = 3.1557e7        # year in seconds

# unit conversions (from the simulation's l0=parsec, t0=yr)
UNIT_L0 = PC
UNIT_T0 = YR
V_UNIT  = UNIT_L0 / UNIT_T0     # pc/yr -> cm/s  (approx 9.78e5 km/s)

# box geometry (code units, RootGridX1 = [-0.02, 0.02])
BOX_MIN = -0.02
BOX_MAX =  0.02
N_CELL  = 128
MB      = 16          # meshblock size


def _stitch(hydro_arr, var_idx):
    """Stitch one variable from the (nvar, 512, 16, 16, 16) hydro array.

    The data is in >f4 (big-endian float32).  LogicalLocations maps block
    index -> (i, j, k) in the 8x8x8 root layout.
    """
    ll = hydro_arr.file['LogicalLocations'][:]
    out = np.empty((N_CELL, N_CELL, N_CELL), dtype=np.float32)
    # hydro_arr shape: (nvar, 512, 16, 16, 16) — note C-order: last axis fastest
    for blk in range(ll.shape[0]):
        i, j, k = ll[blk]
        out[i*MB:(i+1)*MB, j*MB:(j+1)*MB, k*MB:(k+1)*MB] = \
            hydro_arr[var_idx, blk].transpose(2, 1, 0)  # (16,16,16)->(z,y,x)?? check
    return out


def _stitch_block(hydro, var_idx, ll):
    """Stitch into a (128,128,128) array (nz, ny, nx) — z slowest, x fastest."""
    out = np.empty((N_CELL, N_CELL, N_CELL), dtype=np.float32)
    for blk in range(ll.shape[0]):
        i, j, k = ll[blk]   # logical location: (i=x-block, j=y, k=z)
        # hydro[var, blk] shape (16,16,16) with axes (x3=z, x2=y, x1=x)
        block = np.asarray(hydro[var_idx, blk])  # (16,16,16) = (z,y,x) in Athena
        out[k*MB:(k+1)*MB, j*MB:(j+1)*MB, i*MB:(i+1)*MB] = block
    return out


def load_ism_data(data_dir='~/scratch/ism/run_fid'):
    """Load the fiducial ISM dump (cycle 200) and return 128^3 CGS grids.

    Returns
    -------
    dict with keys:
        'n_CO'  : CO number density   [cm^-3]
        'n_OH'  : OH number density   [cm^-3]
        'n_H2'  : H2 number density   [cm^-3]  (for colliders)
        'T'     : gas temperature      [K]
        'vel0'  : x-velocity           [cm/s]
        'vel1'  : y-velocity           [cm/s]
        'vel2'  : z-velocity           [cm/s]
        'x_min' : box lower edge (code units)
        'x_max' : box upper edge (code units)
        'unit_l0': parsec in cm
    """
    import os
    data_dir = os.path.expanduser(data_dir)

    # --- hydro data (species + temperature) ---
    f2 = h5py.File(os.path.join(data_dir, 'tm.out2.00200.athdf'), 'r')
    vn = [v.decode() for v in f2.attrs['VariableNames']]
    hydro = f2['hydro']  # (156, 512, 16, 16, 16) >f4
    ll = f2['LogicalLocations'][:]

    idx_T  = vn.index('T')
    idx_CO = vn.index('CO')
    idx_OH = vn.index('OH')
    idx_H2 = vn.index('H2')

    T   = _stitch_block(hydro, idx_T,  ll).astype(np.float64)
    n_CO = _stitch_block(hydro, idx_CO, ll).astype(np.float64)
    n_OH = _stitch_block(hydro, idx_OH, ll).astype(np.float64)
    n_H2 = _stitch_block(hydro, idx_H2, ll).astype(np.float64)
    f2.close()

    # --- prim data (velocities) ---
    f1 = h5py.File(os.path.join(data_dir, 'tm.out1.00200.athdf'), 'r')
    pv = [v.decode() for v in f1.attrs['VariableNames']]
    prim = f1['prim']  # (27, 512, 16, 16, 16) >f4
    ll1 = f1['LogicalLocations'][:]

    idx_v1 = pv.index('vel1')
    idx_v2 = pv.index('vel2')
    idx_v3 = pv.index('vel3')

    # velocities in code units (pc/yr) -> convert to cm/s
    vel0 = _stitch_block(prim, idx_v1, ll1).astype(np.float64) * V_UNIT
    vel1 = _stitch_block(prim, idx_v2, ll1).astype(np.float64) * V_UNIT
    vel2 = _stitch_block(prim, idx_v3, ll1).astype(np.float64) * V_UNIT
    f1.close()

    return dict(
        n_CO=n_CO, n_OH=n_OH, n_H2=n_H2,
        T=T,
        vel0=vel0, vel1=vel1, vel2=vel2,
        x_min=np.array([BOX_MIN]*3),
        x_max=np.array([BOX_MAX]*3),
        unit_l0=UNIT_L0,
    )


if __name__ == '__main__':
    g = load_ism_data()
    print('Grid shapes:', {k: v.shape for k, v in g.items() if hasattr(v, 'shape')})
    print('n_CO  mean=%.3e max=%.3e' % (g['n_CO'].mean(),  g['n_CO'].max()))
    print('n_OH  mean=%.3e max=%.3e' % (g['n_OH'].mean(),  g['n_OH'].max()))
    print('T     mean=%.1f  max=%.1f'  % (g['T'].mean(),   g['T'].max()))
    print('vel0  std=%.3e cm/s (%.3f km/s)' % (g['vel0'].std(), g['vel0'].std()/1e5))
