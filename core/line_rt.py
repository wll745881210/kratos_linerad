"""High-level interface for line radiative transfer simulations.

Provides a single-entry-point abstraction over the low-level iterate()
pipeline. Users configure geometry, species, sources, and RT parameters
via __init__ and add_source(), then call run() to execute.

Usage:
    rt = LineRt(species="CO", n_species=1e4, temperature=100.0)
    rt.add_source(n_photon=50000, luminosity=0.8*Lsun, wavelength=2.35e-4)
    results = rt.run()
"""

import os
import numpy as np

from .source import make_cartesian_mesh
from .fields import uniform_field
from .species_db import load_species
from .consistency import check_consistency, ConsistencyError, _compute_b

h_cgs = 6.62607015e-27
c_cgs = 2.99792458e10


class LineRt:
    """High-level orchestrator for a line radiative-transfer simulation.

    All __init__ parameters are optional — LineRt() creates a valid
    (empty) object. Use add_source() to add photon sources, then call
    run() to execute.

    Parameters
    ----------
    n_cell : tuple[int, int, int]
        Number of cells in (x, y, z).
    x_min, x_max : tuple[float, float, float]
        Domain bounds in code units (for unit_l0=1.5e13 cm, these are AU).
    unit_l0 : float
        Length unit in CGS (cm per code-length).
    unit_t0 : float
        Time unit in CGS (s per code-time).
    species : str | SpeciesData | None
        LAMDA species name (e.g. "CO") or pre-loaded SpeciesData.
    transition_idx : int
        0-based index into species transitions.
    n_species : float | callable | None
        Number density of the scatterer [cm⁻³]. If callable, receives
        n_cells and returns an ndarray.
    temperature : float | None
        Gas temperature [K]. Required when species is given.
    b_sca : float | callable | None
        Doppler b-parameter [cm/s]. Auto-computed from T if species given.
    mfp_i_sca_0 : float | callable | None
        Inverse scattering mean free path [cm⁻¹]. Required if no species.
    mfp_i_abs_0 : float | callable | None
        Inverse absorption mean free path [cm⁻¹] (default 0).
    vel : tuple | None
        Bulk velocity (vx, vy, vz) [cm/s]. Each component: float | callable.
    mol_mass : float
        Molecular mass [amu] for computing b_sca from temperature.
    a_voigt : float or None
        Voigt damping parameter a. If None (default), uses pure Gaussian profile.
    ph_mode : int
        0=CFR, 1=PRD.
    n_step, n_scat : int
        Max path segments and scattering events per photon packet.
    n_cycles : int
        Number of MC → population → MC cycles.
    path : str or None
        Working directory. Default: ~/scratch/line_rt/<auto-dir>.
    visualize : bool
        If True, automatically plot results after run().
    n_emission_max : int
        Max internal emission photons per cell per cycle.
    ray_output : bool
        If True, enable raw ray output binary (flx + excitation_flux per cell).
    ray_id : int
        Target cell index for ray output (-1 = all cells).
    snapshot : callable or None
        Called after each cycle: fn(results=output, cycle=cycle, populations=pops).
    """

    def __init__(self, *,
                 n_cell=(64, 2, 2),
                 x_min=(-5., 0., 0.),
                 x_max=(5., 0.2, 0.2),
                 unit_l0=1.49598e13, unit_t0=1.0,
                 species=None, transition_idx=0,
                 n_species=None, temperature=None,
                  b_sca=None, mfp_i_sca_0=None, mfp_i_abs_0=0.0,
                  vel=None, mol_mass=28.0, a_voigt=None,
                 ph_mode=0, n_step=10000, n_scat=10000, n_cycles=3,
                  path=None, visualize=True,
                  n_emission_max=10,
                  ray_output=False, ray_id=-1,
                  snapshot=None):
        self._n_cell = tuple(n_cell)
        self._x_min = tuple(x_min)
        self._x_max = tuple(x_max)
        self._unit_l0 = unit_l0
        self._unit_t0 = unit_t0
        self._species_name = species
        self._species_obj = None
        self._transition_idx = transition_idx
        self._n_species = n_species
        self._temperature = temperature
        self._b_sca = b_sca
        self._mfp_i_sca_0 = mfp_i_sca_0
        self._mfp_i_abs_0 = mfp_i_abs_0
        self._vel = vel
        self._mol_mass = mol_mass
        self._a_voigt = a_voigt
        self._ph_mode = ph_mode
        self._n_step = n_step
        self._n_scat = n_scat
        self._n_cycles = n_cycles
        self._path = path
        self._visualize = visualize
        self._n_emission_max = n_emission_max
        self._ray_output = ray_output
        self._ray_id = ray_id
        self._snapshot = snapshot
        self._sources = []
        self._boundary_kinds = "fre fre fre fre fre fre"

    # ── Boundary configuration ──────────────────────────────────────

    def set_boundary(self, kinds):
        """Set boundary conditions for all 6 faces.

        Parameters
        ----------
        kinds : str
            6 space-separated boundary kinds: -x +x -y +y -z +z.
            Each is "fre" (free/escape) or "per" (periodic).
            Example: "fre fre per per per per" for free x-faces,
            periodic y,z (plane-parallel slab).
        """
        kr = kinds.lower().split()
        if len(kr) != 6:
            raise ValueError(f"Need 6 boundary kinds (got {len(kr)}): "
                             "-x +x -y +y -z +z")
        for k in kr:
            if k not in ("fre", "per"):
                raise ValueError(f"Boundary kind must be 'fre' or 'per', got '{k}'")
        self._boundary_kinds = " ".join(kr)
        return self

    # ── Source registration ─────────────────────────────────────────

    def add_source(self, *,
                   type="slab", n_photon=50000,
                   luminosity=None, flux=None, wavelength=None,
                   x=None, direction="+x",
                   y_range=None, z_range=None,
                   position=None,
                   vel_offset=0.0, sigma=None, amplitude=1.0):
        """Add an external photon source.

        Parameters
        ----------
        type : str
            "slab" — plane source at a given x-coordinate. Use **flux**
            [photons cm⁻² s⁻¹] (or erg cm⁻² s⁻¹ with wavelength).
            "point" — point source at (x, y, z). Use **luminosity**
            [photons/s] (or erg/s with wavelength).
        n_photon : int
            Number of photon packets.
        luminosity : float or None
            Total photon-number luminosity [photons/s] (point source).
            If wavelength given, interpret as erg/s.
            Ignored for slab sources if *flux* is provided.
        flux : float or None
            Photon number flux [photons cm⁻² s⁻¹] (slab source only).
            If wavelength given, interpret as erg cm⁻² s⁻¹.
            For a slab source: proper = flux × source_area / n_photon.
        wavelength : float or None
            Line-centre wavelength [cm]. Converts energetic flux/luminosity
            to photon-number flux/luminosity via E_ph = hc/λ.
        x : float or None (slab)
            x-coordinate of the source plane.
        direction : str (slab)
            "+x" or "-x" photon direction.
        y_range : tuple or None (slab)
            (y_min, y_max) for uniform distribution. None → full domain.
        z_range : tuple or None (slab)
            (z_min, z_max) for uniform distribution. None → full domain.
        position : tuple or None (point)
            (x, y, z) of point source.
        vel_offset : float
            Velocity offset of emitted photons [cm/s].
        sigma : float or None
            Intrinsic Doppler width [cm/s]. None → b_sca/√2.
        amplitude : float
            Line strength.
        """
        src = dict(type=type, n_photon=n_photon, luminosity=luminosity,
                   flux=flux, wavelength=wavelength, x=x, direction=direction,
                   y_range=y_range, z_range=z_range, position=position,
                   vel_offset=vel_offset, sigma=sigma, amplitude=amplitude)
        self._sources.append(src)
        return self

    # ── Run ─────────────────────────────────────────────────────────

    def run(self, **overrides):
        """Run the RT simulation and return results.

        Returns
        -------
        dict with keys:
            'results'       — list[dict] (one per cycle)
            'populations'   — final population dict
            'mesh'          — mesh dict
            'exc_flux_flat' — final CGS excitation flux (1D)
            'flx'           — final CGS flux (1D)
            'spectrum'      — {"vel": ..., "n": ...}
            'sources'       — list[dict] (source configs used)
        """
        self._resolve_species()
        self._check()

        mesh = self._build_mesh()
        species = self._species_obj
        n_tot = mesh['n_tot']

        if species is not None and self._n_species is not None:
            n_species_val = self._resolve_field(self._n_species, n_tot)
        else:
            n_species_val = None

        b_sca_val = self._resolve_b_sca(n_tot)
        mfp_abs_val = self._resolve_field(self._mfp_i_abs_0, n_tot)
        vel_vals = self._resolve_vel(n_tot)

        fields = {
            'b_sca':       b_sca_val,
            'temp':        self._resolve_field(self._temperature, n_tot),
            'vel_0':       vel_vals[0],
            'vel_1':       vel_vals[1],
            'vel_2':       vel_vals[2],
            'mfp_i_abs_0': mfp_abs_val,
        }

        if species is not None:
            mfp_sca_0, mfp_abs_0_in = self._resolve_mfp_species(species, n_tot,
                                                                  b_sca_val,
                                                                  n_species_val)
            if mfp_abs_0_in is not None:
                fields['mfp_i_abs_0'] = mfp_abs_0_in
            fields['mfp_i_sca_0'] = mfp_sca_0
        elif self._mfp_i_sca_0 is not None:
            fields['mfp_i_sca_0'] = self._resolve_field(self._mfp_i_sca_0, n_tot)

        v_factor = self._unit_t0 / self._unit_l0
        if species is None:
            for key in list(fields):
                if key.startswith('mfp_i_'):
                    fields[key] = np.asarray(fields[key], dtype=np.float64) * self._unit_l0
                elif key in ('b_sca',) or key.startswith('vel_'):
                    fields[key] = np.asarray(fields[key], dtype=np.float64) * v_factor

        v_factor = self._unit_t0 / self._unit_l0
        for key in list(fields):
            if key.startswith('mfp_i_'):
                fields[key] = np.asarray(fields[key], dtype=np.float64) * self._unit_l0
            elif key in ('b_sca',) or key.startswith('vel_'):
                fields[key] = np.asarray(fields[key], dtype=np.float64) * v_factor

        photons = self._generate_photons(n_tot, mesh, b_sca_val)

        work_dir = self._resolve_path()

        from .iterator import iterate
        a_voigt_val = self._resolve_a_voigt(b_sca_val)
        par_overrides = {'kinds': self._boundary_kinds,
                         'a_voigt': str(float(a_voigt_val))}
        if self._ray_output:
            par_overrides['ray_output'] = '1'
            par_overrides['ray_id'] = str(self._ray_id)
        results, final_pops = iterate(
            photons, species, fields, mesh,
            n_cycles=self._n_cycles,
            n_step=self._n_step, n_scat=self._n_scat,
            ph_mode=self._ph_mode,
            work_dir=work_dir,
            n_species=n_species_val,
            transition_idx=self._transition_idx,
            mol_mass=self._mol_mass,
            unit_l0=self._unit_l0, unit_t0=self._unit_t0,
            n_emission_max=self._n_emission_max,
            callback=self._snapshot,
            par_overrides=par_overrides,
        )

        spectrum = {"vel": np.array([]), "n": np.array([])}
        if results and results[-1].get("photons"):
            phot = results[-1]["photons"]
            if "vel" in phot:
                spectrum = {"vel": np.asarray(phot["vel"]),
                            "n": np.ones_like(phot["vel"])}

        out = {
            "results": results,
            "populations": final_pops,
            "mesh": mesh,
            "exc_flux_flat": results[-1].get("exc_flux_flat", None) if results else None,
            "flx": results[-1].get("flx", None) if results else None,
            "ray_flx": results[-1].get("ray_flx", None) if results else None,
            "ray_exc_flux": results[-1].get("ray_exc_flux", None) if results else None,
            "spectrum": spectrum,
            "sources": list(self._sources),
        }

        if self._visualize:
            self._plot_results(out)

        return out

    # ── Helpers ─────────────────────────────────────────────────────

    def _resolve_species(self):
        if self._species_name is None:
            return
        if isinstance(self._species_name, str):
            self._species_obj = load_species(self._species_name)
        else:
            self._species_obj = self._species_name

    def _check(self):
        check_consistency(
            species=self._species_obj,
            transition_idx=self._transition_idx,
            n_species=self._n_species,
            temperature=self._temperature,
            b_sca=self._b_sca,
            mfp_i_sca_0=self._mfp_i_sca_0,
            sources=self._sources,
            mol_mass=self._mol_mass,
            unit_l0=self._unit_l0, unit_t0=self._unit_t0,
        )

    def _build_mesh(self):
        return make_cartesian_mesh(
            n_cell=self._n_cell,
            x_min=self._x_min,
            x_max=self._x_max,
        )

    def _resolve_field(self, value, n_tot):
        if value is None:
            return np.zeros(n_tot, dtype=np.float64)
        if isinstance(value, np.ndarray):
            return np.asarray(value, dtype=np.float64).ravel()
        if callable(value) and not isinstance(value, (int, float)):
            return np.asarray(value(n_tot), dtype=np.float64).ravel()
        return np.full(n_tot, float(value), dtype=np.float64)

    def _resolve_b_sca(self, n_tot):
        if self._b_sca is not None:
            return self._resolve_field(self._b_sca, n_tot)
        if self._species_obj is not None:
            temp_vals = self._resolve_field(self._temperature, n_tot)
            b_vals = np.sqrt(2.0 * 1.380649e-16 * np.maximum(temp_vals, 0.1)
                             / (self._mol_mass * 1.67262192e-24))
            return b_vals
        return np.full(n_tot, 1e5, dtype=np.float64)

    def _resolve_a_voigt(self, b_sca_val):
        """Resolve Voigt damping parameter a = A_ul * lambda / (4 * pi * b)."""
        if self._a_voigt is not None:
            return float(self._a_voigt)
        if self._species_obj is not None and self._species_obj.transitions is not None:
            t = self._species_obj.transitions[self._transition_idx]
            A_ul = float(t[2])
            freq_GHz = float(t[3])
            if freq_GHz > 0 and A_ul > 0:
                wavelength_cm = c_cgs / (freq_GHz * 1e9)
                b_mean = float(np.mean(np.abs(np.asarray(b_sca_val))))
                if b_mean > 0:
                    return A_ul * wavelength_cm / (4.0 * np.pi * b_mean)
        return 0.0

    def _resolve_vel(self, n_tot):
        if self._vel is None:
            return (np.zeros(n_tot, dtype=np.float64),
                    np.zeros(n_tot, dtype=np.float64),
                    np.zeros(n_tot, dtype=np.float64))
        out = []
        for i, v in enumerate(self._vel):
            if callable(v) and not isinstance(v, (int, float, np.ndarray)):
                out.append(np.asarray(v(n_tot), dtype=np.float64).ravel())
            else:
                out.append(np.full(n_tot, float(v), dtype=np.float64))
        return tuple(out)

    def _resolve_mfp_species(self, species, n_tot, b_sca_val, n_species_val):
        pops = species.initial_populations(n_tot,
                                           n_species=n_species_val)
        mfp_sca = species.compute_opacity(pops, b_sca=b_sca_val,
                                           transition_idx=self._transition_idx)
        mfp_sca_0 = np.asarray(mfp_sca, dtype=np.float64).ravel()
        return mfp_sca_0, None

    def _resolve_path(self):
        if self._path is not None:
            return self._path
        base = os.path.expanduser("~/scratch/line_rt")
        os.makedirs(base, exist_ok=True)
        import time
        ts = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(base, f"rt_{ts}")

    def _generate_photons(self, n_tot, mesh, b_sca_val):
        parts = []
        for src in self._sources:
            parts.append(self._generate_one_source(src, mesh, b_sca_val))
        if not parts:
            return np.zeros((0, 10), dtype=np.float64)
        return np.vstack(parts)

    def _generate_one_source(self, src, mesh, b_sca_val):
        n_ph = int(src.get('n_photon', 50000))
        s_type = src.get('type', 'slab')
        wavelength = src.get('wavelength', None)
        luminosity = src.get('luminosity', None)
        flux = src.get('flux', None)
        vel_offset = float(src.get('vel_offset', 0.0))
        amplitude = float(src.get('amplitude', 1.0))

        sigma = src.get('sigma', None)
        if sigma is None:
            sigma = float(np.mean(b_sca_val)) / np.sqrt(2.0)
        else:
            sigma = float(sigma)

        if s_type == "slab":
            x_min = mesh['x_min']
            x_max_vals = np.array(mesh['x_min']) + np.array(mesh['dx']) * np.array(mesh['n_cell'])

            x_pos = src.get('x') if src.get('x') is not None else x_min[0]
            x_pos = float(x_pos)
            y_rng = src.get('y_range', None)
            z_rng = src.get('z_range', None)
            y_lo = y_rng[0] if y_rng is not None else x_min[1]
            y_lo = float(y_lo)
            y_hi = y_rng[1] if y_rng is not None else x_max_vals[1]
            y_hi = float(y_hi)
            z_lo = z_rng[0] if z_rng is not None else x_min[2]
            z_lo = float(z_lo)
            z_hi = z_rng[1] if z_rng is not None else x_max_vals[2]
            z_hi = float(z_hi)
            direction = src.get('direction', '+x')
            dx_sign = 1.0 if direction == '+x' else -1.0

            source_area_cm2 = (y_hi - y_lo) * (z_hi - z_lo) * self._unit_l0 * self._unit_l0

            if flux is not None and wavelength is not None:
                E_ph = h_cgs * c_cgs / float(wavelength)
                proper = (float(flux) / E_ph) * source_area_cm2 / n_ph
            elif flux is not None:
                proper = float(flux) * source_area_cm2 / n_ph
            elif wavelength is not None and luminosity is not None:
                E_ph = h_cgs * c_cgs / float(wavelength)
                proper = float(luminosity) / E_ph / n_ph
            elif luminosity is not None:
                proper = float(luminosity) / n_ph
            else:
                proper = 1.0 / n_ph

            ph = np.zeros((n_ph, 10), dtype=np.float64)
            ph[:, 6] = proper
            ph[:, 7] = vel_offset
            ph[:, 8] = sigma
            ph[:, 9] = amplitude
            ph[:, 0] = x_pos
            ph[:, 1] = np.random.uniform(y_lo, y_hi, n_ph)
            ph[:, 2] = np.random.uniform(z_lo, z_hi, n_ph)
            ph[:, 3] = dx_sign
            ph[:, 4] = 0.0
            ph[:, 5] = 0.0
        elif s_type == "point":
            if wavelength is not None and luminosity is not None:
                E_ph = h_cgs * c_cgs / float(wavelength)
                proper = float(luminosity) / E_ph / n_ph
            elif luminosity is not None:
                proper = float(luminosity) / n_ph
            else:
                proper = 1.0 / n_ph

            ph = np.zeros((n_ph, 10), dtype=np.float64)
            ph[:, 6] = proper
            ph[:, 7] = vel_offset
            ph[:, 8] = sigma
            ph[:, 9] = amplitude

            pos = src.get('position', (0.0, 0.0, 0.0))
            ph[:, 0] = float(pos[0])
            ph[:, 1] = float(pos[1])
            ph[:, 2] = float(pos[2])
            theta = np.arccos(2.0 * np.random.random(n_ph) - 1.0)
            phi = 2.0 * np.pi * np.random.random(n_ph)
            ph[:, 3] = np.sin(theta) * np.cos(phi)
            ph[:, 4] = np.sin(theta) * np.sin(phi)
            ph[:, 5] = np.cos(theta)
        else:
            raise ValueError(f"Unknown source type: {s_type}")

        return ph

    def _plot_results(self, out):
        from .visualize import plot_flux, plot_population, plot_spectrum
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        plot_flux(out, ax=axes[0])
        plot_population(out, ax=axes[1])
        plot_spectrum(out, ax=axes[2])
        fig.tight_layout()
        plt.show()
