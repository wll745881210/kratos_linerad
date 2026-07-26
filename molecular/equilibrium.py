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
        n_exc_frac = Gamma / (A_ul + Gamma * (1.0 + g_l / g_u))
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
            n_exc_frac = Gamma / (A_ul + Gamma * (1.0 + g_l / g_u))
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
                        rate += A_ul + Gamma * g_l / g_u

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
