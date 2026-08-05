import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize
from mpl_toolkits.axes_grid1 import make_axes_locatable
from numbers import Real
from numpy import asarray, zeros_like, ones_like, ones, array, ceil, \
                  log10, clip, abs, float64, atleast_2d, average, \
                  zeros, arange, int32, isfinite

from .fields import slice_plot_2d

_PLANE_MAP = { 'x' : 'yz', 'y' : 'xz', 'z' : 'xy' };

# Fields with signed values (can be negative/zero) that must use a
# linear colormap, not LogNorm.
_LINEAR_FIELDS = { 'vel_0', 'vel_1', 'vel_2' };

################################################################################
# Default multi-panel plot

_DEFAULT_FIELDS = [ 'spectrum', 'flx', 'mfp_i_sca_0', 'b_sca', \
                    'excited_fraction', 'emissivity', ];

_FIELD_LABELS = { 'flx'             : r'flux [photons cm$^{-2}$ s$^{-1}$]', \
                  'mfp_i_sca_0'     : r'mfp_i_sca_0 [cm$^{-1}$]', \
                  'mfp_i_abs_0'     : r'mfp_i_abs_0 [cm$^{-1}$]', \
                  'b_sca'           : r'b_sca [km s$^{-1}$]', \
                  'n_species'       : r'n$_{\rm species}$ [cm$^{-3}$]', \
                  'temperature'     : r'T [K]', \
                  'vel_0'           : r'$v_x$ [km s$^{-1}$]', \
                  'vel_1'           : r'$v_y$ [km s$^{-1}$]', \
                  'vel_2'           : r'$v_z$ [km s$^{-1}$]', \
                  'excited_fraction': r'n$_{\rm exc}$ / n$_{\rm tot}$', \
                  'emissivity'      : \
                      r'$\epsilon$ [photons s$^{-1}$ cm$^{-3}$ sr$^{-1}$]', };

_FIELD_TITLES = { 'spectrum'        : 'Emergent Spectrum', \
                  'flx'             : 'Flux Map', \
                  'mfp_i_sca_0'     : 'mfp_i_sca_0', \
                  'mfp_i_abs_0'     : 'mfp_i_abs_0', \
                  'b_sca'           : 'b_sca', \
                  'n_species'       : 'n_species', \
                  'temperature'     : 'Temperature', \
                  'vel_0'           : r'$v_x$', \
                  'vel_1'           : r'$v_y$', \
                  'vel_2'           : r'$v_z$', \
                  'excited_fraction': 'Excited Fraction', \
                  'emissivity'      : 'Emissivity', };
#

def _slice_array( data, mesh, plane = 'xy', slice_idx = None ):
    """Return the 2-D slice array that slice_plot_2d would plot.

    Mirrors the reshaping / slicing / transpose done in
    core/fields.slice_plot_2d so that colour limits computed here
    match the data actually rendered in the panel.
    """
    n_cell = mesh.get( 'n_cell', mesh.get( 'n_cell_global', [ 1, 1, 1 ] ) );
    nx, ny, nz = int( n_cell[ 0 ] ), int( n_cell[ 1 ] ), int( n_cell[ 2 ] );
    d = asarray( data );
    if d.ndim == 1:
        if d.size > nx * ny * nz:
            d3 = d.reshape( nz, ny, nx, -1 )[ :, :, :, 0 ];
        else:
            d3 = d.reshape( nz, ny, nx );
    else:
        d3 = d;

    coords = mesh.get( 'coords', 'cartesian' );
    if coords == 'cartesian':
        if plane == 'xy':
            si = slice_idx if slice_idx is not None else nz // 2;
            return d3[ si, :, : ].T;
        elif plane == 'xz':
            si = slice_idx if slice_idx is not None else ny // 2;
            return d3[ :, si, : ].T;
        elif plane == 'yz':
            si = slice_idx if slice_idx is not None else nx // 2;
            return d3[ :, :, si ].T;
    elif coords == 'spherical':
        phi_face = mesh.get( 'phi_face', [ ] );
        if plane == 'rtheta':
            si = slice_idx if slice_idx is not None else \
                 ( len( phi_face ) - 1 ) // 2;
            return d3[ :, :, si ].T;
    # fall back to the full array (limits over everything)
    return d3;
#

def _panel_norm( dyn_range, slc ):
    """Resolve the per-panel colour norm for default_plot.

    ``dyn_range`` accepts a boolean or a number:

      * ``False``/``None`` - unconstrained LogNorm( ).
      * ``True`` - logarithmic with dynamic range clipped to 6 dex
        (upper = 10^ceil of the slice max).
      * number ``D`` - like ``True`` but clipped to ``D`` dex.

    When ``dyn_range`` is ``True`` or a number and the plotted
    slice actually spans less than 1 dex, a linear
    ``Normalize`` is returned instead, with vmin/vmax equal to
    the slice's actual min/max.
    """
    pos = slc[ ( slc > 0 ) & isfinite( slc ) ];
    if dyn_range is False or dyn_range is None:
        return LogNorm( );
    if pos.size == 0:
        return None;
    dex = 6.0 if dyn_range is True else \
          ( float( dyn_range ) if isinstance( dyn_range, Real ) and \
            not isinstance( dyn_range, bool ) else 6.0 );
    pmax = float( pos.max( ) );
    pmin = float( pos.min( ) );
    actual_span = log10( pmax ) - log10( pmin );
    if actual_span < 1.0:
        # nearly constant panel: linear scale matching the slice range
        vmin_l = float( slc.min( ) );
        vmax_l = float( slc.max( ) );
        if not ( vmax_l > vmin_l ):
            # degenerate (constant) slice: widen slightly so the
            # colour scale is non-empty
            pad = max( abs( vmin_l ) * 1e-3, 1e-12 );
            vmax_l = vmin_l + pad;
        return Normalize( vmin = vmin_l, vmax = vmax_l );
    upper_dex = int( ceil( log10( pmax ) ) );
    vmax = 10.0 ** upper_dex;
    span = int( clip( actual_span, 1, dex ) );
    vmin = 10.0 ** ( upper_dex - span );
    if vmin >= vmax:
        vmin = vmax * 1e-3;
    return LogNorm( vmin = vmin, vmax = vmax );
#

def _resolve_log_norm( dyn_range, pos ):
    """Build the shared LogNorm for channel maps.

    ``pos`` is the flattened array of positive finite values to
    be coloured.  ``dyn_range`` is multi-purpose:

      * bool ``True``  - auto limits, dynamic range clipped to
        4 dex (upper = 10^ceil of the max).
      * bool ``False`` - plain LogNorm( ), no clipping.
      * number ``D``   - like ``True`` but clips the dynamic
        range to ``D`` dex.
      * list/tuple of 2 numbers ``[hi, lo]`` - explicit limits:
        vmax = 10^max(hi, lo), vmin = 10^min(hi, lo).  Values
        below vmin (incl. non-positive) saturate to the bottom
        colour rather than being masked.

    Returns a LogNorm or None if no positive finite values.
    """
    if pos.size == 0:
        return None;
    if dyn_range is False:
        return LogNorm( );
    if isinstance( dyn_range, ( list, tuple ) ) and \
       len( dyn_range ) == 2:
        hi, lo = float( dyn_range[ 0 ] ), float( dyn_range[ 1 ] );
        return LogNorm( vmin = 10.0 ** min( hi, lo ), \
                        vmax = 10.0 ** max( hi, lo ), clip = True );
    # auto path: bool True (default) or a number D = max dex span
    dex = 4 if dyn_range is True else \
          ( float( dyn_range ) if isinstance( dyn_range, Real ) and \
            not isinstance( dyn_range, bool ) else 4 );
    pmax = float( pos.max( ) );
    pmin = float( pos.min( ) );
    if not isfinite( pmax ) or pmax <= 0:
        pmax = 1.0;
    if not isfinite( pmin ) or pmin <= 0:
        pmin = pmax * 1e-4;
    upper_dex = int( ceil( log10( pmax ) ) );
    vmax = 10.0 ** upper_dex;
    span = upper_dex - log10( pmin );
    span = int( clip( span, 1, dex ) );
    vmin = 10.0 ** ( upper_dex - span );
    if vmin >= vmax:
        vmin = vmax * 1e-3;
    # clip=True saturates values below vmin (incl. <=0) to
    # the bottom colour instead of masking them to white.
    return LogNorm( vmin = vmin, vmax = vmax, clip = True );
#

def _extract_field( results, field, unit_l0 = 1.0, unit_t0 = 1.0 ):
    """Extract a 3D field array or spectrum data from the results dict.

    Returns (data_3d_or_none, is_spectrum).
    """
    last = results.get( 'results', [ { } ] )[ -1 ] \
           if results.get( 'results' ) else { };

    if field == 'spectrum':
        return None, True;

    if field == 'excited_fraction':
        pops = results.get( 'populations', None );
        if pops is None:
            pops = last.get( 'populations', None );
        if pops is None:
            return None, False;
        n0 = asarray( pops.get( 'n0', pops.get( 'n_total', ones( 1 ) ) ), \
                      dtype = float64 );
        n_exc_keys = [ k for k in pops if k.startswith( 'n' ) and \
                       k != 'n0' and k != 'n_total' ];
        n_exc = zeros_like( n0 );
        for k in n_exc_keys:
            n_exc = n_exc + asarray( pops[ k ], dtype = float64 );
        denom = n0 + n_exc;
        denom[ denom == 0 ] = 1.0;
        return n_exc / denom, False;

    if field == 'b_sca':
        b = results.get( 'b_sca', None );
        if b is None:
            return None, False;
        b = asarray( b, dtype = float64 );
        # convert cm/s -> km/s
        return b * 1e-5, False;

    if field in ( 'vel_0', 'vel_1', 'vel_2' ):
        v = results.get( field, None );
        if v is None:
            return None, False;
        v = asarray( v, dtype = float64 );
        # convert cm/s -> km/s
        return v * 1e-5, False;

    # generic: look in results first, then last cycle output
    val = results.get( field, None );
    if val is None:
        val = last.get( field, None );
    if val is None:
        return None, False;
    return asarray( val, dtype = float64 ), False;
#

def default_plot( results, fields = None, slice_plane = 'z', \
                  slice_idx = None, ax = None, figsize = None, \
                  output_path = None, dyn_range = False, \
                  transition_info = None ):
    """Multi-panel default plot for LineRt results.

    2-column layout; number of rows = ceil(len(fields)/2).

    Parameters
    ----------
    results : dict  from LineRt.run()
    fields : list[str] or None  field names (default: spectrum, flx,
        mfp_i_sca_0, b_sca, excited_fraction, emissivity).
    slice_plane : str  "x"|"y"|"z"  slice axis for colormaps (default "z"
        -> xy plane).
    slice_idx : int or None  cell index along slice_plane (default: middle).
    ax : array of Axes or None  (created if None).
    figsize : tuple or None.
    output_path : str or None  save figure if given.
    dyn_range : bool, number, or None  colour-scale control for the
        colormap panels (spectrum panel unaffected).  ``False``/``None``
        (default) uses an unconstrained LogNorm.  ``True`` applies
        logarithmic limits (upper = 10^ceil(log10(slice max)); lower =
        10^(upper_dex - clip(span, 1, 6))).  A number ``D`` does the
        same but clips the dynamic range to ``D`` dex.  When ``True``
        or a number is given and a panel's actual slice spans less
        than 1 dex, a linear ``Normalize`` is used instead, with
        vmin/vmax equal to the slice's actual min/max.
    transition_info : TransitionInfo or None  when given, labels the
        spectrum panel with the transition name (e.g. "CO J=1->0").
    """
    if fields is None:
        fields = list( _DEFAULT_FIELDS );

    n = len( fields );
    nrows = ( n + 1 ) // 2;
    ncols = 2;

    if ax is None:
        fig, axes = plt.subplots( nrows, ncols, \
                                  figsize = figsize or ( 12, 4 * nrows ), \
                                  squeeze = False );
    else:
        axes = atleast_2d( ax );
        fig = axes[ 0, 0 ].figure;

    mesh = results.get( 'mesh', { } );
    unit_l0 = results.get( 'unit_l0', 1.0 );
    unit_t0 = results.get( 'unit_t0', 1.0 );
    plane = _PLANE_MAP.get( slice_plane, 'xy' );

    for i, field in enumerate( fields ):
        row, col = divmod( i, ncols );
        ax_i = axes[ row, col ];
        title = _FIELD_TITLES.get( field, field );

        data, is_spectrum = _extract_field( results, field, unit_l0, unit_t0 );

        if is_spectrum:
            _draw_spectrum( ax_i, results );
            if transition_info is not None:
                tr = transition_info.transition;
                title = transition_info.transition_name;
            ax_i.set_title( title );
            continue;

        if data is None:
            ax_i.set_title( title );
            ax_i.text( 0.5, 0.5, '(no data)', \
                       transform = ax_i.transAxes, ha = 'center', \
                       va = 'center', fontsize = 10 );
            ax_i.set_xticks( [ ] );
            ax_i.set_yticks( [ ] );
            continue;

        if field in _LINEAR_FIELDS or ( data <= 0 ).all(  ):
            norm = None;
        elif dyn_range:
            # compute limits on the plotted slice so they match the panel
            slc = _slice_array( data, mesh, plane = plane, \
                                slice_idx = slice_idx );
            norm = _panel_norm( dyn_range, slc );
        else:
            norm = LogNorm(  );

        pc = slice_plot_2d( ax_i, data, mesh, plane = plane, \
                            slice_idx = slice_idx, log = ( norm is None ), \
                            cmap = 'turbo', norm = norm );
        if pc is not None:
            cbar = plt.colorbar( pc, ax = ax_i );
            if field.startswith( 'n_coll_' ):
                pname = field[ 7: ];
                label = r'n$_{\rm %s}$ [cm$^{-3}$]' % pname;
            else:
                label = _FIELD_LABELS.get( field, field );
            cbar.set_label( label );
        ax_i.set_title( title );

    # hide unused subplots
    for i in range( n, nrows * ncols ):
        row, col = divmod( i, ncols );
        axes[ row, col ].set_visible( False );

    fig.tight_layout(  );
    if output_path:
        fig.savefig( output_path, dpi = 150, bbox_inches = 'tight' );
    return fig, axes;
#

def _draw_spectrum( ax, results, bins = 80 ):
    """Draw emergent spectrum histogram in km/s."""
    vel = array( [ ] );
    weights = array( [ ] );
    spec = results.get( 'spectrum', { } );
    if spec:
        vel = asarray( spec.get( 'vel', [ ] ) );
        weights = asarray( spec.get( 'n', spec.get( 'proper', \
                                                    ones_like( vel ) ) ) );
    if len( vel ) == 0:
        for r in reversed( results.get( 'results', [ ] ) ):
            phot = r.get( 'photons', { } );
            vel = asarray( phot.get( 'vel', [ ] ) );
            if len( vel ) > 0:
                w_arr = asarray( phot.get( 'proper', ones_like( vel ) ) );
                weights = w_arr.ravel(  ) if w_arr.size == vel.size \
                    else ones_like( vel );
                break;

    if len( vel ) == 0:
        ax.text( 0.5, 0.5, '(no escaped photons)', \
                 transform = ax.transAxes, ha = 'center', \
                 va = 'center', fontsize = 10 );
        ax.set_xticks( [ ] );
        ax.set_yticks( [ ] );
        return;

    vel_kms = vel.ravel(  ) * 1e-5;
    ax.hist( vel_kms, bins = bins, weights = weights.ravel(  ), \
             histtype = 'step', color = 'black' );
    ax.set_xlabel( r'$\Delta v$ [km s$^{-1}$]' );
    ax.set_ylabel( 'count' );
#

################################################################################
# Legacy single-panel helpers (kept for backward compat)

def _find_median( data_flat, mesh, axis ):
    """Return median cell centre coordinate in CGS for a given axis."""
    n = int( mesh[ 'n_cell' ][ 'xyz'.index( axis ) ] );
    dx_val = mesh[ 'dx' ][ 'xyz'.index( axis ) ];
    x0 = mesh[ 'x_min' ][ 'xyz'.index( axis ) ];
    return x0 + ( n // 2 + 0.5 ) * dx_val;
#

def _axis_to_slice( data_flat, mesh, axis, coord ):
    """Convert flat data to 2D slice at given axis and coordinate."""
    n_cell = mesh[ 'n_cell' ];
    nx, ny, nz = int( n_cell[ 0 ] ), int( n_cell[ 1 ] ), \
                 int( n_cell[ 2 ] );

    if data_flat.size > nx * ny * nz:
        data_3d = data_flat.reshape( nz, ny, nx, -1 )[ :, :, :, 0 ];
    else:
        data_3d = data_flat.reshape( nz, ny, nx );

    dx_val = mesh[ 'dx' ][ 'xyz'.index( axis ) ];
    x0 = mesh[ 'x_min' ][ 'xyz'.index( axis ) ];
    nc = int( n_cell[ 'xyz'.index( axis ) ] );

    idx = int( ( coord - x0 ) / dx_val );
    idx = max( 0, min( idx, nc - 1 ) );

    if axis == 'x':
        return data_3d[ :, :, idx ], mesh, 'yz', idx;
    elif axis == 'y':
        return data_3d[ :, idx, : ], mesh, 'xz', idx;
    else:
        return data_3d[ idx, :, : ], mesh, 'xy', idx;
#

def plot_flux( results, axis = 'x', coord = None, ax = None, \
               output_path = None, log = True, cmap = 'turbo' ):
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
        _, ax = plt.subplots(  );
    mesh = results.get( 'mesh', { } );
    flx = results.get( 'flx', None );
    if flx is None and results.get( 'results' ):
        flx = results[ 'results' ][ -1 ].get( 'flx', None );
    if flx is None:
        ax.text( 0.5, 0.5, 'No flux data', transform = ax.transAxes, \
                 ha = 'center', va = 'center' );
        return;

    flx = asarray( flx, dtype = float64 ).ravel(  );
    if coord is None:
        coord = _find_median( flx, mesh, axis );

    slc, _, plane, si = _axis_to_slice( flx, mesh, axis, coord );

    pc = slice_plot_2d( ax, slc.ravel(  ), mesh, plane = plane, \
                        slice_idx = si, log = log, cmap = cmap );

    other = _other_axes( axis );
    ax.set_xlabel( '%s [AU]' % other[ 0 ] );
    ax.set_ylabel( '%s [AU]' % other[ 1 ] );

    ax.set_box_aspect( _aspect_ratio( mesh, axis ) );

    cbar = plt.colorbar( pc, ax = ax );
    cbar.set_label( 'Flux [photons cm$^{-2}$ s$^{-1}$]' );
    ax.set_title( 'Flux slice (%s, %s=%.1f AU)' % ( plane, axis, coord ) );

    if output_path:
        plt.savefig( output_path, dpi = 150, bbox_inches = 'tight' );
    plt.show(  );
#

def plot_population( results, axis = 'x', coord = None, ax = None, \
                     output_path = None, log = True, cmap = 'plasma' ):
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
        _, ax = plt.subplots(  );
    mesh = results.get( 'mesh', { } );
    pops = results.get( 'populations', None );
    if pops is None and results.get( 'results' ):
        pops = results[ 'results' ][ -1 ].get( 'populations', None );
    if pops is None:
        ax.text( 0.5, 0.5, 'No population data', \
                 transform = ax.transAxes, ha = 'center', va = 'center' );
        return;

    n0 = asarray( pops.get( 'n0', pops.get( 'n_total', ones( 1 ) ) ), \
                  dtype = float64 ).ravel(  );
    n_exc_keys = [ k for k in pops.keys(  ) if k.startswith( 'n' ) and \
                   k != 'n0' and k != 'n_total' ];
    n_exc = zeros_like( n0 );
    for k in n_exc_keys:
        n_exc += asarray( pops[ k ], dtype = float64 ).ravel(  );
    denom = n0 + n_exc;
    denom[ denom == 0 ] = 1.0;
    frac = n_exc / denom;

    if coord is None:
        coord = _find_median( frac, mesh, axis );

    slc, _, plane, si = _axis_to_slice( frac, mesh, axis, coord );
    pc = slice_plot_2d( ax, slc.ravel(  ), mesh, plane = plane, \
                        slice_idx = si, log = log, cmap = cmap );

    other = _other_axes( axis );
    ax.set_xlabel( '%s [AU]' % other[ 0 ] );
    ax.set_ylabel( '%s [AU]' % other[ 1 ] );

    ax.set_box_aspect( _aspect_ratio( mesh, axis ) );

    cbar = plt.colorbar( pc, ax = ax );
    cbar.set_label( 'n$_{\\rm exc}$ / (n$_0$ + n$_{\\rm exc}$) ' \
                    '[dimensionless]' );
    ax.set_title( 'Excited fraction (%s, %s=%.1f AU)' % \
                  ( plane, axis, coord ) );

    if output_path:
        plt.savefig( output_path, dpi = 150, bbox_inches = 'tight' );
    plt.show(  );
#

def plot_spectrum( results, ax = None, bins = 80, xlim = None, \
                   output_path = None, label = '' ):
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
        _, ax = plt.subplots(  );
    spectrum = results.get( 'spectrum', { } );
    vel = asarray( spectrum.get( 'vel', [ ] ) );
    weights = asarray( spectrum.get( 'n', \
                                     spectrum.get( 'weights', \
                                                   ones_like( vel ) ) ) );

    if len( vel ) == 0:
        for r in reversed( results.get( 'results', [ ] ) ):
            phot = r.get( 'photons', { } );
            vel = asarray( phot.get( 'vel', [ ] ) );
            if len( vel ) > 0:
                break;

    if len( vel ) == 0:
        ax.text( 0.5, 0.5, 'No escaped photons', \
                 transform = ax.transAxes, ha = 'center', va = 'center' );
        ax.set_xlabel( 'velocity [cm/s]' );
        ax.set_ylabel( 'count' );
        return;

    ax.hist( vel.ravel(  ), bins = bins, weights = weights.ravel(  ), \
             histtype = 'step', density = False, \
             label = label if label else None );

    ax.set_xlabel( '$\\Delta v$ [cm s$^{-1}$]' );
    ax.set_ylabel( 'count' );
    if xlim is not None:
        ax.set_xlim( xlim );
    if label:
        ax.legend(  );

    if output_path:
        plt.savefig( output_path, dpi = 150, bbox_inches = 'tight' );
    plt.show(  );
#

def _other_axes( axis ):
    if axis == 'x':
        return ( 'y', 'z' );
    elif axis == 'y':
        return ( 'x', 'z' );
    else:
        return ( 'x', 'y' );
#

def _aspect_ratio( mesh, axis ):
    dx = mesh[ 'dx' ];
    n_cell = mesh[ 'n_cell' ];
    if axis == 'x':
        return ( n_cell[ 1 ] * dx[ 1 ] ) / ( n_cell[ 2 ] * dx[ 2 ] );
    elif axis == 'y':
        return ( n_cell[ 0 ] * dx[ 0 ] ) / ( n_cell[ 2 ] * dx[ 2 ] );
    else:
        return ( n_cell[ 0 ] * dx[ 0 ] ) / ( n_cell[ 1 ] * dx[ 1 ] );
#

################################################################################
# Backward-compatible wrappers (low-level API)

def plot_emergent_spectrum( ax, photons, bins = 80, xlim = None, \
                            label = '' ):
    if isinstance( photons, dict ):
        vel = asarray( photons.get( 'vel', [ ] ) );
        l_arr = asarray( photons.get( 'proper', \
                       photons.get( 'l', [ ] ) ) );
    else:
        raise TypeError( "photons must be a dict with 'vel' and "
                         "'proper' keys" );

    if len( vel ) == 0:
        ax.text( 0.5, 0.5, 'No escaped photons', \
                 transform = ax.transAxes, ha = 'center', va = 'center' );
        return;

    weights  = l_arr.ravel(  );
    vel_flat = vel  .ravel(  );

    ax.hist( vel_flat, bins = bins, weights = weights, \
             histtype = 'step', density = False, \
             label = label if label else None );

    ax.set_xlabel( 'velocity [cm/s]' );
    ax.set_ylabel( 'proper-weighted count' );
    if xlim is not None:
        ax.set_xlim( xlim );
    if label:
        ax.legend(  );
#

def plot_flux_slice( ax, flx, mesh, title = '', log = True, \
                     cmap = 'turbo', cbar_label = None, slice_idx = None ):
    pc = slice_plot_2d( ax, flx, mesh, plane = 'xy', \
                        slice_idx = slice_idx, log = log, cmap = cmap );
    label = cbar_label or 'flux [photons cm$^{-2}$ s$^{-1}$]';
    plt.colorbar( pc, ax = ax, label = label );
    ax.set_title( title or 'Flux slice (xy)' );
#

def plot_population_map( ax, n, mesh, level = 0, title = '', log = True, \
                         cmap = 'plasma', cbar_label = None ):
    pc = slice_plot_2d( ax, n, mesh, plane = 'xy', slice_idx = None, \
                        log = log, cmap = cmap );
    label = cbar_label or 'n%d [cm$^{-3}$]' % level;
    plt.colorbar( pc, ax = ax, label = label );
    ax.set_title( title or 'Population level %d slice (xy)' % level );
#

def plot_convergence( ax, pop_history, cycles ):
    deltas = [ 0.0 ];
    keys = sorted( pop_history[ 0 ].keys(  ) );
    for k in range( 1, len( pop_history ) ):
        med_delta = max( average( abs( pop_history[ k ][ key ] - \
                                       pop_history[ k - 1 ][ key ] ) ) \
                         for key in keys );
        deltas.append( float( med_delta ) );

    ax.plot( cycles[ : len( deltas ) ], deltas, 'o-', color = 'black' );
    ax.set_xlabel( 'Cycle' );
    ax.set_ylabel( r'$\max\overline{|\Delta n|}$' );
    ax.set_title( 'Population convergence' );
#

################################################################################
# Channel-map grid for imaging cubes

def plot_channel_maps( results, channels = None, n_cols = 6, \
                       n_channels = None, dyn_range = True, ax = None, \
                       figsize = None, output_path = None, cmap = 'magma', \
                       transition_info = None ):
    """Plot a grid of single-channel spatial maps from the
    imaging cube.

    All panels share a single colour scale.  ``dyn_range`` is
    multi-purpose:

      * ``True`` (default): logarithmic scale, dynamic range
        clipped to 4 dex (upper = 10^ceil of the global max).
      * ``False``: plain logarithmic scale, no clipping.
      * number ``D``: like ``True`` but clips the dynamic range
        to ``D`` dex.
      * ``[hi, lo]``: explicit log10 limits, vmin = 10^min(hi,
        lo), vmax = 10^max(hi, lo).

    Values below the lower limit (including non-positive values)
    saturate to the bottom colour rather than being masked out.

    Parameters
    ----------
    results : dict  from LineRt.run() containing 'image'.
    channels : list[int] or None  channel indices to plot.  If
        None, selects ``n_cols`` channels centred on the
        spectral peak.
    n_cols : int  number of columns in the panel grid.
    n_channels : int or None  total number of channels to plot
        (selected around the spectral peak).  If None, defaults
        to ``n_cols`` (one row).  Ignored when ``channels``
        is given explicitly.
    dyn_range : bool, number, or [hi, lo]  colour-scale limits
        (see above).
    ax : array of Axes or None  (created if None).
    figsize : tuple or None.
    output_path : str or None  save figure if given.
    cmap : str  colormap (default 'magma').
    transition_info : TransitionInfo or None  labels the figure
        suptitle with the transition name.
    """
    img = results.get( 'image', None );
    if img is None:
        # look in the last cycle
        res_list = results.get( 'results', [ ] );
        if res_list:
            img = res_list[ -1 ].get( 'image', None );
    if img is None or 'cube' not in img:
        print( 'plot_channel_maps: no image cube in results' );
        return None, None;

    cube  = asarray( img[ 'cube' ], dtype = float64 );  # (n_pix,nch)
    i2d   = asarray( img[ 'i2d' ], dtype = int32 );
    nch   = int( img.get( 'n_chan', cube.shape[ 1 ] ) );

    # Rebuild the 2-D spatial grid from the flat pixel list.
    nx = int( i2d[ :, 0 ].max( ) ) + 1 if i2d.size else 1;
    ny = int( i2d[ :, 1 ].max( ) ) + 1 if i2d.size else 1;
    img2d = zeros( ( nx, ny, nch ) );
    for p in range( i2d.shape[ 0 ] ):
        img2d[ i2d[ p, 0 ], i2d[ p, 1 ], : ] = cube[ p, : ];

    # Velocity axis (cell-edges convention: v_k = v_min + k*dv)
    vcfg = img.get( 'v_chan', None );
    if isinstance( vcfg, ( tuple, list ) ) and len( vcfg ) == 2:
        v_lo, v_hi = float( vcfg[ 0 ] ), float( vcfg[ 1 ] );
    else:
        v_lo, v_hi = -1.0, 1.0;
    dv = ( v_hi - v_lo ) / max( nch - 1, 1 );
    v_axis = v_lo + arange( nch ) * dv;
    v_kms  = v_axis * 1e-5;

    # Channel selection
    if channels is None:
        if n_channels is None:
            n_channels = n_cols;
        n_channels = min( n_channels, nch );
        spectrum = img2d.sum( axis = ( 0, 1 ) );
        peak = int( spectrum.argmax( ) );
        half = n_channels // 2;
        lo = max( 0, peak - half );
        hi = min( nch, lo + n_channels );
        lo = max( 0, hi - n_channels );   # shift up if clipped
        channels = list( range( lo, hi ) );
    channels = [ int( c ) for c in channels ];
    n_pan = len( channels );
    if n_pan == 0:
        return None, None;

    # Shared colour limits across all selected channels.
    stacked = img2d[ :, :, channels ];
    pos = stacked[ ( stacked > 0 ) & isfinite( stacked ) ];
    if pos.size == 0:
        print( 'plot_channel_maps: no positive finite values in cube' );
        return None, None;
    norm = _resolve_log_norm( dyn_range, pos );
    if norm is None:
        print( 'plot_channel_maps: no positive finite values in cube' );
        return None, None;

    # Layout
    ncols = min( n_pan, n_cols );
    nrows = ( n_pan + ncols - 1 ) // ncols;
    if ax is None:
        fig, axes = plt.subplots( nrows, ncols, \
                                  figsize = figsize or \
                                  ( 3.2 * ncols, 3.0 * nrows ), \
                                  squeeze = False );
    else:
        axes = atleast_2d( ax );
        fig = axes[ 0, 0 ].figure;

    # Spatial extent from mesh (AU)
    mesh = results.get( 'mesh', { } );
    xmin = mesh.get( 'x_min', [ 0, 0, 0 ] );
    xmax = mesh.get( 'x_max', [ 1, 1, 1 ] );
    ext  = ( xmin[ 0 ], xmax[ 0 ], xmin[ 1 ], xmax[ 1 ] );

    dv_kms = dv * 1e-5;
    for i, c in enumerate( channels ):
        row, col = divmod( i, ncols );
        ax_i = axes[ row, col ];
        data = img2d[ :, :, c ].T;   # (ny, nx) for imshow
        im = ax_i.imshow( data, origin = 'lower', aspect = 'equal',
                          extent = ext, cmap = cmap, norm = norm,
                          interpolation = 'bilinear' );
        ax_i.set_title( r'$v = %.2f$ km/s' % v_kms[ c ],
                        fontsize = 9 );
        ax_i.set_xlabel( 'x [AU]', fontsize = 8 );
        if col == 0:
            ax_i.set_ylabel( 'y [AU]', fontsize = 8 );
        ax_i.tick_params( labelsize = 7 );
        if i == 0:
            ax_i.text( 0.02, 0.02,
                       r'$\Delta v = %.3f$ km/s' % dv_kms,
                       transform = ax_i.transAxes, va = 'bottom',
                       fontsize = 7, color = 'w' );

    # Hide unused panels
    for i in range( n_pan, nrows * ncols ):
        row, col = divmod( i, ncols );
        axes[ row, col ].set_visible( False );

    # Dedicated colourbar axis beside the last used panel, so it
    # never invades the panel grid.
    last_row, last_col = divmod( n_pan - 1, ncols );
    divider = make_axes_locatable( axes[ last_row, last_col ] );
    cax = divider.append_axes( 'right', size = '4%', pad = 0.08 );
    fig.colorbar( im, cax = cax, label = 'intensity [CGS]',
                  extend = 'min' );

    if transition_info is not None:
        fig.suptitle( transition_info.transition_name, y = 0.995,
                      fontsize = 11 );

    fig.tight_layout( );
    if output_path:
        fig.savefig( output_path, dpi = 150, bbox_inches = 'tight' );
    return fig, axes;
#
