import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
from kratos_io import write_field_data, read_output, write_photon_data

import numpy as np

from .source import AU


def uniform_field(value, n_tot):
    return np.full(n_tot, value, dtype=np.float32)


def spherical_power_law(r_cc, theta_cc, n0, r0, p):
    r_cc = np.asarray(r_cc, dtype=np.float64)
    return (n0 * (r_cc / r0) ** p).astype(np.float32)


def cylindrical_disk(R_cc, z_cc, n0, R0, H0):
    R_cc = np.asarray(R_cc, dtype=np.float64)
    z_cc = np.asarray(z_cc, dtype=np.float64)
    return (n0 * np.exp(-R_cc / R0) * np.exp(-np.abs(z_cc) / H0)).astype(np.float32)


def make_spherical_mesh(r_face, theta_face, phi_face):
    r_face = np.asarray(r_face, dtype=np.float64)
    theta_face = np.asarray(theta_face, dtype=np.float64)
    phi_face = np.asarray(phi_face, dtype=np.float64)

    nr = len(r_face) - 1
    nt = len(theta_face) - 1
    np_phi = len(phi_face) - 1

    n_cell = np.array([nr, nt, np_phi], dtype=np.int32)
    n_tot = int(n_cell.prod())

    r_face_au = (r_face * AU).astype(np.float32)
    x_min = np.array([r_face_au[0], theta_face[0], phi_face[0]], dtype=np.float32)
    dx = np.array(
        [
            (r_face_au[-1] - r_face_au[0]) / nr,
            (theta_face[-1] - theta_face[0]) / nt,
            (phi_face[-1] - phi_face[0]) / np_phi,
        ],
        dtype=np.float32,
    )

    dr = np.diff(r_face_au)
    dtheta = np.diff(theta_face)
    dphi = np.diff(phi_face)
    r_c = 0.5 * (r_face_au[:-1] + r_face_au[1:])
    theta_c = 0.5 * (theta_face[:-1] + theta_face[1:])

    dv = np.zeros((nr, nt, np_phi), dtype=np.float32)
    for i in range(nr):
        sin_th = np.sin(theta_c)
        dv[i, :, :] = (r_c[i] ** 2) * sin_th[:, None] * dr[i] * dtheta[:, None] * dphi[None, :]

    return {
        "n_cell": n_cell,
        "x_min": x_min,
        "dx": dx,
        "n_tot": n_tot,
        "coords": "spherical",
        "r_face": r_face_au,
        "theta_face": theta_face,
        "phi_face": phi_face,
        "dv": dv.ravel().astype(np.float32),
    }


def write_kratos_fields(filename, fields, mesh, unit_l0=1.0):
    write_field_data(filename, fields, mesh, unit_l0=unit_l0)


def read_kratos_output(filename):
    return read_output(filename)


def _edges_from_mesh(mesh, dim):
    x0 = mesh["x_min"][dim]
    nc = int(mesh["n_cell"][dim])
    dx_val = mesh["dx"][dim]
    return np.linspace(x0, x0 + nc * dx_val, nc + 1)


def slice_plot_2d(ax, data, mesh, plane="xy", slice_idx=None, log=True, cmap="turbo", **kwargs):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    n_cell = mesh["n_cell"]
    coords = mesh.get("coords", "cartesian")
    nx, ny, nz = int(n_cell[0]), int(n_cell[1]), int(n_cell[2])

    data = np.asarray(data)
    if data.ndim == 1:
        if data.size > nx * ny * nz:
            data_3d = data.reshape(nz, ny, nx, -1)[:, :, :, 0]
        else:
            data_3d = data.reshape(nz, ny, nx)
    else:
        data_3d = data
    norm = LogNorm() if log else None

    if coords == "cartesian":
        xe = _edges_from_mesh(mesh, 0)
        ye = _edges_from_mesh(mesh, 1)
        ze = _edges_from_mesh(mesh, 2)

        if plane == "xy":
            si = slice_idx if slice_idx is not None else nz // 2
            X, Y = np.meshgrid(xe, ye, indexing="ij")
            pc = ax.pcolormesh(X, Y, data_3d[si, :, :].T, cmap=cmap, norm=norm, **kwargs)
        elif plane == "xz":
            si = slice_idx if slice_idx is not None else ny // 2
            X, Z = np.meshgrid(xe, ze, indexing="ij")
            pc = ax.pcolormesh(X, Z, data_3d[:, si, :].T, cmap=cmap, norm=norm, **kwargs)
        elif plane == "yz":
            si = slice_idx if slice_idx is not None else nx // 2
            Y, Z = np.meshgrid(ye, ze, indexing="ij")
            pc = ax.pcolormesh(Y, Z, data_3d[:, :, si].T, cmap=cmap, norm=norm, **kwargs)
        else:
            raise ValueError(f"Unknown plane '{plane}' for Cartesian mesh")

    elif coords == "spherical":
        r_face = mesh["r_face"]
        theta_face = mesh["theta_face"]
        phi_face = mesh["phi_face"]

        if plane == "rtheta":
            si = slice_idx if slice_idx is not None else (len(phi_face) - 1) // 2
            slc = data_3d[:, :, si]
            R, Theta = np.meshgrid(r_face, theta_face, indexing="ij")
            X = R * np.sin(Theta)
            Y = R * np.cos(Theta)
            pc = ax.pcolormesh(X, Y, slc.T, cmap=cmap, norm=norm, **kwargs)
        else:
            raise ValueError(f"Unknown plane '{plane}' for spherical mesh")
    else:
        raise ValueError(f"Unknown coordinate system '{coords}'")

    return pc


def validate_units(fields):
    c_val = 2.99792458e10
    ok = True
    for key in fields:
        val = np.asarray(fields[key])
        if key.startswith("mfp"):
            if np.any((val != 0) & ((val < 1e-30) | (val > 1e10))):
                ok = False
        elif key.startswith("vel"):
            if np.any(np.abs(val) >= c_val):
                ok = False
    return ok
