from numpy import asarray, zeros, maximum, abs, exp, clip, copy, \
                  linalg, float64;


h_cgs = 6.62607015e-27;        # Planck constant [ erg s ]
k_B   = 1.380649e-16;          # Boltzmann constant [ erg K^-1 ]


def solve_populations( species_data, exc_flux, n_total, T = None, \
                       colliders = None, n_iter = 20, b_param = 1e5, \
                       transition_idx = 0 ):
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
    n_levels = species_data.n_levels;
    n_total = asarray( n_total, dtype = float64 );
    shape = n_total.shape;

    exc_flux = asarray( exc_flux, dtype = float64 );
    if exc_flux.shape != shape:
        exc_flux = zeros( shape, dtype = float64 );

    n = zeros( ( n_levels, ) + shape, dtype = float64 );

    if n_levels == 2:
        t = species_data.transitions[ \
            transition_idx % len( species_data.transitions ) ];
        upper, lower = int( t[ 0 ] ), int( t[ 1 ] );
        A_ul = float( t[ 2 ] );
        g_u = species_data.get_level_weight( upper );
        g_l = species_data.get_level_weight( lower );
        sigma_0 = species_data.cross_section( transition_idx, b_param );

        n_total_c = maximum( n_total, 1e-30 );
        Gamma = abs( exc_flux ) * sigma_0;

        T_arr = asarray( T, dtype = float64 ) if T is not None else None;
        if T_arr is not None:
            nu = float( t[ 3 ] ) * 1e9;
            dE = h_cgs * nu;
            T_safe = maximum( T_arr, 1e-10 );
            x_arg = clip( dE / ( k_B * T_safe ), None, 700.0 );
            x_planck = 1.0 / ( exp( x_arg ) - 1.0 );
            R_abs = ( g_u / g_l ) * x_planck * A_ul;
            R_stim = x_planck * A_ul;
            n_exc_frac = ( Gamma + R_abs ) / \
                         ( A_ul + R_stim + Gamma + R_abs );
        else:
            n_exc_frac = Gamma / ( A_ul + Gamma );
        n_exc_frac = clip( n_exc_frac, 0, 0.9999 );

        n[ upper ] = n_exc_frac * n_total_c;
        n[ 1 - upper ] = n_total_c - n[ upper ];
        return n;

    # Multi-level: iterate over flattened cells (matrix solver per cell)
    t = species_data.transitions[ \
        transition_idx % len( species_data.transitions ) ];
    upper = int( t[ 0 ] );
    lower = int( t[ 1 ] );
    A_ul = float( t[ 2 ] );
    g_u = species_data.get_level_weight( upper );
    g_l = species_data.get_level_weight( lower );
    sigma_0 = species_data.cross_section( transition_idx, b_param );

    n_total_flat = n_total.ravel( );
    exc_flat = exc_flux.ravel( );
    T_flat = asarray( T, dtype = float64 ).ravel( ) \
             if T is not None else None;
    n_flat = zeros( ( n_levels, n_total_flat.size ), dtype = float64 );

    for c in range( n_total_flat.size ):
        n_total_c = max( n_total_flat[ c ], 1e-30 );
        Gamma = abs( exc_flat[ c ] ) * sigma_0;

        T_c = None;
        if T_flat is not None:
            T_c = float( T_flat[ c ] ) if T_flat.size > 1 \
                  else float( T_flat );

        #  Fast path: nothing can drive excitation out of the ground
        #  state — no external flux, no collisions, and no thermal
        #  (Planck) background.  When a temperature is given, the
        #  Planck background must thermalise the target pair even at
        #  zero external flux, so fall through.
        if Gamma < 1e-40 and colliders is None and \
           ( T_c is None or T_c <= 0 ):
            n_flat[ 0, c ] = n_total_c;
            continue;

        if colliders is None or not species_data.collision_partners:
            if T_c is not None and T_c > 0:
                nu = float( t[ 3 ] ) * 1e9;
                dE = h_cgs * nu;
                x_arg = clip( dE / ( k_B * T_c ), None, 700.0 );
                x_planck = 1.0 / ( exp( x_arg ) - 1.0 );
                R_abs = ( g_u / g_l ) * x_planck * A_ul;
                R_stim = x_planck * A_ul;
                n_exc_frac = ( Gamma + R_abs ) / \
                             ( A_ul + R_stim + Gamma + R_abs );
            else:
                n_exc_frac = Gamma / ( A_ul + Gamma );
            n_exc_frac = clip( n_exc_frac, 0, 0.9999 );
            n_flat[ upper, c ] = n_exc_frac * n_total_c;
            n_flat[ lower, c ] = n_total_c - n_flat[ upper, c ];
            continue;

        for _it in range( n_iter ):
            M = zeros( ( n_levels, n_levels ), dtype = float64 );
            for i in range( n_levels ):
                for j in range( n_levels ):
                    if i == j:
                        continue;
                    rate = 0.0;
                    if j == lower and i == upper:
                        rate += Gamma;
                    if j == upper and i == lower:
                        rate += A_ul;
                    if T_flat is not None:
                        T_c = float( T_flat[ c ] ) if T_flat.size > 1 \
                              else float( T_flat );
                        nu = float( t[ 3 ] ) * 1e9;
                        dE = h_cgs * nu;
                        if T_c > 0:
                            x_arg = clip( dE / ( k_B * T_c ), None, 700.0 );
                            x_planck = 1.0 / ( exp( x_arg ) - 1.0 );
                            if j == lower and i == upper:
                                rate += ( g_u / g_l ) * x_planck * A_ul;
                            if j == upper and i == lower:
                                rate += x_planck * A_ul;
                    if T_flat is not None and species_data.collision_partners:
                        for cp in species_data.collision_partners:
                            partner_name = cp[ 'species' ];
                            if colliders and partner_name in colliders:
                                n_coll = \
                                    colliders[ partner_name ][ 'density' ];
                                n_coll_c = n_coll[ c ] if \
                                           hasattr( n_coll, '__len__' ) \
                                           else n_coll;
                                coll_rate = species_data.get_collision_rate( \
                                    j, i, T_c, partner_name );
                                rate += coll_rate * n_coll_c;
                    M[ i, j ] = rate;
            for i in range( n_levels ):
                M[ i, i ] = -M[ :, i ].sum( );
                if M[ i, i ] == 0.0:
                    M[ i, i ] = -1.0;
            A = copy( M );
            A[ -1, : ] = 1.0;
            b = zeros( n_levels, dtype = float64 );
            b[ -1 ] = n_total_c;
            try:
                sol = linalg.solve( A, b );
                sol = maximum( sol, 0 );
                tot = sol.sum( );
                if tot > 1e-30:
                    sol = sol / tot * n_total_c;
                n_flat[ :, c ] = sol;
            except linalg.LinAlgError:
                n_flat[ 0, c ] = n_total_c;

    return n_flat.reshape( ( n_levels, ) + shape );
