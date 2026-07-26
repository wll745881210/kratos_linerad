import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

from .fields import slice_plot_2d


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


def plot_flux_slice(ax, flx, mesh, title="", log=True, cmap="turbo", cbar_label=None):
    pc = slice_plot_2d(ax, flx, mesh, plane="xy", slice_idx=None, log=log, cmap=cmap)
    label = cbar_label or "flux [photons cm$^{-2}$ s$^{-1}$]"
    plt.colorbar(pc, ax=ax, label=label)
    ax.set_title(title or "Flux slice (xy)")


def plot_population_map(ax, n, mesh, level=0, title="", log=True, cmap="plasma", cbar_label=None):
    pc = slice_plot_2d(ax, n, mesh, plane="xy", slice_idx=None, log=log, cmap=cmap)
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
