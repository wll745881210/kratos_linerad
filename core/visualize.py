import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

from .fields import slice_plot_2d


_PLANE_MAP = {"x": "yz", "y": "xz", "z": "xy"}


def _find_median(data_flat, mesh, axis):
    """Return median cell centre coordinate in CGS for a given axis."""
    n = int(mesh["n_cell"]["xyz".index(axis)])
    dx_val = mesh["dx"]["xyz".index(axis)]
    x0 = mesh["x_min"]["xyz".index(axis)]
    return x0 + (n // 2 + 0.5) * dx_val


def _axis_to_slice(data_flat, mesh, axis, coord):
    """Convert flat data to 2D slice at given axis and coordinate."""
    n_cell = mesh["n_cell"]
    nx, ny, nz = int(n_cell[0]), int(n_cell[1]), int(n_cell[2])

    if data_flat.size > nx * ny * nz:
        data_3d = data_flat.reshape(nz, ny, nx, -1)[:, :, :, 0]
    else:
        data_3d = data_flat.reshape(nz, ny, nx)

    dx_val = mesh["dx"]["xyz".index(axis)]
    x0 = mesh["x_min"]["xyz".index(axis)]
    nc = int(n_cell["xyz".index(axis)])

    idx = int((coord - x0) / dx_val)
    idx = max(0, min(idx, nc - 1))

    if axis == "x":
        return data_3d[:, :, idx], mesh, "yz", idx
    elif axis == "y":
        return data_3d[:, idx, :], mesh, "xz", idx
    else:
        return data_3d[idx, :, :], mesh, "xy", idx


def plot_flux(results, axis="x", coord=None, ax=None, output_path=None,
              log=True, cmap="turbo"):
    """2D slice plot of flux at given axis intersection.

    Parameters
    ----------
    results : dict  from LineRt.run()
    axis : str  "x" | "y" | "z" — intersection axis
    coord : float or None  intersection coordinate (default: median)
    ax : Axes or None
    output_path : str or None  save figure if given (always displayed)
    log : bool
    cmap : str
    """
    if ax is None:
        _, ax = plt.subplots()
    mesh = results.get("mesh", {})
    flx = results.get("flx", None)
    if flx is None and results.get("results"):
        flx = results["results"][-1].get("flx", None)
    if flx is None:
        ax.text(0.5, 0.5, "No flux data", transform=ax.transAxes,
                ha="center", va="center")
        return

    flx = np.asarray(flx, dtype=np.float64).ravel()
    if coord is None:
        coord = _find_median(flx, mesh, axis)

    slc, _, plane, si = _axis_to_slice(flx, mesh, axis, coord)

    pc = slice_plot_2d(ax, slc.ravel(), mesh, plane=plane, slice_idx=si,
                        log=log, cmap=cmap)

    other = _other_axes(axis)
    ax.set_xlabel(f"{other[0]} [AU]")
    ax.set_ylabel(f"{other[1]} [AU]")

    ax.set_box_aspect(_aspect_ratio(mesh, axis))

    cbar = plt.colorbar(pc, ax=ax)
    cbar.set_label("Flux [photons cm$^{-2}$ s$^{-1}$]")
    ax.set_title(f"Flux slice ({plane}, {axis}={coord:.1f} AU)")

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_population(results, axis="x", coord=None, ax=None, output_path=None,
                    log=True, cmap="plasma"):
    """2D slice plot of excited fraction at given axis intersection.

    Parameters
    ----------
    results : dict  from LineRt.run()
    axis : str  "x" | "y" | "z"
    coord : float or None
    ax : Axes or None
    output_path : str or None
    log : bool
    cmap : str
    """
    if ax is None:
        _, ax = plt.subplots()
    mesh = results.get("mesh", {})
    pops = results.get("populations", None)
    if pops is None and results.get("results"):
        pops = results["results"][-1].get("populations", None)
    if pops is None:
        ax.text(0.5, 0.5, "No population data", transform=ax.transAxes,
                ha="center", va="center")
        return

    n0 = np.asarray(pops.get("n0", pops.get("n_total", np.ones(1))),
                    dtype=np.float64).ravel()
    n_exc_keys = [k for k in pops.keys() if k.startswith("n") and k != "n0"
                  and k != "n_total"]
    n_exc = np.zeros_like(n0)
    for k in n_exc_keys:
        n_exc += np.asarray(pops[k], dtype=np.float64).ravel()
    denom = n0 + n_exc
    denom[denom == 0] = 1.0
    frac = n_exc / denom

    if coord is None:
        coord = _find_median(frac, mesh, axis)

    slc, _, plane, si = _axis_to_slice(frac, mesh, axis, coord)
    pc = slice_plot_2d(ax, slc.ravel(), mesh, plane=plane, slice_idx=si,
                        log=log, cmap=cmap)

    other = _other_axes(axis)
    ax.set_xlabel(f"{other[0]} [AU]")
    ax.set_ylabel(f"{other[1]} [AU]")

    ax.set_box_aspect(_aspect_ratio(mesh, axis))

    cbar = plt.colorbar(pc, ax=ax)
    cbar.set_label("n$_{\\rm exc}$ / (n$_0$ + n$_{\\rm exc}$) [dimensionless]")
    ax.set_title(f"Excited fraction ({plane}, {axis}={coord:.1f} AU)")

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_spectrum(results, ax=None, bins=80, xlim=None, output_path=None,
                  label=""):
    """Histogram of escaped photon velocities.

    Parameters
    ----------
    results : dict  from LineRt.run()
    ax : Axes or None
    bins : int
    xlim : tuple or None
    output_path : str or None
    label : str
    """
    if ax is None:
        _, ax = plt.subplots()
    spectrum = results.get("spectrum", {})
    vel = np.asarray(spectrum.get("vel", []))
    weights = np.asarray(spectrum.get("n",
                          spectrum.get("weights",
                          np.ones_like(vel))))

    if len(vel) == 0:
        for r in reversed(results.get("results", [])):
            phot = r.get("photons", {})
            vel = np.asarray(phot.get("vel", []))
            if len(vel) > 0:
                break

    if len(vel) == 0:
        ax.text(0.5, 0.5, "No escaped photons", transform=ax.transAxes,
                ha="center", va="center")
        ax.set_xlabel("velocity [cm/s]")
        ax.set_ylabel("count")
        return

    ax.hist(vel.ravel(), bins=bins, weights=weights.ravel(),
            histtype="step", density=False, label=label if label else None)

    ax.set_xlabel("$\\Delta v$ [cm s$^{-1}$]")
    ax.set_ylabel("count")
    if xlim is not None:
        ax.set_xlim(xlim)
    if label:
        ax.legend()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.show()


def _other_axes(axis):
    if axis == "x":
        return ("y", "z")
    elif axis == "y":
        return ("x", "z")
    else:
        return ("x", "y")


def _aspect_ratio(mesh, axis):
    dx = mesh["dx"]
    n_cell = mesh["n_cell"]
    if axis == "x":
        return (n_cell[1] * dx[1]) / (n_cell[2] * dx[2])
    elif axis == "y":
        return (n_cell[0] * dx[0]) / (n_cell[2] * dx[2])
    else:
        return (n_cell[0] * dx[0]) / (n_cell[1] * dx[1])


# ── Backward-compatible wrappers (low-level API) ────────────────────


def plot_emergent_spectrum(ax, photons, bins=80, xlim=None, label=""):
    if isinstance(photons, dict):
        vel = np.asarray(photons.get("vel", []))
        l_arr = np.asarray(photons.get("l", []))
    else:
        raise TypeError("photons must be a dict with 'vel' and 'l' keys")

    if len(vel) == 0:
        ax.text(0.5, 0.5, "No escaped photons", transform=ax.transAxes,
                ha="center", va="center")
        return

    weights = l_arr.ravel()
    vel_flat = vel.ravel()

    ax.hist(vel_flat, bins=bins, weights=weights, histtype="step",
            density=False, label=label if label else None)

    ax.set_xlabel("velocity [cm/s]")
    ax.set_ylabel("l-weighted count")
    if xlim is not None:
        ax.set_xlim(xlim)
    if label:
        ax.legend()


def plot_flux_slice(ax, flx, mesh, title="", log=True, cmap="turbo",
                    cbar_label=None, slice_idx = None ):
    pc = slice_plot_2d(ax, flx, mesh, plane="xy", slice_idx=slice_idx,
                       log=log, cmap=cmap)
    label = cbar_label or "flux [photons cm$^{-2}$ s$^{-1}$]"
    plt.colorbar(pc, ax=ax, label=label)
    ax.set_title(title or "Flux slice (xy)")


def plot_population_map(ax, n, mesh, level=0, title="", log=True,
                        cmap="plasma", cbar_label=None):
    pc = slice_plot_2d(ax, n, mesh, plane="xy", slice_idx=None,
                       log=log, cmap=cmap)
    label = cbar_label or f"n{level} [cm$^{{-3}}]$"
    plt.colorbar(pc, ax=ax, label=label)
    ax.set_title(title or f"Population level {level} slice (xy)")


def plot_convergence(ax, pop_history, cycles):
    deltas = [0.0]
    keys = sorted(pop_history[0].keys())
    for k in range(1, len(pop_history)):
        max_delta = max(
            np.max(np.abs(pop_history[k][key] - pop_history[k - 1][key]))
            for key in keys
        )
        deltas.append(float(max_delta))

    ax.plot(cycles[:len(deltas)], deltas, "o-", color="black")
    ax.set_xlabel("Cycle")
    ax.set_ylabel(r"$\max|\Delta n|$")
    ax.set_title("Population convergence")
