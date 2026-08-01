import numpy as np


def solve_populations(species_data, exc_flux, n_total,
                      T=None, colliders=None, n_iter=20, b_param=1e5,
                      transition_idx=0):
    """
    Solve for steady-state level populations given an excitation flux.

    Parameters
    ----------
    species_data : Species
    exc_flux : ndarray
        1D array (n_cells,) — the overlap-integrated radiative excitation
        fluence F_ext for ONE transition.  Each transition is defined by a
        (lower, upper) pair; injecting this flux excites the lower level
        of the target transition to its upper level.  It is **not** a
        per-level flux — only the target pair receives the excitation rate.
    n_total : ndarray (n_cells,)
    T : ndarray, optional
    colliders : dict, optional
    n_iter : int
    b_param : float
        Doppler b used for the cross-section σ₀ of the target transition.
    transition_idx : int
        Index into species_data.transitions for the pumped transition.
    """
    n_levels = species_data.n_levels
    n_cells = len(n_total)

    exc_flux = np.asarray(exc_flux, dtype=np.float64).ravel()
    if exc_flux.shape[0] != n_cells:
        exc_flux = np.zeros(n_cells, dtype=np.float64)

    n = np.zeros((n_levels, n_cells), dtype=np.float64)

    if n_levels == 2:
        t = species_data.transitions[transition_idx % len(species_data.transitions)]
        upper, lower = int(t[0]), int(t[1])
        A_ul = float(t[2])
        g_u = species_data.get_level_weight(upper)
        g_l = species_data.get_level_weight(lower)
        sigma_0 = species_data.cross_section(transition_idx, b_param)

        n_total_c = np.maximum(n_total, 1e-30)
        Gamma = np.abs(exc_flux) * sigma_0

        # Thermal background (Planck) at temperature T.
        # Bose-Einstein occupation: x = 1/(exp(h*nu/kT) - 1)
        # R_abs = (g_u/g_l) * x * A_ul   (induced absorption)
        # R_stim = x * A_ul               (stimulated emission)
        # Without external radiation field (no background):
        #   n_u/n = Gamma / (A_ul + Gamma)
        # With Planck background at T:
        #   n_u/n = (Gamma + R_abs) / (A_ul + R_stim + Gamma + R_abs)
        # At Gamma=0 this reduces to the Boltzmann distribution.
        T_arr = np.asarray(T, dtype=np.float64) if T is not None else None
        if T_arr is not None:
            nu = float(t[3]) * 1e9
            dE = 6.62607015e-27 * nu
            kB = 1.380649e-16
            T_safe = np.maximum(T_arr.ravel(), 1e-10)
            x_planck = 1.0 / (np.exp(dE / (kB * T_safe)) - 1.0)
            R_abs = (g_u / g_l) * x_planck * A_ul
            R_stim = x_planck * A_ul
            n_exc_frac = (Gamma + R_abs) / (A_ul + R_stim + Gamma + R_abs)
        else:
            n_exc_frac = Gamma / (A_ul + Gamma)
        n_exc_frac = np.clip(n_exc_frac, 0, 0.9999)

        n[upper, :] = n_exc_frac * n_total_c
        n[1 - upper, :] = n_total_c - n[upper, :]
        return n

    t = species_data.transitions[transition_idx % len(species_data.transitions)]
    upper = int(t[0])
    lower = int(t[1])
    A_ul = float(t[2])
    g_u = species_data.get_level_weight(upper)
    g_l = species_data.get_level_weight(lower)
    sigma_0 = species_data.cross_section(transition_idx, b_param)

    for c in range(n_cells):
        n_total_c = max(n_total[c], 1e-30)

        Gamma = np.abs(exc_flux[c]) * sigma_0

        if Gamma < 1e-40 and colliders is None:
            n[0, c] = n_total_c
            continue

        if colliders is None or not species_data.collision_partners:
            T_c = None
            if T is not None:
                T_arr = np.asarray(T, dtype=np.float64)
                T_c = float(T_arr.ravel()[c]) if T_arr.size > 1 else float(T_arr)
            if T_c is not None and T_c > 0:
                nu = float(t[3]) * 1e9
                dE = 6.62607015e-27 * nu
                kB = 1.380649e-16
                x_planck = 1.0 / (np.exp(dE / (kB * T_c)) - 1.0)
                R_abs = (g_u / g_l) * x_planck * A_ul
                R_stim = x_planck * A_ul
                n_exc_frac = (Gamma + R_abs) / (A_ul + R_stim + Gamma + R_abs)
            else:
                n_exc_frac = Gamma / (A_ul + Gamma)
            n_exc_frac = np.clip(n_exc_frac, 0, 0.9999)
            n[upper, c] = n_exc_frac * n_total_c
            n[lower, c] = n_total_c - n[upper, c]
            continue

        for _it in range(n_iter):
            M = np.zeros((n_levels, n_levels), dtype=np.float64)

            for i in range(n_levels):
                for j in range(n_levels):
                    if i == j:
                        continue
                    rate = 0.0

                    if j == lower and i == upper:
                        rate += Gamma
                    if j == upper and i == lower:
                        rate += A_ul
                    if T is not None:
                        T_c = T[c] if hasattr(T, '__len__') and T.ndim > 0 else T
                        nu = float(t[3]) * 1e9
                        dE = 6.62607015e-27 * nu
                        kB = 1.380649e-16
                        if T_c > 0:
                            x_planck = 1.0 / (np.exp(dE / (kB * float(T_c))) - 1.0)
                            if j == lower and i == upper:
                                rate += (g_u / g_l) * x_planck * A_ul
                            if j == upper and i == lower:
                                rate += x_planck * A_ul

                    if T is not None and species_data.collision_partners:
                        T_c = T[c] if T.ndim > 0 else T
                        for cp in species_data.collision_partners:
                            partner_name = cp['species']
                            if colliders and partner_name in colliders:
                                n_coll = colliders[partner_name]['density']
                                n_coll_c = n_coll[c] if hasattr(
                                    n_coll, '__len__') else n_coll
                                coll_rate = species_data.get_collision_rate(
                                    j, i, T_c, partner_name)
                                rate += coll_rate * n_coll_c

                    M[i, j] = rate

            for i in range(n_levels):
                M[i, i] = -np.sum(M[:, i])
                if M[i, i] == 0.0:
                    M[i, i] = -1.0

            A = np.copy(M)
            A[-1, :] = 1.0
            b = np.zeros(n_levels, dtype=np.float64)
            b[-1] = n_total_c

            try:
                sol = np.linalg.solve(A, b)
                sol = np.maximum(sol, 0)
                tot = sol.sum()
                if tot > 1e-30:
                    sol = sol / tot * n_total_c
                n[:, c] = sol
            except np.linalg.LinAlgError:
                n[0, c] = n_total_c

    return n
