from numpy import asarray, zeros, ones, full, arange, maximum, minimum, \
                  abs, exp, clip, copy, linalg, float64, interp;


h_cgs = 6.62607015e-27;        # Planck constant [ erg s ]
k_B   = 1.380649e-16;          # Boltzmann constant [ erg K^-1 ]
c_cgs = 2.99792458e10;         # speed of light [ cm s^-1 ]


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

    # Multi-level: closed-form on the target pair (no colliders, or no
    # temperature, or no collision-partner data), else a batched
    # collisional steady-state solve.  All vectorised over cells.
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
    n_cells = n_total_flat.size;
    T_flat = asarray( T, dtype = float64 ).ravel( ) \
             if T is not None else None;
    n_flat = zeros( ( n_levels, n_cells ), dtype = float64 );

    n_total_c = maximum( n_total_flat, 1e-30 );
    Gamma = abs( exc_flat ) * sigma_0;

    #  Closed-form branch: no collisional excitation possible.  Cells
    #  with no external flux and no thermal background stay in the
    #  ground state; the rest follow the 2-level formula on the pair.
    if colliders is None or not species_data.collision_partners \
       or T_flat is None:
        nu = float( t[ 3 ] ) * 1e9;
        dE = h_cgs * nu;
        if T_flat is not None:
            T_safe = maximum( T_flat, 1e-10 );
            x_arg = clip( dE / ( k_B * T_safe ), None, 700.0 );
            x_planck = 1.0 / ( exp( x_arg ) - 1.0 );
            R_abs = ( g_u / g_l ) * x_planck * A_ul;
            R_stim = x_planck * A_ul;
            n_exc_frac = ( Gamma + R_abs ) / \
                         ( A_ul + R_stim + Gamma + R_abs );
        else:
            n_exc_frac = Gamma / ( A_ul + Gamma );
        n_exc_frac = clip( n_exc_frac, 0, 0.9999 );

        active = ones( n_cells, dtype = bool );
        if colliders is None:
            ground = ( Gamma < 1e-40 );
            if T_flat is not None:
                ground = ground & ( T_flat <= 0 );
            n_flat[ 0, ground ] = n_total_flat[ ground ];
            active = ~ground;
        if active.any( ):
            n_flat[ upper, active ] = n_exc_frac[ active ] * \
                                      n_total_c[ active ];
            n_flat[ lower, active ] = n_total_c[ active ] - \
                                      n_flat[ upper, active ];
        return n_flat.reshape( ( n_levels, ) + shape );

    #  Collisional steady-state: build the rate matrix for every cell and
    #  solve all cells in one batched call.  M[i, j] = rate from level j
    #  to level i; the diagonal is the (negative) total loss rate.
    nu = float( t[ 3 ] ) * 1e9;
    dE = h_cgs * nu;
    L = n_levels;
    M = zeros( ( n_cells, L, L ), dtype = float64 );

    T_safe = maximum( T_flat, 1e-10 );
    x_arg = clip( dE / ( k_B * T_safe ), None, 700.0 );
    x_planck = 1.0 / ( exp( x_arg ) - 1.0 );

    M[ :, upper, lower ] += Gamma;
    M[ :, lower, upper ] += A_ul;
    M[ :, upper, lower ] += ( g_u / g_l ) * x_planck * A_ul;
    M[ :, lower, upper ] += x_planck * A_ul;

    for cp in species_data.collision_partners:
        partner_name = cp[ 'species' ];
        if not ( colliders and partner_name in colliders ):
            continue;
        n_coll = colliders[ partner_name ][ 'density' ];
        n_coll_arr = asarray( n_coll, dtype = float64 ).ravel( ) \
                     if hasattr( n_coll, '__len__' ) \
                     else full( n_cells, float( n_coll ) );
        idxs = cp[ 'trans_indices' ];
        for k in range( idxs.shape[ 0 ] ):
            j, i = int( idxs[ k, 0 ] ), int( idxs[ k, 1 ] );
            rate = interp( T_flat, cp[ 'temps' ], cp[ 'rates' ][ k ] );
            M[ :, i, j ] += rate * n_coll_arr;
            #  Detailed balance: collisional excitation (lower -> upper)
            #  from the tabulated de-excitation rate so the gas relaxes to
            #  LTE at high collider density.
            dE_coll = float( species_data.levels[ j, 0 ] - \
                             species_data.levels[ i, 0 ] ) * h_cgs * \
                      c_cgs * 100.0;
            g_j = species_data.get_level_weight( j );
            g_i = species_data.get_level_weight( i );
            M[ :, j, i ] += rate * n_coll_arr * ( g_j / g_i ) * \
                            exp( clip( -dE_coll / ( k_B * T_safe ), \
                                       None, 700.0 ) );

    diag = -M.sum( axis = 1 );
    diag[ diag == 0.0 ] = -1.0;
    ar = arange( L );
    M[ :, ar, ar ] = diag;

    A = copy( M );
    A[ :, -1, : ] = 1.0;
    b = zeros( ( n_cells, L, 1 ), dtype = float64 );
    b[ :, -1, 0 ] = n_total_flat;
    try:
        sol = linalg.solve( A, b );      # (n_cells, L, 1), batched
        sol = sol[ :, :, 0 ];
        sol = maximum( sol, 0 );
        tot = maximum( sol.sum( axis = 1, keepdims = True ), 1e-30 );
        sol = sol / tot * n_total_flat[ :, None ];
        n_flat = sol.T;
    except linalg.LinAlgError:
        #  A singular batch: solve the offending cells one at a time.
        for c in range( n_cells ):
            Ac = copy( A[ c ] );
            bc = b[ c ];
            try:
                sc = linalg.solve( Ac, bc );
                sc = sc[ :, 0 ];
                sc = maximum( sc, 0 );
                tc = max( sc.sum( ), 1e-30 );
                n_flat[ :, c ] = sc / tc * n_total_flat[ c ];
            except linalg.LinAlgError:
                n_flat[ 0, c ] = n_total_flat[ c ];

    return n_flat.reshape( ( n_levels, ) + shape );
