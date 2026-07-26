import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, NamedTuple

h_cgs = 6.62607015e-27
c_cgs = 2.99792458e10
k_B   = 1.380649e-16
sqrt_pi = 1.77245385091


class Transition(NamedTuple):
    upper: int
    lower: int
    A_ul: float
    freq_GHz: float
    E_u_K: float
    wavelength_um: float

    @classmethod
    def from_row(cls, row, levels=None):
        upper, lower = int(row[0]), int(row[1])
        A_ul = float(row[2])
        freq_GHz = float(row[3])
        wavelength_um = 299792.458 / freq_GHz if freq_GHz > 0 else float('inf')
        E_u_K = float(levels[upper, 0]) if levels is not None else float('nan')
        return cls(upper=upper, lower=lower, A_ul=A_ul,
                   freq_GHz=freq_GHz, E_u_K=E_u_K,
                   wavelength_um=wavelength_um)

    def __repr__(self):
        return (f'Transition(upper={self.upper}, lower={self.lower}, '
                f'A_ul={self.A_ul:.2e}, freq={self.freq_GHz:.3f} GHz, '
                f'lambda={self.wavelength_um:.3f} um, E_u/K={self.E_u_K:.1f} K)')


@dataclass
class SpeciesData:
    name: str
    n_levels: int
    levels: np.ndarray
    n_transitions: int
    transitions: np.ndarray
    collision_partners: List[Dict] = field(default_factory=list)

    @property
    def transitions_list(self):
        return [Transition.from_row(row, self.levels)
                for row in self.transitions]

    def find_transition_idx(self, transition):
        for idx in range(self.n_transitions):
            row = self.transitions[idx]
            if (int(row[0]) == transition.upper
                    and int(row[1]) == transition.lower
                    and abs(float(row[2]) - transition.A_ul) / max(abs(transition.A_ul), 1e-40) < 1e-6
                    and abs(float(row[3]) - transition.freq_GHz) / max(abs(transition.freq_GHz), 1e-40) < 1e-6):
                return idx
        raise ValueError(
            f"Transition {transition} not found in species data. "
            f"Available: {len(self.transitions)} transitions loaded. "
            f"Candidates: {self.transitions_list}")

    def show_transitions(self):
        lines = [f"Species: {self.name} ({self.n_levels} levels, {self.n_transitions} transitions)"]
        lines.append(f"{'Idx':>4s}  {'Upper':>6s}  {'Lower':>6s}  {'A_ul/s⁻¹':>12s}  {'freq/GHz':>10s}  {'λ/µm':>10s}  {'E_u/K':>12s}")
        lines.append("─" * 70)
        for idx, tr in enumerate(self.transitions_list):
            lines.append(
                f"{idx:4d}  {tr.upper:6d}  {tr.lower:6d}  {tr.A_ul:12.3e}  {tr.freq_GHz:10.4f}  {tr.wavelength_um:10.3f}  {tr.E_u_K:12.1f}")
        return "\n".join(lines)

    def get_Einstein_A(self, upper, lower):
        mask = (self.transitions[:, 0] == upper) & (self.transitions[:, 1] == lower)
        match = self.transitions[mask]
        return float(match[0, 2]) if len(match) > 0 else 0.0

    def get_level_energy(self, level_idx):
        return float(self.levels[level_idx, 0])

    def get_level_weight(self, level_idx):
        return float(self.levels[level_idx, 1])

    def get_nu(self, upper, lower):
        mask = (self.transitions[:, 0] == upper) & (self.transitions[:, 1] == lower)
        match = self.transitions[mask]
        return float(match[0, 3]) if len(match) > 0 else 0.0

    def get_collision_rate(self, upper, lower, T, partner='H2'):
        for cp in self.collision_partners:
            if cp['species'] == partner:
                idx = np.where((cp['trans_indices'][:, 0] == upper)
                               & (cp['trans_indices'][:, 1] == lower))[0]
                if len(idx) == 0:
                    return 0.0
                rates = cp['rates'][idx[0]]
                return float(np.interp(T, cp['temps'], rates))
        return 0.0

    def partition_function(self, T):
        g = np.asarray(self.levels[:, 1], dtype=np.float64)
        E_cm = np.asarray(self.levels[:, 0], dtype=np.float64)
        E_erg = E_cm * h_cgs * c_cgs * 100.0
        T_arr = np.asarray(T, dtype=np.float64)
        exponent = E_erg[:, None] / (k_B * T_arr)
        return np.sum(g[:, None] * np.exp(-exponent), axis=0)

    def lte_populations(self, n_total, T):
        n_t = np.asarray(n_total, dtype=np.float64).ravel()
        T_arr = np.asarray(T, dtype=np.float64)
        E_cm = np.asarray(self.levels[:, 0], dtype=np.float64)
        E_erg = E_cm * h_cgs * c_cgs * 100.0
        g = np.asarray(self.levels[:, 1], dtype=np.float64)
        Z = self.partition_function(T_arr)
        pops = {}
        for i in range(self.n_levels):
            pops[f'n{i}'] = (n_t * g[i]
                             * np.exp(-E_erg[i] / (k_B * T_arr)) / Z)
        pops['n_total'] = n_t.copy()
        return pops

    def cross_section(self, transition_idx=0, b_param=1e5):
        t = self.transitions[transition_idx]
        upper, lower = int(t[0]), int(t[1])
        A_ul = t[2]
        nu = t[3] * 1e9
        g_u = self.get_level_weight(upper)
        g_l = self.get_level_weight(lower)
        sigma = (c_cgs * c_cgs * c_cgs) / (8.0 * nu * nu * nu * b_param * sqrt_pi * sqrt_pi * sqrt_pi)
        sigma *= (g_u / g_l) * A_ul
        return sigma

    def initial_populations(self, n_tot, n_gas=None):
        if n_gas is None:
            n_gas = np.ones(n_tot, dtype=np.float64)
        else:
            n_gas = np.broadcast_to(np.asarray(n_gas, dtype=np.float64),
                                    (n_tot,)).copy()
        pops = {}
        for i in range(self.n_levels):
            pops[f'n{i}'] = (n_gas.copy() if i == 0
                             else np.zeros(n_tot, dtype=np.float64))
        pops['n_total'] = n_gas.copy()
        return pops

    def compute_opacity(self, populations, b_sca=1e5,
                          transition_idx=None):
        mfp_sca = np.zeros_like(populations.get('n0',
                   populations.get('n_total', np.ones(1))),
                   dtype=np.float64)
        t_range = [transition_idx] if transition_idx is not None \
                  else range(self.n_transitions)
        for t_idx in t_range:
            upper = int(self.transitions[t_idx, 0])
            lower = int(self.transitions[t_idx, 1])
            n_l = np.asarray(populations.get(f'n{lower}',
                               np.zeros_like(mfp_sca)), dtype=np.float64)
            sigma_s = self.cross_section(t_idx, b_sca)
            mfp_sca += n_l * sigma_s
        return mfp_sca

    def update_populations(self, exc_flux, flx, populations, cycle, dx=1.0, b_sca=1e5,
                             T=None, colliders=None, transition_idx=0):
        from .equilibrium import solve_populations
        pop_vals = list(populations.values())
        n_cells = len(pop_vals[0]) if pop_vals else 1
        n_total = populations.get('n_total',
                   sum(populations.get(f'n{i}', np.zeros(n_cells))
                       for i in range(self.n_levels)))
        exc_flux_arr = np.asarray(exc_flux, dtype=np.float64).ravel() if exc_flux is not None else \
                       np.zeros(n_cells, dtype=np.float64)
        if exc_flux_arr.shape[0] != n_cells:
            exc_flux_arr = np.zeros(n_cells, dtype=np.float64)
        result = solve_populations(self, exc_flux_arr, n_total, T=T, colliders=colliders,
                                    b_param=b_sca, transition_idx=transition_idx)
        if isinstance(result, np.ndarray) and result.ndim == 2:
            pops = {}
            for i in range(self.n_levels):
                pops[f'n{i}'] = result[i, :].copy()
            pops['n_total'] = (n_total.copy() if hasattr(n_total, 'copy')
                               else np.asarray(n_total).copy())
            return pops
        return result

    def compute_emissivity(self, populations, transition_idx, temperature):
        t = self.transitions[transition_idx]
        upper = int(t[0])
        A_ul = float(t[2])
        nu = float(t[3]) * 1e9
        n_u = np.asarray(populations.get(f'n{upper}',
                          np.ones(1)), dtype=np.float64).ravel()
        emissivity = n_u * A_ul * h_cgs * nu / (4.0 * np.pi)
        return np.maximum(emissivity, 0.0)

    def generate_emission_photons(self, populations, transition_idx,
                                   temperature, mesh, n_per_cell_max=10,
                                   b_sca=1e5, rng=None):
        if rng is None:
            rng = np.random.default_rng()
        n_cells = int(np.prod(mesh['n_cell']))
        n_cell = mesh['n_cell']
        x_min = mesh['x_min']
        dx = mesh['dx']
        volume = float(np.prod(dx))

        emissivity = self.compute_emissivity(populations, transition_idx,
                                              temperature)
        t = self.transitions[transition_idx]
        upper = int(t[0])

        photons = []
        for ic in range(n_cells):
            em = emissivity[ic]
            if em <= 0.0:
                continue
            lum_cell = em * volume
            n_ph = max(1, int(np.ceil(lum_cell / max(lum_cell, 1e-40)
                                      * n_per_cell_max)))
            n_ph = min(n_ph, n_per_cell_max)
            n_ph = max(n_ph, 1) if em > 0 else 0

            ix = ic % n_cell[0]
            iy = (ic // n_cell[0]) % n_cell[1]
            iz = ic // (n_cell[0] * n_cell[1])
            x = x_min[0] + (ix + rng.random(n_ph)) * dx[0]
            y = x_min[1] + (iy + rng.random(n_ph)) * dx[1]
            z = x_min[2] + (iz + rng.random(n_ph)) * dx[2]

            cos_theta = 2.0 * rng.random(n_ph) - 1.0
            theta = np.arccos(cos_theta)
            phi = 2.0 * np.pi * rng.random(n_ph)
            dir_x = np.sin(theta) * np.cos(phi)
            dir_y = np.sin(theta) * np.sin(phi)
            dir_z = cos_theta

            b_thermal = np.sqrt(1.66289e8 * temperature[ic]
                                / 28.0 + 1e-35)
            sigma_ph = b_thermal / np.sqrt(2.0)
            vel_draw = rng.normal(0.0, sigma_ph, n_ph)

            weight_per_ph = lum_cell / n_ph if n_ph > 0 else 0.0

            for j in range(n_ph):
                photons.append([x[j], y[j], z[j],
                                dir_x[j], dir_y[j], dir_z[j],
                                weight_per_ph, vel_draw[j],
                                sigma_ph, 1.0])
        if not photons:
            return np.zeros((0, 11), dtype=np.float64)
        return np.array(photons, dtype=np.float64)

    def make_fields(self, populations, step, cycle, base_fields=None,
                     unit_l0=1.0, unit_t0=1.0, transition_idx=None):
        n_total = populations.get('n_total',
                   sum(populations.get(f'n{i}', np.ones(1))
                       for i in range(self.n_levels)))
        mfp_i_sca = self.compute_opacity(populations,
                                          transition_idx=transition_idx)
        n_cells = len(n_total) if hasattr(n_total, '__len__') else 1
        v_factor = unit_t0 / unit_l0
        fields = {}
        if base_fields:
            for k, v in base_fields.items():
                arr = np.asarray(v, dtype=np.float64).copy()
                if k == 'mfp_i_sca_0' or k == 'mfp_i_abs_0':
                    arr *= unit_l0
                elif k in ('b_sca',) or k.startswith('vel_'):
                    arr *= v_factor
                elif k == 'temp':
                    pass
                fields[k] = arr
        if 'mfp_i_sca_0' not in fields:
            fields['mfp_i_sca_0'] = (np.asarray(mfp_i_sca, dtype=np.float64).ravel()
                                     * unit_l0)
        if 'b_sca' not in fields:
            fields['b_sca'] = np.full(n_cells, 1e5 * v_factor, dtype=np.float64)
        for a in range(3):
            key = f'vel_{a}'
            if key not in fields:
                fields[key] = np.zeros(n_cells, dtype=np.float64)
        for i in range(self.n_levels):
            fields[f'n{i}'] = np.asarray(
                populations.get(f'n{i}', np.zeros(n_cells)), dtype=np.float64)
        return fields


def _find_section(lines, marker, start=0):
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if line and not line.startswith('!'):
            return i
        if marker in line:
            return i
        i += 1
    return -1


def _skip_non_section_header(lines, i):
    while i < len(lines) and lines[i].strip().startswith('!'):
        i += 1
    return i


def load_lamda(content):
    if isinstance(content, str):
        lines = content.splitlines()
    else:
        lines = [ln.decode() if isinstance(ln, bytes) else ln for ln in content]

    lines = [ln.strip() for ln in lines]
    mol_idx = -1
    for i, ln in enumerate(lines):
        if ln.startswith('!MOLECULE') or ln.startswith('! MOLECULE'):
            mol_idx = i + 1
            break
    name = lines[mol_idx] if mol_idx >= 0 and mol_idx < len(lines) else 'unknown'

    nlev_idx = -1
    for i in range(mol_idx, len(lines)):
        if 'NUMBER OF ENERGY LEVELS' in lines[i]:
            nlev_idx = i
            break
    n_levels = int(lines[nlev_idx + 1]) if nlev_idx >= 0 else 0

    ntrans_idx = -1
    for i in range(nlev_idx + 1, len(lines)):
        if 'NUMBER OF RADIATIVE TRANSITIONS' in lines[i]:
            ntrans_idx = i
            break
    n_transitions = int(lines[ntrans_idx + 1]) if ntrans_idx >= 0 else 0

    levels = []
    lev_start = nlev_idx + 3
    for i in range(n_levels):
        parts = lines[lev_start + i].split()
        if len(parts) >= 3:
            levels.append([float(parts[1]), float(parts[2])])
    levels = np.array(levels, dtype=np.float64)

    transitions = []
    trans_start = ntrans_idx + 3
    for i in range(n_transitions):
        parts = lines[trans_start + i].split()
        if len(parts) >= 4:
            transitions.append([int(parts[1]) - 1, int(parts[2]) - 1,
                                float(parts[3]), float(parts[4])])
    transitions = np.array(transitions, dtype=np.float64)

    coll_partners = []
    cp_idx = trans_start + n_transitions
    while cp_idx < len(lines):
        line = lines[cp_idx].strip()
        if 'NUMBER OF COLL PARTNERS' in line or 'NUMBER OF COLLISION PARTNERS' in line:
            break
        cp_idx += 1

    if cp_idx < len(lines):
        n_coll_partners = int(lines[cp_idx + 1])
        ci = cp_idx + 2
        for _ in range(n_coll_partners):
            while ci < len(lines) and (
                lines[ci].strip().startswith('!') or not lines[ci].strip()):
                ci += 1
            if ci >= len(lines):
                break
            partner_name = lines[ci].strip()
            ci += 1
            while ci < len(lines) and ('NUMBER OF COLL TRANSITIONS' not in lines[ci]):
                ci += 1
            n_coll_trans = int(lines[ci + 1])
            ci += 2
            while ci < len(lines) and ('NUMBER OF COLL TEMPS' not in lines[ci]):
                ci += 1
            n_coll_temps = int(lines[ci + 1])
            ci += 2
            coll_temps = np.array(
                [float(x) for x in lines[ci].split()])
            ci += 1

            rates = []
            for _ in range(n_coll_trans):
                vals = [float(x) for x in lines[ci].split()]
                rates.append(vals)
                ci += 1
            rates = np.array(rates, dtype=np.float64)

            trans_indices = []
            for n in range(n_coll_trans):
                trans_indices.append(
                    [int(transitions[n, 0]), int(transitions[n, 1])])
            trans_indices = np.array(trans_indices, dtype=np.int64)

            coll_partners.append({
                'species': partner_name,
                'n_trans': n_coll_trans,
                'n_temps': n_coll_temps,
                'temps': coll_temps,
                'rates': rates,
                'trans_indices': trans_indices,
            })

    return SpeciesData(
        name=name,
        n_levels=n_levels,
        levels=levels,
        n_transitions=n_transitions,
        transitions=transitions,
        collision_partners=coll_partners,
    )


def load_species_transition(filepath, *,
                             freq_GHz=None, wavelength_um=None,
                             E_u_K=None, upper=None, lower=None,
                             tolerance=None):
    """Load LAMDA file and select exactly one transition by physical property.

    Parameters
    ----------
    filepath : str or file-like
    freq_GHz : float
        Target rest frequency [GHz]. Tolerance = 5% of centre.
    wavelength_um : float
        Equivalent to freq_GHz = 299792.458 / wavelength_um.
    E_u_K : float
        Upper-level energy [K]. Tolerance = 5% of centre.
    upper : int
        Upper level J (e.g. 1 for CO J=1→0).
    lower : int
        Lower level J (e.g. 0 for CO J=1→0).
    tolerance : float, optional
        Fractional tolerance (default 0.05 = 5%). Not used for upper/lower.

    Returns
    -------
    species : SpeciesData
    transition : Transition
        The unique matching transition.

    Raises
    ------
    ValueError
        If zero or multiple transitions match the criterion.
    """
    with open(filepath) as f:
        content = f.read()
    return _specify_transition(content, freq_GHz=freq_GHz,
                                wavelength_um=wavelength_um,
                                E_u_K=E_u_K, upper=upper, lower=lower,
                                tolerance=tolerance)


def specify_transition(species, *,
                        freq_GHz=None, wavelength_um=None,
                        E_u_K=None, upper=None, lower=None,
                        tolerance=None):
    """Select exactly one transition from an already-loaded SpeciesData.

    Same semantics as load_species_transition but uses a pre-loaded species.
    Returns (species, transition).
    """
    return species, _specify_transition_one(
        species, freq_GHz=freq_GHz, wavelength_um=wavelength_um,
        E_u_K=E_u_K, upper=upper, lower=lower, tolerance=tolerance)


def _specify_transition(content, **kwargs):
    species = load_lamda(content)
    transition = _specify_transition_one(species, **kwargs)
    return species, transition


def _specify_transition_one(species, *, freq_GHz=None, wavelength_um=None,
                             E_u_K=None, upper=None, lower=None,
                             tolerance=None):
    tol = tolerance if tolerance is not None else 0.05
    criteria = []
    if upper is not None or lower is not None:
        if freq_GHz is not None or wavelength_um is not None or E_u_K is not None:
            raise ValueError(
                "Provide EITHER (upper, lower) OR a physical property")
        if upper is None or lower is None:
            raise ValueError(
                "Both upper and lower must be specified together")
    if freq_GHz is not None:
        if wavelength_um is not None or E_u_K is not None:
            raise ValueError(
                "Provide exactly one of freq_GHz, wavelength_um, E_u_K")
        criteria.append(('freq_GHz', float(freq_GHz)))
    elif wavelength_um is not None:
        if E_u_K is not None:
            raise ValueError(
                "Provide exactly one of freq_GHz, wavelength_um, E_u_K")
        centre = 299792.458 / float(wavelength_um)
        criteria.append(('freq_GHz', centre))
    elif E_u_K is not None:
        criteria.append(('E_u_K', float(E_u_K)))
    elif upper is None:
        raise ValueError(
            "Specify one of freq_GHz, wavelength_um, E_u_K, or (upper, lower)")

    if upper is not None:
        matches = []
        for idx, tr in enumerate(species.transitions_list):
            if int(tr.upper) == int(upper) and int(tr.lower) == int(lower):
                matches.append((idx, tr, 0.0))
    else:
        attr, centre = criteria[0]
        matches = []
        for idx, tr in enumerate(species.transitions_list):
            value = getattr(tr, attr)
            if value <= 0:
                continue
            error = abs(value - centre) / max(abs(centre), 1e-40)
            if error <= tol:
                matches.append((idx, tr, error))

    if len(matches) == 0:
        table = species.show_transitions()
        raise ValueError(
            f"No transition matches {attr}={centre:.4f}"
            f" ± {tol*100:.1f}%.\n{table}")
    if len(matches) > 1:
        lines = [f"Multiple transitions match {attr}={centre:.4f}"
                 f" ± {tol*100:.1f}%:"]
        for idx, tr, err in matches:
            lines.append(f"  idx={idx} {tr}  (error={err:.4f})")
        raise ValueError("\n".join(lines))

    idx, tr, _ = matches[0]
    species._selected_transition = tr
    species._selected_transition_idx = idx
    return tr
