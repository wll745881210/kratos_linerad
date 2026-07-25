import numpy as np


def solve_populations(species_data, fab_per_level, n_total,
                      T=None, colliders=None, n_iter=20):
    n_levels = species_data.n_levels
    n_cells = len(n_total)

    if fab_per_level.ndim == 1:
        fab_per_level = fab_per_level.reshape(1, -1)

    n = np.zeros((n_levels, n_cells), dtype=np.float64)

    if n_levels == 2:
        ground = 0
        excited = 1
        n_total_c = np.maximum(n_total, 1e-30)
        fab_exc = np.abs(fab_per_level[excited, :])
        n_exc_frac = np.clip(fab_exc / n_total_c, 0, 0.9999)
        n[excited, :] = n_exc_frac * n_total_c
        n[ground, :] = n_total_c - n[excited, :]
        return n

    for c in range(n_cells):
        n_total_c = max(n_total[c], 1e-30)
        fab = fab_per_level[:, c].copy()

        fab_abs = np.maximum(fab, 0)
        fab_total = fab_abs.sum()
        if fab_total < 1e-40:
            n[0, c] = n_total_c
            continue

        for _it in range(n_iter):
            M = np.zeros((n_levels, n_levels))

            for i in range(n_levels):
                for j in range(n_levels):
                    if i == j:
                        continue
                    rate = 0.0
                    if fab_abs[i] > 0 and fab_total > 1e-40:
                        rate += fab_abs[i] / fab_total * 1e-10

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

            A = np.copy(M)
            A[-1, :] = 1.0
            b = np.zeros(n_levels)
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
